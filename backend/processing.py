"""WCS-registered measurements, variance propagation, differences and candidate evidence."""
from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

import numpy as np
from astropy import units as u
from astropy.time import Time
from astropy.wcs import WCS
from astropy.wcs.utils import pixel_to_pixel, proj_plane_pixel_scales
from PIL import Image
from reproject import reproject_interp
from scipy import ndimage

from backend.science import Observation, scalar, WCS_LOCK

# Informational bits FULLSAMPLE and SOURCE are not defects. Unknown bits are rejected.
INFORMATIONAL_FLAGS = (1 << 12) | (1 << 21)


def valid_pixels(obs: Observation) -> np.ndarray:
    image = obs.arrays['IMAGE']
    valid = np.isfinite(image)
    flags = obs.arrays.get('FLAGS')
    if flags is None or flags.shape != image.shape:
        raise ValueError('A co-shaped FLAGS plane is required for registered scientific processing.')
    valid &= (flags.astype(np.int64) & ~INFORMATIONAL_FLAGS) == 0
    return valid


def sky_grid(ra: float, dec: float, size: int, scale: float) -> WCS:
    w = WCS(naxis=2)
    w.wcs.ctype = ['RA---TAN','DEC--TAN']
    w.wcs.crval = [ra,dec]
    w.wcs.crpix = [(size+1)/2, (size+1)/2]
    w.wcs.cdelt = [-scale/3600,scale/3600]
    return w


def png(data: np.ndarray, valid: np.ndarray | None = None, signed: bool = False, limits=None) -> bytes:
    valid = np.isfinite(data) if valid is None else valid & np.isfinite(data)
    vals = data[valid]
    lo, hi = limits if limits else (np.percentile(vals,[1,99]) if vals.size else (0,1))
    clean = np.where(valid, data, 0)
    if signed:
        bound = max(abs(lo),abs(hi), 1e-12)
        t = np.clip(clean / bound,-1,1)
        white = np.array([238,237,224]); blue=np.array([54,126,193]);red=np.array([223,91,69])
        rgb = np.where((t>=0)[...,None],white+(red-white)*t[...,None],white+(white-blue)*t[...,None])
    else:
        t = np.clip((clean-lo)/max(hi-lo,1e-12),0,1)
        t = np.arcsinh(10*t)/np.arcsinh(10)
        rgb = np.repeat((t*255)[...,None],3,axis=-1)
    rgba = np.concatenate([rgb.astype(np.uint8),(valid*255).astype(np.uint8)[...,None]],axis=-1)
    out = io.BytesIO(); Image.fromarray(np.flipud(rgba)).save(out,format='PNG');return out.getvalue()


def detector_band(obs: Observation, wavelength: float, width: float) -> tuple[np.ndarray,np.ndarray]:
    if obs.spectral is None: raise ValueError('No usable spectral calibration in this observation.')
    h,w = obs.arrays['IMAGE'].shape
    result = np.zeros((h,w),dtype=bool)
    waves = np.full((h,w),np.nan,dtype=np.float32)
    for start in range(0,h,128):
        yy,xx = np.mgrid[start:min(h,start+128),:w]
        wave,band=obs.spectral_values(xx,yy)
        # Selection means measured central wavelengths inside the requested interval.
        result[start:start+128] = np.isfinite(wave)&(np.abs(wave-wavelength)<=width/2)
        waves[start:start+128]=wave
    return result,waves


@dataclass
class Frame:
    image: np.ndarray
    variance: np.ndarray
    wave: np.ndarray
    band: np.ndarray
    valid: np.ndarray
    wcs: WCS
    psf_fwhm: float | None
    unit: str
    timestamp: str | None
    zodi_subtracted: bool = False
    exclusion: np.ndarray | None = None


def timestamp(obs):
    h=obs.headers['IMAGE'];p=obs.headers['PRIMARY']
    for key in ['DATE-OBS','DATE-BEG']:
        if key in h or key in p: return str(h.get(key,p.get(key)))
    for key in ['MJD-OBS','MJD-BEG']:
        if key in h or key in p: return Time(h.get(key,p.get(key)),format='mjd',scale=str(h.get('TIMESYS','UTC')).lower()).utc.isot
    return None


def calibrated_brightness(obs: Observation, subtract_zodi: bool = False) -> np.ndarray:
    """Return native-pixel MJy/sr measurements without altering the FITS arrays."""
    unit=obs.headers['IMAGE'].get('BUNIT')
    if not unit or not u.Unit(unit).is_equivalent(u.MJy/u.sr): raise ValueError('IMAGE units must be convertible to MJy/sr.')
    image=obs.arrays['IMAGE']*u.Unit(unit).to(u.MJy/u.sr)
    if subtract_zodi:
        zodi=obs.arrays.get('ZODI')
        if zodi is None or zodi.shape!=image.shape:
            raise ValueError('ZODI subtraction requires a co-shaped ZODI plane. Supply one or disable ZODI subtraction.')
        zodi_unit=obs.headers['ZODI'].get('BUNIT')
        if not zodi_unit or not u.Unit(zodi_unit).is_equivalent(u.MJy/u.sr):
            raise ValueError('ZODI must declare brightness units convertible to MJy/sr.')
        image=image-zodi*u.Unit(zodi_unit).to(u.MJy/u.sr)
    return image


def project(obs: Observation, grid: WCS, size: int, subtract_zodi: bool = False) -> Frame:
    if not obs.spatial or not obs.spectral: raise ValueError('Both celestial and spectral WCS are required.')
    brightness=calibrated_brightness(obs,subtract_zodi)
    variance=obs.arrays.get('VARIANCE')
    if variance is None or variance.shape != obs.arrays['IMAGE'].shape: raise ValueError('A co-shaped VARIANCE plane is required.')
    variance_unit=obs.headers['VARIANCE'].get('BUNIT')
    if not variance_unit or not u.Unit(variance_unit).is_equivalent((u.MJy/u.sr)**2):
        raise ValueError('VARIANCE must declare compatible squared brightness units.')
    variance_factor=u.Unit(variance_unit).to((u.MJy/u.sr)**2)
    native_valid=valid_pixels(obs)&np.isfinite(brightness)&np.isfinite(variance)&(variance>=0)
    flagged=(obs.arrays['FLAGS'].astype(np.int64)&~INFORMATIONAL_FLAGS)!=0
    yy,xx=np.mgrid[:size,:size]
    with WCS_LOCK, warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sx,sy=pixel_to_pixel(grid,obs.spatial,xx,yy)
    finite=np.isfinite(sx)&np.isfinite(sy)
    safe_x=np.where(finite,sx,0);safe_y=np.where(finite,sy,0)
    # Snap floating-point WCS roundoff on integral pixels (not real pointing offsets).
    safe_x=np.where(np.abs(safe_x-np.rint(safe_x))<1e-7,np.rint(safe_x),safe_x)
    safe_y=np.where(np.abs(safe_y-np.rint(safe_y))<1e-7,np.rint(safe_y),safe_y)
    x0=np.floor(safe_x).astype(int);y0=np.floor(safe_y).astype(int)
    dx=safe_x-x0;dy=safe_y-y0
    h,w=variance.shape; propagated=np.zeros((size,size));out_valid=finite.copy()
    outside=~finite; bad_flag=np.zeros_like(finite)
    for ox,oy,weight in [(0,0,(1-dx)*(1-dy)),(1,0,dx*(1-dy)),(0,1,(1-dx)*dy),(1,1,dx*dy)]:
        x=x0+ox;y=y0+oy;inside=(x>=0)&(x<w)&(y>=0)&(y<h)
        cx=np.clip(x,0,w-1);cy=np.clip(y,0,h-1)
        contributing=weight>1e-10
        outside |= contributing & ~inside
        bad_flag |= contributing & inside & flagged[cy,cx]
        out_valid &= ~contributing | (inside & native_valid[cy,cx])
        propagated += np.where(contributing & inside & native_valid[cy,cx], weight**2*np.nan_to_num(variance[cy,cx])*variance_factor,0)
    with WCS_LOCK, warnings.catch_warnings():
        warnings.simplefilter('ignore')
        image,footprint=reproject_interp((np.where(native_valid,brightness,np.nan),obs.spatial),grid,shape_out=(size,size),order='bilinear')
    wave,band=obs.spectral_values(safe_x,safe_y)
    out_valid &= (footprint>0)&np.isfinite(image)&np.isfinite(wave)&(band>0)
    fwhm=obs.headers['IMAGE'].get('PSF_FWHM')
    fwhm=float(fwhm) if fwhm is not None and np.isfinite(fwhm) and fwhm>0 else None
    exclusion=np.select([out_valid,outside,bad_flag,~np.isfinite(wave)|~(band>0)],[0,1,2,3],default=4).astype(np.uint8)
    return Frame(image,propagated,wave,band,out_valid,grid,fwhm,'MJy/sr',timestamp(obs),subtract_zodi,exclusion)


def smooth(frame: Frame, target: float, scale: float) -> Frame:
    if frame.psf_fwhm is None: raise ValueError('PSF_FWHM is missing; automatic Gaussian PSF matching is unavailable.')
    sigma=np.sqrt(max(0,target**2-frame.psf_fwhm**2))/(2.354820045*scale)
    if sigma<.01:return frame
    radius=max(1,int(np.ceil(4*sigma)));axis=np.arange(-radius,radius+1)
    k=np.exp(-axis**2/(2*sigma*sigma));k/=k.sum();kernel=np.outer(k,k)
    image=ndimage.convolve(np.where(frame.valid,frame.image,0),kernel,mode='constant',cval=0)
    variance=ndimage.convolve(np.where(frame.valid,frame.variance,0),kernel**2,mode='constant',cval=0)
    # Do not borrow neighboring samples across incompatible wavelengths.
    wave_lo=ndimage.minimum_filter(np.where(frame.valid,frame.wave,np.inf),size=2*radius+1,mode='constant',cval=np.inf)
    wave_hi=ndimage.maximum_filter(np.where(frame.valid,frame.wave,-np.inf),size=2*radius+1,mode='constant',cval=-np.inf)
    valid=ndimage.binary_erosion(frame.valid,structure=np.ones(kernel.shape),border_value=0)&((wave_hi-wave_lo)<.25*frame.band)
    return Frame(image,variance,frame.wave,frame.band,valid,frame.wcs,target,frame.unit,frame.timestamp,frame.zodi_subtracted)


EXCLUSION_REASONS={
    1:'Outside an observation’s coverage',
    2:'Flagged detector pixels in an observation',
    3:'Missing wavelength calibration',
    4:'Unusable brightness, uncertainty, or resampled data',
    5:'Wavelength or bandwidth mismatch between dates',
    6:'Sharpness matching needs valid neighbors at similar wavelengths',
    7:'Outside the selected wavelength interval',
}


def comparison_inputs(a: Frame,b: Frame,scale: float,psf_match: bool=True):
    if a.zodi_subtracted!=b.zodi_subtracted:
        raise ValueError('Both observations must use the same ZODI subtraction setting.')
    # Band centers within 1/4 of narrower measured bandwidth and widths within 20%.
    compatible=(np.abs(a.wave-b.wave)<=.25*np.minimum(a.band,b.band)) & (np.abs(a.band-b.band)<=.2*np.maximum(a.band,b.band))
    if psf_match:
        if a.psf_fwhm is None or b.psf_fwhm is None:raise ValueError('PSF metadata is missing. Supply calibrated observations with PSF_FWHM.')
        target=max(a.psf_fwhm,b.psf_fwhm);a=smooth(a,target,scale);b=smooth(b,target,scale)
    else:target=None
    valid=a.valid&b.valid&compatible
    if not valid.any():
        raise ValueError('No valid overlap with compatible wavelengths and bandwidths. Load a matching exposure or choose another sky region.')
    return a,b,target,compatible,valid


def comparison_coverage(a: Frame,b: Frame,scale: float) -> tuple[int,float]:
    *_,valid=comparison_inputs(a,b,scale)
    return int(valid.sum()),float(valid.mean())


def difference(a: Frame,b: Frame,scale: float,background: bool=True,psf_match: bool=True,explain: bool=False):
    before_a,before_b=a,b
    a,b,target,compatible,valid=comparison_inputs(a,b,scale,psf_match)
    exclusion=None
    if explain:
        # Assign each gap one cause; prefer the original data rejection over a downstream mask.
        codes_a=before_a.exclusion if before_a.exclusion is not None else np.where(before_a.valid,0,4)
        codes_b=before_b.exclusion if before_b.exclusion is not None else np.where(before_b.valid,0,4)
        original_codes=[1,2,3,4,7]
        exclusion=np.select([valid]+[(codes_a==i)|(codes_b==i) for i in original_codes]+[~compatible],
                            [0,*original_codes,5],default=6).astype(np.uint8)
    delta=b.image-a.image
    offset=float(np.median(delta[valid])) if background else 0.
    delta=delta-offset
    variance=a.variance+b.variance
    significance=np.divide(delta,np.sqrt(np.maximum(variance,0)),out=np.full_like(delta,np.nan),where=valid&(variance>0))
    return dict(reference=a.image,new=b.image-offset,reference_variance=a.variance,new_variance=b.variance,
                difference=delta,significance=significance,variance=variance,valid=valid,exclusion=exclusion,
                offset=offset,psf_target=target,overlap=float(valid.mean()),wcs=a.wcs,zodi_subtracted=a.zodi_subtracted,
                assumptions=['Independent input pixel errors; resampling introduces inter-pixel correlations.',
                             'Gaussian PSF approximation from median PSF_FWHM; spatial PSF structure remains approximate.',
                             'Band-center/bandwidth checks are approximate, not full filter-response equivalence.',
                             'Significance excludes calibration, PSF-model and fitted-background systematic errors.']+
                            (['Each native IMAGE has its own ZODI model subtracted before reprojection; ZODI model uncertainty is not included in propagated measurement variance.'] if a.zodi_subtracted else []))


def candidates(result: dict, threshold: float, min_pixels: int, max_candidates: int=100) -> list:
    significance=result['significance']; valid=result['valid'];items=[]
    # Separate signs so positive and negative motion lobes remain distinct.
    for sign in [1,-1]:
        labeled,count=ndimage.label(valid&np.isfinite(significance)&(sign*significance>=threshold),structure=np.ones((3,3)))
        for label,slices in enumerate(ndimage.find_objects(labeled),1):
            if slices is None:continue
            sy,sx=slices;local=labeled[slices]==label; n=int(local.sum())
            if n<min_pixels:continue
            yy,xx=np.nonzero(local);yy+=sy.start;xx+=sx.start
            weights=np.abs(significance[yy,xx]);x=float(np.average(xx,weights=weights));y=float(np.average(yy,weights=weights))
            with WCS_LOCK:
                sky=result['wcs'].pixel_to_world(x,y).icrs
            peak=float(sign*significance[yy,xx].max()) if sign==1 else float(significance[yy,xx].min())
            peak_index=int(np.argmax(weights))
            items.append(dict(x=x,y=y,ra_deg=float(sky.ra.deg),dec_deg=float(sky.dec.deg),pixels=n,peak_sigma=peak,
                              peak_x=int(xx[peak_index]),peak_y=int(yy[peak_index]),
                              sign='positive' if sign>0 else 'negative',status='Unverified residual',
                              edge=bool((xx.min()==0) or (yy.min()==0) or (xx.max()==valid.shape[1]-1) or (yy.max()==valid.shape[0]-1))))
    items.sort(key=lambda item:abs(item['peak_sigma']),reverse=True)
    return [dict(id=i+1,**item) for i,item in enumerate(items[:max_candidates])]
