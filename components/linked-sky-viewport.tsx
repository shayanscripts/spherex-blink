'use client';

import { useEffect, useRef, type Dispatch, type ReactNode, type SetStateAction } from 'react';

export type SkyCamera = { zoom: number; x: number; y: number };
type Point = { x: number; y: number };
export const HOME_CAMERA: SkyCamera = { zoom: 1, x: 0, y: 0 };

function clamp(camera: SkyCamera): SkyCamera {
  const edge = (camera.zoom - 1) / 2;
  return { zoom: camera.zoom, x: Math.max(-edge, Math.min(edge, camera.x)), y: Math.max(-edge, Math.min(edge, camera.y)) };
}

export function zoomSky(camera: SkyCamera, factor: number, from: Point = { x: 0, y: 0 }, to = from): SkyCamera {
  const zoom = Math.max(1, Math.min(8, camera.zoom * factor));
  const ratio = zoom / camera.zoom;
  return clamp({ zoom, x: to.x - (from.x - camera.x) * ratio, y: to.y - (from.y - camera.y) * ratio });
}

export function SkyPlane({camera,children}:{camera:SkyCamera;children:ReactNode}){
  return <div className="sky-camera-plane" style={{transform:`translate(${camera.x*100}%, ${camera.y*100}%) scale(${camera.zoom})`}}>{children}</div>;
}

export default function LinkedSkyViewport({camera,setCamera,children,aspectRatio}:{camera:SkyCamera;setCamera:Dispatch<SetStateAction<SkyCamera>>;children:ReactNode;aspectRatio?:number}){
  const viewport=useRef<HTMLDivElement>(null);
  const points=useRef(new Map<number,Point>());
  const dragged=useRef(false);
  function normalize(point:Point,rect:DOMRect){
    return {x:(point.x-rect.left)/rect.width-.5,y:(point.y-rect.top)/rect.height-.5};
  }
  useEffect(()=>{
    const element=viewport.current;
    if(!element)return;
    function wheel(event:WheelEvent){
      // Preserve page scrolling; trackpad pinch is exposed as Ctrl+wheel.
      if(!event.ctrlKey&&!event.metaKey)return;
      event.preventDefault();
      const anchor=normalize({x:event.clientX,y:event.clientY},element!.getBoundingClientRect());
      setCamera(old=>zoomSky(old,Math.exp(-event.deltaY*.012),anchor));
    }
    element.addEventListener('wheel',wheel,{passive:false});
    return()=>element.removeEventListener('wheel',wheel);
  },[setCamera]);

  return <div ref={viewport} className="linked-sky-viewport" style={{aspectRatio}} data-zoomed={camera.zoom>1}
    onPointerDown={e=>{
      if(e.button!==0||points.current.size>=2||(e.target as HTMLElement).closest('button'))return;
      if(!points.current.size)dragged.current=false;
      points.current.set(e.pointerId,{x:e.clientX,y:e.clientY});
      if(points.current.size===2)dragged.current=true;
    }}
    onPointerMove={e=>{
      const previous=points.current.get(e.pointerId);
      if(!previous)return;
      const next={x:e.clientX,y:e.clientY},rect=e.currentTarget.getBoundingClientRect();
      const other=[...points.current].find(([id])=>id!==e.pointerId)?.[1];
      if(!other&&camera.zoom<=1)return;
      if(!dragged.current&&Math.hypot(next.x-previous.x,next.y-previous.y)<4)return;
      dragged.current=true;
      points.current.set(e.pointerId,next);
      if(!e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.setPointerCapture(e.pointerId);
      if(other){
        const midpoint=(p:Point)=>normalize({x:(p.x+other.x)/2,y:(p.y+other.y)/2},rect);
        const before=Math.max(1,Math.hypot(previous.x-other.x,previous.y-other.y));
        const after=Math.max(1,Math.hypot(next.x-other.x,next.y-other.y));
        setCamera(old=>zoomSky(old,after/before,midpoint(previous),midpoint(next)));
      }else{
        setCamera(old=>clamp({...old,x:old.x+(next.x-previous.x)/rect.width,y:old.y+(next.y-previous.y)/rect.height}));
      }
    }}
    onPointerUp={e=>{points.current.delete(e.pointerId);}}
    onPointerCancel={e=>{points.current.delete(e.pointerId);}}
    onLostPointerCapture={e=>{if(e.target===e.currentTarget)points.current.delete(e.pointerId);}}
    onPointerLeave={e=>{if(e.pointerType==='mouse'&&!e.currentTarget.hasPointerCapture(e.pointerId))points.current.delete(e.pointerId);}}
    onClickCapture={e=>{if(dragged.current&&e.detail>0){e.stopPropagation();dragged.current=false;}}}>
    {children}
  </div>;
}
