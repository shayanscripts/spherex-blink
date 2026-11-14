'use client';

import { useEffect, useState } from 'react';
import { ExternalLink, LoaderCircle, Telescope } from 'lucide-react';
import { request } from '@/lib/api';

export type CatalogPosition = { ra: number; dec: number };
type CatalogResult = {
  radius_arcsec: number;
  truncated: boolean;
  objects: { name: string; type: string; spectral_type: string | null; separation_arcsec: number; url: string }[];
};

export default function NearbyObjects({ position }: { position: CatalogPosition }) {
  const { ra, dec } = position;
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<{ key: string; data?: CatalogResult; failed?: boolean }>();
  const key = `${ra},${dec},${retry}`;
  const current = state?.key === key ? state : undefined;

  useEffect(() => {
    const controller = new AbortController();
    request<CatalogResult>(`/catalog/nearby?ra=${ra}&dec=${dec}`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ key, data }); })
      .catch(() => { if (!controller.signal.aborted) setState({ key, failed: true }); });
    return () => controller.abort();
  }, [key, ra, dec]);

  const data = current?.data;
  return <section className="panel nearby-panel" aria-label="Nearby known objects">
    <div className="nearby-heading">
      <Telescope size={19} aria-hidden="true"/>
      <div><h2>Nearby known objects</h2><p>SIMBAD catalog · {ra.toFixed(5)}°, {dec.toFixed(5)}°</p></div>
    </div>
    {!current && <p className="nearby-status" role="status"><LoaderCircle size={15} className="spin" aria-hidden="true"/> Looking up this position…</p>}
    {current?.failed && <div className="nearby-status" role="status">
      SIMBAD lookup unavailable. <button type="button" className="secondary-button" onClick={() => setRetry(n => n + 1)}>Retry</button>
    </div>}
    {data && (data.objects.length ? <>
      <ol className="nearby-list">{data.objects.map((object, index) => <li key={object.name}>
        <div><strong>{object.type}</strong>{index === 0 && <span className="nearby-nearest">Closest listed</span>}
          <a href={object.url} target="_blank" rel="noreferrer">{object.name} <ExternalLink size={12} aria-hidden="true"/></a>
          {object.spectral_type && <small>Spectral type: {object.spectral_type}</small>}
        </div>
        <span title="Angular separation from the marker">{object.separation_arcsec.toFixed(1)}″ away</span>
      </li>)}</ol>
      <p className="nearby-status">{data.truncated ? 'Showing the closest catalog entries. ' : ''}A nearby object may not be the one that changed.</p>
    </> : <p className="nearby-status" role="status">No SIMBAD objects found within {data.radius_arcsec}″. The source of this change is unknown.</p>)}
  </section>;
}
