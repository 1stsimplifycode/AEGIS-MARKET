'use client';

import Link from 'next/link';

import { useMode, useSubject } from '@/lib/mode';

/**
 * Registers what the page is about so a mode switch carries it (spec sections 60, 127).
 *
 * Rendered by server components that know their subject. Renders nothing itself, except
 * the "verify this" affordance, which is the intended bridge from Product to Research:
 * a user who wants to know *how we know* should not have to find the research section
 * and navigate back to the same instrument.
 */
export function SubjectRegistrar({
  instrument,
  event,
  date,
  showBridge = true,
}: {
  instrument?: string;
  event?: string;
  date?: string;
  showBridge?: boolean;
}) {
  useSubject({ instrument, event, date });
  const { mode } = useMode();

  if (!showBridge || mode !== 'product') return null;

  const params = new URLSearchParams();
  if (instrument) params.set('instrument', instrument);
  if (event) params.set('event', event);
  if (date) params.set('date', date);

  return (
    <p className="small" style={{ marginTop: 14 }}>
      <Link href={`/research?${params.toString()}`}>
        How do we know this? Open the research workspace with this instrument in context →
      </Link>
    </p>
  );
}

export default SubjectRegistrar;
