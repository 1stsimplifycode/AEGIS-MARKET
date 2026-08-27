'use client';

/**
 * Progressive disclosure, as one component used everywhere.
 *
 * The product shows an answer. Underneath it, closed, sits the evidence that produced the
 * answer; underneath that, a link into research mode. Three depths, and a reader chooses
 * how far down to go rather than being handed all three at once.
 *
 * It is a `<details>` element, deliberately. The content is in the page whether or not
 * JavaScript runs, it is reachable by keyboard and by find-in-page, and a reader who
 * prints the page gets everything. A custom toggle would have cost all three.
 */
import type { ReactNode } from 'react';

export function Disclosure({
  summary,
  children,
  tone = 'default',
}: {
  /** The invitation, phrased as what the reader will learn. Not "details". */
  summary: string;
  children: ReactNode;
  tone?: 'default' | 'quiet';
}) {
  return (
    <details className="disclosure" data-tone={tone}>
      <summary>
        <span className="disclosure__label">{summary}</span>
        <span className="disclosure__chevron" aria-hidden="true" />
      </summary>
      <div className="disclosure__body">{children}</div>
    </details>
  );
}
