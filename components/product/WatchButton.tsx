'use client';

/**
 * Follow something for analysis.
 *
 * "Follow" is the whole verb. It records that someone wants to come back and look, and it
 * carries no quantity, no cost and no position — a control that implied any of those would
 * be the first step toward a portfolio, and a portfolio implies the one thing this product
 * does not do.
 *
 * An index and an instrument can both be followed and are stored with their kind, so the
 * watchlist can send each to the page that exists for it.
 *
 * Kept on the server. A watchlist held only in `localStorage` disappears with the tab, is
 * invisible to the backend that might act on it, and is not something a product can
 * honestly describe as saved. Every change writes a row and an audit event; the local
 * copy below survives only as the reader for a browser that cannot reach the backend, so
 * the control degrades rather than breaking.
 */
import { useEffect, useState } from 'react';

export const WATCHLIST_KEY = 'aegis.watchlist';

export interface Followed {
  symbol: string;
  addedAt: string;
  kind?: 'instrument' | 'index';
  label?: string;
}

export function readWatchlist(): Followed[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(WATCHLIST_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (r): r is Followed =>
        typeof r === 'object' && r !== null && typeof (r as Followed).symbol === 'string',
    );
  } catch {
    return [];
  }
}

export function writeWatchlist(items: Followed[]): void {
  try {
    window.localStorage.setItem(WATCHLIST_KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable: the list still applies for this session */
  }
}

export function WatchButton({
  symbol,
  label,
  kind = 'instrument',
}: {
  symbol: string;
  label?: string;
  kind?: 'instrument' | 'index';
}) {
  const [following, setFollowing] = useState(false);
  const [ready, setReady] = useState(false);

  const [busy, setBusy] = useState(false);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const response = await fetch('/api/aegis/watchlists', { cache: 'no-store' });
        const payload = await response.json();
        if (cancelled) return;
        if (Array.isArray(payload?.symbols)) {
          setFollowing(payload.symbols.includes(symbol.toUpperCase()));
          setOffline(false);
        } else {
          throw new Error('no watchlist');
        }
      } catch {
        // The backend is not answering. Fall back to what this browser remembers rather
        // than showing an empty list as though nothing were followed.
        if (cancelled) return;
        setFollowing(readWatchlist().some((i) => i.symbol === symbol));
        setOffline(true);
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  async function toggle() {
    const next = !following;
    setBusy(true);
    try {
      const response = await fetch(
        `/api/aegis/watchlists/${next ? 'watch' : 'unwatch'}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol: symbol.toUpperCase() }),
        },
      );
      const payload = await response.json();
      if (!Array.isArray(payload?.symbols)) throw new Error('refused');
      setFollowing(payload.symbols.includes(symbol.toUpperCase()));
      setOffline(false);
      // Mirror locally so a later reload without the backend still shows the truth.
      writeWatchlist(
        payload.symbols.map((s: string) => ({
          symbol: s,
          kind: s === symbol.toUpperCase() ? kind : undefined,
          label: s === symbol.toUpperCase() ? label : undefined,
          addedAt: new Date().toISOString(),
        })),
      );
    } catch {
      setOffline(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="watchBtnWrap">
      <button
        type="button"
        className={following ? 'watchBtn is-following' : 'watchBtn'}
        onClick={() => void toggle()}
        disabled={!ready || busy}
        aria-pressed={following}
      >
        <span aria-hidden="true">{following ? '★' : '☆'}</span>
        {following ? 'Following' : 'Follow for analysis'}
      </button>
      {offline ? (
        <span className="watchBtn__offline small muted" role="status">
          Not saved — the backend is not answering.
        </span>
      ) : null}
    </span>
  );
}
