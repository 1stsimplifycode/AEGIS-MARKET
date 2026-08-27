'use client';

/**
 * One backend response, rendered in both experiences.
 *
 * The badge is the first thing on the panel and it is not decorative. `LIVE_COMPUTATION`
 * means the canonical implementation ran during this request on the slice that was
 * selected; `VERIFIED_ARTIFACT` means a stored run is being replayed and nothing was
 * computed. Everything else on the panel — whether the inputs were applied, whether there
 * is a run identifier to cite — follows from which of those two it is, so it is stated
 * once, plainly, at the top.
 *
 * Product mode simplifies the language and never the meaning. A refusal is shown as a
 * refusal in both modes, with the reason and what to do about it, because a panel that
 * quietly renders nothing teaches a reader that the tool is broken rather than that their
 * selection was too narrow.
 */
import type { RunMetric, RunResponse, RunSeries } from '@/lib/runTypes';
import { MODE_COPY, statusCopy } from '@/lib/runTypes';

/**
 * The mode badge, when there is a result to describe.
 *
 * A refused request produced neither a computation nor a replay, so labelling it as
 * either would describe something that did not happen. The refusal below says what
 * actually occurred; a badge above it would only contradict that.
 */
export function ModeBadge({ response }: { response: RunResponse }) {
  const produced = response.metrics.length > 0 || response.series.length > 0;
  if (!produced) return null;
  const copy = MODE_COPY[response.mode] ?? {
    badge: response.mode_label,
    tone: 'artifact' as const,
    short: response.mode_meaning,
  };
  return (
    <p className="runBadge" data-tone={copy.tone}>
      <span className="runBadge__dot" aria-hidden="true" />
      <span className="runBadge__label">{copy.badge}</span>
      <span className="runBadge__text">{copy.short}</span>
    </p>
  );
}

export function StatusLine({ response }: { response: RunResponse }) {
  const copy = statusCopy(response.status);
  return (
    <p className="runStatus" data-kind={copy.kind}>
      <span className="runStatus__label">{copy.label}</span>
      {response.status === 'OK' && response.elapsed_s ? (
        <span className="small muted"> · {response.elapsed_s.toFixed(2)}s</span>
      ) : null}
    </p>
  );
}

export function Refusal({ response }: { response: RunResponse }) {
  if (!response.error) return null;
  return (
    <div className="runRefusal" role="status">
      <h4>{statusCopy(response.status).label}</h4>
      <p>{response.error.reason}</p>
      {response.error.remedy ? <p className="runRefusal__remedy">{response.error.remedy}</p> : null}
      <p className="small muted mono">{response.error.code}</p>
    </div>
  );
}

function MetricList({ metrics }: { metrics: RunMetric[] }) {
  if (metrics.length === 0) return null;
  return (
    <div className="grid runMetrics">
      {metrics.map((m) => (
        <div className="card metricCard" key={m.key}>
          <span className="card__label">{m.label}</span>
          <span className="card__value">{m.display}</span>
          {m.note ? <span className="card__note">{m.note}</span> : null}
          {m.source ? <span className="metricCard__source mono">{m.source}</span> : null}
        </div>
      ))}
    </div>
  );
}

function SeriesTable({ series }: { series: RunSeries }) {
  return (
    <section className="runSeries">
      <h4>{series.label}</h4>
      {series.note ? <p className="small muted">{series.note}</p> : null}
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              {series.columns.map((c) => (
                <th key={c} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {series.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} className={typeof cell === 'number' ? 'mono' : undefined}>
                    {cell === null ? '—' : String(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {series.truncated ? (
        <p className="small muted">
          Showing {series.rows.length} of {series.total_rows ?? '?'} rows.
        </p>
      ) : null}
    </section>
  );
}

function Observations({ items }: { items: string[] }) {
  if (items.length === 0) return null;
  return (
    <ul className="runObservations">
      {items.map((o, i) => (
        <li key={i}>{o}</li>
      ))}
    </ul>
  );
}

function Uncertainty({ payload }: { payload: Record<string, unknown> }) {
  const reading = typeof payload.reading === 'string' ? payload.reading : '';
  if (!reading) return null;
  const kind = typeof payload.kind === 'string' ? payload.kind : 'unspecified';
  return (
    <section className="runUncertainty">
      <h4>How far this goes</h4>
      <p>{reading}</p>
      <p className="small muted mono">uncertainty: {kind}</p>
    </section>
  );
}

function Provenance({ response }: { response: RunResponse }) {
  const p = response.provenance;
  const rows: [string, string][] = [];
  const push = (k: string, v: unknown) => {
    if (v === null || v === undefined || v === '') return;
    rows.push([k, Array.isArray(v) ? v.join(', ') : String(v)]);
  };
  push('module', p.module_id);
  push('adapter', p.adapter);
  push('canonical called', p.canonical_called ?? p.canonical);
  push('computed during this request', p.computed);
  push('wrote nothing', p.wrote_nothing);
  push('git commit', p.git_commit);
  push('requested at', p.requested_at);
  push('replayed run', p.replayed_run_id);
  push('replayed commit', p.replayed_commit);
  push('artifacts', p.artifacts);
  push('regenerate with', p.regenerate_with);
  push('protected artifacts', p.protected_artifacts);

  return (
    <section className="runProvenance">
      <h4>Provenance</h4>
      {typeof p.execution === 'string' ? <p className="small">{p.execution}</p> : null}
      {typeof p.protection_note === 'string' ? (
        <p className="small">{p.protection_note}</p>
      ) : null}
      <dl className="runProvenance__list">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="mono">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Dataset({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload).filter(([, v]) => v !== null && v !== '');
  if (entries.length === 0) return null;
  return (
    <section className="runDataset">
      <h4>What was read</h4>
      <dl className="runProvenance__list">
        {entries.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd className="mono">
              {typeof v === 'object' ? JSON.stringify(v) : String(v)}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Limitations({ response }: { response: RunResponse }) {
  if (response.limitations.length === 0) return null;
  return (
    <section className="runLimits">
      <h4>What this does not cover</h4>
      <ul>
        {response.limitations.map((l) => (
          <li key={l.id}>
            <span className="mono">{l.id}</span> {l.title}
            {l.scope_note ? <span className="small muted"> — {l.scope_note}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The product reading: the badge, the headline numbers, the plain-language findings. */
export function ResultProduct({ response }: { response: RunResponse }) {
  return (
    <div className="runResult">
      <ModeBadge response={response} />
      <StatusLine response={response} />
      {response.error ? <Refusal response={response} /> : null}
      <MetricList metrics={response.metrics.slice(0, 6)} />
      <Observations items={response.observations} />
      <Uncertainty payload={response.uncertainty} />
      <Limitations response={response} />
    </div>
  );
}

/** The research reading: everything above, plus the tables and the audit trail. */
export function ResultResearch({ response }: { response: RunResponse }) {
  return (
    <div className="runResult">
      <ModeBadge response={response} />
      <StatusLine response={response} />
      {response.error ? <Refusal response={response} /> : null}
      <MetricList metrics={response.metrics} />
      <Observations items={response.observations} />
      {response.series.map((s) => (
        <SeriesTable key={s.key} series={s} />
      ))}
      <Uncertainty payload={response.uncertainty} />
      <Dataset payload={response.dataset} />
      {Object.keys(response.inputs).length > 0 ? (
        <section className="runInputs">
          <h4>Inputs the service accepted</h4>
          <pre className="mono">{JSON.stringify(response.inputs, null, 2)}</pre>
        </section>
      ) : null}
      <Provenance response={response} />
      <Limitations response={response} />
    </div>
  );
}

/** Both readings, switched by the same `data-mode` attribute the rest of the app uses. */
export function Result({ response }: { response: RunResponse }) {
  return (
    <>
      <div className="modeOnly modeOnly--product">
        <ResultProduct response={response} />
      </div>
      <div className="modeOnly modeOnly--research">
        <ResultResearch response={response} />
      </div>
    </>
  );
}
