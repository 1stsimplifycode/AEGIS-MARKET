import Link from 'next/link';

import type { IndexDetail, Sourced } from '@/lib/product';
import { RECENCY_COPY, level, signedPct } from '@/lib/product';

import { Change, SourceLine } from './Bits';

/**
 * The market context every weekly slice is read against.
 *
 * The sixteen weeks build a capability; the benchmark is the world that capability is
 * pointed at. Putting it above each week gives the programme one domain instead of
 * sixteen unrelated exercises — someone demonstrating week 7 can say what the market was
 * doing while they demonstrate it.
 *
 * It is context and nothing more. The strip never implies the week's modules were run on
 * the index, or that the index is what they assessed: the analysis below it is
 * instrument-level, and where the two windows do not meet, the NIFTY 50 page says so.
 */
export function MarketStrip({
  index,
  note,
}: {
  index: Sourced<IndexDetail>;
  note?: string;
}) {
  if (!index.data) return null;
  const i = index.data;
  return (
    <aside className="marketStrip">
      <div className="marketStrip__main">
        <span className="marketStrip__label">Market context</span>
        <Link href="/markets/nifty-50" className="marketStrip__name">
          {i.display_name}
        </Link>
        <span className="marketStrip__level">{level(i.close)}</span>
        <Change value={i.change_pct} />
        <span className="marketStrip__session">
          {RECENCY_COPY[i.recency]} · {i.last_session}
        </span>
      </div>
      <dl className="marketStrip__stats">
        <div>
          <dt>Volatility</dt>
          <dd>
            {i.volatility_20d !== null ? `${(i.volatility_20d * 100).toFixed(1)}%` : '—'}
          </dd>
        </div>
        <div>
          <dt>Drawdown</dt>
          <dd>{i.drawdown !== null ? signedPct(i.drawdown) : '—'}</dd>
        </div>
        <div>
          <dt>52-week range</dt>
          <dd>
            {level(i.low_52w)} – {level(i.high_52w)}
          </dd>
        </div>
      </dl>
      {note ? <p className="marketStrip__note">{note}</p> : null}
      <SourceLine of={index} />
    </aside>
  );
}
