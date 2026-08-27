import Link from 'next/link';

import { LifecycleScopeNotice } from '@/components/ui/NonAdvisoryNotice';
import { Trace } from '@/components/visualization/Sparkline';
import { fmt } from '@/lib/data';
import type { LifecycleTrajectory } from '@/lib/types';

const PHASE_COLOR: Record<string, string> = {
  ENTRY: 'rgba(0, 114, 178, 0.10)',
  HOLDING: 'rgba(213, 94, 0, 0.08)',
  RESOLUTION: 'rgba(0, 158, 115, 0.10)',
};

const STATE_COPY: Record<string, string> = {
  STABLE: 'risk flat within tolerance',
  IMPROVING: 'risk falling on a sustained basis',
  DETERIORATING: 'risk rising on a sustained basis',
  HIGH_UNCERTAINTY: 'the estimate is too uncertain to call a direction',
  MATERIAL_CHANGE: 'a detected change point in the trajectory',
  RESOLVED: 'the window closed with risk back at baseline',
};

function runs(labels: string[], dates: string[]) {
  const out: { label: string; from: string; to: string; n: number }[] = [];
  let start = 0;
  for (let i = 1; i <= labels.length; i += 1) {
    if (i === labels.length || labels[i] !== labels[start]) {
      out.push({
        label: labels[start],
        from: dates[start],
        to: dates[i - 1],
        n: i - start,
      });
      start = i;
    }
  }
  return out;
}

/**
 * Product-mode risk profile timeline.
 *
 * Describes how the risk estimate for one instrument moved across an analysis window,
 * broken into observed states. It answers "what has changed and when", never "what should
 * be done", and there is no path from what it renders to the latter. The scope denial it
 * displays is the shared one, so the enumeration lives in a single place.
 *
 * The phases are ENTRY, HOLDING and RESOLUTION because those are the segments of the
 * *analysis window*. They describe where an observation sits in that window and carry
 * no transactional meaning of any kind.
 */
export function RiskProfileTimeline({ t }: { t: LifecycleTrajectory }) {
  const phaseRuns = runs(t.phase, t.dates);
  const stateRuns = runs(t.state, t.dates).filter((r) => r.n >= 2);
  const bands = phaseRuns.map((r) => ({
    from: r.from,
    to: r.to,
    label: r.label,
    color: PHASE_COLOR[r.label] ?? 'rgba(120,120,120,0.08)',
  }));

  return (
    <section>
      <h2>Risk profile timeline</h2>
      <p className="small muted">
        How this instrument&rsquo;s risk estimate moved across {t.n_sessions} sessions,
        {' '}
        {t.first_date} to {t.last_date}. Shading marks the segment of the analysis window;
        dashed lines mark points where the trajectory changed behaviour.
      </p>
      <Trace
        dates={t.dates}
        values={t.risk}
        spread={t.uncertainty}
        bands={bands}
        markers={t.change_points.map((i) => ({
          at: t.dates[i],
          label: 'change point',
          dash: '3 2',
        }))}
        hlines={[
          { at: 0.25, label: 'moderate' },
          { at: 0.5, label: 'elevated' },
          { at: 0.75, label: 'high' },
        ]}
        label={`risk profile for ${t.symbol}`}
      />

      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              <th>From</th>
              <th>To</th>
              <th>Observed state</th>
              <th>What that means</th>
            </tr>
          </thead>
          <tbody>
            {stateRuns.map((r) => (
              <tr key={`${r.from}-${r.label}`}>
                <td className="mono">{r.from}</td>
                <td className="mono">{r.to}</td>
                <td>{r.label.replace(/_/g, ' ').toLowerCase()}</td>
                <td className="small muted">{STATE_COPY[r.label] ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="small muted">
        Currently {t.final_band.toLowerCase()} at {fmt(t.final_risk)}. The underlying
        quantity is continuous; the bands exist only so a movement can be named.{' '}
        <Link href="/research/lifecycle">
          How this is computed, and what it cannot tell you
        </Link>
        .
      </p>

      <LifecycleScopeNotice />
    </section>
  );
}
