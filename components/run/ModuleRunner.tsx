'use client';

/**
 * The interactive half of a module page: choose a slice, run it, read what came back.
 *
 * The button says which of the two things it will do before it is pressed. A module with a
 * live analysis adapter recomputes on the selection; a module without one replays its
 * stored artifact, and says so both before and after, so nobody presses "Run" expecting
 * fresh numbers and receives old ones under a fresh-looking heading.
 *
 * Protected modules are the interesting case. Their artifacts are cited by the claim
 * ledger, so no request may regenerate them — but many of them can still *analyse* live,
 * because analysing writes nothing. The panel says exactly that rather than presenting the
 * guard as a failure.
 */
import { useMemo, useState } from 'react';

import type { ExecutionSpec, InputSpec, RunResponse } from '@/lib/runTypes';
import { defaultsFor } from '@/lib/runTypes';

import { Controls, type Values } from './Controls';
import { Result } from './Result';
import { useRun } from './useRun';

export function ModuleRunner({
  moduleId,
  moduleName,
  inputs,
  execution,
  summary,
}: {
  moduleId: string;
  moduleName: string;
  inputs: InputSpec[];
  execution: ExecutionSpec;
  summary: string;
}) {
  const [values, setValues] = useState<Values>(() => defaultsFor(inputs));
  const { phase, result, transport, run, reset } = useRun<RunResponse>(
    `/api/aegis/modules/${moduleId}/run`,
  );

  const body = useMemo(
    () => Object.fromEntries(Object.entries(values).filter(([, v]) => v !== '' && v !== null)),
    [values],
  );

  const verb = execution.is_live ? 'Run this analysis' : 'Load the verified result';
  const running = phase === 'running';

  return (
    <section className="runPanel" data-module={moduleId} aria-labelledby={`run-${moduleId}`}>
      <header className="runPanel__head">
        <h3 id={`run-${moduleId}`}>{execution.is_live ? 'Run it yourself' : 'The stored result'}</h3>
        <p className="runPanel__lede">{summary}</p>
        <p className="small muted">
          {execution.is_live ? (
            <>
              The canonical implementation runs on your selection when you press the button.
              Typical time: {execution.typical_seconds}s.
            </>
          ) : (
            <>
              This module does not compute on request. {execution.artifact_reason} The stored,
              provenance-stamped result is served instead, labelled as one.
            </>
          )}
        </p>
        {execution.protected ? (
          <p className="runPanel__guard">
            Its published artifacts are protected: they are cited elsewhere, so no request from
            this page can overwrite them.
            {execution.is_live
              ? ' Analysing here writes nothing, so the guard is not in the way.'
              : ' Regenerating them takes a deliberate terminal command.'}
          </p>
        ) : null}
      </header>

      <Controls
        inputs={inputs}
        values={values}
        onChange={(name, value) => setValues((prev) => ({ ...prev, [name]: value }))}
        disabled={running}
        idPrefix={`run-${moduleId}`}
      />

      <div className="runPanel__actions">
        <button
          type="button"
          className="runPanel__go"
          onClick={() => void run(body)}
          disabled={running}
          aria-busy={running}
        >
          {running ? `Running ${moduleName}…` : verb}
        </button>
        {phase === 'done' ? (
          <button type="button" className="runPanel__reset" onClick={reset}>
            Clear
          </button>
        ) : null}
      </div>

      {running ? (
        <p className="runPanel__waiting" role="status">
          {execution.is_live
            ? `Running ${moduleId} over the selected slice. Nothing is written while it runs.`
            : `Reading the stored result for ${moduleId}.`}
        </p>
      ) : null}

      {transport ? (
        <div className="runRefusal" role="status">
          <h4>No result</h4>
          <p>{transport.reason}</p>
          <p className="runRefusal__remedy">{transport.remedy}</p>
        </div>
      ) : null}

      {result ? <Result response={result} /> : null}
    </section>
  );
}
