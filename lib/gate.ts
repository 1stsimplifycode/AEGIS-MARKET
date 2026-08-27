/**
 * The capability gate, in TypeScript — the same rule `backend/capability.py` enforces.
 *
 * Two copies of a rule is normally two things to drift, so this one is kept to the part
 * that genuinely cannot cross the process boundary: the arithmetic. Which weeks exist and
 * where each unlocks is read from the manifest by the backend and handed over; the
 * comparison `enabled_from_week <= active_week` is repeated here because middleware runs
 * before any backend call and must decide without one.
 *
 * Nothing here is the gate. This file lets the interface *show* the right thing; the
 * backend is what refuses. A reader who edits the cookie changes a label and no more,
 * which is exactly the split §25 of the brief asks for.
 *
 * Isomorphic on purpose: middleware, server components and client components all import
 * it, so it must not reach for `node:fs`.
 */

/** How many weeks the programme has. The manifest is the source; this is the fallback. */
export const LAST_WEEK = 16;

/** The variable a launcher, a shell or a Vercel project sets. */
export const ACTIVE_WEEK_ENV = 'AEGIS_ACTIVE_WEEK';

/** How the interface learns the active week without making every page dynamic. */
export const ACTIVE_WEEK_COOKIE = 'aegis_active_week';

/** What a gated route is rewritten to. */
export const GATED_ROUTE = '/gated';

/**
 * Read an active week from whatever the environment gave us.
 *
 * Absent, empty or unparseable means the complete system. That default is what keeps the
 * gate out of the way of the test suite, the research runners and ordinary development: a
 * demonstration opts into a smaller surface rather than everything else opting out.
 */
export function readActiveWeek(raw: string | undefined | null, last = LAST_WEEK): number {
  if (raw === undefined || raw === null || String(raw).trim() === '') return last;
  const value = Number.parseInt(String(raw).trim(), 10);
  if (!Number.isFinite(value)) return last;
  return Math.max(1, Math.min(last, value));
}

/**
 * The three states a capability can be in, and why the last two are not the same thing.
 *
 * LOCKED means the capability is built, tested and sitting in the repository, and this
 * demonstration simply starts earlier in the programme. UNAVAILABLE means there is no such
 * capability at all. A reader told "coming soon" about something that will never come has
 * been misled, and a reader told "not found" about finished work has been misled the other
 * way — so the two are decided separately and never fall through to each other.
 */
export type CapabilityState = 'ENABLED' | 'LOCKED' | 'UNAVAILABLE';

/** Cumulative, and the only place the comparison is written on this side. */
export function isWeekEnabled(week: number, active: number): boolean {
  return weekState(week, active) === 'ENABLED';
}

/**
 * Whether a week exists at all.
 *
 * `/weeks/99` is not a week this programme has, and calling it "coming soon" would promise
 * something that is never arriving. It has to reach the page's own not-found path.
 */
export function weekExists(week: number, last = LAST_WEEK): boolean {
  return Number.isInteger(week) && week >= 1 && week <= last;
}

export function weekState(
  week: number,
  active: number,
  last = LAST_WEEK,
): CapabilityState {
  if (!weekExists(week, last)) return 'UNAVAILABLE';
  return week <= active ? 'ENABLED' : 'LOCKED';
}

/** The same question for a declared product capability. */
export function capabilityState(
  enabledFromWeek: number | undefined,
  active: number,
): CapabilityState {
  if (enabledFromWeek === undefined) return 'UNAVAILABLE';
  return enabledFromWeek <= active ? 'ENABLED' : 'LOCKED';
}

/** Which weeks a given active week exposes. */
export function enabledWeeks(active: number, last = LAST_WEEK): number[] {
  return Array.from({ length: last }, (_, i) => i + 1).filter((w) => w <= active);
}

/**
 * The week a path belongs to, or null when the path is not weekly.
 *
 * Only three shapes are weekly: the weekly feature and the two module halves. Everything
 * else — the index, the alignment layer, the product read models, Scenario Lab — is market
 * context that week 1 needs in order to be a product rather than a fragment, so it is not
 * gated and this returns null for it.
 */
export function weekForPath(pathname: string): number | null {
  const path = pathname.replace(/\/+$/, '') || '/';

  const week = /^\/weeks\/(\d{1,2})$/.exec(path);
  if (week) return Number.parseInt(week[1], 10);

  const half = /^\/(?:stats|multimodal)\/(\d{1,2})$/.exec(path);
  if (half) return Number.parseInt(half[1], 10);

  return null;
}

/**
 * The same question for an API path, used by the proxy.
 *
 * The proxy has to ask separately because it can serve a stored artifact when no Python
 * process is reachable — a deployment with the gate set and no backend would otherwise
 * hand out exactly the future-week result the gate exists to withhold.
 */
export function weekForApiPath(path: string): number | null {
  const clean = path.replace(/^\/+|\/+$/g, '');

  const week = /^weeks\/(\d{1,2})(?:\/run)?$/.exec(clean);
  if (week) return Number.parseInt(week[1], 10);

  const half = /^modules\/(?:STATS|MULTIMODAL)-(\d{2})(?:\/run)?$/i.exec(clean);
  if (half) return Number.parseInt(half[1], 10);

  return null;
}

/** What a gated page or response says. Written once so both say the same thing. */
export function gateCopy(requiredWeek: number, active: number, last = LAST_WEEK) {
  const available =
    active >= last
      ? 'Every week is available.'
      : active === 1
        ? `Week 1 is available; weeks 2 to ${last} are not.`
        : `Weeks 1 to ${active} are available; weeks ${active + 1} to ${last} are not.`;
  return {
    heading: `Week ${requiredWeek} is not enabled in this demonstration build`,
    available,
    remedy:
      `Set ${ACTIVE_WEEK_ENV}=${requiredWeek} — locally, ` +
      `weeks\\week_${requiredWeek}\\run.bat does that for you.`,
  };
}

/**
 * Exported bundles that carry a gated capability's result, and the week each needs.
 *
 * `public/data` is served as static assets, so a locked week's numbers were one URL away
 * from any browser regardless of what the pages rendered. Gating the page was never enough
 * on its own: `/data/modality_info.json` answered 200 with the week-14 decomposition while
 * `/weeks/14` was correctly refusing.
 *
 * The weeks are not written here — they are read from the capability registry the
 * middleware is handed. This maps a file to the capability that owns it, which is the one
 * fact the registry cannot know.
 */
export const GATED_BUNDLES: Record<string, string> = {
  'modality_info.json': 'contribution-analysis',
  'windows.json': 'event-analysis',
  'audio_model.json': 'audio-evidence',
  'video_model.json': 'video-evidence',
};

/** The capability that owns a static bundle path, or null when nothing owns it. */
export function capabilityForBundlePath(pathname: string): string | null {
  const match = /^\/data\/([A-Za-z0-9_.-]+)$/.exec(pathname);
  if (!match) return null;
  return GATED_BUNDLES[match[1]] ?? null;
}
