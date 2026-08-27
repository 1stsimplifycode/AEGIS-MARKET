'use client';

/**
 * The week this demonstration is running at, for the interface only.
 *
 * The middleware stamps it into a cookie on every request, so the interface can render the
 * right locks without every page becoming server-rendered — which is what keeps
 * `AEGIS_ACTIVE_WEEK` changeable without a rebuild.
 *
 * This is a label, not a permission. Editing the cookie changes which navigation entries
 * carry a lock and nothing else: the middleware reads the environment when it decides what
 * to render, and `backend/capability.py` reads its own when it decides what to answer. A
 * reader who raises it finds the same 403 as before, with no result behind it.
 *
 * It starts at the complete programme and narrows once the cookie is read. That direction
 * is deliberate for the one frame before hydration: the alternative shows a lock on a
 * capability that is open, and a demonstration that briefly claims its own features are
 * unavailable is worse than one that resolves a moment later.
 */
import { useEffect, useState } from 'react';

import { ACTIVE_WEEK_COOKIE, LAST_WEEK, readActiveWeek } from '@/lib/gate';

export function useActiveWeek(last = LAST_WEEK): number {
  const [active, setActive] = useState(last);

  useEffect(() => {
    const match = new RegExp(
      '(?:^|;\\s*)' + ACTIVE_WEEK_COOKIE + '=([^;]*)',
    ).exec(document.cookie);
    setActive(readActiveWeek(match ? decodeURIComponent(match[1]) : null, last));
  }, [last]);

  return active;
}
