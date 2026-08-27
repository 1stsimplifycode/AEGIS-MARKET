/**
 * The route gate, run per request, before any page renders.
 *
 * Two jobs, and it is worth being clear which is which.
 *
 * **It refuses.** A request for `/weeks/8` or `/stats/08` while week 1 is active is
 * rewritten to the gated page. This runs on the server for every request, including the
 * ones a reader types into the address bar, so it is not something a client can decline to
 * do. It is not the only gate — `backend/capability.py` refuses the API independently, and
 * would still refuse if this file were deleted — but it is the one that decides what a
 * *page* renders.
 *
 * **It tells the interface where it stands.** The active week is stamped into a cookie so
 * the navigation and the progress marks can read it without every page becoming
 * server-rendered. That cookie is a label, never a permission: raising it by hand changes
 * what the nav offers to link to and changes nothing about what the middleware rewrites or
 * what the backend returns.
 *
 * Running here rather than at build time is what makes §29 work. `AEGIS_ACTIVE_WEEK` is
 * read from the environment on each request, so a Vercel project can move from week 1 to
 * week 2 by changing a variable and redeploying the environment — the pages themselves are
 * unchanged and stay statically prerendered.
 */
import { NextResponse, type NextRequest } from 'next/server';

import capabilityBundle from '@/public/data/capabilities.json';
import {
  ACTIVE_WEEK_COOKIE,
  ACTIVE_WEEK_ENV,
  GATED_ROUTE,
  capabilityForBundlePath,
  readActiveWeek,
  weekForPath,
  weekState,
} from '@/lib/gate';

export const config = {
  /**
   * Everything except Next's own assets and the files served straight off disk.
   *
   * The API proxy is deliberately *included*: it enforces the gate itself before it can
   * fall back to a stored artifact, and the cookie it gets from here keeps the two in
   * agreement.
   */
  matcher: ['/((?!_next/static|_next/image|favicon.ico|figures/|media/).*)'],
};

export function middleware(request: NextRequest) {
  const active = readActiveWeek(process.env[ACTIVE_WEEK_ENV]);
  const required = weekForPath(request.nextUrl.pathname);

  // Only a week that exists is gated. A request for week 99 is passed straight through to
  // the page's own not-found handling, because "coming soon" about a week the programme
  // does not have is a promise nothing will keep.
  const state = required === null ? 'ENABLED' : weekState(required, active);

  // A static bundle carrying a locked capability's result is refused outright. The pages
  // no longer read those files, but `public/data` is served directly, and "the page does
  // not render it" is not the same as "the browser cannot have it".
  const owner = capabilityForBundlePath(request.nextUrl.pathname);
  if (owner !== null && !bundleAllowed(owner, active)) {
    return refuseBundle(owner, active);
  }

  const response =
    state === 'LOCKED'
      ? rewriteToGate(request, required as number)
      : NextResponse.next();

  response.cookies.set(ACTIVE_WEEK_COOKIE, String(active), {
    path: '/',
    sameSite: 'lax',
    httpOnly: false, // the navigation reads it; it grants nothing
    maxAge: 60 * 60 * 12,
  });
  response.headers.set('x-aegis-active-week', String(active));
  return response;
}

/**
 * Rewrite rather than redirect.
 *
 * The address bar keeps saying `/weeks/8`, which is the honest thing to show: the reader
 * asked for week 8 and week 8 is what is being answered about. A redirect would lose the
 * question and land them somewhere they did not ask for.
 */
function rewriteToGate(request: NextRequest, required: number) {
  const url = request.nextUrl.clone();
  url.pathname = GATED_ROUTE;
  url.search = '';
  url.searchParams.set('week', String(required));
  url.searchParams.set('from', request.nextUrl.pathname);
  return NextResponse.rewrite(url);
}

/**
 * Whether a bundle's owning capability is open at this week.
 *
 * The unlock weeks come from the exported capability bundle, imported so the bundler
 * inlines it: middleware cannot reach the filesystem. That bundle is generated from
 * `research_modules.yaml` by `scripts/export_modules.py`, so the weeks are still declared
 * in exactly one place. Only the active week is read per request, which is what keeps it
 * changeable without a rebuild.
 */
const CAPABILITY_WEEKS: Record<string, number> = Object.fromEntries(
  (capabilityBundle.rows ?? []).map((c) => [c.id, c.enabled_from_week]),
);

function bundleAllowed(capabilityId: string, active: number): boolean {
  const week = CAPABILITY_WEEKS[capabilityId];
  return week === undefined ? true : week <= active;
}

function refuseBundle(capabilityId: string, active: number) {
  return NextResponse.json(
    {
      status: 'FEATURE_NOT_ENABLED',
      capability: capabilityId,
      active_week: active,
      required_week: CAPABILITY_WEEKS[capabilityId] ?? null,
      error: {
        code: 'FEATURE_NOT_ENABLED',
        reason:
          'This result belongs to a capability that is not enabled in this ' +
          'demonstration build.',
        remedy: `Set ${ACTIVE_WEEK_ENV} to that capability's week or later.`,
      },
    },
    { status: 403, headers: { 'Cache-Control': 'no-store' } },
  );
}
