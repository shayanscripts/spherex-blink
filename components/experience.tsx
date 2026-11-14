'use client';
import { useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { Orbit, SlidersHorizontal, Sparkles } from 'lucide-react';
import SimpleExplorer from './simple-explorer';
import type { WorkspaceView } from '@/lib/types';
const Explorer=dynamic(()=>import('./explorer'),{ssr:false,loading:()=> <p className="lab-note">Opening the science workspace…</p>});
export default function Experience(){
  const [mode,setMode]=useState<'simple'|'complex'>('simple');
  const [visitedComplex,setVisitedComplex]=useState(false);
  const [destination,setDestination]=useState<WorkspaceView|undefined>();
  useEffect(()=>{if(localStorage.getItem('spherex-view-mode')==='complex'){setMode('complex');setVisitedComplex(true);}},[]);
  function changeMode(next:'simple'|'complex',target?:WorkspaceView){
    if(next==='complex'){setVisitedComplex(true);setDestination(target);}
    setMode(next);localStorage.setItem('spherex-view-mode',next);window.scrollTo({top:0});
  }
  return <div className={`experience ${mode}-experience`}>
    <header className="experience-header"><a className="experience-brand" href="/" aria-label="Sky Explorer home"><Orbit size={25} strokeWidth={1.3}/><span>sky motion <span>/ explorer</span></span></a><div className="experience-switch" role="group" aria-label="Workspace complexity"><button aria-pressed={mode==='simple'} onClick={()=>changeMode('simple')}><Sparkles size={14}/>Simple</button><button aria-pressed={mode==='complex'} onClick={()=>changeMode('complex')}><SlidersHorizontal size={14}/>Complex</button></div><span className="experience-source"><i className="status-dot"/>SPHEREx FITS EXPLORER</span></header>
    <div hidden={mode!=='simple'}><SimpleExplorer active={mode==='simple'} onComplex={target=>changeMode('complex',target)}/></div>
    {visitedComplex&&<div hidden={mode!=='complex'}><Explorer active={mode==='complex'} destination={destination}/></div>}
  </div>;
}
