'use client';

/**
 * What a reader is told when they reach for a capability this demonstration has not
 * switched on yet.
 *
 * The wording carries the whole point of the gating model, so it is written once here and
 * nowhere else. Every one of these would be false about this repository:
 *
 *   "Feature not implemented"   — it is implemented, and tested
 *   "Development has not begun" — it finished
 *   "Backend unavailable"       — the backend is running and refused on purpose
 *   "Not found"                 — it is found; it is just not on yet
 *
 * What is true is that the product reveals itself in the order it was built, and this
 * capability arrives later in that order. "Coming soon" says that in the register a reader
 * uses. Research mode adds the sentence a reviewer needs — that the work exists in the
 * complete system and the week is a demonstration setting, not a state of the code.
 *
 * Nothing here knows which week anything belongs to: the name and the week arrive from the
 * capability registry, which reads the manifest. A component that hardcoded "Week 8" would
 * have to be edited every time the programme moved.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export interface LockedCapability {
  name: string;
  enabledFromWeek: number;
  activeWeek: number;
  summary?: string;
}

/** How long the notice stays up before dismissing itself. */
const DWELL_MS = 6000;

export function useLockedNotice() {
  const [locked, setLocked] = useState<LockedCapability | null>(null);
  const timer = useRef<number | null>(null);

  const show = useCallback((capability: LockedCapability) => {
    setLocked(capability);
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setLocked(null), DWELL_MS);
  }, []);

  const dismiss = useCallback(() => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    setLocked(null);
  }, []);

  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );

  return { locked, show, dismiss };
}

export function LockedFeatureNotice({
  locked,
  onDismiss,
}: {
  locked: LockedCapability | null;
  onDismiss: () => void;
}) {
  // Escape closes it. A notice that can only be dismissed with a mouse is a notice a
  // keyboard reader has to wait out.
  useEffect(() => {
    if (!locked) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onDismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [locked, onDismiss]);

  if (!locked) return null;

  return (
    <div className="lockedNotice" role="status" aria-live="polite">
      <div className="lockedNotice__body">
        <p className="lockedNotice__head">
          <span className="lockedNotice__lock" aria-hidden="true">
            🔒
          </span>
          Coming soon
        </p>
        <p className="lockedNotice__text">
          <strong>{locked.name}</strong> becomes available in week{' '}
          {locked.enabledFromWeek} of the capstone progression.
        </p>
        {locked.summary ? (
          <p className="lockedNotice__summary">{locked.summary}</p>
        ) : null}
        <p className="lockedNotice__research modeOnly modeOnly--research">
          Implemented in the complete system; enabled from week {locked.enabledFromWeek}.
          This demonstration is running at week {locked.activeWeek}.
        </p>
      </div>
      <button
        type="button"
        className="lockedNotice__close"
        onClick={onDismiss}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}
