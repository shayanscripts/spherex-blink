"""Exploratory shape matching against observed NASA IRTF SpeX standards."""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from pathlib import Path
import warnings

import httpx
import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.time import Time
from astropy.io.fits.verify import VerifyWarning

LIBRARY = 'https://irsa.ipac.caltech.edu/data/IRTF_Extra/SpectralLibrary/speclib.html'
BASE = LIBRARY.rsplit('/', 1)[0] + '/spectra/spectrallibrary/'
TEMPLATES = (
    ('G-type star', 'HD 76151 · G2 V', 'G2V_HD76151.fits', 'https://doi.org/10.1088/0067-0049/185/2/289'),
    ('M-type star', 'Gl 406 · M6 V', 'M6V_Gl406.fits', 'https://doi.org/10.1088/0067-0049/185/2/289'),
    ('L-type ultracool dwarf', '2MASS J15074769−1627386 · L5', 'L5_2MASSJ1507-1627.fits', 'https://doi.org/10.1086/428040'),
)


@lru_cache(maxsize=12)
def reference(cache: Path, filename: str):
    path = cache / filename
    payload = path.read_bytes() if path.is_file() else None
    if payload is None:
        with httpx.stream('GET', BASE + filename, timeout=8) as response:
            response.raise_for_status()
            buffer = bytearray()
            for chunk in response.iter_bytes():
                buffer.extend(chunk)
                if len(buffer) > 2_000_000:
                    raise ValueError('Unexpected reference file size.')
            payload = bytes(buffer)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', VerifyWarning)
        with fits.open(BytesIO(payload)) as hdus:
            header = hdus[0].header
            if header.get('XUNITS') != 'um' or header.get('YUNITS') != 'Wm-2um-1':
                raise ValueError('Unexpected reference flux or wavelength unit.')
            wave, flux = np.asarray(hdus[0].data[:2], dtype=float)
    if not np.isfinite(wave).all() or not (np.diff(wave) > 0).all():
        raise ValueError('Invalid reference wavelength axis.')
    flux = (flux * u.W/u.m**2/u.um).to_value(u.mJy, equivalencies=u.spectral_density(wave*u.um))
    if not path.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    return wave, flux


def band_average(ref, center, width):
    wave, flux = ref
    lo, hi = center-width/2, center+width/2
    if lo < wave[0] or hi > wave[-1]:
        return np.nan
    start, end = np.searchsorted(wave, [lo, hi])
    window = slice(max(0, start-1), min(len(wave), end+1))
    x, y = wave[window], flux[window]
    # Preserve gaps in the published measurements, including telluric gaps.
    if x.size < 2 or not np.isfinite(y).all() or np.max(np.diff(x)) > width/4:
        return np.nan
    grid = np.r_[lo, wave[start:end], hi]
    return np.trapezoid(np.interp(grid, x, y)/grid**2, grid) / (1/lo-1/hi)


def classify(samples, moving, cache: Path):
    result = dict(status='insufficient', reason='', matches=[], points=0, span_um=None,
                  library_url=LIBRARY)
    if moving:
        result['reason'] = 'This spectrum follows an unverified motion path. The stellar library cannot identify a moving object.'
        return result
    usable = [s for s in samples if s['reduced_chi2'] <= 4]
    # A template describes a stable shape. Choose one short observing window,
    # without using the measured flux to choose its wavelength coverage.
    if len(usable) < 5:
        result['reason'] = (
            f'{len(usable)} of {len(samples)} measurements passed the point-source fit check. '
            'Matching needs at least five distinct bands. Blends or a changing background can make the local fit unreliable.'
            if samples else 'No usable FITS measurements are available for matching.'
        )
        return result
    dates = Time([s['timestamp'] for s in usable]).jd
    waves = np.array([s['wavelength_um'] for s in usable])
    widths = np.array([s['bandwidth_um'] for s in usable])
    # Avoid downloading templates for a single narrow-band dataset.
    if np.ptp(waves) < .4:
        result['reason'] = 'The observed wavelength span is below 0.4 µm. Add observations in other bands.'
        return result
    try:
        refs = [reference(cache, item[2]) for item in TEMPLATES]
    except (httpx.HTTPError, ValueError, OSError, TypeError, IndexError):
        result.update(status='unavailable', reason='The published IRTF templates could not be loaded. The SPHEREx measurements are still available.')
        return result
    predicted = np.array([[band_average(ref, w, b) for w, b in zip(waves, widths)] for ref in refs])
    covered = np.isfinite(predicted).all(axis=0)
    covered &= (predicted > 0).all(axis=0)

    best = []
    best_key = (0, 0.)
    for start in sorted(set(dates[covered])):
        indices = np.flatnonzero(covered & (dates >= start) & (dates <= start+1))
        # Keep one representative from each non-overlapping band; correlated
        # repeat exposures or different instrument passbands are not averaged.
        ordered = sorted(indices, key=lambda i: (waves[i]+widths[i]/2, usable[i]['uncertainty_mjy']))
        chosen, edge = [], -np.inf
        for i in ordered:
            if waves[i]-widths[i]/2 >= edge:
                chosen.append(i)
                edge = waves[i]+widths[i]/2
        key = (len(chosen), float(np.ptp(waves[chosen])) if chosen else 0.)
        if key > best_key:
            best, best_key = chosen, key
    n, span = best_key
    result.update(points=n, span_um=span if n else None)
    if n < 5 or span < .4:
        result['reason'] = 'Matching needs five non-overlapping bands spanning at least 0.4 µm within 24 hours, covered by all references.'
        return result
    flux = np.array([usable[i]['flux_mjy'] for i in best])
    error = np.array([usable[i]['uncertainty_mjy'] for i in best])
    if np.count_nonzero(flux/error >= 3) < 3:
        result['reason'] = 'Fewer than three of the comparable bands have a signal at least 3× the measured uncertainty.'
        return result
    for item, model in zip(TEMPLATES, predicted[:, best]):
        weighted = model/error
        scale = max(0., float(np.dot(weighted, flux/error)/np.dot(weighted, weighted)))
        curve = model*scale
        score = float(np.sum(((flux-curve)/error)**2)/(n-1))
        result['matches'].append(dict(kind=item[0], object=item[1], data_url=BASE+item[2],
                                      citation=item[3], reduced_chi2=score, wavelength_um=waves[best].tolist(),
                                      flux_mjy=curve.tolist()))
    result['matches'].sort(key=lambda m: m['reduced_chi2'])
    result['used_ids'] = [usable[i]['id'] for i in best]
    first, second = result['matches'][:2]
    if first['reduced_chi2'] > 4:
        result['reason'] = 'None of the library shapes fits the measured fluxes well. Variability, crowding or a missing object type could explain the mismatch.'
    elif (second['reduced_chi2']-first['reduced_chi2'])*(n-1) < 6:
        result['reason'] = 'Several templates fit about equally well, so the data do not distinguish their types.'
    else:
        result['status'] = 'resemblance'
        ratio = first['flux_mjy'][-1] / first['flux_mjy'][0]
        shape = 'rises' if ratio > 1.15 else 'falls' if ratio < .85 else 'stays fairly level'
        result['reason'] = (f"The {first['kind']} reference follows the measured relative brightness best. "
                            f"Its fitted flux {shape} from {waves[best[0]]:.2f} to {waves[best[-1]]:.2f} µm, "
                            'and it has the smallest uncertainty-weighted mismatch across the shared bands.')
    return result
