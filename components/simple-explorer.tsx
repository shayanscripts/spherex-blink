'use client';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ArrowLeft, ArrowRight, Check, ChevronDown, Crosshair, ExternalLink, Focus, Info, LoaderCircle, Pause, Play, RefreshCw, ScanLine, SlidersHorizontal, Telescope, Upload, Waves } from 'lucide-react';
import { request } from '@/lib/api';
import SpectralFingerprint, { type FingerprintTarget } from './spectral-fingerprint';
import PossibleMotion, { MotionArrow, selectMotionPairs } from './simple-motion';
import NearbyObjects, { type CatalogPosition } from './nearby-objects';
import SimpleDownloads from './simple-downloads';
import LinkedSkyViewport, { HOME_CAMERA, SkyPlane, zoomSky } from './linked-sky-viewport';
import { number, type Analysis, type SkyFrame, type CandidateResult, type Residual, type Observation, type SkySession, type WorkspaceView } from '@/lib/types';

type OriginalPatch={label:string;filename:string;flags?:number|null;bits?:string[];x?:number;y?:number;wave?:number|null;band?:number|null;png?:string;point_x?:number;point_y?:number;error?:string};
type Pick={patches?:OriginalPatch[];pattern?:string;patchError?:string;exclusion_reason?:string|null;ra_deg:number;dec_deg:number;valid:boolean;brightness?:number|null;variance:number|null;wavelength_um?:number|null;difference?:number|null;significance?:number|null;x:number;y:number;unit?:string|null;uncertainty_unit?:string};
function date(value:string|null){if(!value)return 'Date unavailable';const d=new Date(value.endsWith('Z')?value:`${value}Z`);return Number.isNaN(d.valueOf())?value:d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'});}
function ChangeMarkers({markers,size,onPick}:{markers:Residual[];size:number;onPick:(x:number,y:number,marker:Residual)=>void}){
  return <>{markers.map(m=><button key={m.id} className={`residual-marker ${m.sign}`} style={{left:`${(m.x+.5)/size*100}%`,top:`${(size-m.y-.5)/size*100}%`}} aria-label={`Inspect residual ${m.id}, ${number(m.peak_sigma,1)} sigma`} title={`${m.sign} · ${number(m.peak_sigma,1)}σ · ${m.pixels} pixels · unverified`} onClick={()=>onPick(m.peak_x??Math.round(m.x),m.peak_y??Math.round(m.y),m)}>{m.id}</button>)}</>;
}
function SkyImage({src,label,onPick,unavailable,markers=[],gridSize=96,onMarkerPick,onDimensions,overlay}:{overlay?:ReactNode;src:string|null;label:string;onPick?:(x:number,y:number)=>void;unavailable?:string;markers?:Residual[];gridSize?:number;onMarkerPick?:(x:number,y:number,marker:Residual)=>void;onDimensions?:(width:number,height:number)=>void}){
  const [loading,setLoading]=useState(true);const[error,setError]=useState(false);const[selected,setSelected]=useState<{x:number;y:number;w:number;h:number}|null>(null);
  const image=useRef<HTMLImageElement>(null);
  useEffect(()=>{setLoading(!(src&&image.current?.complete&&image.current.naturalWidth));setError(false);setSelected(null);},[src]);
  const pick=(x:number,y:number)=>{const img=image.current;if(!img||!onPick)return;setSelected({x,y,w:img.naturalWidth,h:img.naturalHeight});onPick(x,y);};
  return <div className="simple-image">{src&&!unavailable&&<img ref={image} src={src} alt={label} draggable={false} tabIndex={onPick?0:undefined} onLoad={e=>{setLoading(false);onDimensions?.(e.currentTarget.naturalWidth,e.currentTarget.naturalHeight);}} onError={()=>{setLoading(false);setError(true);}} onClick={onPick?e=>{const r=e.currentTarget.getBoundingClientRect();pick(Math.min(e.currentTarget.naturalWidth-1,Math.floor((e.clientX-r.left)/r.width*e.currentTarget.naturalWidth)),Math.min(e.currentTarget.naturalHeight-1,e.currentTarget.naturalHeight-1-Math.floor((e.clientY-r.top)/r.height*e.currentTarget.naturalHeight)));}:undefined} onKeyDown={e=>{if(!onPick||!image.current)return;const img=image.current;let x=selected?.x??Math.floor(img.naturalWidth/2);let y=selected?.y??Math.floor(img.naturalHeight/2);if(!['Enter','ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();x+=e.key==='ArrowLeft'?-1:e.key==='ArrowRight'?1:0;y+=e.key==='ArrowDown'?-1:e.key==='ArrowUp'?1:0;pick(Math.max(0,Math.min(img.naturalWidth-1,x)),Math.max(0,Math.min(img.naturalHeight-1,y)));}}/>}{(!src||unavailable||loading||error)&&<div className="simple-image-message">{unavailable||error?<><Info size={22}/><p>{unavailable||'Could not load this image. Refresh the observations to retry.'}</p></>:<><LoaderCircle size={22} className="spin"/><p>Preparing real observations…</p></>}</div>}{!unavailable&&!loading&&!error&&overlay}{!unavailable&&!loading&&!error&&<ChangeMarkers markers={markers} size={gridSize} onPick={onMarkerPick??pick}/>}{selected&&!unavailable&&<i className="simple-selection" style={{left:`${(selected.x+.5)/selected.w*100}%`,top:`${(selected.h-selected.y-.5)/selected.h*100}%`}}/>}</div>;
}

function OriginalSkyView({frame,label,onPick}:{frame:SkyFrame;label:string;onPick:(x:number,y:number)=>void}){
  const [camera,setCamera]=useState(HOME_CAMERA);
  const [dimensions,setDimensions]=useState<{width:number;height:number}|null>(null);
  return <article className="simple-observation original-sky-view">
    <div className="simple-image-heading">{label}</div>
    <div className="comparison-view-controls linked-zoom-controls" role="group" aria-label={`${label} zoom`}>
      <div className="simple-segmented">
        <button aria-label={`Zoom out ${label}`} disabled={camera.zoom<=1} onClick={()=>setCamera(old=>zoomSky(old,1/1.5))}>−</button>
        <button aria-label={`Reset ${label} zoom`} onClick={()=>setCamera(HOME_CAMERA)}>{number(camera.zoom,2)}× · Reset</button>
        <button aria-label={`Zoom in ${label}`} disabled={camera.zoom>=8} onClick={()=>setCamera(old=>zoomSky(old,1.5))}>+</button>
      </div>
      {dimensions&&<small>{dimensions.width.toLocaleString()} × {dimensions.height.toLocaleString()} px</small>}
    </div>
    <LinkedSkyViewport camera={camera} setCamera={setCamera} aspectRatio={dimensions?dimensions.width/dimensions.height:1}>
      <SkyPlane camera={camera}>
        <SkyImage src={`/api/science/observations/${frame.id}/image?layer=IMAGE&mask=false`}
          label={`${label} FITS coverage`} onPick={onPick} onDimensions={(width,height)=>setDimensions({width,height})}/>
      </SkyPlane>
    </LinkedSkyViewport>
    <div className="simple-image-caption"><span>{date(frame.timestamp)}</span><small>{frame.filename}</small></div>
  </article>;
}

export default function SimpleExplorer({active,onComplex}:{active:boolean;onComplex:(target?:WorkspaceView)=>void}){
  const [tab,setTab]=useState<'motion'|'wavelength'|'downloads'>('motion');
  const [comparisonView,setComparisonView]=useState<'side-by-side'|'swipe'>('side-by-side');const[markOnImages,setMarkOnImages]=useState(false);
  const [showOriginals,setShowOriginals]=useState(false);
  const [camera,setCamera]=useState(HOME_CAMERA);
  const [showDifferenceMarkers,setShowDifferenceMarkers]=useState(true);
  const [reveal,setReveal]=useState(50);const swipe=useRef<HTMLDivElement>(null);
  const [observation,setObservation]=useState<Observation|null>(null);const[session,setSession]=useState<SkySession|null>(null);
  const [reference,setReference]=useState(0);const[current,setCurrent]=useState(0);const[playing,setPlaying]=useState(false);const[speed,setSpeed]=useState(1);
  const [analysis,setAnalysis]=useState<Analysis|null>(null);const[comparisonError,setComparisonError]=useState('');const[comparing,setComparing]=useState(false);
  const [residuals,setResiduals]=useState<Residual[]>([]);const[threshold,setThreshold]=useState(7);const[motionResult,setMotionResult]=useState<{key:string;pairs:CandidateResult['motion_hypotheses']}|null>(null);
  const[changeView,setChangeView]=useState<'brightness'|'motion'>('brightness');
  const[motionSelection,setMotionSelection]=useState<{key:string;pair:string}|null>(null);const[showAllChanges,setShowAllChanges]=useState(false);const[detecting,setDetecting]=useState(false);const[detectionError,setDetectionError]=useState('');
  const [differenceMode,setDifferenceMode]=useState<'difference'|'significance'>('difference');const[background,setBackground]=useState(true);const[subtractZodi,setSubtractZodi]=useState(true);
  const [busy,setBusy]=useState(true);const[error,setError]=useState('');const[pick,setPick]=useState<Pick|null>(null);const[picking,setPicking]=useState(false);
  const [ra,setRa]=useState('');const[dec,setDec]=useState('');const[wave,setWave]=useState(3.01);const[appliedWave,setAppliedWave]=useState(3.01);
  const[refresh,setRefresh]=useState(0);const input=useRef<HTMLInputElement>(null);const pickRequest=useRef(0);const subtraction=useRef<AbortController|null>(null);
  const [hasLoaded,setHasLoaded]=useState(false);
  const preparedRevision=useRef(-1);
  const endpoints='/api/science';

  useEffect(()=>{
    if(!active)return;
    const controller=new AbortController();let live=true;setBusy(true);setError('');setPlaying(false);
    async function initialize(){
      try{
        const saved=localStorage.getItem('spherex-observation');let obs:Observation|null=null;
        if(saved){try{obs=await request<Observation>(`/observations/${saved}`,{signal:controller.signal});}catch(e){if(controller.signal.aborted)throw e;}}
        if(!obs)obs=(await request<{observation:Observation|null}>('/observations/default',{signal:controller.signal})).observation;
        if(!live)return;
        if(!obs){setError('Load a SPHEREx FITS file to start exploring.');return;}
        setObservation(obs);localStorage.setItem('spherex-observation',obs.id);
        const center=await request<{ra_deg:number|null;dec_deg:number|null;wavelength_um:number|null}>(`/observations/${obs.id}/pixel?x=${Math.floor(obs.shape[1]/2)}&y=${Math.floor(obs.shape[0]/2)}`,{signal:controller.signal});
        if(!live)return;
        const wavelength=center.wavelength_um??3.01;setWave(wavelength);setAppliedWave(wavelength);
        const useRa=refresh&&ra?Number(ra):center.ra_deg;const useDec=refresh&&dec?Number(dec):center.dec_deg;
        if(useRa==null||useDec==null){setError('This file has no sky-coordinate calibration. You can still use the wavelength view or open the complex data inspector.');return;}
        setRa(useRa.toFixed(8));setDec(useDec.toFixed(8));
        const result=await request<SkySession>('/workspace/auto-session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preferred_id:obs.id,ra:useRa,dec:useDec,size:96,scale:6.15,subtract_zodi:subtractZodi}),signal:controller.signal});
        if(!live)return;setSession(result);setReference(result.recommended_pair?.reference??0);setCurrent(result.recommended_pair?.new??Math.min(1,result.frames.length-1));setPick(null);setHasLoaded(true);preparedRevision.current=refresh;
      }catch(e){if(live)setError(e instanceof Error?e.message:'Could not prepare the observations.');}finally{if(live)setBusy(false);}
    }
    // Preserve the prepared session while switching between Simple and Complex.
    if(hasLoaded&&preparedRevision.current===refresh){setBusy(false);return()=>{controller.abort();};}
    setSession(null);setAnalysis(null);setResiduals([]);void initialize();return()=>{live=false;controller.abort();};
  },[active,refresh]);
  useEffect(()=>{if(!active)setPlaying(false);},[active]);
  useEffect(()=>{if(active&&observation&&localStorage.getItem('spherex-observation')!==observation.id){setHasLoaded(false);preparedRevision.current=-1;setSession(null);setRa('');setDec('');setRefresh(old=>old+1);}},[active,observation?.id]);
  useEffect(()=>{const timeout=setTimeout(()=>setAppliedWave(wave),250);return()=>clearTimeout(timeout);},[wave]);
  const epochs=useMemo(()=>{
    const times=new Map<string,number>();session?.frames.forEach((f,i)=>{if(f.timestamp&&f.coverage>0&&!times.has(f.timestamp))times.set(f.timestamp,i);});return [...times.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(item=>item[1]);
  },[session]);
  const matches=useMemo(()=>{
    const result=new Map<number,number>();
    session?.comparisons?.forEach(pair=>{if(!pair.available)return;if(pair.reference===reference)result.set(pair.new,pair.coverage);if(pair.new===reference)result.set(pair.reference,pair.coverage);});
    return result;
  },[session,reference]);
  const playableEpochs=useMemo(()=>epochs.filter(index=>matches.has(index)),[epochs,matches]);
  const referenceAvailable=(index:number)=>session?.comparisons?.some(pair=>pair.available&&(pair.reference===index||pair.new===index))??false;
  function chooseReference(index:number){
    setPlaying(false);setReference(index);setPick(null);
    const choices=session?.comparisons?.filter(p=>p.available&&(p.reference===index||p.new===index)).sort((a,b)=>b.coverage-a.coverage)||[];
    const next=choices.find(p=>p.reference===current||p.new===current)||choices[0];
    if(next)setCurrent(next.reference===index?next.new:next.reference);
  }
  useEffect(()=>{if(session&&!session.comparisons){setSession(null);setRefresh(old=>old+1);}},[session]);
  useEffect(()=>{
    if(!session||matches.has(current)||!matches.size)return;
    setCurrent([...matches.entries()].sort((a,b)=>b[1]-a[1])[0][0]);setPlaying(false);
  },[session,matches,current]);
  useEffect(()=>{if(!playing||playableEpochs.length<2||!active)return;const timer=setInterval(()=>setCurrent(old=>playableEpochs[(playableEpochs.indexOf(old)+1)%playableEpochs.length]),1500/speed);return()=>clearInterval(timer);},[playing,playableEpochs,speed,active]);
  useEffect(()=>{
    subtraction.current?.abort();
    setAnalysis(null);setComparisonError('');setComparing(false);setPick(null);setPicking(false);pickRequest.current++;
    return()=>subtraction.current?.abort();
  },[session,reference,current,background,active,tab]);
  async function subtractImages(){
    if(!session||busy||comparing||!matches.has(current))return;
    setPlaying(false);
    subtraction.current?.abort();
    const controller=new AbortController();
    subtraction.current=controller;
    setAnalysis(null);setComparisonError('');setComparing(true);setPick(null);setPicking(false);pickRequest.current++;
    try{
      const result=await request<Analysis>('/analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session:session.id,reference,new:current,background}),signal:controller.signal});
      if(!controller.signal.aborted)setAnalysis(result);
    }catch(e){
      if(controller.signal.aborted)return;
      const message=e instanceof Error?e.message:'Could not subtract these observations.';
      if(message.startsWith('Workspace session expired.')){setHasLoaded(false);preparedRevision.current=-1;setSession(null);setRefresh(old=>old+1);}
      else setComparisonError(message);
    }finally{if(!controller.signal.aborted)setComparing(false);}
  }
  useEffect(()=>{
    setResiduals([]);setDetectionError('');setDetecting(false);
    if(!analysis||!active||tab!=='motion')return;
    const controller=new AbortController();setDetecting(true);
    request<CandidateResult>(`/analysis/${analysis.id}/candidates?threshold=${threshold}&min_pixels=3`,{signal:controller.signal})
      .then(result=>{if(!controller.signal.aborted){setResiduals(result.candidates);setMotionResult({key:`${analysis.id}/${threshold}`,pairs:result.motion_hypotheses});}}).catch(e=>{if(!controller.signal.aborted){if(e.message.startsWith('Analysis expired.')){setHasLoaded(false);preparedRevision.current=-1;setSession(null);setRefresh(old=>old+1);}else setDetectionError(e.message);}})
      .finally(()=>{if(!controller.signal.aborted)setDetecting(false);});
    return()=>controller.abort();
  },[analysis,threshold,active,tab]);
  const [fingerprintTarget,setFingerprintTarget]=useState<(FingerprintTarget & {analysisId:string;threshold:number;markerId:number;position:CatalogPosition})|null>(null);
  const selectedFingerprint=fingerprintTarget?.analysisId===analysis?.id&&fingerprintTarget?.threshold===threshold?fingerprintTarget:null;
  const [showFingerprint,setShowFingerprint]=useState(false);
  async function inspect(x:number,y:number,which:'reference'|'current'|'difference'|'native',marker?:Residual,nativeFrame?:SkyFrame){
    if(!session&&which!=='native')return;
    setShowFingerprint(false);
    setFingerprintTarget(marker&&analysis?{label:`Residual #${marker.id} · ${marker.sign} · ${marker.ra_deg.toFixed(5)}°, ${marker.dec_deg.toFixed(5)}°`,path:`/analysis/${analysis.id}/fingerprint?candidate_id=${marker.id}&threshold=${threshold}&min_pixels=3`,analysisId:analysis.id,threshold,markerId:marker.id,position:{ra:marker.ra_deg,dec:marker.dec_deg}}:null);
    if(marker&&analysis)requestAnimationFrame(()=>document.getElementById('simple-nearby-objects')?.scrollIntoView({block:'nearest'}));
    const version=++pickRequest.current;setPlaying(false);setPicking(true);
    try{
      let p:Pick;
      if(nativeFrame){
        const pixel=await request<Pick>(`/observations/${nativeFrame.id}/pixel?x=${x}&y=${y}`);
        p={...pixel,valid:pixel.brightness!=null};
      }
      else if(which==='native'&&observation){const result=await request<{ra_deg:number;dec_deg:number;brightness:number|null;variance:number|null;wavelength_um:number|null;flags:number;x:number;y:number}>(`/observations/${observation.id}/pixel?x=${x}&y=${y}`);p={...result,valid:result.brightness!=null,unit:observation.extensions.find(e=>e.name==='IMAGE')?.unit,uncertainty_unit:observation.extensions.find(e=>e.name==='VARIANCE')?.unit?`√(${observation.extensions.find(e=>e.name==='VARIANCE')?.unit})`:'unit unspecified'};}
      else if(which==='difference'&&analysis){
        p=await request<Pick>(`/analysis/${analysis.id}/pixel?x=${x}&y=${y}`);
        if(marker){
          p.pattern=marker.pattern;
          if(version===pickRequest.current)setPick(p);
          try{p={...p,...await request<{patches:OriginalPatch[]}>(`/analysis/${analysis.id}/original-patches?x=${x}&y=${y}`)};}
          catch{p={...p,patchError:'Original patches could not be loaded. Click the marker to retry.'};}
        }
      }
      else {
        const frame=await request<Pick>(`/workspace/sessions/${session!.id}/pixel?index=${which==='reference'?reference:current}&x=${x}&y=${y}`);
        if(analysis){
          const matched=await request<Pick&{reference:number|null;new:number|null;reference_variance:number|null;new_variance:number|null}>(`/analysis/${analysis.id}/pixel?x=${x}&y=${y}`);
          p={...frame,valid:matched.valid,exclusion_reason:matched.exclusion_reason,brightness:which==='reference'?matched.reference:matched.new,variance:which==='reference'?matched.reference_variance:matched.new_variance};
        }else p=frame;
      }
      if(version===pickRequest.current)setPick(p);
    }catch(e){if(version===pickRequest.current)setError(e instanceof Error?e.message:'Could not inspect this pixel.');}finally{if(version===pickRequest.current)setPicking(false);}
  }
  async function upload(file?:File){
    if(!file)return;if(!/\.(fits|fit|fts)$/i.test(file.name)||file.size>256*1024*1024){setError('Choose an uncompressed FITS file up to 256 MiB.');return;}
    setBusy(true);setError('');setPlaying(false);
    try{const body=new FormData();body.append('file',file);const obs=await request<Observation>('/observations',{method:'POST',body});localStorage.setItem('spherex-observation',obs.id);setHasLoaded(false);setSession(null);setRa('');setDec('');setRefresh(old=>old+1);window.dispatchEvent(new CustomEvent('spherex-observation-changed',{detail:obs}));}
    catch(e){setError(e instanceof Error?e.message:'Could not load this FITS file.');setBusy(false);}finally{if(input.current)input.current.value='';}
  }
  const motionKey=`${analysis?.id}/${threshold}`;
  const motionPairs=useMemo(()=>motionResult?.key===motionKey
    ?selectMotionPairs(residuals,motionResult.pairs,analysis?.psf_target_arcsec??0):[],
    [residuals,motionResult,motionKey,analysis?.psf_target_arcsec]);
  const motionMode=changeView==='motion';
  const motionPair=(motionSelection?.key===motionKey?motionPairs.slice(0,3).find(pair=>pair.key===motionSelection.pair):undefined)??motionPairs[0];
  const visibleResiduals=showAllChanges?residuals:residuals.slice(0,5);
  const changeCount=`${visibleResiduals.length} of ${residuals.length} matches shown`;
  useEffect(()=>{setCamera(HOME_CAMERA);},[session?.id]);
  const a=session?.frames[reference];const b=session?.frames[current];
  const headerLabel=session?`${epochs.length} real observation dates`:'Your window into the infrared sky';
  const inspector=<section className="simple-panel simple-inspector" hidden={!pick&&!picking}><div className="simple-panel-heading"><Crosshair size={16}/><h2>Pixel inspector</h2>{picking&&<LoaderCircle size={14} className="spin"/>}</div><p>Click an image to read a pixel. Marker details use the strongest pixel in the residual.</p>{pick?<><div className="simple-pick-position"><span>SKY POSITION / ICRS</span><strong>{number(pick.ra_deg,5)}°, {number(pick.dec_deg,5)}°</strong></div>{!pick.valid&&<p>{pick.exclusion_reason?`Excluded: ${pick.exclusion_reason}.`:"No valid measurement at this pixel."}</p>}<dl>{pick.brightness!==undefined&&<div><dt>Brightness</dt><dd>{number(pick.brightness)} <small>{pick.unit??'MJy/sr'}</small></dd></div>}<div><dt>Pixel uncertainty</dt><dd>{number(pick.variance!=null&&pick.variance>=0?Math.sqrt(pick.variance):null)} <small>{pick.uncertainty_unit??'MJy/sr'}</small></dd></div>{pick.wavelength_um!==undefined&&<div><dt>Wavelength</dt><dd>{number(pick.wavelength_um,4)} <small>µm</small></dd></div>}{pick.difference!==undefined&&<div><dt>Change</dt><dd>{number(pick.difference)} <small>MJy/sr</small></dd></div>}{pick.significance!==undefined&&<div><dt>Approx. significance</dt><dd>{number(pick.significance,2)} <small>σ</small></dd></div>}</dl>{pick.pattern&&<p><strong>{pick.pattern==='opposite-sign neighbor'?'Possible movement pattern':'Single residual pattern'}</strong> — {pick.pattern==='opposite-sign neighbor'?'A nearby residual has the opposite sign. Motion is one possible explanation; alignment and PSF errors can create the same pattern.':'Brightness variation, noise, or a processing artifact could explain it. This is not evidence of motion by itself.'}</p>}{pick.patchError&&<p>{pick.patchError}</p>}{pick.patches&&<div className="original-patches">{pick.patches.map(patch=><figure key={patch.label}><figcaption><strong>{patch.label} · Original detector patch</strong><small>{patch.filename}</small></figcaption>{patch.png?<><div className="original-patch-image"><img src={`data:image/png;base64,${patch.png}`} alt={`Original FITS patch ${patch.label}`}/><i style={{left:`${(patch.point_x??.5)*100}%`,top:`${(patch.point_y??.5)*100}%`}}/></div><p>FITS pixel {patch.x}, {patch.y} · {number(patch.wave,4)} µm · bandwidth {number(patch.band,4)} µm</p><p>FLAGS: {patch.flags??'unavailable'}{patch.bits?.length?` (${patch.bits.join(', ')})`:''}</p></>:<p>{patch.error}</p>}</figure>)}<p>Native detector crops with a shared display stretch. The ring marks the nearest detector pixel; FLAGS are from that original pixel.</p></div>}</>:<div className="simple-pick-empty"><Crosshair size={30} strokeWidth={1}/><strong>A closer look starts with a click.</strong><span>Brightness, wavelength, and uncertainty.</span></div>}<p className="simple-pick-foot">Uncertainty comes from the file’s variance. A bright pixel is not a confirmed source.</p></section>;
  return <div className="simple-app streamlined">
    <nav className="simple-tabs" aria-label="Simple explorer sections"><button aria-pressed={tab==='motion'} onClick={()=>{setTab('motion');setPlaying(false);setPick(null);}}><Telescope size={16}/>Motion Explorer</button><button aria-pressed={tab==='wavelength'} onClick={()=>{setTab('wavelength');setPlaying(false);setPick(null);}}><Waves size={16}/>Wavelength Explorer</button><button type="button" aria-pressed={tab==='downloads'} onClick={()=>{setTab('downloads');setPlaying(false);}}><ArrowRight size={14}/>Downloads</button><a href="#simple-guide">How it works <ArrowRight size={12}/></a></nav>
    <main className="simple-main">
    <div hidden={tab!=='downloads'}><SimpleDownloads onOpen={(obs,center)=>{
      localStorage.setItem('spherex-observation',obs.id);setObservation(obs);
      setRa(String(center.ra));setDec(String(center.dec));setHasLoaded(false);
      setRefresh(old=>old+1);setTab('motion');
    }}/></div>
    <div hidden={tab==='downloads'}><section className="simple-intro"><div><span className="eyebrow">A SMALL WINDOW INTO A VERY BIG UNIVERSE</span><h1>{tab==='motion'?<>One sky. <span>Two moments.</span></>:<>Beyond visible light.<br/><span>Explore the infrared.</span></>}</h1><p>{tab==='motion'?'View both observations, then subtract them to see what changed.':'Move through measured wavelengths. See where the detector is sensitive.'}</p></div><div className="simple-intro-note"><Telescope size={25} strokeWidth={1}/><span>{headerLabel}<small>NASA / IPAC IRSA · SPHEREx</small></span></div></section>
    {error&&<div className="error-banner" role="alert"><Info size={17}/><span>{error}</span><button onClick={()=>setRefresh(old=>old+1)} disabled={busy}><RefreshCw size={14}/> Retry</button></div>}
    {busy&&<div className="loading-banner" role="status"><LoaderCircle className="spin" size={17}/>Preparing your real sky images and aligning their coordinates…</div>}
    <div className="simple-layout"><section className="simple-workspace"><div className="simple-workspace-title"><span><i className="status-dot"/>{tab==='motion'?'OBSERVATION WORKSPACE':'WAVELENGTH WORKSPACE'}</span><small>{tab==='motion'?'SAME SKY · REAL DATES':'NATIVE DETECTOR · REAL CALIBRATION'}</small></div>
    {tab==='motion'?<>
      {(analysis||comparing||comparisonError)&&<section className="simple-difference"><div className="simple-difference-heading"><div><span className="simple-section-label"><ScanLine size={15}/>THE DIFFERENCE</span><h2>What changed?</h2></div>{analysis&&<div className="simple-segmented" role="group" aria-label="Change type"><button type="button" aria-pressed={!motionMode} onClick={()=>setChangeView('brightness')}>Brightness changes</button><button type="button" aria-pressed={motionMode} onClick={()=>setChangeView('motion')}>Possible motion</button></div>}<div className="simple-segmented" role="group" aria-label="Difference display"><button aria-pressed={differenceMode==='difference'} onClick={()=>setDifferenceMode('difference')}>Difference</button><button aria-pressed={differenceMode==='significance'} onClick={()=>setDifferenceMode('significance')}>Significance</button></div></div><div className="simple-difference-body"><SkyImage src={analysis?`${endpoints}/analysis/${analysis.id}/image?kind=${differenceMode}`:null} markers={motionMode?(motionPair?[motionPair.from,motionPair.to]:[]):showDifferenceMarkers?visibleResiduals:[]}
        overlay={motionMode&&motionPair?<MotionArrow pair={motionPair} size={session?.grid.size??96}/>:undefined} onMarkerPick={(x,y,marker)=>void inspect(x,y,'difference',marker)} gridSize={session?.grid.size} label={differenceMode==='difference'?'Signed difference image':'Approximate significance image'} onPick={(x,y)=>void inspect(x,y,'difference')} unavailable={!comparing&&!busy&&!analysis?(comparisonError||'Load observations to make a comparison.'):undefined}/><div className="simple-explainer"><span className="simple-equation"><b>B</b> − A = {differenceMode==='difference'?'change':'change / uncertainty'}</span>{!motionMode&&<label className="difference-marker-toggle"><input type="checkbox" checked={showDifferenceMarkers} onChange={e=>setShowDifferenceMarkers(e.target.checked)}/> Show change markers</label>}<h3>{comparisonError?'A matching observation is needed.':differenceMode==='significance'?'How much does it stand out?':'Red: brighter. Blue: fainter.'}</h3><p>{comparisonError?'Only dates with compatible wavelengths, usable pixels, and PSF metadata are enabled. Find more real observations to add coverage; no measurements are invented.':differenceMode==='significance'?'This map compares the change to the estimated pixel noise. It is an approximate significance, not proof of a new object.':'Each marker is a group of pixels that changed. Select a number to look up nearby objects and inspect the original FITS patches.'}</p><div className="simple-residual-key"><span><i className="positive"/>Positive<small>brighter in B</small></span><span><i className="negative"/>Negative<small>fainter in B</small></span><span><i className="missing"/>Transparent<small>no valid overlap</small></span></div>{analysis&&<span className="simple-processed">{number(analysis.overlap_fraction*100,1)}% comparable sky · WCS aligned · {analysis.zodi_subtracted?'ZODI subtracted':'ZODI off'}{differenceMode==='significance'?' · display ±5σ':' · MJy/sr'}</span>}{analysis&&motionMode&&<PossibleMotion pairs={motionPairs} selected={motionPair} loading={detecting} failed={!!detectionError}
        onSelect={pair=>{setMotionSelection({key:motionKey,pair});setFingerprintTarget(null);setShowFingerprint(false);setPick(null);setPicking(false);pickRequest.current++;}}/>}
      {analysis&&<div className="simple-nearby" id="simple-nearby-objects">
        {selectedFingerprint&&active&&tab==='motion'&&<NearbyObjects position={selectedFingerprint.position}/>}
        {!motionMode&&<div className="simple-object-picker">
          <strong>Look up an object</strong>
          <p>{detecting?'Finding changes…':detectionError?'Change markers could not be loaded.':visibleResiduals.length?'Click a number on the image or choose one here.':'No numbered changes at this threshold. Try a lower threshold under Highlighted changes.'}</p>
          {!!visibleResiduals.length&&<div className="simple-object-buttons" aria-label="Choose a change to look up">
            {visibleResiduals.map(marker=><button type="button" key={marker.id} className="secondary-button"
              aria-pressed={selectedFingerprint?.markerId===marker.id}
              onClick={()=>void inspect(marker.peak_x??Math.round(marker.x),marker.peak_y??Math.round(marker.y),'difference',marker)}>#{marker.id}</button>)}
          </div>}
        </div>}
      </div>}</div></div></section>}
      {inspector}
      {selectedFingerprint&&<div className="simple-fingerprint">
        <button className="secondary-button" aria-expanded={showFingerprint} onClick={()=>setShowFingerprint(value=>!value)}><Waves size={15}/>{showFingerprint?'Hide spectral fingerprint':'View spectral fingerprint'}</button>
        {showFingerprint&&active&&tab==='motion'&&<SpectralFingerprint target={selectedFingerprint}/>}
      </div>}
      {analysis&&<details className="comparison-options comparison-trust"><summary>Comparison checks <ChevronDown size={14}/></summary><ul>{analysis.checks?.map(check=><li key={check.label}><strong>{check.label}</strong> — {check.detail}</li>)}</ul></details>}
      <div className="compare-toolbar"><div><strong>{comparisonView==='side-by-side'?'Side by side':'Before & after'}</strong><span>{analysis?`${number(analysis.overlap_fraction*100,0)}% comparable sky · ${analysis.zodi_subtracted?'ZODI removed':'ZODI off'}`:busy||comparing?'Preparing your comparison…':'Real observations · same sky'}</span></div><button className="icon-button" aria-label="Find another comparison" disabled={busy||comparing} onClick={()=>{setBackground(true);setRefresh(old=>old+1);}} title="Find a compatible pair"><RefreshCw size={16}/></button></div>
      <div className="comparison-view-controls">
        <button className="primary-button" type="button" disabled={busy||comparing||!matches.has(current)} onClick={()=>void subtractImages()}><ScanLine size={16}/>{comparing?'Subtracting…':'Subtract images'}</button>
        <span className="simple-matching-note">{analysis?'Same sky area and scale · shared comparison mask.':'Same sky area and scale in both images.'} {session&&!matches.has(current)&&'This pair cannot be subtracted.'}</span>
      </div>
      <div className="comparison-view-controls"><div className="simple-segmented" role="group" aria-label="Comparison layout"><button aria-pressed={comparisonView==='side-by-side'} onClick={()=>setComparisonView('side-by-side')}>Side by side</button><button aria-pressed={comparisonView==='swipe'} onClick={()=>setComparisonView('swipe')}>Before / after</button></div><label className="simple-check"><input type="checkbox" checked={markOnImages} onChange={e=>setMarkOnImages(e.target.checked)}/>Mark changes on images</label></div>
      {session&&<div className="comparison-view-controls linked-zoom-controls" role="group" aria-label="Linked sky zoom">
        <div className="simple-segmented">
          <button aria-label="Zoom out both images" disabled={camera.zoom<=1} onClick={()=>setCamera(old=>zoomSky(old,1/1.5))}>−</button>
          <button aria-label="Reset zoom and pan" onClick={()=>setCamera(HOME_CAMERA)}>{number(camera.zoom,2)}× · Reset</button>
          <button aria-label="Zoom in both images" disabled={camera.zoom>=8} onClick={()=>setCamera(old=>zoomSky(old,1.5))}>+</button>
        </div>
        <small>Pinch or Ctrl + scroll to zoom. Drag when zoomed. Both images stay aligned.</small>
      </div>}
      {analysis&&analysis.overlap_fraction<1&&<div className="comparison-mask-notice" role="note" aria-label="About checkerboard gaps">
        <Info size={16} aria-hidden="true"/>
        <div><p><strong>Why these gaps appear:</strong> {number((1-analysis.overlap_fraction)*100,1)}% of this view was excluded from both images.</p>
        {!!analysis.exclusions?.length&&<ul>{analysis.exclusions.map(({reason,pixels})=><li key={reason}>{reason}: {pixels.toLocaleString()} pixels</li>)}</ul>}
        <p>Click a checkerboard spot to see its reason in the pixel inspector.</p></div>
      </div>}
      {comparisonView==='side-by-side'?<div className="simple-observations">{(['reference','current'] as const).map((which,i)=>{const frame=which==='reference'?a:b;return <article className="simple-observation" key={which}><div className="simple-image-heading"><span><i className={i?'frame-letter warm':'frame-letter'}>{i?'B':'A'}</i>{i?'Current observation':'Reference observation'}</span></div><LinkedSkyViewport camera={camera} setCamera={setCamera}><SkyPlane camera={camera}><SkyImage
        src={analysis?`${endpoints}/analysis/${analysis.id}/image?kind=${i?'new':'reference'}`:session?`${endpoints}/workspace/sessions/${session.id}/frames/${i?current:reference}`:null}
        label={i?'Current sky observation':'Reference sky observation'}
        markers={markOnImages?visibleResiduals:[]} gridSize={session?.grid.size}
        onMarkerPick={(x,y,marker)=>void inspect(x,y,'difference',marker)}
        onPick={(x,y)=>void inspect(x,y,which)}
      /></SkyPlane></LinkedSkyViewport><div className="simple-image-caption"><span>{date(frame?.timestamp??null)}</span><small>{number(frame?.wavelength_min_um,3)}–{number(frame?.wavelength_max_um,3)} µm</small></div></article>;})}</div>:<section className="swipe-comparison" aria-label="Before and after comparison">
        <div className="swipe-images" ref={swipe}><LinkedSkyViewport camera={camera} setCamera={setCamera}>
          <SkyPlane camera={camera}><SkyImage src={analysis?`${endpoints}/analysis/${analysis.id}/image?kind=new`:session?`${endpoints}/workspace/sessions/${session.id}/frames/${current}`:null} label="Current sky observation" onPick={(x,y)=>void inspect(x,y,'current')}/></SkyPlane>
          <div className="swipe-before" style={{clipPath:`inset(0 ${100-reveal}% 0 0)`}}><SkyPlane camera={camera}><SkyImage src={analysis?`${endpoints}/analysis/${analysis.id}/image?kind=reference`:session?`${endpoints}/workspace/sessions/${session.id}/frames/${reference}`:null} label="Reference sky observation" onPick={(x,y)=>void inspect(x,y,'reference')}/></SkyPlane></div>
          <span className="swipe-date before">A · {date(a?.timestamp??null)}</span><span className="swipe-date after">B · {date(b?.timestamp??null)}</span>
          {markOnImages&&analysis&&<div className="comparison-markers"><SkyPlane camera={camera}><ChangeMarkers markers={visibleResiduals} size={session?.grid.size??96} onPick={(x,y,marker)=>void inspect(x,y,'difference',marker)}/></SkyPlane></div>}
          <div className="swipe-divider" style={{left:`${reveal}%`}}><button type="button" aria-label="Drag image comparison divider" onPointerDown={e=>{e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId)||!swipe.current)return;const bounds=swipe.current.getBoundingClientRect();setReveal(Math.max(0,Math.min(100,Math.round((e.clientX-bounds.left)/bounds.width*100))));}} onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}} onKeyDown={e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();setReveal(old=>e.key==='Home'?0:e.key==='End'?100:Math.max(0,Math.min(100,old+(e.key==='ArrowRight'?5:-5))));}}><ArrowLeft size={12}/><ArrowRight size={12}/></button></div>
        </LinkedSkyViewport></div>
        <div className="swipe-control"><label htmlFor="before-after-slider">Before</label><input id="before-after-slider" aria-label="Before and after slider" type="range" min="0" max="100" step="1" value={reveal} disabled={!session||busy} aria-valuetext={`${reveal}% reference image, ${100-reveal}% current image`} onChange={e=>setReveal(Number(e.target.value))}/><label htmlFor="before-after-slider">After</label></div>
        <p className="swipe-hint">Slide to reveal each date. Click the sky to inspect a pixel.</p>
      </section>}
      <section className="current-date-control" aria-label="Current observation control"><div><label htmlFor="current-observation-slider">Current observation</label><strong>{date(b?.timestamp??null)}</strong></div><div className="date-slider-row"><button className="icon-button" aria-label="Earlier current observation" disabled={busy||playableEpochs.length<2||playableEpochs.indexOf(current)<=0} onClick={()=>{setPlaying(false);setCurrent(playableEpochs[playableEpochs.indexOf(current)-1]);}}><ArrowLeft size={15}/></button><input id="current-observation-slider" type="range" aria-label="Current observation slider" min="0" max={Math.max(1,playableEpochs.length-1)} step="1" value={Math.max(0,playableEpochs.indexOf(current))} disabled={busy||playableEpochs.length<2} aria-valuetext={date(b?.timestamp??null)} onChange={e=>{const index=playableEpochs[Number(e.target.value)];if(index===undefined)return;setCurrent(index);setPlaying(false);setPick(null);}}/><button className="icon-button" aria-label="Later current observation" disabled={busy||playableEpochs.length<2||playableEpochs.indexOf(current)>=playableEpochs.length-1} onClick={()=>{setPlaying(false);setCurrent(playableEpochs[playableEpochs.indexOf(current)+1]);}}><ArrowRight size={15}/></button></div><p>{playableEpochs.length>1?`${playableEpochs.length} compatible dates · reference stays fixed`:playableEpochs.length===1?'One compatible date for this reference. Choose a different reference in More options for other pairs.':'Finding compatible dates…'}</p>{markOnImages&&<p className="inline-change-key">{detecting?'Finding changes…':`${changeCount} · red = brighter · blue = fainter · click a marker`}{detectionError&&` · ${detectionError}`}</p>}</section>
      {a&&b&&<details className="comparison-options" onToggle={e=>setShowOriginals(e.currentTarget.open)}>
        <summary>Original FITS coverage <ChevronDown size={14}/></summary>
        <p className="lab-note">A cutout stores only part of a detector frame, so it can cover less sky. Pinch, Ctrl + scroll, or use + / − on either original; drag while zoomed. Original views zoom independently because their detector grids differ.</p>
        {showOriginals&&<div className="simple-observations">{([a,b] as const).map((frame,i)=>
          <OriginalSkyView key={`${i}:${frame.id}`} frame={frame} label={i?'Current original':'Reference original'}
            onPick={(x,y)=>void inspect(x,y,i?'current':'reference',undefined,frame)}/>
        )}</div>}
      </details>}
      <details className="residual-results" aria-label="Significant differences"><summary>{detecting?'Checking changes…':`Highlighted changes (${changeCount})`} <ChevronDown size={14}/></summary><div className="auto-pipeline-heading"><div><strong>{detecting?'Checking significance…':changeCount}</strong><p>At least 3 connected pixels above ±{threshold}σ. Approximate significance; unverified residuals.</p>{residuals.length>5&&<label className="simple-check"><input type="checkbox" checked={showAllChanges} onChange={e=>setShowAllChanges(e.target.checked)}/> Show all matches</label>}</div><label>Threshold<select aria-label="Residual significance threshold" value={threshold} onChange={e=>setThreshold(Number(e.target.value))}>{[3,5,7,10].map(n=><option key={n} value={n}>{n}σ</option>)}</select></label></div>{detectionError&&<p role="alert">{detectionError}</p>}{analysis&&!detecting&&!detectionError&&!residuals.length&&<p>No residual regions pass this threshold in the compatible overlap.</p>}<div className="residual-list">{visibleResiduals.map(r=><button key={r.id} onClick={()=>void inspect(r.peak_x??Math.round(r.x),r.peak_y??Math.round(r.y),'difference',r)}><i className={r.sign}/><strong>#{r.id} {r.sign}</strong><span>{number(r.peak_sigma,1)}σ · {r.pixels} pixels{r.edge?' · edge':''}</span><small>{number(r.ra_deg,5)}°, {number(r.dec_deg,5)}°</small></button>)}</div></details>
      <details className="comparison-options"><summary>Dates & playback <ChevronDown size={14}/></summary>      <div className="simple-timeline"><div className="simple-section-label"><span>OBSERVATION TIMELINE</span><small>{playableEpochs.length} MATCHING / {epochs.length} DATES</small></div><div className="simple-playback"><button className="simple-play" aria-label={playing?'Pause animation':'Play animation'} disabled={busy||playableEpochs.length<2} onClick={()=>setPlaying(!playing)}>{playing?<Pause size={17}/>:<Play size={17}/>}</button><button className="icon-button" aria-label="Previous date" disabled={playableEpochs.length<2||busy} onClick={()=>{setPlaying(false);setCurrent(playableEpochs[(playableEpochs.indexOf(current)-1+playableEpochs.length)%playableEpochs.length]);}}><ArrowLeft size={15}/></button><div className="simple-epochs">{epochs.map((index,i)=><button key={session!.frames[index].id} aria-pressed={index===current} aria-label={`Select observation ${i+1}`} disabled={!matches.has(index)||busy} title={index===reference?'Reference baseline':matches.has(index)?`${number(matches.get(index)!*100,1)}% compatible sky overlap`:'Not comparable with this reference; wavelength, quality, or PSF overlap is unavailable.'} onClick={()=>{setCurrent(index);setPlaying(false);}}><i/><strong>{index===reference?'REF':String(i+1).padStart(2,'0')}</strong><small>{date(session!.frames[index].timestamp)}</small></button>)}</div><button className="icon-button" aria-label="Next date" disabled={playableEpochs.length<2||busy} onClick={()=>{setPlaying(false);setCurrent(playableEpochs[(playableEpochs.indexOf(current)+1)%playableEpochs.length]);}}><ArrowRight size={15}/></button></div>{!busy&&<p className="simple-matching-note">{playableEpochs.length===0?'No matching dates are loaded for this reference. Add another real observation.':playableEpochs.length===1?'One matching date is available. Playback needs at least two matching dates.':'Playback uses matching dates only.'} Dimmed dates cannot be subtracted from this reference.</p>}</div>
</details>
      {session&&<details className="comparison-options comparison-provenance"><summary>Observation sources · {epochs.length} epochs <ChevronDown size={14}/></summary><ul>{session.frames.map((frame,i)=><li key={frame.id}><strong>{i===reference?'A · ':i===current?'B · ':''}{frame.timestamp??'Date unavailable'}{frame.time_system?` (${frame.time_system.value})`:''}</strong><br/>{frame.observation?.value&&<>FITS observation ID: {frame.observation.value}<br/></>}<a href={frame.source_url} target="_blank" rel="noreferrer">{frame.filename} <ExternalLink size={11}/></a><br/>Wavelength over usable sky grid: {number(frame.wavelength_min_um,4)}–{number(frame.wavelength_max_um,4)} µm<br/><small>Local file SHA-256: {frame.id}<br/>{frame.provenance}</small></li>)}</ul></details>}
      <details className="auto-pipeline" aria-label="Automatic comparison pipeline"><summary>How these images are processed <ChevronDown size={14}/></summary><div className="auto-pipeline-heading"><div><strong>Find changes in the same sky</strong><p>{session?.selection?`Library: ${session.selection.library_count} images · ${session.selection.checked} checked · ${session.frames.length} loaded`:'Find a real pair and compare it automatically.'}</p></div><button className="secondary-button" disabled={busy||comparing} onClick={()=>{setBackground(true);setRefresh(old=>old+1);}}><RefreshCw size={14}/>{busy?'Finding a pair…':'Find & compare automatically'}</button></div><ol>{[
        ['Two different dates',Boolean(a&&b&&a.timestamp!==b.timestamp)],
        ['Compatible wavelengths',Boolean(analysis)],
        ['Aligned with WCS',Boolean(session)],
        ['Brightness & sharpness matched',Boolean(analysis&&background)],
        ['Subtract & highlight',Boolean(analysis&&!detecting&&!detectionError)],
      ].map(([label,done],i)=><li key={String(label)} data-complete={done}>{done?<Check size={14}/>:<span>{i+1}</span>}{label}</li>)}</ol>{analysis&&<p className="auto-pipeline-evidence">{analysis.valid_pixels.toLocaleString()} comparable pixels · {number(analysis.overlap_fraction*100,1)}% overlap · PSF {number(analysis.psf_target_arcsec,2)}″ · background correction {number(analysis.background_offset)} MJy/sr{!background?' (disabled)':''} · {analysis.zodi_subtracted?'IMAGE − ZODI':'ZODI subtraction off'}</p>}</details>
    </>:<div className="simple-wavelength"><div className="simple-wavelength-controls"><span>{number(wave,3)} <small>µm</small></span><input type="range" aria-label="Simple wavelength slider" min=".75" max="5" step=".005" value={wave} disabled={!observation} onChange={e=>{setWave(Number(e.target.value));setPick(null);}}/><div><small>0.75 µm</small><small>5.00 µm</small></div><p>Showing pixels measured between {number(wave-.025,3)} and {number(wave+.025,3)} µm. Empty areas have no measurement in this interval.</p></div><SkyImage src={observation?.spectral?`${endpoints}/observations/${observation.id}/wavelength-image?wavelength=${appliedWave}&width=.05`:null} label="Measured detector pixels at the selected wavelength" unavailable={observation&&!observation.spectral?'This file has no usable wavelength calibration. Open Complex to inspect its headers.':undefined} onPick={(x,y)=>void inspect(x,y,'native')}/><div className="simple-wavelength-note"><Info size={16}/><p>One exposure measures different wavelengths at different detector positions. It is not a complete sky photograph at every wavelength. Use Complex for a combined fixed-sky wavelength view.</p></div></div>}
    </section>
    {tab==='wavelength'&&inspector}
    <aside className="simple-sidebar"><details className="simple-panel simple-extra"><summary><SlidersHorizontal size={16}/>More options<ChevronDown size={14}/></summary><div className="simple-panel-heading"><h2>Comparison settings</h2><button className="icon-button" aria-label="Reload observations" disabled={busy} onClick={()=>setRefresh(old=>old+1)}><RefreshCw size={14}/></button></div><div className="simple-control-content">
      {tab==='motion'?<><label>Reference date<select aria-label="Simple reference date" value={reference} disabled={!session||busy||playing} onChange={e=>chooseReference(Number(e.target.value))}>{session?.frames.map((f,i)=><option key={f.id} value={i} disabled={!referenceAvailable(i)}>{date(f.timestamp)} · {i+1}{referenceAvailable(i)?'':' · no matching dates'}</option>)}</select></label><label>Current date<select aria-label="Simple current date" value={current} disabled={!session||busy||playing} onChange={e=>{setCurrent(Number(e.target.value));setPick(null);}}>{session?.frames.map((f,i)=><option key={f.id} value={i} disabled={!matches.has(i)}>{date(f.timestamp)} · {i+1}{i===reference?' · reference':matches.has(i)?' · matching':' · not comparable'}</option>)}</select></label><label>Playback speed<select aria-label="Simple playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value=".5">Slow</option><option value="1">Normal</option><option value="2">Fast</option></select></label><label className="simple-check"><input type="checkbox" checked={subtractZodi} disabled={busy} onChange={e=>{setSubtractZodi(e.target.checked);setPlaying(false);setSession(null);setAnalysis(null);setResiduals([]);setRefresh(old=>old+1);}}/>Subtract zodiacal light (ZODI)</label><p className="simple-control-note">Subtracts each observation’s modeled foreground before alignment. Model uncertainty is excluded from significance.</p><label className="simple-check"><input type="checkbox" checked={background} onChange={e=>setBackground(e.target.checked)}/>Match background levels</label><p className="simple-control-note">Removes the remaining median brightness offset over compatible pixels. Sharpness is matched using the FITS PSF widths.</p><div className="simple-alignment"><Focus size={16}/><div><strong>{session?'Sky alignment applied':'Sky alignment automatic'}</strong><small>{comparing?'Checking this pair…':analysis?'Wavelengths checked · PSF matched':'Real WCS coordinates · quality masks'}</small></div>{session&&<Check size={15}/>}</div></>:<><div className="simple-calibration"><Waves size={20}/><strong>{number(observation?.spectral?.min_um,3)}–{number(observation?.spectral?.max_um,3)} µm</strong><span>Actual range in this observation</span></div><p className="simple-control-note">The wavelength slider selects real detector pixels. A single observation cannot provide a full source spectrum.</p></>}
      <details className="simple-position"><summary>Change sky position <ChevronDown size={13}/></summary><form onSubmit={e=>{e.preventDefault();setRefresh(old=>old+1);}}><label>RA / degrees<input type="number" min="0" max="359.99999999" step="any" value={ra} onChange={e=>setRa(e.target.value)} required/></label><label>Dec / degrees<input type="number" min="-90" max="90" step="any" value={dec} onChange={e=>setDec(e.target.value)} required/></label><button className="secondary-button" disabled={busy}>Update sky region</button></form></details>
      <input className="sr-only" ref={input} aria-label="Simple FITS upload" type="file" accept=".fits,.fit,.fts" onChange={e=>void upload(e.target.files?.[0])}/><button className="secondary-button simple-upload" disabled={busy} onClick={()=>input.current?.click()}><Upload size={14}/>Load FITS file</button><button className="text-link simple-more" onClick={()=>{setTab('downloads');setPlaying(false);}}>Open Downloads <ArrowRight size={13}/></button>
    </div></details>
    <div className="simple-complex-link"><ScanLine size={20}/><h3>Ready to go deeper?</h3><p>Inspect headers, search the archive, and investigate candidate residuals.</p><button className="text-link" onClick={()=>onComplex('investigate')}>Open Complex view <ArrowRight size={13}/></button></div></aside></div>
    <details className="simple-guide-wrapper" id="simple-guide"><summary>How it works <ChevronDown size={14}/></summary><section className="simple-guide"><div><span className="eyebrow">THE FIELD GUIDE</span><h2>From pixels<br/>to possibility.</h2><p>The same ideas as the lab.<br/>This time, with real measurements.</p></div><div>{[
      ['01','Compare the same sky','The observations are aligned using their actual sky-coordinate calibration. Different telescope pointings do not become false object motion.'],
      ['02','Watch the wavelength','A source can look different at another infrared wavelength. Subtraction only includes pixels with compatible wavelengths and bandwidths.'],
      ['03','Read the red and blue','Red is a positive change; blue is a negative change. A moving source may leave both, but artifacts and variable sources can also make residuals.'],
      ['04','Understand the uncertainty','Significance uses propagated measurement variance. Resampling and approximate PSF matching leave correlated and systematic errors, so significance is exploratory.'],
      ['05','Keep the evidence in view','Every displayed observation comes from a real FITS file. Dates are preserved. Missing coverage remains missing, and no candidate is a confirmed new object.'],
    ].map(([n,title,text])=><details key={n}><summary><span>{n}</span><h3>{title}</h3><b>+</b></summary><p>{text}</p></details>)}</div></section>
    </details><footer className="simple-footer"><span><i className="status-dot"/>REAL DATA. REAL QUESTIONS.</span><a href={observation?.source_url||'https://irsa.ipac.caltech.edu/Missions/spherex.html'} target="_blank" rel="noreferrer">NASA / IPAC IRSA <ExternalLink size={12}/></a></footer>
    </div></main>
  </div>;
}
