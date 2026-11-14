'use client';

import { useId } from 'react';
import { ArrowRight, MoveUpRight } from 'lucide-react';
import { number, type Motion, type Residual } from '@/lib/types';

export type MotionPair = { key: string; motion: Motion; from: Residual; to: Residual; alternatives: boolean };

export function selectMotionPairs(candidates: Residual[], hypotheses: Motion[], resolutionArcsec: number): MotionPair[] {
  const byId = new Map(candidates.map(candidate => [candidate.id, candidate]));
  const pairs = hypotheses.flatMap(motion => {
    const from = byId.get(motion.negative_id);
    const to = byId.get(motion.positive_id);
    // Skip edge fragments and offsets smaller than the matched image's sharpness.
    if (!from || !to || from.edge || to.edge || motion.separation_arcsec < resolutionArcsec) return [];
    return [{ key: `${from.id}-${to.id}`, motion, from, to, alternatives: false }];
  });
  const counts = new Map<number, number>();
  for (const pair of pairs) {
    for (const id of [pair.from.id, pair.to.id]) counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  const strength = ({from, to}: MotionPair) => Math.min(Math.abs(from.peak_sigma), Math.abs(to.peak_sigma));
  return pairs
    .sort((a, b) => strength(b) - strength(a) || a.motion.separation_arcsec - b.motion.separation_arcsec)
    .map(pair => ({ ...pair, alternatives: (counts.get(pair.from.id) ?? 0) > 1 || (counts.get(pair.to.id) ?? 0) > 1 }));
}

export function MotionArrow({ pair, size }: { pair: MotionPair; size: number }) {
  const id = useId();
  const { from, to } = pair;
  const x1 = from.x + .5, y1 = size - from.y - .5;
  const x2 = to.x + .5, y2 = size - to.y - .5;
  const path = `M ${x1} ${y1} L ${(x1+x2)/2} ${(y1+y2)/2} L ${x2} ${y2}`;
  return <svg className="simple-motion-arrow" viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
    <defs><marker id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="3.8" markerHeight="3.8" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/>
    </marker></defs>
    <path d={path} fill="none" stroke="#14171b" strokeWidth="4" vectorEffect="non-scaling-stroke"/>
    <path d={path} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" markerMid={`url(#${id})`}/>
  </svg>;
}

export default function PossibleMotion({ pairs, selected, loading, failed, onSelect }: {
  pairs: MotionPair[]; selected?: MotionPair; loading: boolean; failed: boolean; onSelect: (key: string) => void;
}) {
  return <div className="simple-motion-card">
    <h3><MoveUpRight size={18} aria-hidden="true"/> Possible motion</h3>
    <p>An object could have left a blue mark at its reference position and a red mark at its current position.</p>
    {loading || failed || !pairs.length ? <p role="status">{loading ? 'Checking for pairs…' : failed ? 'Change markers could not be loaded.' : 'No clearly separated blue–red pairs at this threshold. Try another date.'}</p> : <>
      <div className="simple-motion-choices" aria-label="Possible motion pairs">
        {pairs.slice(0, 3).map(pair => <button type="button" key={pair.key} className="secondary-button" aria-pressed={selected?.key === pair.key}
          onClick={() => onSelect(pair.key)} aria-label={`From marker ${pair.from.id} to marker ${pair.to.id}`}>
          #{pair.from.id} <ArrowRight size={12} aria-hidden="true"/> #{pair.to.id}
        </button>)}
      </div>
      {selected && <p className="simple-motion-evidence" aria-live="polite">
        <strong>{number(selected.motion.separation_arcsec, 1)}″ apart</strong> · Reference #{selected.from.id} → Current #{selected.to.id}.
        {selected.alternatives && ' A marker also has another possible partner.'}
      </p>}
      {pairs.length > 3 && <p>Showing 3 of {pairs.length} pairs, ordered by the strength of their weaker mark.</p>}
      <p>Unconfirmed. Brightness changes or image artifacts can also leave a pair.</p>
    </>}
  </div>;
}
