import Link from 'next/link';

import type { EvidenceSource, EvidenceSummary, Sourced } from '@/lib/product';

import { SourceLine } from './Bits';
import { Disclosure } from './Disclosure';

/**
 * "What evidence does AEGIS actually have for this market period?"
 *
 * One component family, used everywhere that question is asked, so the answer cannot
 * differ between two pages. Each piece renders a status the backend computed for one
 * specific pair — the alignment layer is consulted, never reimplemented, and no threshold
 * or session count is written into this file.
 *
 * The registers are separated by CSS rather than by branching. Product mode sees a mark,
 * a verdict and a sentence; research mode sees the sessions, the ratio and the windows.
 * Both are in the prerendered HTML, so switching depth changes what is shown and never
 * what is true.
 */

const MARKS: Record<string, string> = {
  check: '✓',
  partial: '◑',
  cross: '○',
  unknown: '?',
};

/** The verdict alone: a mark, a word, a colour. */
export function EvidenceStatusBadge({
  mark,
  badge,
  tone,
}: {
  mark: string;
  badge: string;
  tone: string;
}) {
  return (
    <span className="evBadge" data-tone={tone}>
      <span className="evBadge__mark" aria-hidden="true">
        {MARKS[mark] ?? '·'}
      </span>
      {badge}
    </span>
  );
}

/**
 * One source, as a card: what it is, when it covers, how much it shares, and the verdict.
 */
export function EvidenceAlignmentCard({ source }: { source: EvidenceSource }) {
  const aligned = source.status === 'ALIGNED';
  return (
    <article className="evCard" data-status={source.status}>
      <header className="evCard__head">
        <span className="evCard__title">{source.product_label}</span>
        <EvidenceStatusBadge
          mark={source.mark}
          badge={source.badge}
          tone={source.tone}
        />
      </header>

      <p className="evCard__blurb">{source.product_blurb}</p>

      <dl className="evCard__facts">
        <div>
          <dt>Period</dt>
          <dd>{source.period}</dd>
        </div>
        <div>
          <dt>Shared sessions</dt>
          <dd>
            {source.shared_sessions.toLocaleString('en-IN')}
            <span className="evCard__of">
              {' / '}
              {source.index_sessions.toLocaleString('en-IN')}
            </span>
          </dd>
        </div>
      </dl>

      <p className="evCard__status modeOnly modeOnly--product">
        {source.product_status}
      </p>
      <p className="evCard__status modeOnly modeOnly--research">{source.summary}</p>

      <div className="modeOnly modeOnly--research evCard__research">
        <dl className="evCard__facts">
          <div>
            <dt>Coverage ratio</dt>
            <dd>{(source.coverage_ratio * 100).toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Source window</dt>
            <dd className="mono">
              {source.period_from} → {source.period_to}
            </dd>
          </div>
          {source.overlap_from ? (
            <div>
              <dt>Overlap</dt>
              <dd className="mono">
                {source.overlap_from} → {source.overlap_to}
              </dd>
            </div>
          ) : null}
          <div>
            <dt>Combined analysis</dt>
            <dd>{source.permits.combined_analysis ? 'permitted' : 'not permitted'}</dd>
          </div>
        </dl>
        <p className="small muted">{source.source_note}</p>
      </div>

      <Link className="evCard__link" href={aligned ? source.href : '/research/alignment'}>
        {aligned ? 'View evidence' : 'Why?'} <span aria-hidden="true">→</span>
      </Link>
    </article>
  );
}

/**
 * The compact form, for a card that already has a job.
 *
 * Three marks and three words. It exists so the home page can answer the question at a
 * glance without becoming a second alignment panel.
 */
export function EvidenceCoverageSummary({
  summary,
  href = '/markets/nifty-50',
}: {
  summary: EvidenceSummary;
  href?: string;
}) {
  return (
    <div className="evSummary">
      <span className="evSummary__label">Evidence available</span>
      <ul className="evSummary__list">
        {summary.sources.map((s) => (
          <li key={s.source_id} data-tone={s.tone}>
            <span className="evSummary__mark" aria-hidden="true">
              {MARKS[s.mark] ?? '·'}
            </span>
            {s.product_label}
          </li>
        ))}
      </ul>
      <Link className="evSummary__cta" href={href}>
        Explore <span aria-hidden="true">→</span>
      </Link>
    </div>
  );
}

/** A one-line form for a page that is showing a week or a scenario. */
export function EvidenceStrip({ summary }: { summary: EvidenceSummary }) {
  return (
    <p className="evStrip">
      <span className="evStrip__label">Evidence for this market period</span>
      {summary.sources.map((s) => (
        <span className="evStrip__item" key={s.source_id} data-tone={s.tone}>
          <span aria-hidden="true">{MARKS[s.mark] ?? '·'}</span> {s.product_label}
        </span>
      ))}
      <Link className="evStrip__cta" href="/research/alignment">
        Understand evidence <span aria-hidden="true">→</span>
      </Link>
    </p>
  );
}

/**
 * The full section: the cards, the headline, and the detail behind a disclosure.
 *
 * The disclosure carries the distinction that is easiest to lose — an aligned source
 * covers the same sessions, which is not the same as an experiment having used it. That
 * sentence is the difference between "evidence is available" and "evidence was used", and
 * the product would be overclaiming without it.
 */
export function EvidenceSection({
  evidence,
  title = 'Market evidence',
}: {
  evidence: Sourced<EvidenceSummary>;
  title?: string;
}) {
  const e = evidence.data;
  if (!e) {
    return (
      <div className="productEmpty">
        <h3>Evidence not computed</h3>
        <p>{evidence.note}</p>
      </div>
    );
  }
  return (
    <section className="home__section">
      <div className="home__sectionHead">
        <h2>{title}</h2>
        <span className="home__asof">
          {e.index_period} · {e.index_sessions.toLocaleString('en-IN')} sessions
        </span>
      </div>

      <p className="evHeadline">{e.headline}</p>

      <div className="evGrid">
        {e.sources.map((s) => (
          <EvidenceAlignmentCard key={s.source_id} source={s} />
        ))}
      </div>

      <SourceLine of={evidence} />

      <Disclosure summary="Understand why — available evidence is not used evidence">
        <p style={{ marginTop: 0 }} className="modeOnly modeOnly--product">
          {e.experiments_using_index.product_note}
        </p>
        <p style={{ marginTop: 0 }} className="modeOnly modeOnly--research">
          {e.experiments_using_index.research_note}
        </p>
        <p>
          A source marked aligned covers the same sessions as the benchmark, so a result
          about both would at least be about a real period. Whether any analysis has
          actually been run that way is a separate question, and the answer today is no:{' '}
          {e.experiments_using_index.count} experiments in this project take the index as
          an input.
        </p>
        <p className="instrument__deeper">
          <Link href="/research/alignment">See the full alignment matrix →</Link>
          <span className="small muted">
            Every pair, with its windows, overlap, coverage ratio and the threshold that
            produced the verdict.
          </span>
        </p>
      </Disclosure>
    </section>
  );
}
