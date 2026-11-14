"""Known-answer multi-observation tests; all generated pixels remain test fixtures."""
import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import gaussian_filter

from backend import processing as p
from backend.science import Observation
from backend.tests.conftest import fixture_fits


def calibrated(path, timestamp='2025-01-01T00:00:00', wavelength=3., dx=0., move=0.):
    w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crval=[180,45];w.wcs.crpix=[16.5+dx,16.5];w.wcs.cdelt=[-6.15/3600,6.15/3600]
    h=w.to_header();h['BUNIT']='MJy/sr';h['DATE-OBS']=timestamp;h['PSF_FWHM']=(6.15,'[arcsec] PSF FWHM Median')
    for key,value in {'WCSAXESW':2,'CTYPE1W':'WAVE-TAB','CTYPE2W':'WAVE-TAB','CUNIT1W':'um','CUNIT2W':'um','CRPIX1W':1.,'CRPIX2W':1.,'CRVAL1W':0.,'CRVAL2W':0.,'CDELT1W':1.,'CDELT2W':1.,'PS1_0W':'WCS-WAVE','PS2_0W':'WCS-WAVE','PS1_1W':'VALUES','PS2_1W':'VALUES','PS1_2W':'X','PS2_2W':'Y','PV1_1W':1,'PV2_1W':1,'PV1_3W':1,'PV2_3W':2}.items():h[key]=value
    table=fits.BinTableHDU.from_columns([fits.Column(name='X',format='2D',array=[[0,31]]),fits.Column(name='Y',format='2D',array=[[0,31]]),fits.Column(name='VALUES',format='8D',dim='(2,2,2)',array=[np.array([[[wavelength,.1],[wavelength,.1]],[[wavelength,.1],[wavelength,.1]]])])],name='WCS-WAVE')
    yy,xx=np.mgrid[:32,:32];image=50*np.exp(-((xx-10-dx)**2+(yy-16)**2)/2)+30*np.exp(-((xx-21-dx-move)**2+(yy-8)**2)/2)
    variance=fits.ImageHDU(np.ones((32,32)),name='VARIANCE');variance.header['BUNIT']='MJy2/sr2'
    fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(image,header=h,name='IMAGE'),fits.ImageHDU(np.zeros((32,32),dtype='int32'),name='FLAGS'),variance,table]).writeto(path)
    return Observation.read(path)


def test_stationary_sources_align_despite_pointing_offset(tmp_path):
    a=calibrated(tmp_path/'a.fits');b=calibrated(tmp_path/'b.fits',timestamp='2025-01-02T00:00:00',dx=1)
    grid=p.sky_grid(180,45,32,6.15);fa=p.project(a,grid,32);fb=p.project(b,grid,32)
    result=p.difference(fa,fb,6.15,background=False)
    assert np.max(np.abs(result['difference'][result['valid']]))<1e-6
    assert np.allclose(result['variance'][result['valid']],2)


def test_squared_interpolation_weights_propagate_variance(tmp_path):
    obs=calibrated(tmp_path/'a.fits');grid=p.sky_grid(180,45,32,6.15);grid.wcs.crpix += .5
    frame=p.project(obs,grid,32)
    assert frame.variance[16,16]==pytest.approx(.25,abs=1e-7)


def test_identical_images_give_zero_difference(tmp_path):
    obs=calibrated(tmp_path/'a.fits');frame=p.project(obs,p.sky_grid(180,45,32,6.15),32)
    result=p.difference(frame,frame,6.15,background=False)
    assert np.all(result['difference'][result['valid']]==0)
    assert np.all(result['significance'][result['valid']]==0)


def test_different_wavelengths_are_not_equivalent(tmp_path):
    a=calibrated(tmp_path/'a.fits');b=calibrated(tmp_path/'b.fits',wavelength=4.)
    grid=p.sky_grid(180,45,32,6.15)
    with pytest.raises(ValueError,match='compatible wavelengths'):p.difference(p.project(a,grid,32),p.project(b,grid,32),6.15)


def test_quality_bits_and_detector_band_selection(tmp_path):
    obs=calibrated(tmp_path/'a.fits');obs.arrays['FLAGS'][5,5]=1<<21;obs.arrays['FLAGS'][6,6]=1<<6
    valid=p.valid_pixels(obs);assert valid[5,5];assert not valid[6,6]
    selected,_=p.detector_band(obs,3.,.02);assert selected.all()
    selected,_=p.detector_band(obs,4.,.02);assert not selected.any()


def test_moving_source_retains_opposite_sign_residuals(tmp_path):
    a=calibrated(tmp_path/'a.fits');b=calibrated(tmp_path/'b.fits',timestamp='2025-01-02T00:00:00',move=3)
    grid=p.sky_grid(180,45,32,6.15);result=p.difference(p.project(a,grid,32),p.project(b,grid,32),6.15,background=False)
    assert abs(result['difference'][16,10])<1e-6
    assert result['difference'][8,21]<-20;assert result['difference'][8,24]>20
    candidates=p.candidates(result,5,3)
    assert any(c['sign']=='positive' for c in candidates)
    assert any(c['sign']=='negative' for c in candidates)
    assert all(c['status']=='Unverified residual' for c in candidates)


def test_psf_matching_propagates_kernel_squared_variance(tmp_path):
    frame=p.project(calibrated(tmp_path/'a.fits'),p.sky_grid(180,45,32,6.15),32)
    smoothed=p.smooth(frame,10,6.15)
    assert 0<smoothed.variance[16,16]<frame.variance[16,16]
    assert smoothed.psf_fwhm==10


def test_workspace_api_and_candidate_motion(tmp_path,monkeypatch):
    from backend import main
    from fastapi.testclient import TestClient
    from backend.workspace import SESSIONS,ANALYSES
    monkeypatch.setattr(main,'DATA_DIR',tmp_path/'cache');main.load.cache_clear();main.metadata.cache_clear();SESSIONS.clear();ANALYSES.clear()
    a=calibrated(tmp_path/'a.fits');b=calibrated(tmp_path/'b.fits',timestamp='2025-01-02T00:00:00',move=3)
    ma=main.register(a.path,'a.fits');mb=main.register(b.path,'b.fits');client=TestClient(main.app)
    response=client.post('/workspace/sessions',json=dict(ids=[ma['id'],mb['id']],ra=180,dec=45,size=32,scale=6.15))
    assert response.status_code==200,response.text
    session=response.json();assert session['distinct_epochs']==2
    response=client.post('/analysis',json=dict(session=session['id'],reference=0,new=1,background=False))
    assert response.status_code==200,response.text
    analysis=response.json();key=analysis['id'];assert analysis['overlap_fraction']>.8
    assert client.get(f'/analysis/{key}/image?kind=difference').headers['content-type']=='image/png'
    evidence=client.get(f'/analysis/{key}/pixel?x=24&y=8').json();assert evidence['significance']>10
    candidates=client.get(f'/analysis/{key}/candidates?threshold=5&min_pixels=3').json()
    assert candidates['motion_hypotheses'];motion=candidates['motion_hypotheses'][0]
    assert motion['speed_arcsec_hour']>0
    track=client.get(f'/analysis/{key}/track?negative_id={motion["negative_id"]}&positive_id={motion["positive_id"]}').json()
    assert len(track['epochs'])==2
    spectrum=client.get(f'/workspace/sessions/{session["id"]}/spectrum?ra=180&dec=45')
    assert spectrum.status_code==200
    assert client.post('/analysis',json=dict(session=session['id'],reference=0,new=0)).status_code==422


def test_official_archive_url_validation():
    from backend.archive import validate_url
    for url in ['http://127.0.0.1/private.fits','https://example.com/x.fits','https://irsa.ipac.caltech.edu/ibe/data/spherex/qr2/x.fits?other=x','https://irsa.ipac.caltech.edu@evil.org/ibe/data/spherex/x.fits']:
        with pytest.raises(ValueError):validate_url(url)


def test_session_comparison_availability_matches_actual_analysis(tmp_path,monkeypatch):
    from backend import main
    from backend.workspace import SESSIONS,ANALYSES
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main,'DATA_DIR',tmp_path/'cache');main.load.cache_clear();main.metadata.cache_clear();SESSIONS.clear();ANALYSES.clear()
    observations=[calibrated(tmp_path/'a.fits'),calibrated(tmp_path/'b.fits',timestamp='2025-01-02T00:00:00',move=3),calibrated(tmp_path/'c.fits',timestamp='2025-01-03T00:00:00',wavelength=4.)]
    ids=[main.register(o.path,o.path.name)['id'] for o in observations]
    client=TestClient(main.app)
    session=client.post('/workspace/sessions',json=dict(ids=ids,ra=180,dec=45,size=32,scale=6.15)).json()
    assert len(session['comparisons'])==3
    assert session['recommended_pair']['reference']==0
    assert session['recommended_pair']['new']==1
    for pair in session['comparisons']:
        response=client.post('/analysis',json=dict(session=session['id'],reference=pair['reference'],new=pair['new']))
        assert pair['available']==(response.status_code==200)
        if pair['available']:
            assert pair['coverage']==pytest.approx(response.json()['overlap_fraction'])
        else:
            assert pair['reason']
            assert pair['coverage']==0


def test_background_matching_display_and_difference_agree(tmp_path):
    a=p.project(calibrated(tmp_path/'a.fits'),p.sky_grid(180,45,32,6.15),32)
    b=p.Frame(a.image+17,a.variance,a.wave,a.band,a.valid,a.wcs,a.psf_fwhm,a.unit,'2025-01-02T00:00:00')
    result=p.difference(a,b,6.15)
    assert result['offset']==pytest.approx(17)
    assert np.allclose(result['difference'][result['valid']],0,atol=1e-12)
    assert np.allclose((result['new']-result['reference'])[result['valid']],result['difference'][result['valid']])


def test_automatic_search_finds_pair_beyond_twelve_files(tmp_path,monkeypatch):
    from backend import main
    from backend.workspace import SESSIONS,ANALYSES
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main,'DATA_DIR',tmp_path/'cache');main.load.cache_clear();main.metadata.cache_clear();SESSIONS.clear();ANALYSES.clear()
    ids=[]
    for i in range(13):
        # First twelve have one shared epoch, so none can be subtracted.
        obs=calibrated(tmp_path/f'{i}.fits',timestamp='2025-01-02T00:00:00' if i==12 else '2025-01-01T00:00:00',wavelength=3.+i*.001,move=3 if i==12 else 0)
        ids.append(main.register(obs.path,obs.path.name)['id'])
    client=TestClient(main.app)
    response=client.post('/workspace/auto-session',json=dict(preferred_id=ids[0],ra=180,dec=45,size=32))
    assert response.status_code==200,response.text
    s=response.json();assert s['selection']['checked']==13
    assert len(s['frames'])<=12
    pair=s['recommended_pair'];assert pair is not None
    assert s['frames'][pair['reference']]['timestamp']<s['frames'][pair['new']]['timestamp']
    result=client.post('/analysis',json=dict(session=s['id'],reference=pair['reference'],new=pair['new']))
    assert result.status_code==200,result.text
    assert client.get(f"/analysis/{result.json()['id']}/candidates").json()['candidates']
    response=client.post('/workspace/auto-session',json=dict(ra=0,dec=-60,size=32))
    assert response.status_code==422
    assert 'No distinct-date pair' in response.json()['detail']


def with_zodi(path, timestamp='2025-01-01T00:00:00', slope=1., move=0., dx=0.):
    calibrated(path,timestamp=timestamp,move=move,dx=dx)
    yy,xx=np.mgrid[:32,:32];model=5+slope*xx+.2*yy
    with fits.open(path,mode='update') as hdus:
        hdus['IMAGE'].data+=model
        zodi=fits.ImageHDU(model*1e9,name='ZODI');zodi.header['BUNIT']='mJy/sr'
        hdus.append(zodi)
    return Observation.read(path)


def test_zodi_removed_before_alignment_with_units_and_variance_preserved(tmp_path):
    a=with_zodi(tmp_path/'a.fits',slope=1.)
    b=with_zodi(tmp_path/'b.fits',timestamp='2025-01-02T00:00:00',slope=2.,dx=1)
    original=a.arrays['IMAGE'].copy();grid=p.sky_grid(180,45,32,6.15)
    fa=p.project(a,grid,32,True);fb=p.project(b,grid,32,True)
    result=p.difference(fa,fb,6.15,background=False)
    assert result['zodi_subtracted']
    assert np.max(np.abs(result['difference'][result['valid']]))<1e-6
    assert np.allclose(result['variance'][result['valid']],2)
    raw=p.difference(p.project(a,grid,32),p.project(b,grid,32),6.15,background=False)
    assert np.max(np.abs(raw['difference'][raw['valid']]))>10
    assert np.array_equal(original,a.arrays['IMAGE'])
    assert any('ZODI model uncertainty' in note for note in result['assumptions'])
    assert p.smooth(fa,10,6.15).zodi_subtracted
    with pytest.raises(ValueError,match='same ZODI'):p.difference(fa,p.project(b,grid,32),6.15)


@pytest.mark.parametrize('problem',['missing','shape','units','missing_units'])
def test_unusable_zodi_never_silently_falls_back(tmp_path,problem):
    obs=with_zodi(tmp_path/'a.fits')
    if problem=='missing':obs.arrays.pop('ZODI')
    if problem=='shape':obs.arrays['ZODI']=np.zeros((2,2))
    if problem=='units':obs.headers['ZODI']['BUNIT']='s'
    if problem=='missing_units':obs.headers['ZODI'].pop('BUNIT')
    grid=p.sky_grid(180,45,32,6.15)
    with pytest.raises(ValueError,match='ZODI'):p.project(obs,grid,32,True)
    assert p.project(obs,grid,32,False).valid.any()


def test_nonfinite_zodi_masks_pixels_only_when_enabled(tmp_path):
    obs=with_zodi(tmp_path/'a.fits');obs.arrays['ZODI'][10,10]=np.nan
    grid=p.sky_grid(180,45,32,6.15)
    assert not p.project(obs,grid,32,True).valid[10,10]
    assert p.project(obs,grid,32,False).valid[10,10]


def test_zodi_session_cache_analysis_and_candidates(tmp_path,monkeypatch):
    from backend import main
    from backend.workspace import SESSIONS,ANALYSES
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main,'DATA_DIR',tmp_path/'cache');main.load.cache_clear();main.metadata.cache_clear();SESSIONS.clear();ANALYSES.clear()
    a=with_zodi(tmp_path/'a.fits',slope=1.)
    b=with_zodi(tmp_path/'b.fits',timestamp='2025-01-02T00:00:00',slope=2.,move=3)
    ids=[main.register(o.path,o.path.name)['id'] for o in [a,b]]
    client=TestClient(main.app);sessions=[]
    for enabled in [False,True]:
        response=client.post('/workspace/sessions',json=dict(ids=ids,ra=180,dec=45,size=32,subtract_zodi=enabled))
        assert response.status_code==200,response.text
        s=response.json();sessions.append(s);assert s['grid']['subtract_zodi']==enabled
        response=client.post('/analysis',json=dict(session=s['id'],reference=0,new=1,background=False))
        assert response.status_code==200,response.text
        analysis=response.json();assert analysis['zodi_subtracted']==enabled
        if enabled:
            pixel=client.get(f"/analysis/{analysis['id']}/pixel?x=24&y=8").json()
            assert pixel['difference']>20
            assert abs(client.get(f"/analysis/{analysis['id']}/pixel?x=10&y=16").json()['difference'])<1e-6
            candidates=client.get(f"/analysis/{analysis['id']}/candidates").json()['candidates']
            assert {c['sign'] for c in candidates}=={'positive','negative'}
            spectrum=client.get(f"/workspace/sessions/{s['id']}/spectrum?ra=180&dec=45").json()
            assert spectrum['zodi_subtracted'] and 'ZODI' in spectrum['note']
    assert sessions[0]['id']!=sessions[1]['id']
    auto=client.post('/workspace/auto-session',json=dict(ra=180,dec=45,size=32,subtract_zodi=True))
    assert auto.status_code==200,auto.text
    assert auto.json()['grid']['subtract_zodi']
