import Link from 'next/link';

import {
  RISK_STATE_COLOR,
  RISK_STATE_COPY,
  STATUS_TONE,
  type ResearchStatus,
  type RiskState,
} from '@/lib/types';

export function StatCard({
  label,
  value,
  note,
  href,
}: {
  label: string;
  value: string;
  note?: string;
  href?: string;
}) {
  const body = (
    <>
      <div className="card__label">{label}</div>
      <div className="card__value">{value}</div>
      {note ? <div className="card__note">{note}</div> : null}
    </>
  );
  return href ? (
    <Link href={href} className="card">
      {body}
    </Link>
  ) : (
    <div className="card">{body}</div>
  );
}

/**
 * A risk state, with a shape cue as well as colour.
 *
 * Colour alone would fail anyone with a colour-vision deficiency and anyone printing in
 * greyscale, so the label carries the meaning and the dot carries only emphasis.
 */
export function StatePill({ state }: { state: RiskState }) {
  const copy = RISK_STATE_COPY[state] ?? { label: state, meaning: '' };
  return (
    <span
      className="pill"
      style={{ background: RISK_STATE_COLOR[state] ?? '#666' }}
      title={copy.meaning}
    >
      {copy.label}
    </span>
  );
}

export function StatusChip({ status }: { status: ResearchStatus | string }) {
  const tone = STATUS_TONE[status as ResearchStatus] ?? 'neutral';
  const cls =
    tone === 'good'
      ? 'chip chip--good'
      : tone === 'warn'
        ? 'chip chip--warn'
        : tone === 'bad'
          ? 'chip chip--bad'
          : 'chip';
  return <span className={cls}>{String(status).replace(/_/g, ' ')}</span>;
}

export function ScoreBar({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className="muted">n/a</span>;
  }
  const clamped = Math.max(0, Math.min(1, value));
  return (
    <div className="bar" role="img" aria-label={`score ${clamped.toFixed(3)}`}>
      <div className="bar__fill" style={{ width: `${clamped * 100}%` }} />
    </div>
  );
}

/**
 * Shown wherever an artifact has not been exported. Names what is missing and how to
 * produce it rather than rendering a plausible-looking empty chart.
 */
export function NoData({ what, note }: { what: string; note?: string }) {
  return (
    <div className="empty">
      <strong>{what} not available.</strong>
      <p style={{ margin: '6px 0 0' }}>
        {note ??
          'This view renders only exported research artifacts. Nothing is generated at request time.'}
      </p>
      <p style={{ margin: '6px 0 0' }}>
        Produce it with <code>python scripts/build_dataset.py</code>,{' '}
        <code>python scripts/run_experiments.py</code>,{' '}
        <code>python scripts/run_research_angles.py</code>, then{' '}
        <code>python scripts/export_app_data.py</code>.
      </p>
    </div>
  );
}

export function Caveat({ children }: { children: React.ReactNode }) {
  return (
    <aside className="notice notice--compact">
      <span className="notice__badge">Caveat</span>
      <p className="notice__text">{children}</p>
    </aside>
  );
}

/**
 * The evidence boundary shown in Product mode (research-angle section 50).
 *
 * Product mode stays simple, but a user reading a risk state deserves to know what that
 * state rests on. Four short lines and a link is the whole budget; the depth lives one
 * click away in Research mode.
 */
export function EvidenceBoundary({
  items,
  href = '/research/limitations',
}: {
  items: string[];
  href?: string;
}) {
  return (
    <section className="boundary">
      <h3>Evidence boundary</h3>
      <ul>
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
      <p style={{ margin: '8px 0 0' }}>
        <Link href={href}>What this does and does not support →</Link>
      </p>
    </section>
  );
}

/** Product-mode explanation with an escape hatch into the research depth. */
export function WhyFlagged({
  reasons,
  researchHref,
}: {
  reasons: { label: string; value: string }[];
  researchHref: string;
}) {
  return (
    <details className="disclosure">
      <summary>Why was this flagged?</summary>
      <table>
        <tbody>
          {reasons.map((r) => (
            <tr key={r.label}>
              <td>{r.label}</td>
              <td className="num">{r.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ margin: '10px 0 0' }}>
        <Link href={researchHref}>Technical explanation, methods and attributions →</Link>
      </p>
    </details>
  );
}
