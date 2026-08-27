'use client';

/**
 * The request half of a run panel: state, the POST, and the four outcomes.
 *
 * A run ends in exactly one of four states and each is rendered differently, because
 * collapsing them would mean showing a user the wrong thing:
 *
 * * **a result** — the service answered, whether it computed or replayed;
 * * **a refusal** — the service answered and declined, with a reason and a remedy; it
 *   arrives as an ordinary response and is rendered from the response, not invented here;
 * * **a transport failure** — nothing answered. This hook does not manufacture a response
 *   for that case: an empty panel with an explanation is honest, a fabricated payload is
 *   not;
 * * **still running** — with the module's declared typical duration, so a slow module
 *   reads as slow rather than as broken.
 */
import { useCallback, useRef, useState } from 'react';

import type { RunResponse, WeekRunResponse } from '@/lib/runTypes';

export type Phase = 'idle' | 'running' | 'done';

export interface Transport {
  reason: string;
  remedy: string;
}

export function useRun<T extends RunResponse | WeekRunResponse>(endpoint: string) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [result, setResult] = useState<T | null>(null);
  const [transport, setTransport] = useState<Transport | null>(null);
  const [ranAt, setRanAt] = useState<string | null>(null);
  // A second click while a run is in flight must not race the first one's result into
  // view after the second's; the older request is abandoned rather than rendered.
  const inflight = useRef<AbortController | null>(null);

  const run = useCallback(
    async (body: Record<string, unknown>) => {
      inflight.current?.abort();
      const controller = new AbortController();
      inflight.current = controller;
      setPhase('running');
      setTransport(null);

      try {
        const res = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: controller.signal,
        });
        const text = await res.text();
        let payload: unknown;
        try {
          payload = JSON.parse(text);
        } catch {
          setResult(null);
          setTransport({
            reason: 'The service answered with something that is not a result.',
            remedy: 'Check that the analysis backend is the one this build expects.',
          });
          setPhase('done');
          return;
        }
        setResult(payload as T);
        setRanAt(new Date().toISOString());
        setPhase('done');
      } catch (err) {
        if (controller.signal.aborted) return;
        setResult(null);
        setTransport({
          reason:
            err instanceof Error && err.name === 'TimeoutError'
              ? 'The request took longer than this page waits.'
              : 'No answer from the analysis service.',
          remedy:
            'Start it with run_dev.bat, or open this page against a deployment that has ' +
            'one. Stored results remain readable without it.',
        });
        setPhase('done');
      } finally {
        if (inflight.current === controller) inflight.current = null;
      }
    },
    [endpoint],
  );

  const reset = useCallback(() => {
    inflight.current?.abort();
    setPhase('idle');
    setResult(null);
    setTransport(null);
  }, []);

  return { phase, result, transport, ranAt, run, reset };
}
