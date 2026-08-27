'use client';

/**
 * Direction of observed price movement, plus the two clocks that matter.
 *
 * Two timestamps sit side by side here on purpose, because collapsing them is the
 * mistake this strip exists to prevent:
 *
 * *Observed to* is the last session the data contains. It is the date every number on
 * this page belongs to.
 *
 * *Viewed* is the reader's own clock, updated live. It is the time right now, and it is
 * labelled as the page's clock rather than a market time — a page that shows only "now"
 * next to a price invites the reading that the price is from now.
 *
 * The direction label is a count, not an opinion: four independent readings are taken
 * from the same closes and the label reports which way most of them point, with the
 * tally shown so a reader can check it. It describes what the price did up to the
 * observed-to date and says nothing about what happens next.
 */
import { useEffect, useState } from 'react';

export interface DirectionBlock {
  available: boolean;
  why?: string;
  state?: 'advancing' | 'declining' | 'mixed';
  label?: string;
  readings?: { name: string; detail: string; points: string }[];
  agreeing?: number;
  total_readings?: number;
  summary?: string;
  observed_to?: string | null;
  session_change_pct?: number | null;
  basis?: string;
  scope_note?: string;
}

/** The viewer's own clock, in their timezone, refreshed once a second. */
function useNow(): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export function DirectionStrip({
  direction,
  observedTo,
}: {
  direction?: DirectionBlock;
  observedTo: string;
}) {
  const now = useNow();
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <div className="direction" data-state={direction?.state ?? 'unknown'}>
      <div className="direction__verdict">
        <span className="direction__label">Observed price direction</span>
        <span className="direction__state">
          {direction?.available ? direction.label : 'INSUFFICIENT DATA'}
        </span>
        <span className="direction__tally">
          {direction?.available ? direction.summary : direction?.why}
        </span>
      </div>

      {direction?.available && direction.readings ? (
        <ul className="direction__readings">
          {direction.readings.map((r) => (
            <li key={r.name} data-points={r.points}>
              <span className="direction__readingName">{r.name}</span>
              <span className="direction__readingDetail">{r.detail}</span>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="direction__clocks">
        <div>
          <span className="direction__clockLabel">Observed to</span>
          <span className="direction__clockValue">{observedTo}</span>
          <span className="direction__clockNote">last session in the data</span>
        </div>
        <div>
          <span className="direction__clockLabel">Viewed</span>
          <span className="direction__clockValue" suppressHydrationWarning>
            {now
              ? `${now.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} · ${now.toLocaleTimeString('en-GB', { hour12: false })}`
              : '—'}
          </span>
          <span className="direction__clockNote">
            your clock{tz ? ` · ${tz}` : ''}, not a market time
          </span>
        </div>
      </div>

      {direction?.scope_note ? (
        <p className="direction__scope">{direction.scope_note}</p>
      ) : null}
    </div>
  );
}
