"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Crosshair, Download, Grid2X2, LoaderCircle, Maximize, Minus, Plus, RotateCcw } from "lucide-react";
import type { Layer, Observation } from "@/lib/types";

type Props = { observation: Observation; layer: Layer; stretch: string; palette: string; mask: boolean; limits: string; selected: { x: number; y: number } | null; onSelect: (x: number, y: number) => void };

export default function DetectorView({ observation, layer, stretch, palette, mask, limits, selected, onSelect }: Props) {
  const wrapper = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ width: 600, height: 500 });
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [grid, setGrid] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; px: number; py: number; moved: boolean } | null>(null);
  const ext = observation.extensions.find(e => e.name === layer)!;
  const [height, width] = ext.shape;
  const fit = Math.min((size.width - 72) / width, (size.height - 72) / height);
  const scale = fit * zoom;
  const left = (size.width - width * scale) / 2 + pan.x;
  const top = (size.height - height * scale) / 2 + pan.y;
  const url = `/api/science/observations/${observation.id}/image?layer=${layer}&stretch=${stretch}&palette=${palette}&mask=${mask}${limits}`;

  useEffect(() => {
    if (!wrapper.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(wrapper.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setImage(null);
    const next = new Image();
    next.onload = () => { if (active) { setImage(next); setLoading(false); } };
    next.onerror = () => { if (active) { setError("This layer could not be rendered. Check the science service or adjust display limits."); setLoading(false); } };
    next.src = url;
    return () => { active = false; next.onload = null; next.onerror = null; };
  }, [url]);

  useEffect(() => { setZoom(1); setPan({ x: 0, y: 0 }); }, [observation.id, layer]);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return;
    const dpr = window.devicePixelRatio || 1;
    element.width = Math.round(size.width * dpr); element.height = Math.round(size.height * dpr);
    const ctx = element.getContext("2d")!;
    ctx.scale(dpr, dpr);
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, size.width, size.height);
    if (!image) return;
    ctx.drawImage(image, left, top, width * scale, height * scale);
    ctx.strokeStyle = "#55606a"; ctx.lineWidth = 1;
    ctx.strokeRect(left - .5, top - .5, width * scale + 1, height * scale + 1);
    if (grid) {
      ctx.save(); ctx.beginPath(); ctx.rect(left, top, width * scale, height * scale); ctx.clip();
      ctx.strokeStyle = "#a8b5c34a"; ctx.setLineDash([3, 5]);
      for (let i = 1; i < 4; i++) {
        ctx.beginPath(); ctx.moveTo(left + width * scale * i / 4, top); ctx.lineTo(left + width * scale * i / 4, top + height * scale); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(left, top + height * scale * i / 4); ctx.lineTo(left + width * scale, top + height * scale * i / 4); ctx.stroke();
      }
      ctx.restore();
    }
    if (selected) {
      const x = left + (selected.x + .5) * scale;
      const y = top + (height - selected.y - .5) * scale;
      ctx.strokeStyle = "#e9b567"; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.stroke();
      for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
        ctx.beginPath(); ctx.moveTo(x + dx * 13, y + dy * 13); ctx.lineTo(x + dx * 21, y + dy * 21); ctx.stroke();
      }
    }
    ctx.fillStyle = "#8b969f"; ctx.font = "10px 'IBM Plex Mono', monospace";
    ctx.fillText("0", left, top + height * scale + 17);
    ctx.fillText(String(width - 1), left + width * scale - 24, top + height * scale + 17);
    ctx.fillText(`Y ${height - 1}`, left, top - 10);
    ctx.fillText("X →", left + width * scale / 2, top + height * scale + 17);
  }, [image, grid, left, top, width, height, scale, selected, size]);

  const changeZoom = useCallback((amount: number) => setZoom(old => Math.max(.25, Math.min(32, old * amount))), []);
  const reset = () => { setZoom(1); setPan({ x: 0, y: 0 }); };
  const pick = (clientX: number, clientY: number) => {
    const rect = canvas.current!.getBoundingClientRect();
    const x = Math.floor((clientX - rect.left - left) / scale);
    const y = height - 1 - Math.floor((clientY - rect.top - top) / scale);
    if (x >= 0 && y >= 0 && x < width && y < height) onSelect(x, y);
  };

  return <div className="detector-shell" ref={wrapper}>
    <div className="viewer-label"><span className="status-dot" /> DETECTOR COORDINATES <span>·</span> Y UP</div>
    <canvas ref={canvas} className="detector-canvas" aria-label={`${layer} detector image. Click to inspect a pixel; drag to pan. Use plus and minus to zoom, arrows to move the selected pixel.`} tabIndex={0}
      onWheel={e => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); changeZoom(e.deltaY < 0 ? 1.1 : 1 / 1.1); } }}
      onKeyDown={e => {
        if (e.key === "+" || e.key === "=") { e.preventDefault(); changeZoom(1.3); }
        else if (e.key === "-") { e.preventDefault(); changeZoom(1 / 1.3); }
        else if (e.key === "0") reset();
        else if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter"].includes(e.key)) {
          e.preventDefault(); const pos = selected || { x: Math.floor(width / 2), y: Math.floor(height / 2) };
          onSelect(Math.max(0, Math.min(width - 1, pos.x + (e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0))), Math.max(0, Math.min(height - 1, pos.y + (e.key === "ArrowDown" ? -1 : e.key === "ArrowUp" ? 1 : 0))));
        }
      }}
      onPointerDown={e => { if (e.button !== 0) return; e.currentTarget.setPointerCapture(e.pointerId); drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y, moved: false }; }}
      onPointerMove={e => { const d = drag.current; if (!d) return; if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 3) d.moved = true; if (d.moved) setPan({ x: d.px + e.clientX - d.x, y: d.py + e.clientY - d.y }); }}
      onPointerUp={e => { if (drag.current && !drag.current.moved && image) pick(e.clientX, e.clientY); drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
    />
    {loading && <div className="viewer-message" role="status"><LoaderCircle className="spin" size={22} /> Rendering actual {layer} pixels…</div>}
    {error && <div className="viewer-message error-text" role="alert">{error}</div>}
    <div className="viewer-tools">
      <button title="Zoom in" aria-label="Zoom in" onClick={() => changeZoom(1.3)}><Plus size={16} /></button>
      <span className="zoom-value">{Math.round(zoom * 100)}%</span>
      <button title="Zoom out" aria-label="Zoom out" onClick={() => changeZoom(1 / 1.3)}><Minus size={16} /></button>
      <i />
      <button title="Fit image" aria-label="Fit image" onClick={reset}><Maximize size={15} /></button>
      <button title="Toggle detector grid" aria-label="Toggle detector grid" aria-pressed={grid} onClick={() => setGrid(!grid)} className={grid ? "active-tool" : ""}><Grid2X2 size={15} /></button>
      <button title="Inspect center pixel" aria-label="Inspect center pixel" onClick={() => onSelect(Math.floor(width / 2), Math.floor(height / 2))}><Crosshair size={16} /></button>
      <button title="Reset view" aria-label="Reset view" onClick={reset}><RotateCcw size={14} /></button>
      <i />
      <a href={url} download={`${observation.filename}-${layer}-display.png`} title="Download display PNG (not scientific FITS)" aria-label="Download display PNG"><Download size={15} /></a>
    </div>
    <span className="viewer-corner">{width} × {height} native px</span>
  </div>;
}
