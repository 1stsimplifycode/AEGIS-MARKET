/**
 * The panels both module experiences are assembled from.
 *
 * Product mode and Research mode use the *same* panels wherever the content is the same
 * thing at two depths — a metric is a metric — and different panels only where research
 * mode adds a layer that has no product equivalent, such as the artifact provenance
 * table. That is deliberate: two component trees would be two places for the number to
 * drift.
 */
import Link from 'next/link';

import type {
  ModuleClaim,
  ModuleFigure,
  ModuleInput,
  ModuleLimitation,
  ModuleMetric,
  ModuleRun,
  ModuleTable,
  ResearchModule,
} from '@/lib/moduleTypes';
import { CONFIDENCE_COPY, CONFIDENCE_TONE, PRODUCT_STATUS_COPY } from '@/lib/moduleTypes';

/* -- metrics ------------------------------------------------------------------------- */

export function MetricCard({
  metric,
  showExpression = false,
}: {
  metric: ModuleMetric;
  showExpression?: boolean;
}) {
  return (
    <div className="card metricCard">
      <div className="card__label">{metric.label}</div>
      {metric.unavailable ? (
        <>
          <div className="card__value card__value--muted">not available</div>
          <div className="card__note">{metric.unavailable}</div>
        </>
      ) : (
        <>
          <div className="card__value">{metric.display}</div>
          {metric.note ? <div className="card__note">{metric.note}</div> : null}
        </>
      )}
      {showExpression ? (
        <div className="metricCard__source mono">
          {metric.source ?? 'no artifact'}
          <span className="metricCard__expr">{metric.expression}</span>
        </div>
      ) : null}
    </div>
  );
}

export function MetricGrid({
  metrics,
  showExpression = false,
}: {
  metrics: ModuleMetric[];
  showExpression?: boolean;
}) {
  if (metrics.length === 0) {
    return <p className="muted small">This module reports no scalar metric.</p>;
  }
  return (
    <div className="grid">
      {metrics.map((m) => (
        <MetricCard key={m.label} metric={m} showExpression={showExpression} />
      ))}
    </div>
  );
}

/** Research mode: the same numbers with their lookup, so a reader can check them. */
export function ResearchMetricTable({ metrics }: { metrics: ModuleMetric[] }) {
  if (metrics.length === 0) {
    return <p className="muted small">No research metric is declared for this module.</p>;
  }
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Quantity</th>
            <th className="num">Value</th>
            <th>Artifact</th>
            <th>Lookup</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map((m) => (
            <tr key={m.label}>
              <td>{m.label}</td>
              <td className="num">{m.unavailable ? '—' : m.display}</td>
              <td className="small mono">{m.source ?? '—'}</td>
              <td className="small mono muted">
                {m.unavailable ? m.unavailable : m.expression.split('#')[1]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* -- product-mode framing ------------------------------------------------------------ */

export function UncertaintyCard({ module: mod }: { module: ResearchModule }) {
  const conf = CONFIDENCE_COPY[mod.product.confidence];
  const tone = CONFIDENCE_TONE[mod.product.confidence];
  return (
    <section className={`uncertainty uncertainty--${tone}`}>
      <h3>How far this goes</h3>
      <p className="uncertainty__level">{conf.label}</p>
      <p className="uncertainty__meaning">{conf.meaning}</p>
      <p className="uncertainty__risk">{mod.product.risk}</p>
    </section>
  );
}

export function EvidenceCard({
  module: mod,
  researchHref,
}: {
  module: ResearchModule;
  researchHref: string;
}) {
  const artifacts = mod.research.outputs;
  return (
    <section className="boundary">
      <h3>Evidence used</h3>
      <ul>
        <li>
          {artifacts.length} artifact{artifacts.length === 1 ? '' : 's'} written by{' '}
          <code>{mod.research.adapter}</code>
        </li>
        <li>
          {mod.figures.filter((f) => f.available).length} figure(s) and{' '}
          {mod.tables.filter((t) => t.available).length} table(s) drawn from it
        </li>
        <li>
          {mod.research.claims.length} claim(s) in the ledger rest on this module&apos;s
          evidence
        </li>
        {mod.research.last_run?.at ? (
          <li>Last executed {new Date(mod.research.last_run.at).toUTCString()}</li>
        ) : (
          <li>No execution log is present in this build</li>
        )}
      </ul>
      <p style={{ margin: '8px 0 0' }}>
        <Link href={researchHref}>Why am I seeing this? View the evidence →</Link>
      </p>
    </section>
  );
}

export function ActionList({ actions }: { actions: string[] }) {
  if (actions.length === 0) return null;
  return (
    <section className="actions">
      <h3>What you can do here</h3>
      <ul>
        {actions.map((a) => (
          <li key={a}>{a}</li>
        ))}
      </ul>
    </section>
  );
}

export function InputPanel({ inputs }: { inputs: ModuleInput[] }) {
  if (inputs.length === 0) return null;
  return (
    <section className="inputs">
      <h3>Inputs</h3>
      <dl>
        {inputs.map((i) => (
          <div key={i.kind} className="inputs__row">
            <dt>
              {i.label} <span className="chip">{i.kind}</span>
            </dt>
            <dd>{i.note}</dd>
          </div>
        ))}
      </dl>
      <p className="muted small" style={{ margin: '6px 0 0' }}>
        Every input selects among values the pipeline already produced. No data supplied
        here can enter a research artifact, which is what keeps provenance intact.
      </p>
    </section>
  );
}

/* -- research-mode panels ------------------------------------------------------------ */

export function ExperimentMetadata({
  module: mod,
  run,
}: {
  module: ResearchModule;
  run: ModuleRun | null;
}) {
  return (
    <div className="tableWrap">
      <table>
        <tbody>
          <tr>
            <th style={{ width: 190 }}>Module</th>
            <td className="mono">{mod.id}</td>
          </tr>
          <tr>
            <th>Experiment</th>
            <td className="mono">{mod.research.experiment_id ?? '—'}</td>
          </tr>
          <tr>
            <th>Research question</th>
            <td>{mod.research.research_question}</td>
          </tr>
          <tr>
            <th>Research status</th>
            <td className="mono">{mod.research.status}</td>
          </tr>
          <tr>
            <th>Wrapper status</th>
            <td className="mono">{mod.research.wrapper_status}</td>
          </tr>
          <tr>
            <th>Adapter</th>
            <td className="mono small">{mod.research.adapter}</td>
          </tr>
          <tr>
            <th>Canonical implementation</th>
            <td className="mono small">
              {mod.research.canonical.length
                ? mod.research.canonical.map((c) => <div key={c}>{c}</div>)
                : '—'}
            </td>
          </tr>
          <tr>
            <th>Depends on</th>
            <td className="mono small">
              {mod.research.depends_on.join(', ') || 'nothing'}
            </td>
          </tr>
          <tr>
            <th>Last run</th>
            <td className="small">
              {run?.at ? (
                <>
                  {run.at} · <span className="mono">{run.status}</span> ·{' '}
                  {run.elapsed_s}s · commit{' '}
                  <span className="mono">{run.git_commit?.slice(0, 8) ?? 'n/a'}</span> ·{' '}
                  {run.runs_recorded} run(s) recorded
                </>
              ) : (
                'no execution log in this build'
              )}
            </td>
          </tr>
          <tr>
            <th>Notes</th>
            <td className="small">{mod.research.notes || '—'}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function ProvenancePanel({ module: mod }: { module: ResearchModule }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Direction</th>
            <th>Path</th>
          </tr>
        </thead>
        <tbody>
          {mod.research.inputs.map((i) => (
            <tr key={`in-${i}`}>
              <td>
                <span className="chip">input</span>
              </td>
              <td className="mono small">{i}</td>
            </tr>
          ))}
          {mod.research.outputs.map((o) => (
            <tr key={`out-${o}`}>
              <td>
                <span className="chip chip--good">output</span>
              </td>
              <td className="mono small">{o}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small" style={{ margin: '8px 0 0' }}>
        Regenerate with <code>python scripts/run_module.py --module {mod.id}</code>, then{' '}
        <code>python scripts/export_modules.py</code>. The interface never runs the
        module: it reads what that command wrote.
      </p>
    </div>
  );
}

export function LimitationPanel({
  limitations,
}: {
  limitations: ModuleLimitation[];
}) {
  if (limitations.length === 0) {
    return (
      <p className="muted small">
        No limitation is registered against this module. That means none has been
        identified, not that none exists.
      </p>
    );
  }
  return (
    <div className="limitations">
      {limitations.map((l) => (
        <article key={l.id} className="limitations__item">
          <h4>
            <Link href={`/research/limitations/${l.id}`}>{l.id}</Link> — {l.title}{' '}
            <span className="chip">{l.status.replace(/_/g, ' ')}</span>
          </h4>
          <p>{l.description}</p>
          {l.scope_note ? <p className="limitations__scope">{l.scope_note}</p> : null}
        </article>
      ))}
    </div>
  );
}

export function ClaimPanel({ claims }: { claims: ModuleClaim[] }) {
  if (claims.length === 0) {
    return (
      <p className="muted small">
        No claim in the ledger currently rests on this module&apos;s evidence.
      </p>
    );
  }
  return (
    <div className="claims">
      {claims.map((c) => (
        <article key={c.id} className="claims__item">
          <div className="claims__head">
            <Link href={`/research/claims#${c.id}`} className="mono">
              {c.id}
            </Link>
            <span className="chip">{c.status.replace(/_/g, ' ')}</span>
            <span className="chip">{c.scope}</span>
          </div>
          <p className="claims__text">{c.claim}</p>
          <dl className="claims__meta">
            <div>
              <dt>Evidence</dt>
              <dd>{c.evidence}</dd>
            </div>
            <div>
              <dt>Metric</dt>
              <dd>{c.metric}</dd>
            </div>
            <div>
              <dt>Statistical test</dt>
              <dd>{c.statistical_test}</dd>
            </div>
            <div>
              <dt>Dataset</dt>
              <dd>{c.dataset}</dd>
            </div>
            <div>
              <dt>Artifacts</dt>
              <dd className="mono small">{c.artifacts.join(', ') || '—'}</dd>
            </div>
            <div>
              <dt>Bounded by</dt>
              <dd>
                {c.limitations.length
                  ? c.limitations.map((l) => (
                      <Link
                        key={l}
                        href={`/research/limitations/${l}`}
                        style={{ marginRight: 8 }}
                      >
                        {l}
                      </Link>
                    ))
                  : 'nothing — this claim does not depend on the dataset'}
              </dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

/* -- figures and tables -------------------------------------------------------------- */

export function FigureViewer({
  figures,
  compact = false,
}: {
  figures: ModuleFigure[];
  compact?: boolean;
}) {
  if (figures.length === 0) {
    return <p className="muted small">This module cites no figure.</p>;
  }
  return (
    <div className={compact ? 'figures figures--compact' : 'figures'}>
      {figures.map((f) => (
        <figure key={f.figure} className="figures__item">
          {f.available && f.url ? (
            <a href={f.url} target="_blank" rel="noreferrer">
              {/* Deliberately a plain <img>: these are pre-rendered research figures of
                  known provenance served from this origin, and next/image would
                  re-encode an artifact the paper cites. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={f.url} alt={f.caption ?? f.figure} loading="lazy" />
            </a>
          ) : (
            <div className="figures__missing">
              Not present in this build. Regenerate with{' '}
              <code>python scripts/generate_research_figures.py</code>.
            </div>
          )}
          <figcaption>
            <span className="mono">{f.figure}</span>
            <span>{f.caption}</span>
            {f.source_data ? (
              <span className="muted mono small">source: {f.source_data}</span>
            ) : null}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

export function TableList({ tables }: { tables: ModuleTable[] }) {
  if (tables.length === 0) {
    return <p className="muted small">This module cites no table.</p>;
  }
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Table</th>
            <th className="num">Rows</th>
            <th>Caption</th>
            <th>Source artifact</th>
          </tr>
        </thead>
        <tbody>
          {tables.map((t) => (
            <tr key={t.table}>
              <td className="mono">
                <Link href={`/research/tables#${t.table}`}>{t.table}</Link>
              </td>
              <td className="num">{t.rows ?? '—'}</td>
              <td className="small">{t.caption ?? '—'}</td>
              <td className="small mono muted">{t.source ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* -- shared header pieces ------------------------------------------------------------ */

export function StatusPair({ module: mod }: { module: ResearchModule }) {
  return (
    <div className="statusPair">
      <span
        className={`chip chip--${
          mod.product.status === 'VERIFIED'
            ? 'good'
            : mod.product.status === 'UNAVAILABLE'
              ? 'bad'
              : 'warn'
        }`}
        title={PRODUCT_STATUS_COPY[mod.product.status]}
      >
        {mod.product.status}
      </span>
      <span
        className={`chip chip--${CONFIDENCE_TONE[mod.product.confidence] === 'good' ? 'good' : 'warn'}`}
        title={CONFIDENCE_COPY[mod.product.confidence].meaning}
      >
        {CONFIDENCE_COPY[mod.product.confidence].label}
      </span>
    </div>
  );
}
