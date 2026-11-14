"""Explicitly synthetic fixtures for validation only; never offered by the explorer."""
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS


@pytest.fixture
def fixture_fits(tmp_path: Path) -> Path:
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [3, 3]
    wcs.wcs.crval = [180, 45]
    wcs.wcs.cdelt = [-.001, .001]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    header = wcs.to_header()
    header["BUNIT"] = "MJy/sr"
    header["DATE-OBS"] = "2025-04-28T16:16:34.491"
    header["DATE"] = "2026-01-01T00:00:00"
    header["TIMESYS"] = "UTC"
    header["INSTRUME"] = "SYNTHETIC TEST FIXTURE"
    # Real FITS -TAB structure, with an analytically known linear mapping.
    for key, value in {
        "WCSAXESW": 2, "WCSNAMEW": "Synthetic wavelength test", "CTYPE1W": "WAVE-TAB", "CTYPE2W": "WAVE-TAB",
        "CUNIT1W": "um", "CUNIT2W": "um", "CRPIX1W": 1., "CRPIX2W": 1., "CRVAL1W": 0., "CRVAL2W": 0.,
        "CDELT1W": 1., "CDELT2W": 1., "PS1_0W": "WCS-WAVE", "PS2_0W": "WCS-WAVE", "PS1_1W": "VALUES", "PS2_1W": "VALUES",
        "PS1_2W": "X", "PS2_2W": "Y", "PV1_1W": 1, "PV2_1W": 1, "PV1_3W": 1, "PV2_3W": 2,
    }.items(): header[key] = value
    values = np.array([[[2., .1], [2.5, .1]], [[3., .2], [3.5, .2]]])
    table = fits.BinTableHDU.from_columns([
        fits.Column(name="X", format="2D", array=[[0., 5.]]),
        fits.Column(name="Y", format="2D", array=[[0., 5.]]),
        fits.Column(name="VALUES", format="8D", dim="(2,2,2)", array=[values]),
    ], name="WCS-WAVE")
    data = np.arange(36, dtype=np.float32).reshape(6, 6)
    variance = np.full((6, 6), 4., dtype=np.float32)
    variance[0, 0] = -1
    variance[0, 1] = np.nan
    flags = np.zeros((6, 6), dtype=np.int32)
    flags[2, 2] = 5
    flag_hdu = fits.ImageHDU(flags, name="FLAGS")
    flag_hdu.header["MP_TEST"] = (0, "Synthetic fixture flag definition")
    hdus = [fits.PrimaryHDU(), fits.ImageHDU(data, header=header, name="IMAGE"), flag_hdu,
            fits.ImageHDU(variance, name="VARIANCE"), fits.ImageHDU(np.ones((6, 6)), name="ZODI"),
            fits.ImageHDU(np.zeros((3, 5, 5)), name="PSF"), table]
    path = tmp_path / "synthetic_validation_only.fits"
    fits.HDUList(hdus).writeto(path)
    return path
