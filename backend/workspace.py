"""Multi-observation workspace routes. Real files only; derived products are labeled."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from threading import Event
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy.wcs.utils import proj_plane_pixel_scales
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, model_validator

from backend import archive, processing as proc
from backend.science import scalar, WCS_LOCK

def service():
    from backend import main
    return main


router = APIRouter()
SESSIONS: dict = {}
ANALYSES: dict = {}


def bad_request(exc):
    return HTTPException(422,str(exc))


def bounded_store(store,key,value):
    if key not in store and len(store)>=4:store.pop(next(iter(store)))
    store[key]=value


@router.get('/library')
def library():
    items=[]
    for path in sorted(service().DATA_DIR.glob('*.json')):
        if len(path.stem)!=64:continue
        try:
            record=json.loads(path.read_text())
            items.append(record.get('metadata') or service().metadata(path.stem))
        except (ValueError,OSError,HTTPException):continue
    items.sort(key=lambda item:str((item.get('timestamp') or {}).get('value','')))
    return dict(observations=items)


@router.get('/archive/search')
def search(ra: Annotated[float,Query(ge=0,lt=360)],dec: Annotated[float,Query(ge=-90,le=90)],
           radius: Annotated[float,Query(gt=0,le=1)]=.01,
           collection: Literal['spherex_dr1','spherex_dr1_deep','spherex_qr3','spherex_qr3_deep']='spherex_dr1',
           limit: Annotated[int,Query(ge=1,le=500)]=100):
    try:return archive.search(ra,dec,radius,collection,limit)
    except Exception as exc:raise HTTPException(502,f'IRSA search failed: {exc}. No observations were substituted.') from exc


class ImportRequest(BaseModel):
    url: str
    ra: float=Field(ge=0,lt=360)
    dec: float=Field(ge=-90,le=90)
    size_deg: float=Field(default=.2,gt=0,le=1)
    full_frame: bool=False


@router.post('/archive/import')
def import_observation(body: ImportRequest):
    return _import_observation(body)


def _import_observation(body: ImportRequest, *, progress=None, cancel=None):
    try:
        archive.validate_url(body.url)
        ra,dec=(None,None) if body.full_frame else (body.ra,body.dec)
        path,request_url=archive.download(body.url,service().DATA_DIR,ra,dec,body.size_deg,progress=progress,cancel=cancel)
        if cancel is not None and cancel.is_set():raise archive.DownloadCancelled()
        result=service().register(path,Path(urlsplit(body.url).path).name)
        record_path=service().DATA_DIR/f'{result["id"]}.json'
        record=json.loads(record_path.read_text())
        record['archive']=dict(url=request_url,original_url=body.url,release=urlsplit(body.url).path.split('/')[4].upper())
        record_path.write_text(json.dumps(record))
        service().metadata.cache_clear()
        result=service().metadata(result['id'])
        record['metadata']=result;record_path.write_text(json.dumps(record))
        return result
    except archive.DownloadCancelled:raise
    except archive.ArchiveUnavailable as exc:raise HTTPException(503,str(exc)) from exc
    except ValueError as exc:raise bad_request(exc) from exc
    except Exception as exc:raise HTTPException(502,f'IRSA import failed: {exc}. No replacement data were generated.') from exc


@router.post('/archive/import-stream')
async def import_stream(body: ImportRequest):
    try:archive.validate_url(body.url)
    except ValueError as exc:raise bad_request(exc) from exc

    async def events():
        cancelled=Event()
        latest=(0,None)

        def update(received,total):
            nonlocal latest
            latest=(received,total)

        def work():
            try:return dict(type='complete',observation=_import_observation(body,progress=update,cancel=cancelled))
            except archive.DownloadCancelled:return dict(type='cancelled')
            except HTTPException as exc:return dict(type='error',message=str(exc.detail))

        worker=asyncio.create_task(asyncio.to_thread(work))
        try:
            while not worker.done():
                received,total=latest
                yield json.dumps(dict(type='progress',received=received,total=total))+'\n'
                await asyncio.sleep(.25)
            yield json.dumps(await worker)+'\n'
        finally:
            cancelled.set()

    return StreamingResponse(events(),media_type='application/x-ndjson',
                             headers={'Cache-Control':'no-store, no-transform','X-Accel-Buffering':'no'})


@router.get('/observations/{file_id}/wavelength-image')
def wavelength_image(file_id:str, wavelength:Annotated[float,Query(ge=.7,le=5.1)],width:Annotated[float,Query(gt=0,le=1)]=.05,
                     mode:Literal['selection','calibration']='selection'):
    try:
        obs=service().load(file_id);selected,wave=proc.detector_band(obs,wavelength,width)
        if mode=='calibration':return Response(proc.png(wave),media_type='image/png')
        return Response(proc.png(obs.arrays['IMAGE'],selected),media_type='image/png')
    except ValueError as exc:raise bad_request(exc) from exc


class SessionRequest(BaseModel):
    ids: list[str]=Field(min_length=1,max_length=12)
    ra: float=Field(ge=0,lt=360)
    dec: float=Field(ge=-90,le=90)
    size: int=Field(default=96,ge=16,le=256)
    scale: float=Field(default=6.15,ge=.5,le=30)
    wavelength: float|None=Field(default=None,ge=.7,le=5.1)
    width: float=Field(default=.05,gt=0,le=1)
    subtract_zodi: bool=False


@router.post('/workspace/sessions')
def create_session(body:SessionRequest):
    if len(set(body.ids))!=len(body.ids):raise HTTPException(422,'Select distinct observation files.')
    key=hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:24]
    if key in SESSIONS:return SESSIONS[key]['metadata']
    grid=proc.sky_grid(body.ra,body.dec,body.size,body.scale)
    frames=[];info=[];seen_exposures=set()
    try:
        for file_id in body.ids:
            obs=service().load(file_id)
            exposure=(obs.headers['IMAGE'].get('OBSID'),obs.headers['IMAGE'].get('DETECTOR'),proc.timestamp(obs))
            if all(v is not None for v in exposure):
                if exposure in seen_exposures:raise ValueError('Two selected files describe the same exposure and detector. Select only one to avoid double-counting correlated measurements.')
                seen_exposures.add(exposure)
            frame=proc.project(obs,grid,body.size,body.subtract_zodi)
            if body.wavelength is not None:
                in_band=np.abs(frame.wave-body.wavelength)<=body.width/2
                frame.exclusion[frame.valid&~in_band]=7
                frame.valid &= in_band
            frames.append(frame);valid=frame.valid;meta=service().metadata(file_id)
            info.append(dict(id=file_id,filename=meta['filename'],timestamp=frame.timestamp,coverage=float(valid.mean()),
                             observation=meta['observation'],time_system=meta['time_system'],provenance=meta['provenance'],
                             wavelength_min_um=scalar(np.min(frame.wave[valid])) if valid.any() else None,
                             wavelength_max_um=scalar(np.max(frame.wave[valid])) if valid.any() else None,
                             psf_fwhm_arcsec=frame.psf_fwhm,source_url=meta['source_url']))
        values=np.concatenate([f.image[f.valid] for f in frames])
        limits=np.percentile(values,[1,99]).tolist() if values.size else [0,1]
        recommended=None;comparisons=[]
        for i,a in enumerate(frames):
            for j,b in enumerate(frames):
                if j<=i:continue
                pair=dict(reference=i,new=j,available=False,coverage=0.,reason=None)
                try:
                    if not a.timestamp or not b.timestamp or a.timestamp==b.timestamp:
                        raise ValueError('Distinct known observation dates are required.')
                    # Use the same masks and PSF matching as the actual comparison,
                    # not an exposure-wide wavelength-range or pre-smoothing guess.
                    _,coverage=proc.comparison_coverage(a,b,body.scale)
                    pair.update(available=True,coverage=coverage)
                    if recommended is None or pair['coverage']>recommended['coverage']:
                        recommended=dict(reference=i,new=j,coverage=pair['coverage'])
                except ValueError as exc:
                    pair['reason']=str(exc)
                comparisons.append(pair)
        result=dict(id=key,frames=info,grid=body.model_dump(exclude={'ids'}),limits=limits,recommended_pair=recommended,comparisons=comparisons,
                    distinct_epochs=len({f.timestamp for f in frames if f.timestamp}),
                    note='Registered to a common ICRS TAN sky grid. No registration against stars that could erase motion.')
        bounded_store(SESSIONS,key,dict(metadata=result,frames=frames,grid=grid,body=body))
        return result
    except (ValueError,TypeError) as exc:raise bad_request(exc) from exc


def session(key):
    if key not in SESSIONS:raise HTTPException(404,'Workspace session expired. Build the sky view again.')
    return SESSIONS[key]


class AutoSessionRequest(BaseModel):
    ra: float=Field(ge=0,lt=360)
    dec: float=Field(ge=-90,le=90)
    size: int=Field(default=96,ge=16,le=256)
    scale: float=Field(default=6.15,ge=.5,le=30)
    preferred_id: str|None=None
    subtract_zodi: bool=False


@router.post('/workspace/auto-session')
def auto_session(body:AutoSessionRequest):
    """Search beyond the 12-frame display limit; validate actual registered pixels."""
    items=library()['observations']
    preferred=next((o for o in items if o['id']==body.preferred_id),{})
    detector=(preferred.get('detector') or {}).get('value')
    wave=preferred.get('center_wavelength_um')
    if preferred:
        try:
            obs=service().load(preferred['id']);pos=obs.locate(body.ra,body.dec)
            measured,_=obs.spectral_values(pos['x'],pos['y'])
            if np.isfinite(measured):wave=float(measured)
        except (ValueError,TypeError,HTTPException):pass
    def rank(o):
        value=o.get('center_wavelength_um')
        return (o['id']!=body.preferred_id,(o.get('detector') or {}).get('value')!=detector,
                abs(value-wave) if value is not None and wave is not None else 100)
    items.sort(key=rank)
    grid=proc.sky_grid(body.ra,body.dec,body.size,body.scale)
    projected=[];seen=set();chosen=None;checked=0
    for meta in items:
        if not meta.get('spatial_wcs') or not meta.get('spectral'):continue
        exposure=tuple((meta.get(k) or {}).get('value') for k in ('observation','detector','timestamp'))
        if all(v is not None for v in exposure):
            if exposure in seen:continue
            seen.add(exposure)
        checked+=1
        try:
            frame=proc.project(service().load(meta['id']),grid,body.size,body.subtract_zodi)
            if not frame.timestamp or not frame.valid.any():continue
            if chosen is None:
                for old_meta,old in projected:
                    if old.timestamp==frame.timestamp:continue
                    compatible=old.valid&frame.valid&(np.abs(old.wave-frame.wave)<=.25*np.minimum(old.band,frame.band))&(np.abs(old.band-frame.band)<=.2*np.maximum(old.band,frame.band))
                    if not compatible.any():continue
                    try: count,_=proc.comparison_coverage(old,frame,body.scale)
                    except ValueError:continue
                    if count>=9:
                        chosen=[old_meta['id'],meta['id']];break
            projected.append((meta,frame))
            if chosen is not None and len(projected)>=12:break
        except (ValueError,TypeError,HTTPException):continue
    if chosen is None:
        extra=' A usable ZODI plane is required for every observation while ZODI subtraction is enabled.' if body.subtract_zodi else ''
        raise HTTPException(422,f'Checked {checked} calibrated observations. No distinct-date pair has usable wavelength-compatible overlap after PSF matching at this position.{extra} Choose another sky region or load matching exposures.')
    ids=list(dict.fromkeys(chosen+[meta['id'] for meta,_ in projected]))[:12]
    result=create_session(SessionRequest(ids=ids,ra=body.ra,dec=body.dec,size=body.size,scale=body.scale,subtract_zodi=body.subtract_zodi))
    # Prefer a reference with several compatible dates for the current-date slider.
    available=[p for p in result['comparisons'] if p['available']]
    neighbors={i:set() for i in range(len(result['frames']))}
    for pair in available:
        i,j=pair['reference'],pair['new']
        older,newer=(i,j) if result['frames'][i]['timestamp']<result['frames'][j]['timestamp'] else (j,i)
        neighbors[older].add(newer)
    if available:
        anchor=min(neighbors,key=lambda i:(-len(neighbors[i]),result['frames'][i]['timestamp'] or ''))
        choices=[p for p in available if anchor in (p['reference'],p['new']) and
                 (p['new'] if p['reference']==anchor else p['reference']) in neighbors[anchor]]
        pair=max(choices,key=lambda p:p['coverage']);other=pair['new'] if pair['reference']==anchor else pair['reference']
        result={**result,'recommended_pair':dict(reference=anchor,new=other,coverage=pair['coverage'])}
    return {**result,'selection':dict(library_count=len(items),checked=checked,method='Distinct epochs; per-pixel wavelength/bandwidth, quality and PSF overlap checks')}


@router.get('/workspace/sessions/{key}/frames/{index}')
def frame_image(key:str,index:int):
    s=session(key)
    if not 0<=index<len(s['frames']):raise HTTPException(404,'Frame not found.')
    f=s['frames'][index]
    return Response(proc.png(f.image,f.valid,limits=s['metadata']['limits']),media_type='image/png')


@router.get('/workspace/sessions/{key}/coadd')
def coadd(key:str):
    s=session(key)
    if s['body'].wavelength is None:raise HTTPException(422,'Select a wavelength interval and rebuild before combining measurements.')
    frames=s['frames'];shape=frames[0].valid.shape
    numerator=np.zeros(shape);weights=np.zeros(shape);anchor_wave=np.full(shape,np.nan);anchor_band=np.full(shape,np.nan)
    for f in frames:
        valid=f.valid&(f.variance>0)
        first=valid&~np.isfinite(anchor_wave);anchor_wave[first]=f.wave[first];anchor_band[first]=f.band[first]
        valid &= (np.abs(f.wave-anchor_wave)<=.25*np.minimum(f.band,anchor_band))&(np.abs(f.band-anchor_band)<=.2*np.maximum(f.band,anchor_band))
        weight=np.divide(1,f.variance,out=np.zeros(shape),where=valid)
        numerator+=np.where(valid,f.image,0)*weight;weights+=weight
    data=np.divide(numerator,weights,out=np.full(shape,np.nan),where=weights>0)
    return Response(proc.png(data,weights>0),media_type='image/png',headers={'X-Processing':'Inverse-variance weighted compatible samples; no interpolation over missing coverage'})


@router.get('/workspace/sessions/{key}/pixel')
def frame_pixel(key:str,index:Annotated[int,Query(ge=0)],x:Annotated[int,Query(ge=0)],y:Annotated[int,Query(ge=0)]):
    s=session(key)
    if index>=len(s['frames']) or x>=s['body'].size or y>=s['body'].size:raise HTTPException(422,'Outside sky-grid frame.')
    frame=s['frames'][index]
    with WCS_LOCK:
        sky=frame.wcs.pixel_to_world(x,y).icrs
    return dict(x=x,y=y,ra_deg=float(sky.ra.deg),dec_deg=float(sky.dec.deg),valid=bool(frame.valid[y,x]),
                brightness=scalar(frame.image[y,x]) if frame.valid[y,x] else None,variance=scalar(frame.variance[y,x]) if frame.valid[y,x] else None,
                wavelength_um=scalar(frame.wave[y,x]) if frame.valid[y,x] else None,bandwidth_um=scalar(frame.band[y,x]) if frame.valid[y,x] else None)


class ComparisonRequest(BaseModel):
    session: str
    reference: int=Field(ge=0)
    new: int=Field(ge=0)
    background: bool=True


@router.post('/analysis')
def analyze(body:ComparisonRequest):
    s=session(body.session);frames=s['frames'];n=len(frames)
    if body.reference>=n or body.new>=n:raise HTTPException(422,'Select frames in this session.')
    a,b=frames[body.reference],frames[body.new]
    if body.reference==body.new or a.timestamp==b.timestamp:raise HTTPException(422,'Independent observations at distinct known epochs are required.')
    if not a.timestamp or not b.timestamp:raise HTTPException(422,'Original observation timestamps are required for comparison.')
    key=hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:24]
    try:
        result=proc.difference(a,b,s['body'].scale,body.background,explain=True)
        result['request']=body;result['session']=s
        metadata=dict(id=key,overlap_fraction=result['overlap'],valid_pixels=int(result['valid'].sum()),
                      background_offset=result['offset'],psf_target_arcsec=result['psf_target'],zodi_subtracted=result['zodi_subtracted'],
                      reference_timestamp=a.timestamp,new_timestamp=b.timestamp,assumptions=result['assumptions'],
                      unit='MJy/sr',difference_limits=[scalar(np.percentile(result['difference'][result['valid']],1)),scalar(np.percentile(result['difference'][result['valid']],99))])
        counts=np.bincount(result['exclusion'].ravel(),minlength=len(proc.EXCLUSION_REASONS)+1)
        metadata['exclusions']=[dict(reason=reason,pixels=int(counts[code])) for code,reason in proc.EXCLUSION_REASONS.items() if counts[code]]
        mask=result['valid']
        wave_ratio=float(np.max((np.abs(a.wave-b.wave)/np.minimum(a.band,b.band))[mask]))
        median=float(np.median(result['difference'][mask]))
        metadata['checks']=[
            dict(label='Wavelengths', detail=f'Maximum center difference: {wave_ratio:.1%} of the narrower bandwidth (limit 25%). Bandwidth differences also pass the 20% limit.'),
            dict(label='WCS alignment', detail='Both observations were mapped to one sky grid using their FITS WCS. Residual star alignment was not independently measured.'),
            dict(label='Sharpness', detail=f'Header PSF widths: {a.psf_fwhm:.2f}″ and {b.psf_fwhm:.2f}″; Gaussian matched to {result["psf_target"]:.2f}″. Local PSF mismatch can remain.'),
            dict(label='Background', detail=f'Median offset removed: {result["offset"]:.4g} MJy/sr. Remaining median: {median:.4g} MJy/sr.' if body.background else 'Median background correction is off.'),
            dict(label='Pixel FLAGS', detail=f'{int(mask.sum()):,} pixels passed the overlap, quality, and matching masks. Informational FLAGS bits 12 and 21 are allowed.'),
        ]
        result['metadata']=metadata;bounded_store(ANALYSES,key,result);return metadata
    except ValueError as exc:raise bad_request(exc) from exc


def analysis(key):
    if key not in ANALYSES:raise HTTPException(404,'Analysis expired. Recompute the comparison.')
    return ANALYSES[key]


@router.get('/analysis/{key}/image')
def analysis_image(key:str,kind:Literal['reference','new','difference','significance','overlap']='difference'):
    result=analysis(key)
    if kind=='overlap':return Response(proc.png(result['valid'].astype(float),np.ones_like(result['valid']),limits=(0,1)),media_type='image/png')
    limits=(-5,5) if kind=='significance' else result['session']['metadata']['limits'] if kind in ('reference','new') else None
    return Response(proc.png(result[kind],result['valid'],signed=kind in ('difference','significance'),limits=limits),media_type='image/png')


@router.get('/analysis/{key}/pixel')
def analysis_pixel(key:str,x:Annotated[int,Query(ge=0)],y:Annotated[int,Query(ge=0)]):
    result=analysis(key);shape=result['valid'].shape
    if x>=shape[1] or y>=shape[0]:raise HTTPException(422,'Outside analysis grid.')
    valid=bool(result['valid'][y,x])
    with WCS_LOCK:
        sky=result['wcs'].pixel_to_world(x,y).icrs
    return dict(x=x,y=y,ra_deg=float(sky.ra.deg),dec_deg=float(sky.dec.deg),valid=valid,
                exclusion_reason=proc.EXCLUSION_REASONS.get(int(result['exclusion'][y,x])),
                **{k:scalar(result[k][y,x]) if valid else None for k in ('reference','new','reference_variance','new_variance','difference','significance','variance')})


@router.get('/analysis/{key}/original-patches')
def original_patches(key:str,x:Annotated[int,Query(ge=0)],y:Annotated[int,Query(ge=0)]):
    result=analysis(key);shape=result['valid'].shape
    if x>=shape[1] or y>=shape[0]:raise HTTPException(422,'Outside analysis grid.')
    with WCS_LOCK:
        sky=result['wcs'].pixel_to_world(x,y).icrs
    s=result['session'];request=result['request'];patches=[];data=[]
    for label,index in [('A',request.reference),('B',request.new)]:
        obs=service().load(s['body'].ids[index]);entry=dict(label=label,filename=s['metadata']['frames'][index]['filename'])
        try:
            pos=obs.locate(float(sky.ra.deg),float(sky.dec.deg));px,py=pos['x'],pos['y'];sample=obs.pixel('IMAGE',px,py)
            source=obs.arrays['IMAGE'];h,w=source.shape
            x0,y0=max(0,px-5),max(0,py-5)
            patch=source[y0:min(h,py+6),x0:min(w,px+6)]*u.Unit(obs.headers['IMAGE']['BUNIT']).to(u.MJy/u.sr)
            bit_names={c.value:c.keyword.removeprefix('MP_') for c in obs.headers['FLAGS'].cards if c.keyword.startswith('MP') and isinstance(c.value,int)}
            entry.update(x=sample['fits_x'],y=sample['fits_y'],flags=sample['flags'],
                         bits=[bit_names.get(bit,f'bit {bit}') for bit in sample['flag_bits']],
                         wave=sample['wavelength_um'],band=sample['bandwidth_um'],
                         point_x=(px-x0+.5)/patch.shape[1],point_y=1-(py-y0+.5)/patch.shape[0])
            data.append(patch)
        except ValueError as exc:
            entry['error']=str(exc);data.append(None)
        patches.append(entry)
    finite=np.concatenate([p[np.isfinite(p)] for p in data if p is not None]) if any(p is not None for p in data) else np.array([])
    limits=np.percentile(finite,[1,99]).tolist() if finite.size else [0,1]
    for entry,patch in zip(patches,data):
        if patch is not None:entry['png']=base64.b64encode(proc.png(patch,limits=limits)).decode('ascii')
    return dict(patches=patches)


@router.get('/analysis/{key}/candidates')
def candidate_list(key:str,threshold:Annotated[float,Query(ge=3,le=50)]=5,min_pixels:Annotated[int,Query(ge=2,le=100)]=3,
                   max_motion_arcsec:Annotated[float,Query(gt=0,le=3600)]=120):
    result=analysis(key);items=proc.candidates(result,threshold,min_pixels);pairs=[]
    negative=[c for c in items if c['sign']=='negative'];positive=[c for c in items if c['sign']=='positive']
    dt=(Time(result['metadata']['new_timestamp'])-Time(result['metadata']['reference_timestamp'])).to_value(u.hour)
    if dt:
        # All plausible lobe associations are hypotheses; no unique match is asserted.
        for p in positive:
            newer=SkyCoord(p['ra_deg']*u.deg,p['dec_deg']*u.deg)
            for n in negative:
                older=SkyCoord(n['ra_deg']*u.deg,n['dec_deg']*u.deg);sep=older.separation(newer).arcsec
                if 0<sep<=max_motion_arcsec:
                    dx,dy=older.spherical_offsets_to(newer)
                    pairs.append(dict(negative_id=n['id'],positive_id=p['id'],separation_arcsec=float(sep),
                                      ra_motion_arcsec_hour=float(dx.arcsec/dt),dec_motion_arcsec_hour=float(dy.arcsec/dt),
                                      speed_arcsec_hour=float(sep/abs(dt)),status='Ambiguous two-epoch motion hypothesis'))
    paired_ids={p[k] for p in pairs for k in ('positive_id','negative_id')}
    for item in items:
        item['pattern']='opposite-sign neighbor' if item['id'] in paired_ids else 'unpaired residual'
    return dict(candidates=items,motion_hypotheses=pairs[:100],threshold=threshold,min_pixels=min_pixels,
                note='Residual groups and lobe associations are unverified. Gaussian PSF mismatch, foregrounds, variable sources and correlated noise can mimic motion.')


@router.get('/workspace/sessions/{key}/spectrum')
def spectrum(key:str,ra:Annotated[float,Query(ge=0,lt=360)],dec:Annotated[float,Query(ge=-90,le=90)]):
    s=session(key);samples=[];unavailable=[]
    for file_id in s['body'].ids:
        obs=service().load(file_id)
        try:
            pos=obs.locate(ra,dec);cx,cy=pos['x'],pos['y'];brightness=proc.calibrated_brightness(obs,s['body'].subtract_zodi)
            valid=proc.valid_pixels(obs)&np.isfinite(brightness)
            var=obs.arrays.get('VARIANCE')
            if var is None or var.shape!=valid.shape:raise ValueError('Variance unavailable')
            iy,ix=np.mgrid[max(0,cy-5):min(valid.shape[0],cy+6),max(0,cx-5):min(valid.shape[1],cx+6)]
            r2=(ix-cx)**2+(iy-cy)**2;good=valid[iy,ix]&np.isfinite(var[iy,ix])&(var[iy,ix]>=0)
            aperture=(r2<=4);annulus=(r2>=9)&(r2<=25)&good
            if not np.all(good[aperture]) or int(annulus.sum())<10:raise ValueError('Insufficient valid aperture/annulus pixels')
            wave,band=obs.spectral_values(ix[aperture],iy[aperture])
            if not np.isfinite(wave).all() or np.ptp(wave)>.25*np.median(band):raise ValueError('Aperture mixes incompatible wavelengths')
            image=brightness[iy,ix].astype(float)
            brightness_unit=obs.headers['IMAGE'].get('BUNIT');variance_unit=obs.headers['VARIANCE'].get('BUNIT')
            if not brightness_unit or not variance_unit:raise ValueError('Missing measurement units')
            factor=1. # calibrated_brightness already converted IMAGE and ZODI to MJy/sr.
            variance_factor=u.Unit(variance_unit).to((u.MJy/u.sr)**2)
            background=float(np.median(image[annulus]))
            n=int(aperture.sum());flux=float(np.sum(image[aperture]-background))*factor
            propagated=(float(np.sum(var[iy,ix][aperture]))+n*n*np.pi/2*float(np.median(var[iy,ix][annulus]))/int(annulus.sum()))*variance_factor
            # Projection-plane pixel area; a local solid-angle approximation, no aperture correction.
            area_sr=float(np.prod(proj_plane_pixel_scales(obs.spatial)))*(np.pi/180)**2
            conversion=area_sr*1e9
            samples.append(dict(id=file_id,timestamp=proc.timestamp(obs),wavelength_um=float(np.mean(wave)),bandwidth_um=float(np.mean(band)),
                                flux_mjy=flux*conversion,uncertainty_mjy=float(np.sqrt(propagated))*conversion,
                                snr=flux/np.sqrt(propagated) if propagated>0 else None,aperture_pixels=n,background_brightness=background*factor))
        except (ValueError,TypeError) as exc:unavailable.append(dict(id=file_id,reason=str(exc)))
    samples.sort(key=lambda item:item['wavelength_um'])
    return dict(samples=samples,unavailable=unavailable,unit='mJy',zodi_subtracted=s['body'].subtract_zodi,
                note=('IMAGE − ZODI before aperture measurement; ZODI model uncertainty excluded. ' if s['body'].subtract_zodi else '')+
                     'Background-subtracted 2-pixel-radius aperture, 3–5-pixel annulus. Approximate solid angle and median-background variance; no PSF aperture correction. Different epochs may include source variability.')


@router.get('/analysis/{key}/track')
def track(key:str,negative_id:int,positive_id:int,threshold:Annotated[float,Query(ge=3,le=50)]=5,
          min_pixels:Annotated[int,Query(ge=2,le=100)]=3):
    result=analysis(key);items=proc.candidates(result,threshold,min_pixels)
    by_id={item['id']:item for item in items};n=by_id.get(negative_id);p=by_id.get(positive_id)
    if not n or not p or n['sign']!='negative' or p['sign']!='positive':raise HTTPException(422,'Select one negative and one positive residual.')
    s=result['session'];reference=result['request'].reference
    t0=Time(result['metadata']['reference_timestamp']);t1=Time(result['metadata']['new_timestamp'])
    duration=(t1-t0).to_value(u.hour)
    rows=[]
    for i,frame in enumerate(s['frames']):
        if not frame.timestamp:continue
        ratio=(Time(frame.timestamp)-t0).to_value(u.hour)/duration
        px=n['x']+(p['x']-n['x'])*ratio;py=n['y']+(p['y']-n['y'])*ratio
        row=dict(timestamp=frame.timestamp,frame=i,predicted_x=px,predicted_y=py,detection=None,reason=None)
        if i==reference:
            row['reason']='Reference negative residual anchors hypothesis; not an independent source detection.'
        else:
            try:
                compared=proc.difference(s['frames'][reference],frame,s['body'].scale,result['request'].background)
                detections=[c for c in proc.candidates(compared,threshold,min_pixels) if c['sign']=='positive']
                near=sorted(detections,key=lambda c:(c['x']-px)**2+(c['y']-py)**2)
                if near and np.hypot(near[0]['x']-px,near[0]['y']-py)<=3:
                    row['detection']=near[0]
                else:row['reason']='No significant positive residual within 3 grid pixels of the predicted path.'
            except ValueError as exc:row['reason']=str(exc)
        rows.append(row)
    return dict(epochs=rows,note='Linear path from a chosen two-epoch lobe association. Nearest residual matches within 3 pixels are tentative; all comparisons share a reference and have correlated errors.')
