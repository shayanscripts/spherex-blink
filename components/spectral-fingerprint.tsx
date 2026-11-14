'use client';

import { useEffect, useMemo, useState } from 'react';
import dynamic from 'next/dynamic';
import { ExternalLink, LoaderCircle, Waves } from 'lucide-react';
import type { Data } from 'plotly.js';
import { request } from '@/lib/api';

const Chart = dynamic(() => import('./science-chart'), { ssr: false });
const colors = ['#84cbb5', '#a6b8ff', '#f09dc5'];
type Sample = {
  id: string; filename: string; source_url: string | null; timestamp: string;
  wavelength_um: number; bandwidth_um: number; flux_mjy: number; uncertainty_mjy: number;
  snr: number; reduced_chi2: number; center_flags: number;
};
type Match = {
  kind: string; object: string; data_url: string; citation: string; reduced_chi2: number;
  wavelength_um: number[]; flux_mjy: number[];
};
type Result = {
  samples: Sample[]; unavailable: { id: string; reason: string }[];
  scanned: number; eligible: number; anchor: string; motion: boolean; zodi_subtracted: boolean;
  classification: { status: 'insufficient' | 'unavailable' | 'resemblance'; reason: string; matches: Match[];
    points: number; span_um: number | null; library_url: string; used_ids?: string[] };
};
export type FingerprintTarget = { label: string; path: string; moving?: boolean };

export default function SpectralFingerprint({ target }: { target: FingerprintTarget | null }) {
  const [scope, setScope] = useState('library');
  const [days, setDays] = useState('7');
  const [response, setResponse] = useState<{ key: string; result?: Result; error?: string }>();
  const [retry, setRetry] = useState(0);
  const [overlay, setOverlay] = useState(true);
  const path = target ? `${target.path}&scope=${scope}&days=${target.moving ? 7 : days}` : null;
  const key = path ? `${path}#${retry}` : null;
  const current = response?.key === key ? response : undefined;
  const result = current?.result;
  const loading = !!path && !current;

  useEffect(() => {
    if (!path || !key) return;
    const controller = new AbortController();
    request<Result>(path, { signal: controller.signal })
      .then(result => setResponse({ key, result }))
      .catch(error => { if (!controller.signal.aborted) setResponse({ key, error: error.message }); });
    return () => controller.abort();
  }, [path, key]);

  const traces = useMemo<Data[]>(() => {
    if (!result?.samples.length) return [];
    const ids = new Set(result.classification.used_ids ?? []);
    const observations: Data = {
      type: 'scatter', mode: 'markers', name: 'SPHEREx measured',
      x: result.samples.map(s => s.wavelength_um), y: result.samples.map(s => s.flux_mjy),
      marker: { color: '#f0bd72', size: 8, symbol: result.samples.map(s => ids.has(s.id) ? 'diamond' : 'circle-open') },
      error_y: { type: 'data', array: result.samples.map(s => s.uncertainty_mjy), visible: true, color: '#d8a967' },
      error_x: { type: 'data', array: result.samples.map(s => s.bandwidth_um / 2), visible: true, color: '#a88657' },
      text: result.samples.map(s => `${s.timestamp} UTC<br>±${s.uncertainty_mjy.toPrecision(3)} mJy · ${s.snr.toFixed(1)}σ`),
      hovertemplate: '%{x:.4f} µm<br>%{y:.4g} mJy<br>%{text}<extra>SPHEREx</extra>',
    };
    const templates: Data[] = overlay ? result.classification.matches.map((m, i) => ({
      type: 'scatter', mode: 'markers', name: m.kind, x: m.wavelength_um, y: m.flux_mjy,
      marker: { color: colors[i], size: 9, symbol: ['square-open', 'triangle-up-open', 'x'][i] },
      hovertemplate: '%{x:.4f} µm<br>%{y:.4g} mJy<extra>%{fullData.name}</extra>',
    })) : [];
    return [...templates, observations];
  }, [result, overlay]);

  const samples = result?.samples ?? [];
  const classification = result?.classification;
  const wavelengthRange = samples.length
    ? `${samples[0].wavelength_um.toFixed(2)}–${samples.at(-1)!.wavelength_um.toFixed(2)} µm`
    : 'No usable bands';

  return <section className="panel fingerprint-panel" aria-label="Spectral Fingerprint">
    <div className="fingerprint-heading">
      <span className="fingerprint-icon"><Waves size={21} aria-hidden="true" /></span>
      <div><span className="eyebrow">SPHEREx · SOURCE SPECTRUM</span>
        <h2>Spectral Fingerprint</h2>
        <p>{target?.label ?? 'See how an object’s infrared brightness changes with wavelength.'}</p>
      </div>
    </div>
    {!target ? <p className="fingerprint-empty">Select a source in the sky image, or choose a candidate in Investigate.</p> : <>
      <div className="fingerprint-controls">
        <label>Observations<select value={scope} onChange={event => setScope(event.target.value)}>
          <option value="library">Cached observation library</option><option value="session">Current workspace only</option>
        </select></label>
        {!target.moving && <label>Date window<select value={days} onChange={event => setDays(event.target.value)}>
          <option value="1">±1 day</option><option value="7">±7 days</option><option value="30">±30 days</option>
        </select></label>}
        {result && <p>{result.motion ? 'Between the two selected epochs' : `Centered on ${result.anchor.slice(0, 10)} UTC`}</p>}
      </div>
      {loading && <p className="fingerprint-empty" role="status"><LoaderCircle size={16} className="spin" /> Measuring native FITS pixels…</p>}
      {current?.error && <div className="fingerprint-empty" role="alert">{current.error} <button className="secondary-button" onClick={() => setRetry(r => r + 1)}>Retry</button></div>}
      {result && classification && <div className="fingerprint-body">
        <dl className="fingerprint-metrics">
          <div><dt>FITS measurements</dt><dd>{samples.length} <small>of {result.scanned} checked</small></dd></div>
          <div><dt>Measured range</dt><dd>{wavelengthRange}</dd></div>
          <div><dt>Reference fit</dt><dd>{classification.status === 'resemblance' ? classification.matches[0].kind : classification.status === 'unavailable' ? 'Library unavailable' : 'Insufficient data'}</dd></div>
        </dl>
        {!!classification.matches.length && <label className="check-label fingerprint-overlay">
          <input type="checkbox" checked={overlay} onChange={event => setOverlay(event.target.checked)} /> Overlay scaled reference bands
        </label>}
        {samples.length ? <>
          <Chart data={traces} xTitle="Wavelength (µm)" yTitle="Flux density (mJy)" legend />
          <p className="fingerprint-caption">Vertical bars: 1σ flux uncertainty. Horizontal bars: filter bandwidth. {classification.used_ids?.length ? 'Diamonds mark observations used for matching. Reference symbols show predicted band averages.' : 'Open circles show individual measurements, including low signal and negative flux.'}</p>
        </> : <p className="fingerprint-empty">No usable ePSF measurements. Add DR1 or QR3 observations of this position within the date window, or check the exclusions below.</p>}
        <div className="fingerprint-verdict" role="status">
          <strong>{classification.status === 'resemblance' ? 'Closest resemblance' : classification.status === 'unavailable' ? 'Reference comparison unavailable' : 'Insufficient data for classification'}</strong>
          <p>{classification.reason}</p>
          {classification.points > 0 && <p>Reference coverage: {classification.points} independent wavelength bands across {classification.span_um?.toFixed(2)} µm.</p>}
          {classification.matches.length > 0 && <ol className="fingerprint-matches">{classification.matches.map((m, i) =>
            <li key={m.kind}><span className="fingerprint-rank" style={{ color: colors[i] }}>{i + 1}</span>
              <div><strong>{m.kind}</strong><a href={m.citation} target="_blank" rel="noreferrer">{m.object} <ExternalLink size={12}/></a></div>
              <span title="Reduced chi-squared; smaller means a closer fit">χ²ᵣ {m.reduced_chi2.toFixed(2)}</span>
              <a href={m.data_url} target="_blank" rel="noreferrer" aria-label={`Open ${m.object} reference FITS`}>FITS <ExternalLink size={12}/></a>
            </li>)}</ol>}
          <a className="fingerprint-library" href={classification.library_url} target="_blank" rel="noreferrer">NASA IRTF SpeX reference library <ExternalLink size={12}/></a>
        </div>
        <p className="fingerprint-caption">{result.motion ? 'Positions follow a tentative linear path between the two residuals; no extrapolation. ' : 'Measurements from different dates may include source variability. '}
          Fits use a local background{result.zodi_subtracted ? ' after subtracting the FITS ZODI model' : ''}. Uncertainties exclude calibration, crowding and model systematics.
          {result.eligible > result.scanned && ` Only the first ${result.scanned} of ${result.eligible} eligible cached files were checked.`}</p>
        <details className="assumptions">
          <summary>Measurement details and exclusions ({result.unavailable.length})</summary>
          <p>Wavelengths use FITS WCS-WAVE. Templates are averaged in fully covered bands using an approximate rectangular passband, then fit with one brightness scale. Similarity to a small template library is not an object identification.</p>
          {!!samples.length && <div className="lab-table-wrap"><table className="lab-table"><thead><tr>
            <th>Observation / UTC</th><th>µm ± half-band</th><th>mJy ± 1σ</th><th>Signal / noise</th><th>Fit χ²ᵣ</th><th>Center FLAGS</th>
          </tr></thead><tbody>{samples.map(s => <tr key={s.id}>
            <td>{s.source_url ? <a href={s.source_url}>{s.filename}</a> : s.filename}<br/>{s.timestamp}</td>
            <td>{s.wavelength_um.toFixed(4)} ± {(s.bandwidth_um/2).toFixed(4)}</td>
            <td>{s.flux_mjy.toPrecision(4)} ± {s.uncertainty_mjy.toPrecision(3)}</td><td>{s.snr.toFixed(1)}</td><td>{s.reduced_chi2.toFixed(2)}</td><td>{s.center_flags}</td>
          </tr>)}</tbody></table></div>}
          {!!result.unavailable.length && <ul>{result.unavailable.map(s => <li key={s.id}><code>{s.id.slice(0, 8)}</code> · {s.reason}</li>)}</ul>}
        </details>
      </div>}
    </>}
  </section>;
}
