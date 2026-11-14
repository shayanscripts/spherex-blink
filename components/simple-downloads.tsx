'use client';

import { useEffect, useRef, useState } from 'react';
import { Download } from 'lucide-react';
import { request } from '@/lib/api';
import { SAMPLE_CENTER, SAMPLE_FILES, streamCutout } from '@/lib/downloads';
import type { Observation } from '@/lib/types';

function formatBytes(bytes:number){
  const units=['B','KB','MB','GB'];
  let unit=0;
  while(bytes>=1000&&unit<units.length-1){bytes/=1000;unit++;}
  return `${bytes.toLocaleString(undefined,{maximumFractionDigits:unit===0?0:1})} ${units[unit]}`;
}

export default function SimpleDownloads({onOpen}:{onOpen:(observation:Observation,center:{ra:number;dec:number})=>void}){
  const [size,setSize]=useState('0.2');
  const [resolution,setResolution]=useState<'cutout'|'full'>('cutout');
  const [destination,setDestination]=useState('Checking backend…');
  const [stats,setStats]=useState<{total:number;checked:number;ready:number;bytes:number}|null>(null);
  useEffect(()=>{
    const controller=new AbortController();
    fetch('/api/download-destination',{signal:controller.signal,cache:'no-store'})
      .then(r=>{if(!r.ok)throw new Error();return r.json() as Promise<{destination:string}>;})
      .then(r=>setDestination(r.destination))
      .catch(()=>{if(!controller.signal.aborted)setDestination('Unknown backend');});
    return()=>controller.abort();
  },[]);
  const pixels=Math.round(Number(size)*3600/6.15);
  const fullFrame=resolution==='full';
  const [ra,setRa]=useState(String(SAMPLE_CENTER.ra));
  const [dec,setDec]=useState(String(SAMPLE_CENTER.dec));
  const [count,setCount]=useState('10');
  const [progress,setProgress]=useState('');
  const [status,setStatus]=useState('');
  const [failure,setFailure]=useState('');
  const [paused,setPaused]=useState(false);
  const [fileProgress,setFileProgress]=useState<{received:number;total:number|null}|null>(null);
  const batch=useRef<AbortController|null>(null);
  const pause=useRef(false);
  const wake=useRef<(()=>void)|null>(null);
  useEffect(()=>()=>{batch.current?.abort();wake.current?.();},[]);
  const [downloaded,setDownloaded]=useState<{observation:Observation;center:{ra:number;dec:number}}|null>(null);

  async function download(sample:boolean){
    if(batch.current)return;
    const controller=new AbortController();batch.current=controller;
    pause.current=false;setPaused(false);setFileProgress(null);
    setProgress(sample?'Preparing sample…':'Searching IRSA…');setStatus('');setFailure('');setDownloaded(null);setStats(null);
    const center=sample?SAMPLE_CENTER:{ra:Number(ra),dec:Number(dec)};
    try{
      if(fullFrame){
        const health=await request<{full_frame_downloads?:boolean}>('/health',{signal:controller.signal});
        if(!health.full_frame_downloads)throw new Error('This backend does not support full detector downloads yet. Update the backend or choose Cutout.');
      }
      let urls:readonly string[]=SAMPLE_FILES;
      if(!sample){
        if(!ra.trim()||!dec.trim()||!Number.isFinite(center.ra)||!Number.isFinite(center.dec)||center.ra<0||center.ra>=360||Math.abs(center.dec)>90)throw new Error('Enter valid RA and Dec in decimal degrees.');
        const wanted=Number(count);
        const collections=wanted>50?['spherex_dr1','spherex_qr3']:['spherex_dr1'];
        const searches=await Promise.allSettled(collections.map(collection=>{
          const params=new URLSearchParams({ra,dec,radius:'0.001',collection,limit:String(Math.max(200,wanted))});
          return request<{results:{url:string;obs_id?:string;detector?:string}[]}>(`/archive/search?${params}`,{signal:controller.signal});
        }));
        if(controller.signal.aborted)return;
        const exposures=new Map<string,string>();
        let foundCollections=0;
        for(const search of searches){
          if(search.status==='rejected')continue;
          foundCollections++;
          for(const row of search.value.results){
            const key=row.obs_id&&row.detector?`${row.obs_id}/${row.detector}`:row.url;
            if(!exposures.has(key))exposures.set(key,row.url);
          }
        }
        if(!foundCollections)throw new Error('IRSA search failed. Try again.');
        if(foundCollections<collections.length)setFailure('One archive collection could not be searched. Results may be incomplete.');
        urls=[...exposures.values()].slice(0,wanted);
      }
      if(!urls.length){setStatus('No observations found at this position.');return;}
      let ready=0,bytes=0;const failures:string[]=[];
      setStats({total:urls.length,checked:0,ready,bytes});
      for(const [index,url] of urls.entries()){
        if(pause.current&&!controller.signal.aborted){
          setProgress('Paused. Resume to download the next file.');
          await new Promise<void>(resolve=>{wake.current=resolve;});
        }
        if(controller.signal.aborted)break;
        setFileProgress({received:0,total:null});
        setProgress(`Downloading ${index+1} of ${urls.length}…`);
        try{
          const observation=await streamCutout({url,...center,size_deg:Number(size),full_frame:fullFrame},controller.signal,(received,total)=>setFileProgress({received,total}));
          if(ready===0)setDownloaded({observation,center});
          ready++;bytes+=observation.bytes??0;
        }catch(e){if(controller.signal.aborted)break;failures.push(e instanceof Error?e.message:'Download failed.');}
        setStats({total:urls.length,checked:index+1,ready,bytes});
      }
      setStatus(`${controller.signal.aborted?"Cancelled. ":""}${ready} of ${urls.length} FITS files ready in the observation library.${!sample&&urls.length<Number(count)?` Found ${urls.length} of ${count} requested.`:""}`);
      if(failures.length)setFailure(old=>[old,`${failures.length} downloads failed. ${failures[0]}`].filter(Boolean).join(" "));
    }catch(e){if(!controller.signal.aborted)setFailure(e instanceof Error?e.message:'Download failed.');}
    finally{
      batch.current=null;pause.current=false;wake.current=null;
      setProgress('');setPaused(false);setFileProgress(null);
    }
  }

  return <>
    <section className="simple-intro"><div><h1>Downloads</h1><p>Add real SPHEREx images to your library.</p></div></section>
    <section className="panel archive-panel">
      <p className="lab-note"><strong>Save destination: {destination}</strong> · FITS files are stored in the backend’s observation library.</p>
      <div className="archive-controls">
        <label>Image resolution<select value={resolution} disabled={!!progress} onChange={e=>setResolution(e.target.value==='full'?'full':'cutout')}>
          <option value="cutout">Native resolution · cutout</option><option value="full">Native resolution · full detector (2,040 × 2,040 px)</option>
        </select></label>
        <label>Cutout size<select value={size} disabled={!!progress||fullFrame} onChange={e=>setSize(e.target.value)}>
          <option value="0.05">3 arcmin</option><option value="0.1">6 arcmin</option><option value="0.2">12 arcmin</option><option value="0.5">30 arcmin</option><option value="1">60 arcmin</option>
        </select></label>
        <button className="primary-button" type="button" disabled={!!progress} onClick={()=>void download(true)}><Download size={15}/>Download sample</button>
      </div>
      <p className="lab-note">The sample includes two observations. {fullFrame?'Full detectors cover more sky at the same native sharpness. A typical file is about 70 MB.':`Approx. ${pixels} × ${pixels} native pixels per cutout; detector edges can reduce the size. FITS file size also includes calibration data.`}</p>
      <details className="comparison-options">
        <summary>Download a different sky region</summary>
        <form className="archive-controls" onSubmit={e=>{e.preventDefault();void download(false);}}>
          <label>RA (degrees)<input type="number" required min="0" max="359.99999999" step="any" value={ra} disabled={!!progress} onChange={e=>setRa(e.target.value)}/></label>
          <label>Dec (degrees)<input type="number" required min="-90" max="90" step="any" value={dec} disabled={!!progress} onChange={e=>setDec(e.target.value)}/></label>
          <label>Number of observations<select value={count} disabled={!!progress} onChange={e=>setCount(e.target.value)}>{[2,5,10,25,50,100,200,400,500].map(n=><option key={n}>{n}</option>)}</select></label>
          <button className="secondary-button" disabled={!!progress}><Download size={15}/>Download region</button>
        </form>
      </details>
      {progress&&<div className="archive-controls">
        <button type="button" className="secondary-button" disabled={paused} onClick={()=>{pause.current=true;setPaused(true);}}>Pause</button>
        <button type="button" className="secondary-button" disabled={!paused} onClick={()=>{pause.current=false;setPaused(false);wake.current?.();wake.current=null;}}>Resume</button>
        <button type="button" className="secondary-button" onClick={()=>{batch.current?.abort();wake.current?.();setStatus('Cancelled. Completed files stay in the library.');}}>Cancel</button>
        {paused&&!progress.startsWith('Paused')&&<p className="lab-note">Pausing after the current file.</p>}
      </div>}
      {fileProgress&&progress.startsWith('Downloading')&&<div className="lab-note">
        <progress aria-label="Current file bytes" max={fileProgress.total||undefined} value={fileProgress.total?Math.min(fileProgress.received,fileProgress.total):undefined} style={{width:'100%',accentColor:'var(--amber)'}}/>
        <p>Current file: {formatBytes(fileProgress.received)}{fileProgress.total?` / ${formatBytes(fileProgress.total)}`:' received · total size not reported'}</p>
      </div>}
      {(progress||status)&&<p className="lab-note" role="status">{progress||status}</p>}
      {stats&&<div className="lab-note">
        <progress aria-label="Files processed" max={stats.total} value={stats.checked} style={{width:'100%',accentColor:'var(--amber)'}}/>
        <p>{stats.checked} / {stats.total} processed · {stats.ready} ready · {formatBytes(stats.bytes)} in ready FITS files (includes cached files)</p>
        {!!progress&&stats.ready>0&&stats.checked<stats.total&&<p>Estimated batch size: {formatBytes(stats.bytes/stats.ready*stats.total)} based on files ready so far.</p>}
      </div>}
      {failure&&<p className="error-banner" role="alert">{failure}</p>}
      {downloaded&&!progress&&<div className="archive-controls"><button className="secondary-button" onClick={()=>onOpen(downloaded.observation,downloaded.center)}>Open in Motion Explorer</button></div>}
    </section>
  </>;
}
