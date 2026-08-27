'use client';

/**
 * A week, as one product feature rather than two module panels.
 *
 * The old shape was honest and unreadable: STATS-N's metrics beside MULTIMODAL-N's, with
 * nothing saying what the pair was for. This composes them into the order a reader thinks
 * in — the question, one action, the headline figures, the picture, what was observed,
 * how far it goes — and puts the per-module detail one disclosure below that.
 *
 * Nothing here decides what is interesting. Which figures lead and which series is the
 * picture are declared in the manifest's `feature:` block and validated against live
 * module output by a test, so this component reads a plan it did not write. A headline
 * naming a metric the module stopped returning shows as unavailable rather than as a
 * confident blank.
 *
 * Both halves still run through the same backend call the week always used. This is a
 * change of presentation, not of execution.
 */
import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import type {
  InputSpec,
  RunResponse,
  RunSeries,
  WeekRecord,
  WeekRunResponse,
} from '@/lib/runTypes';
import { defaultsFor, statusCopy } from '@/lib/runTypes';

import { Controls, type Values } from './Controls';
import { Result } from './Result';
import { useRun } from './useRun';

interface HeadlineSpec {
  module: string;
  metric: string;
  label: string;
}

interface VisualSpec {
  module: string;
  series: string;
  label_column: string;
  value_column: string;
  kind: 'bars' | 'line';
  caption?: string;
}

/** The coverage marks the backend computed for this market period. */
export interface FeatureEvidence {
  sources: {
    source_id: string;
    product_label: string;
    product_status: string;
    mark: string;
    tone: string;
    shared_sessions: number;
    index_sessions: number;
  }[];
}

interface FeatureSpec {
  product_question?: string;
  story?: string;
  headline?: HeadlineSpec[];
  primary_visual?: VisualSpec;
  secondary_visual?: VisualSpec;
}

/** Parameters both halves declare identically, hoisted so one slice drives both. */
function partition(week: WeekRecord): {
  shared: InputSpec[];
  perModule: Record<string, InputSpec[]>;
} {
  const ids = [week.stats_module, week.multimodal_module];
  const schemas = ids.map((id) => week.input_schema[id] ?? []);
  const [first, second] = schemas;
  const sharedNames = new Set(
    (first ?? [])
      .filter((a) => (second ?? []).some((b) => b.name === a.name && b.kind === a.kind))
      .map((a) => a.name),
  );
  return {
    shared: (first ?? []).filter((i) => sharedNames.has(i.name)),
    perModule: Object.fromEntries(
      ids.map((id, n) => [id, (schemas[n] ?? []).filter((i) => !sharedNames.has(i.name))]),
    ),
  };
}

function seriesFrom(
  result: WeekRunResponse | null,
  spec: VisualSpec | undefined,
): { series: RunSeries; spec: VisualSpec } | null {
  if (!spec || !result?.results) return null;
  const half = result.results[spec.module];
  const series = half?.series.find((s) => s.key === spec.series);
  return series ? { series, spec } : null;
}

/**
 * A chart drawn from one declared series.
 *
 * The columns are named in the manifest, so this looks them up rather than guessing at
 * position — a series that gains a column keeps drawing the right one.
 */
function FeatureChart({ series, spec }: { series: RunSeries; spec: VisualSpec }) {
  const labelAt = series.columns.indexOf(spec.label_column);
  const valueAt = series.columns.indexOf(spec.value_column);
  if (labelAt < 0 || valueAt < 0) {
    return (
      <p className="small muted">
        This chart expects columns <span className="mono">{spec.label_column}</span> and{' '}
        <span className="mono">{spec.value_column}</span>, which{' '}
        <span className="mono">{spec.series}</span> did not return.
      </p>
    );
  }

  // A missing value is missing, not zero. The backend nulls non-finite floats — that is
  // the only valid JSON encoding for one — and `Number(null)` is 0, which is finite, so a
  // naive conversion draws a confident bar at zero where the module had no number at all.
  const missing = (v: unknown) => v === null || v === undefined || v === '';
  const points = series.rows
    .map((row) => ({
      label: String(row[labelAt] ?? ''),
      value: missing(row[valueAt]) ? Number.NaN : Number(row[valueAt]),
    }))
    .filter((p) => Number.isFinite(p.value))
    .slice(0, 24);

  if (points.length === 0) {
    return <p className="small muted">No rows in this series carried a value.</p>;
  }

  const values = points.map((p) => p.value);
  const high = Math.max(...values, 0);
  const low = Math.min(...values, 0);
  const span = high - low || 1;

  if (spec.kind === 'line') {
    const step = 100 / Math.max(1, points.length - 1);
    const path = values
      .map(
        (v, i) =>
          `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(2)},${(
            100 -
            ((v - low) / span) * 100
          ).toFixed(2)}`,
      )
      .join(' ');
    return (
      <figure className="featureChart">
        <div className="featureChart__line">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <path d={path} vectorEffect="non-scaling-stroke" />
          </svg>
        </div>
        <figcaption>
          <span className="featureChart__axis">
            <span>{points[0].label}</span>
            <span>{points[points.length - 1].label}</span>
          </span>
          {spec.caption ? <span>{spec.caption}</span> : null}
        </figcaption>
      </figure>
    );
  }

  return (
    <figure className="featureChart">
      <ul className="featureBars">
        {points.map((p) => (
          <li key={p.label}>
            <span className="featureBars__label">{p.label}</span>
            <span className="featureBars__track">
              <span
                className="featureBars__fill"
                style={{ width: `${Math.max(2, ((p.value - low) / span) * 100)}%` }}
              />
            </span>
            <span className="featureBars__value">
              {Math.abs(p.value) < 1 && p.value !== 0
                ? p.value.toFixed(3)
                : p.value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
            </span>
          </li>
        ))}
      </ul>
      {spec.caption ? <figcaption>{spec.caption}</figcaption> : null}
    </figure>
  );
}

/**
 * How long the analysis has been running, and what it did when it finished.
 *
 * Several of these weeks fit a model and take a minute. A button that greys out and says
 * nothing for sixty seconds is indistinguishable from one that has crashed, so the band
 * counts up while it waits and states plainly what happened when it stops.
 */
function StatusBand({
  phase,
  result,
  transport,
  modules,
}: {
  phase: 'idle' | 'running' | 'done';
  result: WeekRunResponse | null;
  transport: { reason: string; remedy: string } | null;
  modules: string[];
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (phase !== 'running') return undefined;
    setElapsed(0);
    const started = Date.now();
    const timer = window.setInterval(
      () => setElapsed(Math.round((Date.now() - started) / 1000)),
      500,
    );
    return () => window.clearInterval(timer);
  }, [phase]);

  if (phase === 'running') {
    return (
      <p className="statusBand" data-state="running" role="status" aria-live="polite">
        <span className="statusBand__spinner" aria-hidden="true" />
        <strong>Running analysis…</strong>
        <span>
          {modules.length} analyses over the selected slice · {elapsed}s
        </span>
        <span className="statusBand__note">Nothing is written while it runs.</span>
      </p>
    );
  }

  if (transport) {
    return (
      <div className="statusBand statusBand--block" data-state="failed" role="status">
        <strong>The analysis did not run</strong>
        <span>{transport.reason}</span>
        <span className="statusBand__note">{transport.remedy}</span>
      </div>
    );
  }

  if (phase === 'done' && result) {
    const refused = Object.values(result.results ?? {}).filter(
      (r) => r.status !== 'OK',
    );
    if (refused.length > 0) {
      return (
        <div className="statusBand statusBand--block" data-state="refused" role="status">
          <strong>
            {refused.length === modules.length
              ? 'The analysis could not be completed'
              : 'Part of the analysis could not be completed'}
          </strong>
          {refused.map((r) => (
            <span key={r.module_id}>
              {r.error?.reason ?? statusCopy(r.status).label}
            </span>
          ))}
          <span className="statusBand__note">
            {refused[0].error?.remedy ?? 'Adjust the selection and run it again.'}
          </span>
        </div>
      );
    }
    return (
      <p className="statusBand" data-state="done" role="status">
        <span className="statusBand__tick" aria-hidden="true">
          ✓
        </span>
        <strong>Analysis complete</strong>
        <span>
          {modules.length} analyses · {result.elapsed_s.toFixed(1)}s
        </span>
      </p>
    );
  }

  return null;
}

/** The evidence marks, compact, for the result block. */
function EvidenceLine({ evidence }: { evidence: FeatureEvidence | null }) {
  if (!evidence?.sources?.length) return null;
  const marks: Record<string, string> = {
    check: '✓',
    partial: '◑',
    cross: '○',
    unknown: '?',
  };
  return (
    <ul className="featureEvidence">
      {evidence.sources.map((s) => (
        <li key={s.source_id} data-tone={s.tone}>
          <span aria-hidden="true">{marks[s.mark] ?? '·'}</span>
          <span className="featureEvidence__label">{s.product_label}</span>
          <span className="featureEvidence__state modeOnly modeOnly--inline modeOnly--product">
            {s.product_status}
          </span>
          <span className="featureEvidence__state modeOnly modeOnly--inline modeOnly--research">
            {s.shared_sessions} of {s.index_sessions} sessions shared
          </span>
        </li>
      ))}
    </ul>
  );
}

export function WeekFeature({
  week,
  evidence = null,
}: {
  week: WeekRecord;
  /** Coverage marks for the market period, computed by the backend. */
  evidence?: FeatureEvidence | null;
}) {
  const feature = ((week as WeekRecord & { feature?: FeatureSpec }).feature ??
    {}) as FeatureSpec;
  const { shared, perModule } = useMemo(() => partition(week), [week]);
  const ids = useMemo(
    () => [week.stats_module, week.multimodal_module],
    [week.stats_module, week.multimodal_module],
  );

  const [sharedValues, setSharedValues] = useState<Values>(() => defaultsFor(shared));
  const [moduleValues, setModuleValues] = useState<Record<string, Values>>(() =>
    Object.fromEntries(ids.map((id) => [id, defaultsFor(perModule[id] ?? [])])),
  );
  const [showInputs, setShowInputs] = useState(false);

  const { phase, result, transport, run, reset } = useRun<WeekRunResponse>(
    `/api/aegis/weeks/${week.week}/run`,
  );
  const running = phase === 'running';

  const body = useMemo(() => {
    const clean = (v: Values) =>
      Object.fromEntries(Object.entries(v).filter(([, x]) => x !== '' && x !== null));
    const out: Record<string, unknown> = clean(sharedValues);
    for (const id of ids) {
      const extras = clean(moduleValues[id] ?? {});
      if (Object.keys(extras).length > 0) out[id] = extras;
    }
    return out;
  }, [sharedValues, moduleValues, ids]);

  const halves = ids.map((id) => result?.results?.[id] ?? null);
  const succeeded = halves.filter(
    (h): h is RunResponse => h !== null && h.status === 'OK',
  );
  const anyResult = succeeded.length > 0;

  const headline = (feature.headline ?? []).map((h) => {
    const half = result?.results?.[h.module];
    const metric = half?.metrics.find((m) => m.key === h.metric);
    return { ...h, display: metric?.display ?? null, note: metric?.note ?? '' };
  });

  const primary = seriesFrom(result, feature.primary_visual);
  const secondary = seriesFrom(result, feature.secondary_visual);

  // Straight from the modules. Nothing on this page writes a finding: a sentence the
  // interface composed would read exactly like one the analysis produced.
  const observations = succeeded.flatMap((h) => h.observations).slice(0, 6);
  const uncertainty = succeeded
    .map((h) => h.uncertainty)
    .find((u) => typeof u.reading === 'string');
  const limitations = Object.values(
    Object.fromEntries(
      succeeded.flatMap((h) => h.limitations).map((l) => [l.id, l]),
    ),
  );

  const seconds = ids.reduce(
    (t, id) => t + (week.execution[id]?.typical_seconds ?? 0),
    0,
  );
  const live = ids.filter((id) => week.execution[id]?.is_live).length;

  return (
    <section className="feature">
      <header className="feature__head">
        <div className="feature__actions">
          <button
            type="button"
            className="runPanel__go feature__run"
            onClick={() => void run(body)}
            disabled={running}
            aria-busy={running}
          >
            {running ? 'Running…' : anyResult ? 'Run again' : 'Run this analysis'}
          </button>
          <button
            type="button"
            className="runPanel__reset"
            onClick={() => setShowInputs((v) => !v)}
            aria-expanded={showInputs}
          >
            {showInputs ? 'Hide options' : 'Change what is analysed'}
          </button>
          {phase === 'done' ? (
            <button type="button" className="runPanel__reset" onClick={reset}>
              Clear
            </button>
          ) : null}
          <span className="feature__timing">
            {live} of {ids.length} computed on request · about{' '}
            {Math.max(1, Math.round(seconds))}s
          </span>
        </div>

        {showInputs ? (
          <div className="feature__inputs">
            {shared.length > 0 ? (
              <div className="weekLab__shared">
                <h3>What is analysed</h3>
                <Controls
                  inputs={shared}
                  values={sharedValues}
                  onChange={(name, value) =>
                    setSharedValues((p) => ({ ...p, [name]: value }))
                  }
                  disabled={running}
                  idPrefix={`week-${week.week}-shared`}
                />
              </div>
            ) : null}
            <div className="weekLab__split">
              {ids.map((id) => {
                const extras = perModule[id] ?? [];
                if (extras.length === 0) return null;
                const mod = week.modules.find((m) => m.module_id === id);
                return (
                  <div className="weekLab__half" key={id}>
                    <h3>{mod?.product_name ?? mod?.name ?? id}</h3>
                    <Controls
                      inputs={extras}
                      values={moduleValues[id] ?? {}}
                      onChange={(name, value) =>
                        setModuleValues((p) => ({
                          ...p,
                          [id]: { ...(p[id] ?? {}), [name]: value },
                        }))
                      }
                      disabled={running}
                      idPrefix={`week-${week.week}-${id}`}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </header>

      <StatusBand
        phase={phase}
        result={result}
        transport={transport}
        modules={ids}
      />

      {!anyResult && !running && !transport && phase !== 'done' ? (
        <div className="feature__idle">
          <p>
            Press <strong>Run this analysis</strong> to compute this result on live data.
            Nothing on this page is stored output waiting to be revealed.
          </p>
        </div>
      ) : null}

      {anyResult ? (
        <>
          {headline.length > 0 ? (
            <div className="cardRow feature__headline">
              {headline.map((h) => (
                <article className="tile" key={`${h.module}-${h.metric}`}>
                  <span className="tile__label">{h.label}</span>
                  <span className="tile__value">{h.display ?? '—'}</span>
                  {h.note ? <span className="tile__note">{h.note}</span> : null}
                </article>
              ))}
            </div>
          ) : null}

          {observations.length > 0 ? (
            <section className="feature__block">
              <h3>What AEGIS found</h3>
              <ul className="observations">
                {observations.map((o, i) => (
                  <li key={i}>{o}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {primary ? (
            <section className="feature__block">
              <h3>{primary.spec.series.replace(/_/g, ' ')}</h3>
              <FeatureChart series={primary.series} spec={primary.spec} />
            </section>
          ) : null}

          {evidence ? (
            <section className="feature__block">
              <h3>Evidence behind this</h3>
              <EvidenceLine evidence={evidence} />
            </section>
          ) : null}

          {uncertainty?.reading || limitations.length > 0 ? (
            <section className="feature__block">
              <h3>How far this goes</h3>
              {uncertainty?.reading ? (
                <p className="feature__uncertaintyText">
                  {String(uncertainty.reading)}
                </p>
              ) : null}
              {limitations.length > 0 ? (
                <ul className="featureLimits">
                  {limitations.map((l) => (
                    <li key={l.id}>
                      <span className="modeOnly modeOnly--inline modeOnly--research mono">
                        {l.id}{' '}
                      </span>
                      {l.title}
                      {l.scope_note ? (
                        <span className="small muted"> — {l.scope_note}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}

          {secondary ? (
            <section className="feature__block">
              <h3>Supporting evidence</h3>
              <FeatureChart series={secondary.series} spec={secondary.spec} />
            </section>
          ) : null}

          <details className="disclosure feature__detail">
            <summary>
              <span className="disclosure__label">
                Understand evidence — the full result from each half
              </span>
              <span className="disclosure__chevron" aria-hidden="true" />
            </summary>
            <div className="disclosure__body">
              {ids.map((id, i) => {
                const half = halves[i];
                const mod = week.modules.find((m) => m.module_id === id);
                return (
                  <section className="feature__half" key={id}>
                    <h4>
                      <span className="modeOnly modeOnly--inline modeOnly--product">
                        {mod?.product_name ?? id}
                      </span>
                      <span className="modeOnly modeOnly--inline modeOnly--research mono">
                        {id}
                      </span>{' '}
                      <Link className="small" href={mod?.route ?? '/'}>
                        open capability →
                      </Link>
                    </h4>
                    {half ? (
                      <Result response={half} />
                    ) : (
                      <p className="small muted">
                        {statusCopy(result?.status ?? 'FAILED').label}: this half returned
                        nothing.
                      </p>
                    )}
                  </section>
                );
              })}
            </div>
          </details>
        </>
      ) : null}
    </section>
  );
}
