"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowRight, BookOpen, Check, ChevronDown, ChevronRight, CircleHelp, Crosshair, Database, ExternalLink, FileCode2, FileUp, FlaskConical, Focus, Info, Layers3, LoaderCircle, Orbit, Radio, RefreshCw, Search, ShieldCheck, SlidersHorizontal, Sparkles, Telescope, Upload, Waves, X } from "lucide-react";
import dynamic from "next/dynamic";
import { request } from "@/lib/api";
import { layerInfo, number, type HeaderCard, type Layer, type Observation, type Pixel, type WorkspaceView } from "@/lib/types";

const DetectorView = dynamic(() => import("./detector-view"), { ssr: false, loading: () => <div className="detector-placeholder"><LoaderCircle className="spin" /> Preparing detector viewer…</div> });
const ScienceWorkspace = dynamic(() => import("./science-workspace"), { ssr: false });
const layers: Layer[] = ["IMAGE", "VARIANCE", "FLAGS", "ZODI"];

function Aperture({ small = false }: { small?: boolean }) {
  return <svg className={small ? "aperture small" : "aperture"} viewBox="0 0 180 180" fill="none" aria-hidden="true">
    <circle cx="90" cy="90" r="72" stroke="currentColor" strokeWidth=".7" strokeDasharray="2 7" />
    <circle cx="90" cy="90" r="55" stroke="currentColor" strokeWidth=".6" />
    <circle cx="90" cy="90" r="37" stroke="currentColor" strokeWidth=".6" />
    <path d="M90 5v27M90 148v27M5 90h27M148 90h27M39 39l19 19M122 122l19 19M39 141l19-19M122 58l19-19" stroke="currentColor" strokeWidth=".7" />
    <path d="m90 51 34 20v39l-34 20-34-20V71zM56 71h45l23 39M90 51 68 90l22 40M56 110l23-39 45 0M124 110H79L56 71" stroke="currentColor" strokeWidth="1.2" />
    <circle cx="90" cy="90" r="3" fill="currentColor" />
  </svg>;
}

function HeaderBrowser({ observation, initialExtension = "PRIMARY" }: { observation: Observation; initialExtension?: string }) {
  const [extension, setExtension] = useState(initialExtension);
  const [cards, setCards] = useState<HeaderCard[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(""); setCards([]);
    request<HeaderCard[]>(`/observations/${observation.id}/headers?extension=${encodeURIComponent(extension)}`, { signal: controller.signal })
      .then(setCards).catch(e => { if (e.name !== "AbortError") setError(e.message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [extension, observation.id]);
  const selected = observation.extensions.find(e => e.name === extension);
  const filtered = cards.filter(card => `${card.key} ${card.value} ${card.comment}`.toLowerCase().includes(filter.toLowerCase()));
  return <div className="header-browser">
    <div className="header-browser-controls">
      <label className="field-label">EXTENSION<select value={extension} onChange={e => setExtension(e.target.value)}>{observation.extensions.map(ext => <option key={ext.index} value={ext.name}>{ext.index} · {ext.name}</option>)}</select></label>
      <label className="search-field"><Search size={15} /><input placeholder="Search FITS keywords…" aria-label="Search FITS keywords" value={filter} onChange={e => setFilter(e.target.value)} /></label>
      <span className="mono muted">{filtered.length} cards</span>
    </div>
    <div className="extension-description"><span>{selected?.kind}</span><span>{selected?.shape.length ? `${selected.shape.join(" × ")} (NumPy axes)` : "No image array"}</span><span>Units: {selected?.unit || "not specified"}</span></div>
    {!!selected?.columns.length && <div className="table-columns">Table columns: {selected.columns.map(c => `${c.name} [${c.format}${c.dim ? `; ${c.dim}` : ""}${c.unit ? `; ${c.unit}` : ""}]`).join(" · ")}</div>}
    {loading ? <div className="inline-loading"><LoaderCircle size={16} className="spin" /> Reading original header…</div> : error ? <p className="error-text" role="alert">{error}</p> : <div className="header-table-wrap"><table className="header-table"><thead><tr><th>KEYWORD</th><th>VALUE</th><th>COMMENT</th></tr></thead><tbody>{filtered.map((card, index) => <tr key={`${index}-${card.key}`}><td>{card.key || "(blank)"}</td><td>{String(card.value ?? "—")}</td><td>{card.comment}</td></tr>)}</tbody></table>{!filtered.length && <p className="muted">No matching header cards.</p>}</div>}
  </div>;
}

function Help({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  return <dialog ref={ref} onClose={onClose} className="help-dialog"><div className="panel-title"><div><span className="eyebrow">FIELD GUIDE / REAL DATA</span><h2>A closer look at your observation</h2></div><button className="icon-button" aria-label="Close guide" onClick={() => ref.current?.close()}><X size={20} /></button></div>
    <p>Load a single SPHEREx Level 2 FITS file. Every displayed measurement comes from that file; no demonstration observation is preloaded.</p>
    <div className="guide-step"><span>01</span><div><h3>Bring your observation</h3><p>Upload an uncompressed FITS file up to 256 MiB, or configure <code>SPHEREX_FITS_PATH</code> on the Python service.</p></div></div>
    <div className="guide-step"><span>02</span><div><h3>Read the detector</h3><p>Switch between IMAGE, VARIANCE, FLAGS, and ZODI. Click to inspect a pixel, drag to pan, and use the toolbar to zoom. Transparent pixels are missing or masked.</p></div></div>
    <div className="guide-step"><span>03</span><div><h3>Inspect the evidence</h3><p>The pixel inspector reports native values, ICRS coordinates, and calibrated wavelength when available. Data Inspector exposes original headers, units, dimensions, and calibration table columns.</p></div></div>
    <div className="notice"><Info size={17} /><p>A single exposure samples different wavelengths at different detector positions. It does not contain a complete spectrum at each sky position. Open Find observations to load additional real cutouts, then build a fixed-sky workspace for timeline, comparison, and candidate tools.</p></div>
    <p className="muted">Keyboard: focus the detector canvas, press Enter to inspect its center, use arrow keys to move the selection, + / − to zoom, and 0 to fit the image.</p>
    <a className="text-link" href="https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/" target="_blank" rel="noreferrer">Read the official IRSA data guide <ExternalLink size={14} /></a>
  </dialog>;
}

export default function Explorer({ active = true, destination }: { active?: boolean; destination?: WorkspaceView }) {
  const [observation, setObservation] = useState<Observation | null>(null);
  const [view, setView] = useState<"explore" | "inspector" | WorkspaceView>("explore");
  const [layer, setLayer] = useState<Layer>("IMAGE");
  const [busy, setBusy] = useState(false);
  const [connecting, setConnecting] = useState(true);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState("");
  const [help, setHelp] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [stretch, setStretch] = useState("asinh");
  const [palette, setPalette] = useState("gray");
  const [mask, setMask] = useState(false);
  const [limits, setLimits] = useState("");
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [pixel, setPixel] = useState<Pixel | null>(null);
  const [pixelBusy, setPixelBusy] = useState(false);
  const [pixelError, setPixelError] = useState("");
  const [selected, setSelected] = useState<{ x: number; y: number } | null>(null);
  const [ra, setRa] = useState("");
  const [dec, setDec] = useState("");
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [headerExtension, setHeaderExtension] = useState("PRIMARY");
  const input = useRef<HTMLInputElement>(null);
  const uploadLock = useRef(false);

  function acceptObservation(obs: Observation) {
    setObservation(obs); setLayer("IMAGE"); setPixel(null); setSelected(null); setLimits(""); setLow(""); setHigh("");
    setView("explore"); setError(""); setConnected(true); setRa(""); setDec(""); setLocationError("");
    setHeaderExtension("PRIMARY");
    localStorage.setItem("spherex-observation", obs.id);
  }

  async function connect(signal?: AbortSignal) {
    setConnecting(true); setError("");
    try {
      await request("/health", { signal }); setConnected(true);
      const saved = localStorage.getItem("spherex-observation");
      if (saved) {
        try { acceptObservation(await request<Observation>(`/observations/${saved}`, { signal })); return; }
        catch (e) { if (signal?.aborted) throw e; localStorage.removeItem("spherex-observation"); }
      }
      const data = await request<{ observation: Observation | null }>("/observations/default", { signal });
      if (data.observation) acceptObservation(data.observation);
    } catch (e) {
      if (!signal?.aborted) { setConnected(false); setError(e instanceof Error ? e.message : "Could not connect to the science service."); }
    } finally { if (!signal?.aborted) setConnecting(false); }
  }

  useEffect(() => { const controller = new AbortController(); void connect(controller.signal); return () => controller.abort(); }, []); // initial connection only

  async function upload(file?: File) {
    if (!file || uploadLock.current || connecting) return;
    if (!/\.(fits|fit|fts)$/i.test(file.name)) { setError("Choose an uncompressed .fits, .fit, or .fts file."); return; }
    if (file.size > 256 * 1024 * 1024) { setError("This file exceeds the 256 MiB limit. Upload an uncompressed observation or a smaller archive cutout."); return; }
    uploadLock.current = true; setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("file", file);
      acceptObservation(await request<Observation>("/observations", { method: "POST", body }));
    } catch (e) { setError(e instanceof Error ? e.message : "Could not read this observation."); }
    finally { setBusy(false); uploadLock.current = false; if (input.current) input.current.value = ""; }
  }

  useEffect(() => { setPixel(null); setLimits(""); setLow(""); setHigh(""); setPixelError(""); }, [layer]);

  useEffect(() => {
    if (!observation || !selected) { setPixelBusy(false); return; }
    const controller = new AbortController(); setPixelBusy(true); setPixelError(""); setPixel(null);
    request<Pixel>(`/observations/${observation.id}/pixel?layer=${layer}&x=${selected.x}&y=${selected.y}`, { signal: controller.signal })
      .then(setPixel).catch(e => { if (e.name !== "AbortError") setPixelError(e.message); }).finally(() => { if (!controller.signal.aborted) setPixelBusy(false); });
    return () => controller.abort();
  }, [observation, layer, selected]);

  const isWorkspace = view !== "explore" && view !== "inspector";
  const viewLabel = ({ explore: "Explore", inspector: "Data Inspector", wavelengths: "Wavelengths", timeline: "Timeline", difference: "Difference", investigate: "Investigate", archive: "Archive" })[view];
  useEffect(() => { if (active && destination) setView(destination); }, [active, destination]);
  useEffect(() => { const update = (event: Event) => acceptObservation((event as CustomEvent<Observation>).detail); window.addEventListener("spherex-observation-changed", update); return () => window.removeEventListener("spherex-observation-changed", update); }, []);
  const stats = observation?.stats[layer];
  const extension = observation?.extensions.find(e => e.name === layer);
  const availableLayers = layers.filter(name => observation?.stats[name]);
  const shape = extension?.shape;
  const flags = observation?.extensions.find(e => e.name === "FLAGS");
  const maskAvailable = !!shape && !!flags && shape.join() === flags.shape.join();
  const uploadDisabled = busy || connecting;
  const selectPixel = (x: number, y: number) => setSelected({ x, y });
  function showHeaders(name = "PRIMARY") { setHeaderExtension(name); setView("inspector"); }

  async function locate(e: React.FormEvent) {
    e.preventDefault(); if (!observation) return;
    if (!ra.trim() || !dec.trim()) { setLocationError("Enter both RA and Dec in decimal degrees."); return; }
    setLocating(true); setLocationError("");
    try {
      const pos = await request<{ x: number; y: number }>(`/observations/${observation.id}/locate?ra=${encodeURIComponent(ra)}&dec=${encodeURIComponent(dec)}`);
      setLayer("IMAGE"); selectPixel(pos.x, pos.y);
    } catch (e) { setLocationError(e instanceof Error ? e.message : "Could not locate those coordinates."); }
    finally { setLocating(false); }
  }

  return <div className="app-shell" onDragOver={e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDragging(true); } }} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }} onDrop={e => { e.preventDefault(); setDragging(false); void upload(e.dataTransfer.files[0]); }}>
    <input className="sr-only" ref={input} type="file" accept=".fits,.fit,.fts" aria-label="Upload FITS observation" disabled={uploadDisabled} onChange={e => void upload(e.target.files?.[0])} />
    {dragging && <div className="drop-overlay"><FileUp size={42} /><h2>Drop your observation here</h2><p>Uncompressed FITS · up to 256 MiB</p></div>}
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="SPHEREx Sky Explorer home"><div className="brand-mark"><Orbit size={28} strokeWidth={1.2} /></div><div><strong>SPHEREx<span>↗</span></strong><small>SKY EXPLORER</small></div></a>
      <div className="workspace-tag"><span className="status-dot amber" /> OBSERVATION WORKSPACE</div>
      <div className="nav-label">WORKSPACE</div>
      <nav aria-label="Workspace navigation">
        <button className={view === "explore" ? "nav-item current" : "nav-item"} onClick={() => setView("explore")}><Telescope size={18} /> Explore <span className="nav-shortcut">01</span></button>
        <button className={view === "inspector" ? "nav-item current" : "nav-item"} onClick={() => showHeaders()}><Database size={17} /> Data Inspector <span className="nav-shortcut">02</span></button>
      </nav>
      <div className="nav-label later-label">SCIENCE WORKSPACE</div>
      <nav aria-label="Science navigation">{([['wavelengths','Wavelengths',Waves],['timeline','Timeline',Radio],['difference','Difference imaging',Layers3],['investigate','Investigate',Crosshair],['archive','Find observations',Search]] as const).map(([key,label,Icon])=><button key={key} className={view===key?'nav-item current':'nav-item'} aria-label={label} onClick={()=>setView(key)}><Icon size={17}/>{label}</button>)}</nav>
      <div className="sidebar-file"><span className="nav-label">ACTIVE OBSERVATION</span>{observation ? <><div className="active-file"><FileCode2 size={20} /><div><strong title={observation.filename}>{observation.filename}</strong><small>{number(observation.bytes / 1024 / 1024, 1)} MiB · {observation.extensions.length} HDUs</small></div><span className="status-dot" /></div><button className="sidebar-import" onClick={() => input.current?.click()} disabled={uploadDisabled}><RefreshCw size={13} /> Replace observation</button></> : <><p>No observation loaded.</p><button className="sidebar-import" onClick={() => input.current?.click()} disabled={uploadDisabled}><PlusIcon /> Import a FITS file</button></>}</div>
      <div className="sidebar-bottom"><div className="science-note"><ShieldCheck size={18} /><span>Real files. Traceable science.<small>No simulated sky measurements.</small></span></div><button className="guide-button" onClick={() => setHelp(true)}><BookOpen size={16} /> Quick-start guide <ChevronRight size={14} /></button><a className="archive-link" href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noreferrer">NASA / IPAC IRSA <ExternalLink size={12} /></a><div className="version-label">REAL-DATA EXPLORER · v0.2</div></div>
    </aside>

    <div className="main-shell">
      <header className="topbar"><div className="breadcrumbs"><span>Workspace</span><ChevronRight size={12} /><strong>{viewLabel}</strong></div><div className="topbar-right"><span className={`service-state ${connected ? "online" : ""}`}><span className="status-dot" />{connecting ? "Connecting…" : connected ? "Science service connected" : "Science service offline"}</span><span className="topbar-divider" /><button className="icon-button" title="Open field guide" aria-label="Open field guide" onClick={() => setHelp(true)}><CircleHelp size={18} /></button><span className="workspace-avatar" title="Local science workspace"><FlaskConical size={16} /></span></div></header>
      <main>
        {isWorkspace ? <ScienceWorkspace active={active} view={view as WorkspaceView} observation={observation} onLoad={acceptObservation} onUpload={() => input.current?.click()} /> : <>
        <section className="page-heading"><div><div className="eyebrow"><span /> A NEW PERSPECTIVE ON THE UNIVERSE</div><h1>{view === "explore" ? <>One observation.<br className="mobile-break" /> A sky of possibilities.</> : <>The science, under the surface.</>}</h1><p>{view === "explore" ? "Explore the infrared sky, one real measurement at a time." : "Read the original FITS headers, array dimensions, and calibration metadata."}</p></div><button className="primary-button heading-upload" onClick={() => input.current?.click()} disabled={uploadDisabled}>{busy ? <LoaderCircle className="spin" size={16} /> : <Upload size={16} />}{busy ? "Reading FITS…" : "Load observation"}</button></section>

        {error && <div className="error-banner" role="alert"><Info size={18} /><span>{error}</span>{!connected && <button onClick={() => void connect()} disabled={connecting}>Reconnect <RefreshCw size={13} /></button>}<button aria-label="Dismiss error" className="icon-button" onClick={() => setError("")}><X size={15} /></button></div>}
        {busy && <div className="loading-banner" role="status"><LoaderCircle className="spin" size={16} /> Reading your FITS extensions, WCS, and wavelength calibration. Large observations may take a moment.</div>}

        <div className="summary-grid">
          <Summary icon={<Focus size={17} />} title="OBSERVATION" value={observation ? String(observation.observation?.value || "ID not specified") : "Awaiting observation"} detail={observation ? observation.filename : "Load a SPHEREx Level 2 FITS file"} />
          <Summary icon={<Radio size={17} />} title="OBSERVED AT" value={observation?.timestamp ? String(observation.timestamp.value) : "—"} detail={observation?.timestamp ? `${observation.timestamp.key} · ${observation.time_system?.value || "time system not specified"}` : "Original timestamp from FITS header"} />
          <Summary icon={<Waves size={17} />} title="WAVELENGTH COVERAGE" value={observation?.spectral ? `${number(observation.spectral.min_um, 3)} – ${number(observation.spectral.max_um, 3)}` : "—"} suffix={observation?.spectral ? "µm" : undefined} detail={observation?.spectral ? "Position-dependent · WCS-WAVE" : "Read from the detector calibration"} />
          <Summary icon={<GridIcon />} title="NATIVE DIMENSIONS" value={observation ? `${observation.shape[1]} × ${observation.shape[0]}` : "— × —"} suffix="px" detail={observation ? `Detector ${observation.detector?.value || "not specified"} · ${observation.extensions.length} HDUs` : "Actual resolution, never synthesized"} />
        </div>

        {view === "inspector" ? <section className="panel full-inspector"><div className="panel-title"><div className="title-with-icon"><Database size={17} /><h2>Data Inspector</h2></div><span className="tag">ORIGINAL FITS HEADERS</span></div>{observation ? <HeaderBrowser key={`${observation.id}-${headerExtension}`} observation={observation} initialExtension={headerExtension} /> : <div className="inspector-empty"><Database size={35} /><h3>Your file is the source of truth.</h3><p>Load an observation to browse every extension and its original header.</p><button className="primary-button" disabled={uploadDisabled} onClick={() => input.current?.click()}><Upload size={15} /> Load FITS file</button></div>}</section> : <>
          <div className="workspace-grid">
            <section className="panel viewer-panel"><div className="panel-title"><div className="title-with-icon"><Telescope size={17} /><h2>Observation viewer</h2><span className="tag">LEVEL 2</span></div><span className={`live-label ${observation ? "loaded" : ""}`}><span className="status-dot" />{observation ? "FILE LOADED" : "NO DATA LOADED"}</span></div>
              <div className="layer-tabs" role="tablist" aria-label="FITS image layers">{layers.map(name => <button role="tab" aria-selected={layer === name} key={name} className={layer === name ? "selected" : ""} disabled={!observation?.stats[name]} onClick={() => { setSelected(null); setLayer(name); }}>{name === "IMAGE" ? <Layers3 size={14} /> : name === "VARIANCE" ? <SlidersHorizontal size={14} /> : name === "FLAGS" ? <ShieldCheck size={14} /> : <Sparkles size={14} />}{layerInfo[name].label}<span>{name}</span></button>)}</div>
              {observation ? <DetectorView observation={observation} layer={layer} stretch={stretch} palette={palette} mask={mask && maskAvailable && layer !== "FLAGS"} limits={limits} selected={selected} onSelect={selectPixel} /> : <div className="empty-viewer"><div className="empty-axis x-axis" /><div className="empty-axis y-axis" /><span className="empty-corner top-left" /><span className="empty-corner top-right" /><span className="empty-corner bottom-left" /><span className="empty-corner bottom-right" /><div className="empty-viewer-content"><Aperture /><span className="eyebrow">YOUR NEXT DISCOVERY STARTS WITH DATA</span><h2>Bring the infrared sky into focus.</h2><p>Load your SPHEREx observation to explore its<br />image, wavelength calibration, and pixel measurements.</p><button className="primary-button" onClick={() => input.current?.click()} disabled={uploadDisabled}>{connecting || busy ? <LoaderCircle size={16} className="spin" /> : <FileUp size={17} />}{connecting ? "Connecting to service…" : busy ? "Reading observation…" : "Choose a FITS file"}<ArrowRight size={16} /></button><span className="file-hint">or drag and drop here · .fits, .fit, .fts · max 256 MiB</span></div><span className="empty-viewer-foot"><span className="status-dot amber" /> No image displayed until a real file is loaded.</span></div>}
              <div className="viewer-foot"><span><Info size={13} />{observation ? "Click a pixel to inspect · Drag to pan · Toolbar to zoom" : "The detector view will preserve your file’s native resolution."}</span><span className="mono">{observation ? extension?.unit || "UNIT NOT SPECIFIED" : "FITS / MEF"}</span></div>
            </section>

            <aside className="inspector-column"><section className="panel pixel-panel"><div className="panel-title"><div className="title-with-icon"><Crosshair size={16} /><h2>Pixel inspector</h2></div>{pixelBusy ? <LoaderCircle size={14} className="spin" /> : <span className="tiny-label">NATIVE VALUES</span>}</div>
              {!pixel ? <div className="pixel-empty"><div className="target-symbol"><Crosshair size={29} strokeWidth={1} /></div><h3>{pixelBusy ? "Reading measurement…" : "Every pixel tells a story."}</h3><p>{pixelBusy ? "Fetching native values and calibrated coordinates." : observation ? "Click the image or use the center-pixel tool to read a measurement." : "Load an observation, then click a pixel to reveal its measurements."}</p>{pixelError && <p className="error-text" role="alert">{pixelError}</p>}</div> : <div className="pixel-data"><div className="pixel-position"><span>DETECTOR PIXEL</span><strong>X {pixel.x} <span>/</span> Y {pixel.y}</strong></div><div className="pixel-sky"><div><span>RA · ICRS</span><strong>{number(pixel.ra_deg, 6)}{pixel.ra_deg != null && "°"}</strong></div><div><span>DEC · ICRS</span><strong>{number(pixel.dec_deg, 6)}{pixel.dec_deg != null && "°"}</strong></div></div><dl className="measurements"><Metric label="Brightness" value={number(pixel.brightness)} unit={observation?.extensions.find(e => e.name === "IMAGE")?.unit || "unit unspecified"} /><Metric label="Variance" value={number(pixel.variance)} unit={observation?.extensions.find(e => e.name === "VARIANCE")?.unit || "unit unspecified"} /><Metric label="Uncertainty · σ" value={number(pixel.uncertainty)} unit={observation?.extensions.find(e => e.name === "VARIANCE")?.unit ? `√(${observation.extensions.find(e => e.name === "VARIANCE")?.unit})` : "unit unspecified"} /><Metric label="Zodiacal model" value={number(pixel.zodi)} unit={observation?.extensions.find(e => e.name === "ZODI")?.unit || "unit unspecified"} /><Metric label="Wavelength" value={number(pixel.wavelength_um, 5)} unit="µm" /><Metric label="Bandwidth" value={number(pixel.bandwidth_um, 5)} unit="µm" /></dl><div className={`flag-readout ${pixel.flags ? "flagged" : ""}`}><ShieldCheck size={14} /><span>{pixel.flags == null ? "Flags unavailable" : pixel.flags === 0 ? "No active quality bits" : `Flags ${pixel.flags} · bits ${pixel.flag_bits.join(", ")}`}</span></div><p className="pixel-convention">0-based coordinates · FITS ({pixel.fits_x}, {pixel.fits_y})</p></div>}
              <div className="pixel-panel-note"><Info size={13} /><p>{pixel?.measurement_note || "Uncertainty comes from √VARIANCE. Raw brightness is not a source SNR."}</p></div>
            </section>
            <section className="panel display-panel"><div className="panel-title"><div className="title-with-icon"><SlidersHorizontal size={15} /><h2>Display settings</h2></div></div><div className="display-body"><div className="setting-row"><label htmlFor="stretch">Stretch</label><select id="stretch" disabled={!observation} value={stretch} onChange={e => setStretch(e.target.value)}><option value="asinh">Asinh</option><option value="linear">Linear</option><option value="log">Logarithmic</option></select></div><div className="setting-row"><label htmlFor="palette">Color map</label><select id="palette" disabled={!observation} value={palette} onChange={e => setPalette(e.target.value)}><option value="gray">Grayscale</option><option value="amber">Amber</option><option value="ice">Ice</option></select></div><div className={`color-scale ${palette}`} /><div className="scale-labels"><span>{limits ? number(Number(low)) : number(stats?.low)}</span><span>{limits ? number(Number(high)) : number(stats?.high)}</span></div><details className="range-details"><summary>Display range <ChevronDown size={12} /></summary><form onSubmit={e => { e.preventDefault(); if (!low.trim() || !high.trim() || !Number.isFinite(Number(low)) || !Number.isFinite(Number(high)) || Number(high) <= Number(low)) { setError("Enter finite display limits with upper > lower."); return; } setLimits(`&low=${Number(low)}&high=${Number(high)}`); }}><label>Lower<input type="number" step="any" value={low} disabled={!observation} onChange={e => setLow(e.target.value)} /></label><label>Upper<input type="number" step="any" value={high} disabled={!observation} onChange={e => setHigh(e.target.value)} /></label><button disabled={!observation} type="submit">Apply</button><button disabled={!observation} type="button" onClick={() => { setLimits(""); setLow(""); setHigh(""); }}>Auto</button></form></details><label className="toggle-row"><span>Exclude flagged pixels<small>Conservative: all nonzero bits</small></span><input type="checkbox" checked={mask} disabled={!observation || !maskAvailable || layer === "FLAGS"} onChange={e => setMask(e.target.checked)} /><span className="toggle" /></label><p className="display-caption">{observation ? layerInfo[layer].description : "Display controls activate when data is loaded."}</p></div></section>
            </aside>
          </div>

          <div className="lower-grid"><section className="panel observation-panel"><div className="panel-title"><div className="title-with-icon"><FileCode2 size={16} /><h2>Observation details</h2></div><button className="text-link" onClick={() => showHeaders()}>View FITS headers <ArrowRight size={13} /></button></div><dl className="observation-details"><Detail label="Instrument" value={String(observation?.instrument?.value || (observation?.source_url.endsWith(".fits") ? "SPHEREx · verified archive" : observation ? "Not specified in header" : "Not loaded"))} /><Detail label="Data release" value={String(observation?.release?.value || (observation ? "Not specified in header" : "—"))} /><Detail label="Processing version" value={String(observation?.processing_version?.value || "—")} /><Detail label="Coordinate solution" value={observation ? observation.spatial_wcs ? "Celestial WCS available" : "Unavailable" : "—"} /><Detail label="Data origin" value={observation ? observation.source_url.endsWith(".fits") ? "NASA/IPAC IRSA · verified reference" : "Uploaded / configured local FITS" : "Your SPHEREx Level 2 observation"} /><Detail label="Available image layers" value={observation ? availableLayers.join(" · ") : "Awaiting file"} /></dl><div className="source-foot"><ShieldCheck size={15} /><span>{observation ? observation.provenance : "Scientific values will be read directly from your observation."}</span><a href={observation?.source_url || "https://irsa.ipac.caltech.edu/Missions/spherex.html"} target="_blank" rel="noreferrer" aria-label="Open SPHEREx archive">IRSA <ExternalLink size={12} /></a></div></section>
            <section className="panel wavelength-panel"><div className="panel-title"><div className="title-with-icon"><Waves size={17} /><h2>Wavelength calibration</h2></div><span className="tag">WCS-WAVE</span></div><div className="wavelength-content"><div className="wavelength-reading"><strong>{observation?.spectral ? `${number(observation.spectral.min_um, 3)}–${number(observation.spectral.max_um, 3)}` : "—"}</strong><span>µm</span><span className="range-tag">{observation?.spectral ? "DETECTOR RANGE" : "NOT LOADED"}</span></div><div className={`wavelength-bar ${observation?.spectral ? "has-data" : ""}`}><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /></div><div className="wavelength-axis"><span>{observation?.spectral ? `${number(observation.spectral.min_um, 3)} µm` : "Lower wavelength"}</span><span>{observation?.spectral ? `${number(observation.spectral.max_um, 3)} µm` : "Upper wavelength"}</span></div><p>Wavelength varies across the detector. Select a pixel to read its central wavelength and bandwidth.</p><div className="calibration-note"><Info size={13} /><span>{observation?.spectral ? "Lookup-table calibration for visualization. Not a source spectrum." : observation ? "Calibration could not be resolved. Inspect the header for details." : "Read from your file. No spectral channels are assumed."}</span></div></div></section></div>

          <section className="panel coordinate-panel"><div className="coordinate-intro"><Focus size={19} /><div><h3>Find a sky position in this observation</h3><p>Locate an ICRS coordinate using the file’s celestial WCS.</p></div></div><form onSubmit={locate}><label>RIGHT ASCENSION<input aria-label="Right ascension in degrees" type="number" step="any" min="0" max="359.999999999" placeholder="0 ≤ RA < 360°" value={ra} onChange={e => setRa(e.target.value)} disabled={!observation?.spatial_wcs} required /></label><label>DECLINATION<input aria-label="Declination in degrees" type="number" step="any" min="-90" max="90" placeholder="−90° to +90°" value={dec} onChange={e => setDec(e.target.value)} disabled={!observation?.spatial_wcs} required /></label><button className="secondary-button" disabled={!observation?.spatial_wcs || locating}>{locating ? <LoaderCircle size={15} className="spin" /> : <Search size={15} />} Locate pixel</button></form>{locationError && <p className="coordinate-error error-text" role="alert">{locationError}</p>}</section>
        </>}

        {observation && <div className="file-notices"><div className="notice-heading"><Info size={15} /> FILE VALIDATION & LIMITATIONS</div>{observation.notices.map((notice, i) => <p key={i}>{notice}</p>)}{!!observation.flag_definitions.length && <details><summary>Quality flag definitions from this file</summary><dl>{observation.flag_definitions.map(card => <Detail key={card.key} label={`${card.key} = ${card.value}`} value={card.comment} />)}</dl></details>}<p>This detector view shows one observation. Use the science workspace to register selected observations, compare epochs, and investigate unverified residuals.</p></div>}
        <footer className="page-footer"><span><span className="status-dot amber" /> REAL DATA <i>/</i> SPHEREx Sky Explorer</span><span>Built for exploration. Grounded in real data. <Orbit size={13} /></span></footer>
        </>}
      </main>
    </div>
    {help && <Help onClose={() => setHelp(false)} />}
  </div>;
}

function Summary({ icon, title, value, suffix, detail }: { icon: React.ReactNode; title: string; value: string; suffix?: string; detail: string }) {
  return <section className="summary-card"><div className="summary-label">{icon}<span>{title}</span></div><div className="summary-value" title={value}>{value}<small>{suffix}</small></div><p title={detail}>{detail}</p></section>;
}
function Metric({ label, value, unit }: { label: string; value: string; unit: string }) { return <div><dt>{label}</dt><dd>{value}<small>{unit}</small></dd></div>; }
function Detail({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div>; }
function GridIcon() { return <svg width="17" height="17" viewBox="0 0 17 17" fill="none" aria-hidden="true"><rect x="2" y="2" width="13" height="13" rx="2" stroke="currentColor" /><path d="M6.3 2v13M10.7 2v13M2 6.3h13M2 10.7h13" stroke="currentColor" strokeWidth=".7" /></svg>; }
function PlusIcon() { return <svg width="13" height="13" viewBox="0 0 13 13" aria-hidden="true"><path d="M6.5 2v9M2 6.5h9" stroke="currentColor" /></svg>; }
