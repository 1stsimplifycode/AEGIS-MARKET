import type { AlignmentPair, AlignmentMatrix, Sourced } from '@/lib/product';
import { ALIGNMENT_COPY } from '@/lib/product';

import { SourceLine } from './Bits';
import { Disclosure } from './Disclosure';

/**
 * Whether two bodies of evidence can be spoken about together.
 *
 * The panel exists because the honest answer to "what does the benchmark say about the
 * model's findings" is currently *nothing*, and an interface that left that to be
 * inferred from an empty chart would be inviting the reader to infer something else.
 *
 * Product mode gets one line and a way in. Research mode gets the windows, the overlap,
 * the coverage ratio and the threshold that produced the verdict — because a status is
 * only checkable if the arithmetic behind it is visible.
 *
 * Nothing here is stored. The status arrives computed from the sessions each source
 * holds, so this component will start reporting ALIGNED the day an overlapping source is
 * ingested, without being touched.
 */

function Bar({ pair }: { pair: AlignmentPair }) {
  const a = pair.source_a;
  const b = pair.source_b;
  const starts = [a.start, b.start].filter(Boolean) as string[];
  const ends = [a.end, b.end].filter(Boolean) as string[];
  if (!starts.length || !ends.length) return null;

  const min = new Date(starts.sort()[0]).getTime();
  const max = new Date(ends.sort()[ends.length - 1]).getTime();
  const span = max - min || 1;
  const place = (from: string | null, to: string | null) => {
    if (!from || !to) return null;
    const left = ((new Date(from).getTime() - min) / span) * 100;
    const width = ((new Date(to).getTime() - new Date(from).getTime()) / span) * 100;
    return { left: `${left}%`, width: `${Math.max(width, 0.6)}%` };
  };

  const aPos = place(a.start, a.end);
  const bPos = place(b.start, b.end);
  const overlapPos = place(pair.overlap_start, pair.overlap_end);

  return (
    <div className="alignBar" data-status={pair.alignment_status}>
      <div className="alignBar__row">
        <span className="alignBar__name">{a.label}</span>
        <span className="alignBar__track">
          {aPos ? <span className="alignBar__span" style={aPos} /> : null}
          {overlapPos ? (
            <span className="alignBar__overlap" style={overlapPos} />
          ) : null}
        </span>
        <span className="alignBar__count">{a.sessions.toLocaleString('en-IN')}</span>
      </div>
      <div className="alignBar__row">
        <span className="alignBar__name">{b.label}</span>
        <span className="alignBar__track">
          {bPos ? <span className="alignBar__span" style={bPos} /> : null}
          {overlapPos ? (
            <span className="alignBar__overlap" style={overlapPos} />
          ) : null}
        </span>
        <span className="alignBar__count">{b.sessions.toLocaleString('en-IN')}</span>
      </div>
      <div className="alignBar__axis">
        <span>{starts[0]}</span>
        <span>
          {pair.overlap_sessions === 0
            ? 'no shared sessions'
            : `${pair.overlap_sessions.toLocaleString('en-IN')} shared`}
        </span>
        <span>{ends[ends.length - 1]}</span>
      </div>
    </div>
  );
}

/** One pair, at both depths. */
export function AlignmentCard({ pair }: { pair: AlignmentPair }) {
  const copy = ALIGNMENT_COPY[pair.alignment_status];
  return (
    <article className="alignCard" data-status={pair.alignment_status}>
      <header className="alignCard__head">
        <span className="alignCard__pair">
          {pair.source_a.label} <span aria-hidden="true">×</span> {pair.source_b.label}
        </span>
        <span className="tag" data-tone={copy.tone}>
          {copy.label}
        </span>
      </header>

      <p className="alignCard__product modeOnly modeOnly--product">{copy.product}</p>
      <p className="alignCard__product modeOnly modeOnly--research">{pair.summary}</p>

      <Bar pair={pair} />

      <div className="modeOnly modeOnly--research">
        <dl className="alignCard__facts">
          <div>
            <dt>Overlap</dt>
            <dd>
              {pair.overlap_sessions} sessions
              {pair.overlap_start
                ? ` · ${pair.overlap_start} → ${pair.overlap_end}`
                : ''}
            </dd>
          </div>
          <div>
            <dt>Coverage ratio</dt>
            <dd>{(pair.coverage_ratio * 100).toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Status rule</dt>
            <dd>
              aligned at ≥ {(pair.thresholds.aligned_at * 100).toFixed(0)}% and ≥{' '}
              {pair.thresholds.minimum_sessions} sessions
            </dd>
          </div>
          <div>
            <dt>Combined analysis</dt>
            <dd>{pair.permits.combined_analysis ? 'permitted' : 'not permitted'}</dd>
          </div>
        </dl>
        {pair.why_it_matters ? (
          <p className="small muted">{pair.why_it_matters}</p>
        ) : null}
      </div>
    </article>
  );
}

/**
 * The whole matrix, for the research surface.
 */
export function AlignmentPanel({
  alignment,
  title = 'Evidence alignment',
}: {
  alignment: Sourced<AlignmentMatrix>;
  title?: string;
}) {
  const m = alignment.data;
  if (!m) {
    return (
      <div className="productEmpty">
        <h3>Alignment not computed</h3>
        <p>{alignment.note}</p>
      </div>
    );
  }
  return (
    <section className="alignPanel">
      <div className="home__sectionHead">
        <h2>{title}</h2>
        <span className="home__asof">
          {m.counts.aligned} aligned · {m.counts.partial} partial ·{' '}
          {m.counts.not_aligned} not aligned
        </span>
      </div>

      <div className="alignGrid">
        {m.pairs.map((p) => (
          <AlignmentCard
            key={`${p.source_a.source_id}-${p.source_b.source_id}`}
            pair={p}
          />
        ))}
      </div>

      <SourceLine of={alignment} />

      <Disclosure summary="Understand why — how alignment is decided" tone="quiet">
        <p style={{ marginTop: 0 }}>{m.reading}</p>
        <p>{m.pairs[0]?.coverage_ratio_note}</p>
        <p>{m.pairs[0]?.permits.note}</p>
        <h4>If this changes</h4>
        <p>{m.future_path}</p>
        <div className="modeOnly modeOnly--research">
          <h4>Coverage of every source</h4>
          <div className="tableWrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Source</th>
                  <th scope="col">Kind</th>
                  <th scope="col">From</th>
                  <th scope="col">To</th>
                  <th scope="col">Sessions</th>
                </tr>
              </thead>
              <tbody>
                {m.sources.map((s) => (
                  <tr key={s.source_id}>
                    <th scope="row" className="mono">
                      {s.source_id}
                    </th>
                    <td className="mono small">{s.kind}</td>
                    <td className="mono">{s.start ?? '—'}</td>
                    <td className="mono">{s.end ?? '—'}</td>
                    <td className="mono">{s.sessions.toLocaleString('en-IN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Disclosure>
    </section>
  );
}

/**
 * A single line for a page that is showing one of the two sources.
 *
 * Used where a reader might otherwise assume a relationship — the benchmark page, a
 * weekly slice — so the assumption is answered before it forms.
 */
export function AlignmentNote({
  pair,
  href = '/research/alignment',
}: {
  pair: AlignmentPair | null;
  href?: string;
}) {
  if (!pair) return null;
  const copy = ALIGNMENT_COPY[pair.alignment_status];
  return (
    <p className="alignNote" data-tone={copy.tone}>
      <span className="alignNote__badge">{copy.label}</span>
      <span className="modeOnly modeOnly--inline modeOnly--product">{copy.product}</span>
      <span className="modeOnly modeOnly--inline modeOnly--research">{pair.summary}</span>{' '}
      <a href={href}>Understand evidence →</a>
    </p>
  );
}
