'use client';

/**
 * Search, as the first thing on the page.
 *
 * It filters a list the page already has rather than calling anything: every instrument
 * the product can open is in the snapshot the server rendered, so matching happens as the
 * reader types with nothing in between. A network round trip per keystroke would be
 * slower and would find exactly the same instruments.
 *
 * Submitting with nothing selected goes to Discover with the term, so the search box is
 * never a dead end.
 */
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMemo, useRef, useState } from 'react';

export interface SearchItem {
  symbol: string;
  tracked: boolean;
  analysed: boolean;
  stateLabel: string | null;
  stateTone: string | null;
}

/**
 * Entities that are not instruments but that a reader will certainly search for.
 *
 * NIFTY 50 is an index: it has a level, not a price, and its own page. Someone typing
 * "nifty" means the benchmark, and a search that answered with fifty equities would be
 * answering a question they did not ask.
 */
interface Entity {
  id: string;
  label: string;
  kind: string;
  blurb: string;
  href: string;
  aliases: string[];
}

const ENTITIES: Entity[] = [
  {
    id: 'NIFTY50',
    label: 'NIFTY 50',
    kind: 'Index',
    blurb: 'Indian large-cap benchmark · 50 constituents',
    href: '/markets/nifty-50',
    aliases: ['NIFTY', 'NIFTY50', 'NIFTY 50', '^NSEI', 'NSEI', 'BENCHMARK', 'INDEX'],
  },
];

function matchEntities(q: string): Entity[] {
  if (!q) return [];
  return ENTITIES.filter((e) =>
    e.aliases.some((a) => a.replace(/\s+/g, '').includes(q.replace(/\s+/g, ''))),
  );
}

export function SearchBox({
  items,
  placeholder = 'Search instruments by symbol…',
  autoFocus = false,
}: {
  items: SearchItem[];
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const router = useRouter();
  const box = useRef<HTMLDivElement>(null);

  const query = term.trim().toUpperCase();
  const entities = useMemo(() => matchEntities(query), [query]);
  const matches = useMemo(() => {
    if (!query) return [];
    const starts = items.filter((i) => i.symbol.startsWith(query));
    const contains = items.filter(
      (i) => !i.symbol.startsWith(query) && i.symbol.includes(query),
    );
    return [...starts, ...contains].slice(0, 8);
  }, [query, items]);
  const hasResults = entities.length + matches.length > 0;

  function go(symbol: string) {
    setOpen(false);
    setTerm('');
    router.push(`/instruments/${symbol}`);
  }

  return (
    <div className="search" ref={box}>
      <div className="search__field">
        <span className="search__icon" aria-hidden="true">
          ⌕
        </span>
        <input
          type="search"
          value={term}
          autoFocus={autoFocus}
          placeholder={placeholder}
          aria-label="Search instruments"
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => {
            setTerm(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, matches.length - 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              if (entities.length > 0) {
                setOpen(false);
                router.push(entities[0].href);
              } else if (matches[active]) go(matches[active].symbol);
              else if (term.trim()) {
                router.push(`/discover?q=${encodeURIComponent(term.trim())}`);
              }
            } else if (e.key === 'Escape') {
              setOpen(false);
            }
          }}
        />
      </div>

      {open && hasResults ? (
        <ul className="search__results" role="listbox">
          {entities.map((e) => (
            <li key={e.id}>
              <Link
                href={e.href}
                className="search__result search__result--entity"
                onClick={() => setOpen(false)}
              >
                <span className="search__entity">
                  <span className="search__symbol">{e.label}</span>
                  <span className="search__blurb">{e.blurb}</span>
                </span>
                <span className="tag" data-tone="calm">
                  {e.kind}
                </span>
              </Link>
            </li>
          ))}
          {matches.map((m, i) => (
            <li key={m.symbol}>
              <Link
                href={`/instruments/${m.symbol}`}
                className={`search__result${i === active ? ' is-active' : ''}`}
                onMouseEnter={() => setActive(i)}
                onClick={() => setOpen(false)}
              >
                <span className="search__symbol">{m.symbol}</span>
                <span className="search__meta">
                  {m.tracked ? <span className="tag">Tracked</span> : null}
                  {m.analysed && m.stateLabel ? (
                    <span className="tag" data-tone={m.stateTone ?? 'calm'}>
                      {m.stateLabel}
                    </span>
                  ) : (
                    <span className="tag tag--quiet">Price only</span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}

      {open && term.trim() && !hasResults ? (
        <div className="search__results search__results--empty">
          <p>
            No instrument symbol contains <strong>{term.trim().toUpperCase()}</strong>.
          </p>
          <p className="small muted">
            Search is by NSE symbol — try TCS, RELIANCE or INFY.
          </p>
        </div>
      ) : null}
    </div>
  );
}
