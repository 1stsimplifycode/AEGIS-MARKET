'use client';

/**
 * The module sidebar.
 *
 * All 32 modules are listed rather than paginated or grouped behind a menu, because a
 * researcher's most common navigation is "the one next to the one I am reading" and a
 * product user's is "what else is here". Every link carries the current mode so the
 * chosen depth survives navigation as well as the toggle.
 *
 * It is a `<nav>` with real links, not a client-side router shim: every module page is
 * prerendered, so following one is a document load that works without JavaScript.
 */
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { useMode } from '@/lib/mode';
import type { ResearchModule } from '@/lib/moduleTypes';

const RESEARCH_LAB = [
  { href: '/research/datasets', label: 'Datasets' },
  { href: '/research/experiments', label: 'Experiments' },
  { href: '/research/figures', label: 'Figures' },
  { href: '/research/tables', label: 'Tables' },
  { href: '/research/artifacts', label: 'Artifacts' },
  { href: '/research/claims', label: 'Claim ledger' },
  { href: '/research/limitations', label: 'Limitations' },
  { href: '/research/reproducibility', label: 'Reproducibility' },
];

export function ModuleNav({ modules }: { modules: ResearchModule[] }) {
  const pathname = usePathname() ?? '';
  const { mode } = useMode();
  const stats = modules.filter((m) => m.category === 'STATS');
  const multimodal = modules.filter((m) => m.category === 'MULTIMODAL');
  const scenario = modules.filter((m) => m.category === 'SCENARIO');

  const section = (title: string, base: string, list: ResearchModule[]) => (
    <div className="moduleNav__section">
      <Link href={`${base}?mode=${mode}`} className="moduleNav__heading">
        {title}
        <span className="moduleNav__count">{list.length}</span>
      </Link>
      <ul>
        {list.map((m) => {
          const active = pathname === m.route;
          return (
            <li key={m.id}>
              <Link
                href={`${m.route}?mode=${mode}`}
                className={active ? 'moduleNav__link is-active' : 'moduleNav__link'}
                aria-current={active ? 'page' : undefined}
              >
                <span className="moduleNav__index">
                  {String(m.index).padStart(2, '0')}
                </span>
                <span className="moduleNav__label">{m.name}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    <nav className="moduleNav" aria-label="Research modules">
      {section('STATS', '/stats', stats)}
      {section('MULTIMODAL', '/multimodal', multimodal)}
      {section('SCENARIO LAB', '/scenario', scenario)}
      <div className="moduleNav__section">
        <span className="moduleNav__heading">Research lab</span>
        <ul>
          {RESEARCH_LAB.map((l) => (
            <li key={l.href}>
              <Link
                href={l.href}
                className={
                  pathname.startsWith(l.href)
                    ? 'moduleNav__link is-active'
                    : 'moduleNav__link'
                }
              >
                <span className="moduleNav__label">{l.label}</span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
