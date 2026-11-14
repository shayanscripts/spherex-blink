export const SAMPLE_CENTER={ra:304.52129078,dec:39.07848168};
export const SAMPLE_FILES=[
  'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_1B/l2b-v27-2026-196/4/level2_2025W18_1B_0023_2D4_spx_l2b-v27-2026-196.fits',
  'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_2B/l2b-v27-2026-197/4/level2_2025W18_2B_0097_3D4_spx_l2b-v27-2026-197.fits',
];

type StreamEvent =
  | { type: 'progress'; received: number; total: number | null }
  | { type: 'complete'; observation: import('./types').Observation }
  | { type: 'cancelled' }
  | { type: 'error'; message: string };

export async function streamCutout(body: object, signal: AbortSignal, progress: (received:number,total:number|null)=>void){
  const response=await fetch('/api/science/archive/import-stream',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal,
  });
  if(response.status===404)throw new Error('Update the backend to enable live download progress.');
  if(!response.ok||!response.body){
    const error=await response.json().catch(()=>null);
    throw new Error(typeof error?.detail==='string'?error.detail:`Download failed (HTTP ${response.status}).`);
  }
  const reader=response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer='';
  try{
    for(;;){
      const {value,done}=await reader.read();
      if(done)break;
      buffer+=value;
      const lines=buffer.split('\n');buffer=lines.pop()??'';
      for(const line of lines){
        if(!line.trim())continue;
        const event=JSON.parse(line) as StreamEvent;
        if(event.type==='progress')progress(event.received,event.total);
        else if(event.type==='complete')return event.observation;
        else if(event.type==='error')throw new Error(event.message);
        else if(event.type==='cancelled')throw new DOMException('Download cancelled','AbortError');
      }
    }
    throw new Error('The download connection closed before the FITS file was ready.');
  }finally{await reader.cancel().catch(()=>{});reader.releaseLock();}
}
