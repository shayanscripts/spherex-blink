"""Native-pixel forced photometry from SPHEREx DR1 / QR3 ePSFs."""
from __future__ import annotations

import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.wcs import NoConvergence
from astropy.wcs.utils import proj_plane_pixel_area
from scipy.ndimage import map_coordinates

from backend.processing import INFORMATIONAL_FLAGS
from backend.science import Observation, WCS_LOCK

BRIGHTNESS = u.MJy / u.sr


def forced_photometry(obs: Observation, sky, subtract_zodi: bool) -> dict:
    """Fit source flux and a local constant background at a fixed ICRS position."""
    if obs.spatial is None or obs.spectral is None:
        raise ValueError('Celestial and spectral FITS WCS are required.')
    try:
        with WCS_LOCK:
            x, y = map(float, obs.spatial.world_to_pixel(sky))
            area = float(proj_plane_pixel_area(obs.spatial)) * (np.pi / 180)**2
    except NoConvergence as exc:
        raise ValueError('Celestial WCS could not map this position onto the detector.') from exc
    image = obs.arrays['IMAGE']
    height, width = image.shape
    if not (-.5 <= x < width-.5 and -.5 <= y < height-.5):
        raise ValueError('Position lies outside FITS coverage.')
    if 'EPSF' not in obs.headers:
        raise ValueError('No calibrated ePSF in this FITS file. Use DR1 or QR3.')
    hdr = obs.headers['IMAGE']
    epsf_hdr = obs.headers['EPSF']
    if any(k not in hdr for k in ('CRPIX1A', 'CRPIX2A')) or any(k not in epsf_hdr for k in ('OVSMPX', 'OVSMPY')):
        raise ValueError('Missing detector coordinates or ePSF oversampling metadata.')
    # IRSA cutouts shift alternate WCS A; the ePSF table retains parent-image coordinates.
    xp, yp = x + 1 - hdr['CRPIX1A'], y + 1 - hdr['CRPIX2A']
    ox, oy = int(epsf_hdr['OVSMPX']), int(epsf_hdr['OVSMPY'])
    if min(ox, oy) < 1:
        raise ValueError('Invalid ePSF oversampling.')
    with fits.open(obs.path, memmap=True) as hdus:
        zones = hdus['EPSF'].data
        if not {'XCENTER', 'YCENTER', 'EPSF'}.issubset(zones.names):
            raise ValueError('Unrecognized ePSF calibration table.')
        distances = (zones['XCENTER']-xp)**2 + (zones['YCENTER']-yp)**2
        if not np.isfinite(distances).any():
            raise ValueError('ePSF detector zones are unavailable.')
        model = np.array(zones['EPSF'][np.nanargmin(distances)], dtype=float)
    if model.ndim != 2 or not np.isfinite(model).all():
        raise ValueError('No finite ePSF model at the detector position.')

    # An ePSF already includes the pixel response. Sample at native centers,
    # as in IRSA's ImagePSF example, and normalize before excluding bad pixels.
    radius = max(5, int(np.ceil(max((model.shape[1]-1)/(2*ox), (model.shape[0]-1)/(2*oy))))+1)
    cx, cy = min(width-1, int(round(x))), min(height-1, int(round(y)))
    yy, xx = np.mgrid[cy-radius:cy+radius+1, cx-radius:cx+radius+1]
    psf = map_coordinates(model, [(model.shape[0]-1)/2+(yy-y)*oy,
                                  (model.shape[1]-1)/2+(xx-x)*ox],
                          order=3, mode='constant', cval=0)
    total = psf.sum()
    if not np.isfinite(total) or total <= 0:
        raise ValueError('Invalid ePSF normalization.')
    psf /= total
    power = np.sum(psf**2)
    inside = (xx >= 0) & (xx < width) & (yy >= 0) & (yy < height)
    xx, yy, psf = xx[inside], yy[inside], psf[inside]

    def plane(name, unit=None):
        arr = obs.arrays.get(name)
        if arr is None or arr.shape != image.shape:
            raise ValueError(f'Co-shaped {name} pixels are required.')
        values = arr[yy, xx]
        if unit is not None:
            declared = obs.headers[name].get('BUNIT')
            if not declared:
                raise ValueError(f'{name} is missing its FITS unit.')
            return values.astype(float) * u.Unit(declared).to(unit)
        return values

    values = plane('IMAGE', BRIGHTNESS)
    if subtract_zodi:
        values -= plane('ZODI', BRIGHTNESS)
    var = plane('VARIANCE', BRIGHTNESS**2)
    flags = plane('FLAGS')
    good = (flags.astype(np.int64) & ~INFORMATIONAL_FLAGS) == 0
    good &= np.isfinite(values) & np.isfinite(var) & (var > 0)
    wave, band = map(float, obs.spectral_values(x, y))
    if not (np.isfinite(wave) and np.isfinite(band) and wave > band/2 > 0):
        raise ValueError('No calibrated wavelength and bandwidth at this position.')
    core = np.abs(psf) >= .03 * np.max(np.abs(psf))
    waves, bands = obs.spectral_values(xx[core], yy[core])
    compatible = np.isfinite(waves) & np.isfinite(bands) & (bands > 0)
    compatible &= (np.abs(waves-wave) <= .25*band) & (np.abs(bands-band) <= .25*band)
    good[core] &= compatible
    if good.sum() < 15 or np.sum(psf[good]**2) < .75 * power:
        raise ValueError('Image edges, FLAGS, variance or wavelength calibration exclude too much of the ePSF.')
    p, v, sigma = psf[good], values[good], np.sqrt(var[good])
    design = np.column_stack((p, np.ones(len(p)))) / sigma[:, None]
    fit, _, rank, _ = np.linalg.lstsq(design, v/sigma, rcond=None)
    if rank != 2 or not np.isfinite(area) or area <= 0:
        raise ValueError('The source and background cannot be fitted independently.')
    chi2 = float(np.sum(((v - fit[0]*p - fit[1])/sigma)**2)/(len(p)-2))
    error = float(np.sqrt(np.linalg.inv(design.T @ design)[0, 0] * max(1., chi2)))
    if not np.isfinite([fit[0], error, chi2]).all() or error <= 0:
        raise ValueError('The fit did not produce a finite flux and uncertainty.')
    conversion = area * 1e9
    return dict(wavelength_um=wave, bandwidth_um=band, flux_mjy=float(fit[0])*conversion,
                uncertainty_mjy=error*conversion, snr=float(fit[0])/error,
                reduced_chi2=chi2, fit_pixels=int(good.sum()), center_flags=int(obs.arrays['FLAGS'][cy,cx]),
                ra_deg=float(sky.icrs.ra.deg), dec_deg=float(sky.icrs.dec.deg))
