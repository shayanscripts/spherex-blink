"""Read-only single-observation science. No generated measurements or foreground subtraction."""
from __future__ import annotations

import io
import re
import warnings
from threading import RLock
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image

LAYERS = ("IMAGE", "VARIANCE", "FLAGS", "ZODI")
DOCS = "https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/"
# WCSLIB -TAB transforms in Astropy 8.0.2 can segfault on a shared WCS
# when FastAPI worker threads call them concurrently (confirmed by stress test).
WCS_LOCK = RLock()


def scalar(value: Any) -> Any:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (bool, str)) or value is None:
        return value
    return str(value)


def summary(data: np.ndarray, name: str) -> dict:
    valid = np.isfinite(data)
    if name == "VARIANCE":
        valid &= data >= 0
    values = data[valid]
    if not values.size:
        return dict(min=None, max=None, low=None, high=None, valid_pixels=0, total_pixels=data.size)
    low, high = np.percentile(values, [1, 99])
    return dict(min=scalar(values.min()), max=scalar(values.max()), low=float(low), high=float(high),
                valid_pixels=int(values.size), total_pixels=int(data.size))


@dataclass
class Observation:
    path: Path
    arrays: dict
    headers: dict
    extensions: list
    spatial: WCS | None
    spectral: WCS | None
    spectral_error: str | None
    stats: dict

    @classmethod
    def read(cls, path: Path) -> "Observation":
        arrays, headers, extensions = {}, {}, []
        spatial = spectral = None
        spectral_error = None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with fits.open(path, memmap=False, lazy_load_hdus=False) as hdus:
                hdus.verify("exception")
                for index, hdu in enumerate(hdus):
                    name = "PRIMARY" if index == 0 else hdu.name.upper()
                    if name in headers:
                        raise ValueError(f"Duplicate extension {name}; select an unambiguous single observation.")
                    headers[name] = hdu.header.copy()
                    shape = list(getattr(hdu, "shape", ()) or ())
                    if np.prod(shape, dtype=np.float64) > 32_000_000:
                        raise ValueError(f"{name} exceeds the 32 million element safety limit.")
                    extensions.append(dict(index=index, name=name, kind=type(hdu).__name__,
                                           shape=shape, unit=hdu.header.get("BUNIT"),
                                           columns=[dict(name=c.name, format=c.format, unit=c.unit, dim=c.dim)
                                                    for c in hdu.columns] if isinstance(hdu, fits.BinTableHDU) else []))
                    if name in LAYERS and hdu.data is not None:
                        if hdu.data.ndim != 2 or hdu.data.dtype.kind not in "iuf":
                            raise ValueError(f"{name} must be a numeric 2D image, got {hdu.data.shape}.")
                        if name == "FLAGS" and hdu.data.dtype.kind not in "iu":
                            raise ValueError("FLAGS must contain integer bit fields.")
                        arrays[name] = np.array(hdu.data, copy=True)
                if "IMAGE" not in arrays or not arrays["IMAGE"].size:
                    raise ValueError("This file has no nonempty 2D IMAGE extension.")
                try:
                    candidate = WCS(headers["IMAGE"], fobj=hdus).celestial
                    if candidate.has_celestial:
                        spatial = candidate
                except Exception:
                    pass
                try:
                    if "WCS-WAVE" not in headers:
                        raise ValueError("No WCS-WAVE extension is present.")
                    # Official IRSA recipe: alternate WCS W, with SIP explicitly disabled.
                    spectral = WCS(headers["IMAGE"], fobj=hdus, key="W")
                    spectral.sip = None
                    if spectral.pixel_n_dim != 2 or spectral.world_n_dim != 2:
                        raise ValueError("Spectral WCS must map two pixel axes to wavelength and bandwidth.")
                    if not all("TAB" in c for c in spectral.wcs.ctype):
                        raise ValueError("Spectral WCS W does not reference a TAB calibration.")
                    for unit in spectral.world_axis_units:
                        u.Unit(unit).to(u.um)
                except Exception as exc:
                    spectral = None
                    spectral_error = str(exc)
        return cls(path, arrays, headers, extensions, spatial, spectral, spectral_error,
                   {name: summary(data, name) for name, data in arrays.items()})

    def metadata(self, file_id: str, filename: str) -> dict:
        def first(*keys):
            for key in keys:
                for name in ("IMAGE", "PRIMARY"):
                    if key in self.headers[name]:
                        return dict(key=key, value=scalar(self.headers[name][key]), extension=name)
            return None

        shape = self.arrays["IMAGE"].shape
        notices = []
        for name in LAYERS[1:]:
            if name not in self.arrays:
                notices.append(f"{name} is unavailable in this file.")
            elif self.arrays[name].shape != shape:
                notices.append(f"{name} has its own {self.arrays[name].shape} shape; no IMAGE-pixel correspondence is assumed.")
        if not self.spatial:
            notices.append("Celestial WCS is unavailable; only detector coordinates can be inspected.")
        if not self.spectral:
            notices.append(f"Wavelength calibration unavailable: {self.spectral_error}")
        if min(shape) <= 6:
            notices.append("This is a very small cutout. Enlarged pixels do not add spatial resolution.")
        instrument = first("INSTRUME", "TELESCOP")
        if not instrument or "SPHEREX" not in str(instrument["value"]).upper():
            notices.append("SPHEREx provenance is not established by the instrument header. Verify the file's archive origin.")
        spectral_summary = None
        if self.spectral:
            # Full detector coverage, evaluated in bounded strips; never a fabricated range.
            extrema = [np.inf, -np.inf, np.inf, -np.inf]
            for start in range(0, shape[0], 64):
                yy, xx = np.mgrid[start:min(start + 64, shape[0]), :shape[1]]
                wave, band = self.spectral_values(xx, yy)
                for offset, values in ((0, wave), (2, band)):
                    finite = values[np.isfinite(values) & (values > 0)]
                    if finite.size:
                        extrema[offset] = min(extrema[offset], float(finite.min()))
                        extrema[offset + 1] = max(extrema[offset + 1], float(finite.max()))
            spectral_summary = dict(min_um=scalar(extrema[0]), max_um=scalar(extrema[1]),
                                    bandwidth_min_um=scalar(extrema[2]), bandwidth_max_um=scalar(extrema[3]),
                                    method="WCS W / WCS-WAVE; SIP disabled", purpose="Visualization calibration, not precision photometry")
        # Expose header flag definitions verbatim; never guess version-specific bit meanings.
        flag_definitions = [dict(key=c.keyword, value=scalar(c.value), comment=c.comment)
                            for c in self.headers.get("FLAGS", fits.Header()).cards if c.keyword.startswith("MP")]
        return dict(id=file_id, filename=filename, bytes=self.path.stat().st_size,
                    shape=list(shape), extensions=self.extensions, stats=self.stats,
                    observation=first("OBSID", "OBS_ID"), instrument=instrument,
                    timestamp=first("DATE-OBS", "DATE-BEG", "MJD-OBS", "MJD-BEG", "MJDSTART"),
                    time_system=first("TIMESYS"), detector=first("DETECTOR", "DET_ID"),
                    release=first("DATA_REL", "DATAREL", "RELEASE", "DR"),
                    processing_version=first("VERSION", "PROCVER", "PIPEVER"),
                    spatial_wcs=bool(self.spatial), spectral=spectral_summary,
                    flag_definitions=flag_definitions, notices=notices,
                    source_url="https://irsa.ipac.caltech.edu/Missions/spherex.html",
                    provenance="User-supplied FITS; archive origin is not independently verified.")

    def spectral_values(self, x, y):
        with WCS_LOCK:
            values = self.spectral.pixel_to_world_values(x, y)
            return tuple(np.asarray(v) * u.Unit(unit).to(u.um)
                         for v, unit in zip(values, self.spectral.world_axis_units))

    def pixel(self, layer: str, x: int, y: int) -> dict:
        data = self.arrays[layer]
        if not (0 <= x < data.shape[1] and 0 <= y < data.shape[0]):
            raise ValueError("Pixel is outside this extension's dimensions.")
        same_shape = data.shape == self.arrays["IMAGE"].shape
        result = dict(x=x, y=y, fits_x=x+1, fits_y=y+1, layer=layer,
                      value=scalar(data[y, x]), unit=self.headers[layer].get("BUNIT"),
                      ra_deg=None, dec_deg=None, wavelength_um=None, bandwidth_um=None,
                      brightness=None, variance=None, uncertainty=None, flags=None, flag_bits=[], zodi=None,
                      measurement_note="No source SNR is inferred from raw pixel brightness.")
        if same_shape:
            for name, key in (("IMAGE", "brightness"), ("VARIANCE", "variance"), ("FLAGS", "flags"), ("ZODI", "zodi")):
                array = self.arrays.get(name)
                if array is not None and array.shape == data.shape:
                    result[key] = scalar(array[y, x])
            variance = result["variance"]
            if variance is not None and variance >= 0:
                result["uncertainty"] = float(np.sqrt(variance))
            if result["flags"] is not None:
                bits = int(result["flags"])
                # Preserve unsigned bit pattern for signed FITS integer storage.
                if bits < 0:
                    bits &= (1 << (self.arrays["FLAGS"].dtype.itemsize * 8)) - 1
                result["flag_bits"] = [i for i in range(bits.bit_length()) if bits & (1 << i)]
            if self.spatial:
                with WCS_LOCK:
                    sky = self.spatial.pixel_to_world(x, y).icrs
                result.update(ra_deg=scalar(sky.ra.deg), dec_deg=scalar(sky.dec.deg))
            if self.spectral:
                wave, band = self.spectral_values(x, y)
                result.update(wavelength_um=scalar(wave.item()), bandwidth_um=scalar(band.item()))
        else:
            result["measurement_note"] = "This extension has different dimensions; IMAGE coordinates and related measurements are unavailable."
        return result

    def locate(self, ra: float, dec: float) -> dict:
        if not self.spatial:
            raise ValueError("This observation has no valid celestial WCS.")
        from astropy.coordinates import SkyCoord
        with WCS_LOCK:
            x, y = self.spatial.world_to_pixel(SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame="icrs"))
        if not np.isfinite([x, y]).all():
            raise ValueError("This sky position cannot be mapped to the observation.")
        h, w = self.arrays["IMAGE"].shape
        if not (-0.5 <= x < w-0.5 and -0.5 <= y < h-0.5):
            raise ValueError("No coverage: that sky position is outside this observation.")
        return dict(x=int(np.floor(x + 0.5)), y=int(np.floor(y + 0.5)))

    def render(self, layer: str, stretch: str, palette: str, mask: bool, low: float | None, high: float | None) -> bytes:
        data = self.arrays[layer]
        valid = np.isfinite(data)
        if layer == "VARIANCE":
            valid &= data >= 0
        flags = self.arrays.get("FLAGS")
        if mask and flags is not None and flags.shape == data.shape:
            valid &= flags == 0
        stats = self.stats[layer]
        lo = low if low is not None else stats["low"]
        hi = high if high is not None else stats["high"]
        if lo is None or hi is None:
            lo, hi = 0.0, 1.0
        if hi < lo:
            raise ValueError("Upper display limit must exceed the lower limit.")
        safe = np.where(valid, data, lo).astype(np.float64)
        scaled = np.clip((safe - lo) / (hi - lo if hi > lo else 1), 0, 1)
        if stretch == "asinh":
            scaled = np.arcsinh(10 * scaled) / np.arcsinh(10)
        elif stretch == "log":
            scaled = np.log1p(1000 * scaled) / np.log1p(1000)
        if palette == "amber":
            stops = np.array([[9, 12, 16], [83, 37, 19], [197, 103, 42], [246, 199, 111], [255, 249, 229]])
        elif palette == "ice":
            stops = np.array([[7, 12, 20], [22, 61, 91], [37, 131, 159], [139, 210, 209], [242, 250, 245]])
        else:
            stops = np.array([[0, 0, 0], [255, 255, 255]])
        rgb = np.stack([np.interp(scaled, np.linspace(0, 1, len(stops)), stops[:, i]) for i in range(3)], axis=-1)
        rgba = np.concatenate((rgb.astype(np.uint8), (valid * 255).astype(np.uint8)[..., None]), axis=-1)
        # FITS y increases upwards. PNG starts at top; inspection reverses this once.
        image = Image.fromarray(np.flipud(rgba))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


def header_cards(observation: Observation, name: str) -> list:
    if name not in observation.headers:
        raise ValueError("Unknown FITS extension.")
    return [dict(key=card.keyword, value=scalar(card.value), comment=card.comment)
            for card in observation.headers[name].cards]
