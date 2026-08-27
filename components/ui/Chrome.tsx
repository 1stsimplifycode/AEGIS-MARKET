'use client';

/**
 * Global chrome: masthead, mode toggle, theme control, mode-aware navigation.
 *
 * The mode toggle is deliberately the most prominent control after the wordmark. It
 * changes what the whole application shows, so hiding it in Settings would make the two
 * experiences feel like two products rather than two depths of one.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import {
  LockedFeatureNotice,
  useLockedNotice,
  type LockedCapability,
} from '@/components/product/LockedFeature';
import { capabilityState } from '@/lib/gate';
import { useMode, type ExperienceMode, type Theme } from '@/lib/mode';
import { useActiveWeek } from '@/lib/useActiveWeek';

/**
 * Product navigation names what a reader can do, not what the system is made of.
 *
 * The previous version listed the architecture — Universe, Events, Weeks, Statistics,
 * Multimodal — which is an accurate description of the repository and a poor description
 * of the product. Every one of those still exists; they are reached through Markets,
 * Analysis and Research, where a reader arrives already knowing what they came for.
 */
const PRODUCT_NAV = [
  { href: '/', label: 'Home' },
  // The benchmark is the market context everything else is read against, so it is a
  // destination rather than something to be found inside a list of instruments.
  { href: '/markets/nifty-50', label: 'NIFTY 50' },
  { href: '/discover', label: 'Discover' },
  { href: '/markets', label: 'Instruments' },
  { href: '/analysis', label: 'Analysis' },
  { href: '/watchlist', label: 'Watchlist' },
  // The operational surface. Simulated and labelled as such on every page, but a real
  // workflow: persistent, validated against real market data, and audited.
  { href: '/trading', label: 'Trading' },
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/funds', label: 'Funds' },
  { href: '/research', label: 'Research' },
  { href: '/settings', label: 'Settings' },
];

/**
 * A navigation entry, which may be a capability the current week has not reached.
 *
 * The shape of the product does not change with the active week — every capability stays
 * in the navigation, so a reader can see what AEGIS-Market is rather than a truncated
 * version of it. What changes is whether an entry is a destination or a locked control
 * that explains itself.
 */
type NavEntry = {
  href: string;
  label: string;
  capability?: { id: string; enabledFromWeek: number; summary: string };
};

/**
 * Research navigation keeps every concept the programme uses, under its own name.
 *
 * Nothing was removed from here. The weekly programme moved to Development progress,
 * which is what it is: a demonstration of how the capability was built, not a way for a
 * reader to find an answer.
 */
const RESEARCH_NAV = [
  { href: '/research', label: 'Overview' },
  { href: '/research/experiments', label: 'Experiments' },
  { href: '/research/ablations', label: 'Ablations' },
  { href: '/research/models', label: 'Models' },
  { href: '/research/datasets', label: 'Datasets' },
  { href: '/research/alignment', label: 'Evidence alignment' },
  { href: '/research/xai', label: 'XAI Lab' },
  { href: '/research/lifecycle', label: 'Lifecycle' },
  { href: '/research/trustworthy-ai', label: 'Trustworthy AI' },
  { href: '/research/affective-lab', label: 'Affective Lab' },
  { href: '/research/statistics', label: 'Statistics' },
  { href: '/research/robustness', label: 'Robustness & Seeds' },
  { href: '/stats', label: 'STATS modules' },
  { href: '/multimodal', label: 'Multimodal modules' },
  { href: '/scenario', label: 'Scenario Lab' },
  { href: '/research/progress', label: 'Development progress' },
  { href: '/research/figures', label: 'Figures' },
  { href: '/research/tables', label: 'Tables' },
  { href: '/research/artifacts', label: 'Artifacts' },
  { href: '/research/limitations', label: 'Limitations & Opportunities' },
  { href: '/research/claims', label: 'Claim Ledger' },
  { href: '/research/paper-lab', label: 'Paper Lab' },
  { href: '/research/reproducibility', label: 'Reproducibility' },
  { href: '/settings', label: 'Settings' },
];

const MOBILE_PRODUCT = ['/', '/markets/nifty-50', '/discover', '/analysis'].map(
  (href) => PRODUCT_NAV.find((n) => n.href === href)!,
);

/**
 * Picked by href rather than by position: an earlier version indexed into RESEARCH_NAV,
 * so inserting one entry silently repointed the mobile bar at a different page.
 */
const MOBILE_RESEARCH = [
  '/research',
  '/stats',
  '/multimodal',
  '/scenario',
].map((href) => RESEARCH_NAV.find((n) => n.href === href)!);

export function ModeToggle() {
  const { mode, setMode, modeForcedByRoute } = useMode();
  return (
    <div
      className="modeToggle"
      role="radiogroup"
      aria-label="Experience mode"
      title={
        modeForcedByRoute
          ? 'This route is a research route, so Research mode is active'
          : undefined
      }
    >
      {(['product', 'research'] as ExperienceMode[]).map((m) => (
        <button
          key={m}
          type="button"
          role="radio"
          aria-checked={mode === m}
          className={mode === m ? 'modeToggle__btn is-active' : 'modeToggle__btn'}
          onClick={() => setMode(m)}
        >
          {m === 'product' ? 'Product' : 'Research'}
          <span className="modeToggle__hint">
            {m === 'product' ? 'understand' : 'verify'}
          </span>
        </button>
      ))}
    </div>
  );
}

export function ThemeControl() {
  const { theme, setTheme } = useMode();
  return (
    <label className="themeControl">
      <span className="visually-hidden">Theme</span>
      <select
        value={theme}
        onChange={(e) => setTheme(e.target.value as Theme)}
        aria-label="Theme"
      >
        <option value="system">Auto</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}

export function Masthead({
  capabilities = [],
}: {
  /**
   * The product's capabilities and the week each joins, read from the manifest by the
   * server layout. Passed in rather than imported so this component holds no list of its
   * own: adding a capability is a manifest edit.
   */
  capabilities?: {
    id: string;
    name: string;
    href: string;
    enabled_from_week: number;
    summary: string;
    surfaces?: string[];
  }[];
} = {}) {
  const { mode } = useMode();
  const pathname = usePathname() ?? '/';
  const activeWeek = useActiveWeek();
  const { locked, show, dismiss } = useLockedNotice();

  // Capabilities that are already ordinary navigation entries are not repeated; the rest
  // join the product nav in the order the manifest declares them.
  const existing = new Set(PRODUCT_NAV.map((n) => n.href));
  const extra: NavEntry[] = capabilities
    .filter((c) => (c.surfaces ?? ['nav']).includes('nav'))
    .filter((c) => !existing.has(c.href))
    .map((c) => ({
      href: c.href,
      label: c.name,
      capability: {
        id: c.id,
        enabledFromWeek: c.enabled_from_week,
        summary: c.summary,
      },
    }));
  const productNav: NavEntry[] = [...PRODUCT_NAV.slice(0, -2), ...extra,
                                  ...PRODUCT_NAV.slice(-2)];
  const nav: NavEntry[] = mode === 'research' ? RESEARCH_NAV : productNav;
  const mobile = mode === 'research' ? MOBILE_RESEARCH : MOBILE_PRODUCT;

  /**
   * A locked entry is a button, not a disabled link.
   *
   * `disabled` would stop it receiving the click, and the click is the whole point — it is
   * how a reader finds out why the capability is not open yet. `aria-disabled` states the
   * condition to assistive technology while leaving the control operable, which is the
   * accessible pattern for exactly this case.
   */
  const onLocked = (entry: NavEntry) => {
    const c = entry.capability;
    if (!c) return;
    show({
      name: entry.label,
      enabledFromWeek: c.enabledFromWeek,
      activeWeek,
      summary: c.summary,
    } satisfies LockedCapability);
  };

  return (
    <>
      <header className="masthead" data-mode={mode}>
        <div className="masthead__row">
          <Link href="/" className="masthead__title">
            AEGIS<span className="masthead__accent">-Market</span>
          </Link>
          <ModeToggle />
          <form className="mastheadSearch" action="/discover" role="search">
            <input
              type="search"
              name="q"
              placeholder="Search instruments…"
              aria-label="Search instruments"
            />
          </form>
          <span className="masthead__market" title="Market covered">
            India · NSE
          </span>
          <ThemeControl />
        </div>
        <p className="masthead__sub">
          {mode === 'product'
            ? 'Understand unusual market behaviour through the evidence behind it.'
            : 'Research workspace — every number traceable to an experiment, a dataset and a seed.'}
        </p>
        <nav className="nav" aria-label="Primary">
          {nav.map((n) => {
            const active =
              n.href === '/' ? pathname === '/' : pathname.startsWith(n.href);
            const state = n.capability
              ? capabilityState(n.capability.enabledFromWeek, activeWeek)
              : 'ENABLED';
            if (state === 'LOCKED') {
              return (
                <button
                  key={n.href}
                  type="button"
                  className="nav__link nav__link--locked"
                  aria-disabled="true"
                  data-requires-week={n.capability?.enabledFromWeek}
                  onClick={() => onLocked(n)}
                >
                  {n.label}
                  <span className="nav__lock" aria-hidden="true">
                    🔒
                  </span>
                  <span className="visually-hidden">
                    {' '}
                    — coming soon, available from week {n.capability?.enabledFromWeek}
                  </span>
                </button>
              );
            }
            return (
              <Link
                key={n.href}
                href={n.href}
                className={active ? 'nav__link is-active' : 'nav__link'}
                aria-current={active ? 'page' : undefined}
              >
                {n.label}
              </Link>
            );
          })}
        </nav>
      </header>

      <LockedFeatureNotice locked={locked} onDismiss={dismiss} />

      <nav className="mobileNav" aria-label="Primary mobile">
        {mobile.map((n) => (
          <Link key={n.href} href={n.href} className="mobileNav__link">
            {n.label}
          </Link>
        ))}
        <Link href="/settings" className="mobileNav__link">
          More
        </Link>
      </nav>
    </>
  );
}
