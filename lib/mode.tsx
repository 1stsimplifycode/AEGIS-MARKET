'use client';

/**
 * Experience mode: PRODUCT answers "what is happening", RESEARCH answers "how do we know".
 *
 * Four properties the brief calls for, and the reasons they are separate concerns:
 *
 * 1. **Mode is independent of theme.** Light/dark is a rendering preference; product/
 *    research changes what information is shown. Storing them in one key would couple two
 *    unrelated decisions and make each harder to reason about.
 * 2. **Mode persists, and a research URL activates research mode.** Someone who lands on
 *    `/research/...` from a link is a researcher for that visit, whatever their stored
 *    preference says; the preference is not overwritten by that inference.
 * 3. **Context survives the switch.** Switching mode while viewing an instrument keeps the
 *    instrument, the date and the event, because sending a user back to Home to punish
 *    them for wanting more depth is the opposite of the intent.
 * 4. **A module route never navigates on a mode switch.** Every module page — the 32
 *    STATS and MULTIMODAL modules, the 8 Scenario Lab modules and the 16 weekly
 *    pages — carries both
 *    experiences in one page, so switching depth there changes the section that
 *    renders and nothing else. The mode is written into the query string as well, so
 *    a module URL reproduces the exact view someone was looking at.
 */
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export type ExperienceMode = 'product' | 'research';
export type Theme = 'light' | 'dark' | 'system';

const MODE_KEY = 'aegis.experienceMode';
const THEME_KEY = 'aegis.theme';

/** Routes that render both experiences in one page and must not navigate on a switch. */
export const MODULE_ROUTE = /^\/(stats|multimodal|scenario|weeks)(\/|$)/;

export function isModuleRoute(pathname: string): boolean {
  return MODULE_ROUTE.test(pathname);
}

/** Context carried across a mode switch so depth never costs the user their place. */
export interface ModeContextValue {
  mode: ExperienceMode;
  setMode: (m: ExperienceMode) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** Instrument, event and date the user is currently looking at, if any. */
  context: { instrument?: string; event?: string; date?: string };
  setContext: (c: { instrument?: string; event?: string; date?: string }) => void;
  /** True when the current route forced the mode, rather than the stored preference. */
  modeForcedByRoute: boolean;
}

const Ctx = createContext<ModeContextValue | null>(null);

function readStored<T extends string>(key: string, fallback: T): T {
  if (typeof window === 'undefined') return fallback;
  try {
    const v = window.localStorage.getItem(key);
    return (v as T) ?? fallback;
  } catch {
    return fallback;
  }
}

export function routeMode(pathname: string): ExperienceMode | null {
  if (pathname.startsWith('/research')) return 'research';
  return null;
}

export function ModeProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? '/';
  const router = useRouter();

  const forced = routeMode(pathname);
  // First render must match the server output, so start from the default and adopt the
  // stored preference in an effect. Reading localStorage during render would produce a
  // hydration mismatch on every visit by a returning user.
  const [stored, setStored] = useState<ExperienceMode>('product');
  const [theme, setThemeState] = useState<Theme>('system');
  const [context, setContextState] = useState<ModeContextValue['context']>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setStored(readStored<ExperienceMode>(MODE_KEY, 'product'));
    setThemeState(readStored<Theme>(THEME_KEY, 'system'));
    setHydrated(true);
  }, []);

  const mode: ExperienceMode = forced ?? stored;

  useEffect(() => {
    if (!hydrated) return;
    const root = document.documentElement;
    root.dataset.mode = mode;
    const resolved =
      theme === 'system'
        ? window.matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light'
        : theme;
    root.dataset.theme = resolved;
  }, [mode, theme, hydrated]);

  const persist = useCallback((m: ExperienceMode) => {
    setStored(m);
    try {
      window.localStorage.setItem(MODE_KEY, m);
    } catch {
      /* storage unavailable: the mode still applies for this session */
    }
  }, []);

  const setMode = useCallback(
    (m: ExperienceMode) => {
      persist(m);

      // A module page holds both experiences. Switching there is a change of depth, not
      // of place, so the route stays and only the query records which depth is showing.
      if (isModuleRoute(pathname)) {
        router.replace(`${pathname}?mode=${m}`, { scroll: false });
        return;
      }

      // Carry the current subject across the switch rather than resetting to Home.
      const params = new URLSearchParams();
      if (context.instrument) params.set('instrument', context.instrument);
      if (context.event) params.set('event', context.event);
      if (context.date) params.set('date', context.date);
      const qs = params.toString() ? `?${params.toString()}` : '';
      if (m === 'research' && !pathname.startsWith('/research')) {
        router.push(`/research${qs}`);
      } else if (m === 'product' && pathname.startsWith('/research')) {
        router.push(context.instrument ? `/instruments/${context.instrument}` : '/');
      }
    },
    [context, pathname, router, persist],
  );

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    try {
      window.localStorage.setItem(THEME_KEY, t);
    } catch {
      /* ignore */
    }
  }, []);

  const setContext = useCallback((c: ModeContextValue['context']) => {
    setContextState((prev) => ({ ...prev, ...c }));
  }, []);

  const value = useMemo<ModeContextValue>(
    () => ({
      mode,
      setMode,
      theme,
      setTheme,
      context,
      setContext,
      modeForcedByRoute: forced !== null,
    }),
    [mode, setMode, theme, setTheme, context, setContext, forced],
  );

  return (
    <Ctx.Provider value={value}>
      {/* `useSearchParams` opts its whole subtree out of prerendering. Isolating it in
          this leaf keeps every page server-rendered; putting it in the provider made
          client-component pages ship a blank shell until JavaScript loaded. */}
      <Suspense fallback={null}>
        <QuerySync onMode={persist} />
      </Suspense>
      {children}
    </Ctx.Provider>
  );
}

/**
 * Restores state from the query string: the subject on a deep-linked research route, and
 * the mode on a shared module URL.
 *
 * A shared `?mode=research` link has to open in research mode for the person receiving
 * it, which is the whole point of putting the mode in the URL. It updates the stored
 * preference too, because someone who follows a research link and keeps browsing is
 * expressing a preference.
 */
function QuerySync({ onMode }: { onMode: (m: ExperienceMode) => void }) {
  const search = useSearchParams();
  const pathname = usePathname() ?? '/';
  const { setContext } = useMode();
  const instrument = search?.get('instrument') ?? undefined;
  const event = search?.get('event') ?? undefined;
  const date = search?.get('date') ?? undefined;
  const queryMode = search?.get('mode') ?? undefined;

  useEffect(() => {
    if (instrument || event || date) setContext({ instrument, event, date });
  }, [instrument, event, date, setContext]);

  useEffect(() => {
    if (!isModuleRoute(pathname)) return;
    if (queryMode === 'product' || queryMode === 'research') onMode(queryMode);
  }, [pathname, queryMode, onMode]);

  return null;
}

export function useMode(): ModeContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useMode must be used inside <ModeProvider>');
  return v;
}

/** Registers the subject of the current page so a mode switch can carry it. */
export function useSubject(subject: {
  instrument?: string;
  event?: string;
  date?: string;
}) {
  const { setContext } = useMode();
  const { instrument, event, date } = subject;
  useEffect(() => {
    setContext({ instrument, event, date });
  }, [instrument, event, date, setContext]);
}
