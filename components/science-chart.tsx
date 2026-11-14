'use client';
import { useEffect, useRef } from 'react';
import type { Data, Layout } from 'plotly.js';
export default function ScienceChart({ data, xTitle, yTitle }: { data: Data[]; xTitle:string; yTitle:string }) {
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    let live=true;const element=ref.current;
    void import('plotly.js-basic-dist-min').then(module=>{
      if(!live||!element)return;
      const Plotly=module.default||module;
      const layout:Partial<Layout>={paper_bgcolor:'#12161c',plot_bgcolor:'#12161c',font:{color:'#8b95a3',family:'DM Sans Variable, sans-serif',size:11},margin:{t:20,r:25,b:55,l:65},xaxis:{title:{text:xTitle},gridcolor:'#252c35',zerolinecolor:'#626d7a'},yaxis:{title:{text:yTitle},gridcolor:'#252c35',zerolinecolor:'#626d7a'},showlegend:false,autosize:true};
      void Plotly.react(element,data,layout,{responsive:true,displaylogo:false});
    });
    return ()=>{live=false;if(element)void import('plotly.js-basic-dist-min').then(m=>(m.default||m).purge(element));};
  },[data,xTitle,yTitle]);
  return <div ref={ref} className="science-chart" aria-label={`${yTitle} versus ${xTitle}`} />;
}
