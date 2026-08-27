'use client';

/**
 * One week, executed as one action.
 *
 * A week is a pair — a statistical treatment and the modality it is applied to — and the
 * point of running them together is that they run on *the same slice*. So the parameters
 * both halves declare are hoisted into one shared set of controls, and the parameters only
 * one half declares stay with that half. The request mirrors that shape exactly, which is
 * the shape `backend.service.run_week` already expects: shared keys at the top level,
 * module-specific keys under the module's identifier.
 *
 * Each half reports its own mode. A week where one half computes live and the other
 * replays a protected artifact is a normal outcome and is shown as one, per half, rather
 * than averaged into a single misleading label for the week.
 */
import { useMemo, useState } from 'react';

import type { InputSpec, WeekRecord, WeekRunResponse } from '@/lib/runTypes';
import { defaultsFor } from '@/lib/runTypes';

import { Controls, type Values } from './Controls';
import { Result } from './Result';
import { useRun } from './useRun';

/** Parameters both halves declare identically. Anything else belongs to one half only. */
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

export function WeekLab({ week }: { week: WeekRecord }) {
  const { shared, perModule } = useMemo(() => partition(week), [week]);
  const ids = useMemo(
    () => [week.stats_module, week.multimodal_module],
    [week.stats_module, week.multimodal_module],
  );

  const [sharedValues, setSharedValues] = useState<Values>(() => defaultsFor(shared));
  const [moduleValues, setModuleValues] = useState<Record<string, Values>>(() =>
    Object.fromEntries(ids.map((id) => [id, defaultsFor(perModule[id] ?? [])])),
  );

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

  const liveCount = ids.filter((id) => week.execution[id]?.is_live).length;
  const seconds = ids.reduce((t, id) => t + (week.execution[id]?.typical_seconds ?? 0), 0);

  return (
    <section className="weekLab" aria-labelledby="weekLab-title">
      <header className="runPanel__head">
        <h2 id="weekLab-title">Run this week</h2>
        <p className="runPanel__lede">
          Both halves run on the slice you choose below. {liveCount} of {ids.length}{' '}
          {liveCount === 1 ? 'computes' : 'compute'} live; the rest replay their stored,
          provenance-stamped result and are labelled as replays. Typical time: about{' '}
          {Math.max(1, Math.round(seconds))}s.
        </p>
      </header>

      {shared.length > 0 ? (
        <div className="weekLab__shared">
          <h3>The slice both halves see</h3>
          <Controls
            inputs={shared}
            values={sharedValues}
            onChange={(name, value) => setSharedValues((p) => ({ ...p, [name]: value }))}
            disabled={running}
            idPrefix={`week-${week.week}-shared`}
          />
        </div>
      ) : null}

      <div className="weekLab__split">
        {ids.map((id) => {
          const extras = perModule[id] ?? [];
          const mod = week.modules.find((m) => m.module_id === id);
          return (
            <div className="weekLab__half" key={id}>
              <h3>
                <span className="mono">{id}</span> {mod?.name ?? ''}
              </h3>
              <p className="small muted">
                {week.execution[id]?.is_live
                  ? 'Computes live on the selection.'
                  : `Replays its verified artifact. ${week.execution[id]?.artifact_reason ?? ''}`}
              </p>
              {extras.length > 0 ? (
                <Controls
                  inputs={extras}
                  values={moduleValues[id] ?? {}}
                  onChange={(name, value) =>
                    setModuleValues((p) => ({ ...p, [id]: { ...(p[id] ?? {}), [name]: value } }))
                  }
                  disabled={running}
                  idPrefix={`week-${week.week}-${id}`}
                />
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="runPanel__actions">
        <button
          type="button"
          className="runPanel__go"
          onClick={() => void run(body)}
          disabled={running}
          aria-busy={running}
        >
          {running ? 'Running both halves…' : `Run week ${week.week}`}
        </button>
        {phase === 'done' ? (
          <button type="button" className="runPanel__reset" onClick={reset}>
            Clear
          </button>
        ) : null}
      </div>

      {running ? (
        <p className="runPanel__waiting" role="status">
          Running {ids.join(' and ')} over the selected slice. Nothing is written while they run.
        </p>
      ) : null}

      {transport ? (
        <div className="runRefusal" role="status">
          <h4>No result</h4>
          <p>{transport.reason}</p>
          <p className="runRefusal__remedy">{transport.remedy}</p>
        </div>
      ) : null}

      {result ? (
        <div className="weekLab__results">
          {result.reading ? <p className="weekLab__reading">{result.reading}</p> : null}
          {result.error ? (
            <div className="runRefusal" role="status">
              <h4>Nothing was computed</h4>
              <p>{result.error.reason}</p>
              {result.error.remedy ? (
                <p className="runRefusal__remedy">{result.error.remedy}</p>
              ) : null}
            </div>
          ) : null}
          <div className="weekLab__split">
            {ids.map((id) => {
              const response = result.results?.[id];
              return (
                <div className="weekLab__half" key={id}>
                  <h3>
                    <span className="mono">{id}</span>
                  </h3>
                  {response ? (
                    <Result response={response} />
                  ) : (
                    <p className="small muted">This half returned nothing.</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}
