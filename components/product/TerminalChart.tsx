'use client';

/**
 * The charting workspace for one security: candles, volume, RSI and MACD under a shared
 * crosshair.
 *
 * **One hover index drives every panel.** The pointer position is converted to a session
 * index once, and all four panels draw their guide at that same index. This is what makes
 * the panels readable together: the RSI value under the cursor is the RSI *of the candle
 * under the cursor*, and a reader can see that rather than having to trust it.
 *
 * **The tooltip shows stored values, never interpolated ones.** The index is snapped to a
 * real session, so every figure in the tooltip is a number that exists in the payload. A
 * session with no indicator yet — the RSI warm-up — reports that it has none rather than
 * borrowing the neighbouring value.
 *
 * **Timeframes offered are only those the data supports.** The window arrives from the
 * backend already bounded; the buttons slice that window and a range longer than what was
 * fetched is not offered, because a button that silently returns the same 120 sessions
 * under four different labels is lying about the range.
 *
 * Nothing here is an instruction. The panels are labelled as evidence, the RSI reference
 * lines are labelled as reference levels, and there is no control that proposes an action.
 */
import { useCallback, useMemo, useRef, useState } from 'react';

import type { IndicatorSeries } from '@/lib/product';

import type { Candle } from './Bits';

const RANGES = [
  { key: '1M', sessions: 21 },
  { key: '3M', sessions: 63 },
  { key: '6M', sessions: 126 },
  { key: '1Y', sessions: 252 },
  { key: 'MAX', sessions: Number.POSITIVE_INFINITY },
] as const;

type RangeKey = (typeof RANGES)[number]['key'];

const inr = (n: number) =>
  `₹${n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const vol = (n: number) =>
  n >= 1e7 ? `${(n / 1e7).toFixed(2)}Cr` : n >= 1e5 ? `${(n / 1e5).toFixed(2)}L` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : `${n}`;

const pretty = (iso: string) => {
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(d);
};

function path(values: (number | null)[], lo: number, hi: number, slot: number) {
  const span = hi - lo || 1;
  const out: string[] = [];
  let open = false;
  values.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) {
      open = false;
      return;
    }
    const x = i * slot + slot / 2;
    const y = 100 - ((v - lo) / span) * 100;
    out.push(`${open ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`);
    open = true;
  });
  return out.join(' ');
}

export function TerminalChart({
  candles,
  indicators,
}: {
  candles: Candle[];
  indicators?: IndicatorSeries;
}) {
  const [range, setRange] = useState<RangeKey>('MAX');
  const [hover, setHover] = useState<number | null>(null);
  const [cursor, setCursor] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const wrap = useRef<HTMLDivElement | null>(null);

  const total = candles.length;
  const available = useMemo(
    () => RANGES.filter((r) => r.sessions <= total || r.key === 'MAX'),
    [total],
  );

  const view = useMemo(() => {
    const spec = RANGES.find((r) => r.key === range) ?? RANGES[RANGES.length - 1];
    const n = Math.min(spec.sessions === Number.POSITIVE_INFINITY ? total : spec.sessions, total);
    const start = total - n;
    const ind = indicators && indicators.dates.length === total ? indicators : undefined;
    return {
      candles: candles.slice(start),
      rsi: ind ? ind.rsi.slice(start) : null,
      macd: ind ? ind.macd.slice(start) : null,
      signal: ind ? ind.macd_signal.slice(start) : null,
      hist: ind ? ind.macd_histogram.slice(start) : null,
      refs: ind?.rsi_reference_levels ?? [30, 70],
    };
  }, [candles, indicators, range, total]);

  const n = view.candles.length;
  const slot = 100 / Math.max(n, 1);

  const price = useMemo(() => {
    const lows = view.candles.map((c) => c.low);
    const highs = view.candles.map((c) => c.high);
    const lo = Math.min(...lows);
    const hi = Math.max(...highs);
    const pad = (hi - lo || 1) * 0.05;
    return { lo: lo - pad, hi: hi + pad };
  }, [view.candles]);

  const maxVol = useMemo(
    () => Math.max(...view.candles.map((c) => (typeof c.volume === 'number' ? c.volume : 0)), 1),
    [view.candles],
  );

  const macdBounds = useMemo(() => {
    const all = [...(view.macd ?? []), ...(view.signal ?? []), ...(view.hist ?? [])].filter(
      (v): v is number => typeof v === 'number' && Number.isFinite(v),
    );
    if (!all.length) return null;
    return { lo: Math.min(...all), hi: Math.max(...all) };
  }, [view.macd, view.signal, view.hist]);

  const onMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const el = wrap.current;
      if (!el || n === 0) return;
      const r = el.getBoundingClientRect();
      const frac = (e.clientX - r.left) / r.width;
      const idx = Math.min(n - 1, Math.max(0, Math.floor(frac * n)));
      setHover(idx);
      setCursor({ x: e.clientX - r.left, y: e.clientY - r.top });
    },
    [n],
  );

  const leave = useCallback(() => setHover(null), []);

  if (n < 2) {
    return <p className="small muted">Not enough sessions with complete OHLC to draw the workspace.</p>;
  }

  const c = hover !== null ? view.candles[hover] : null;
  const guideX = hover !== null ? hover * slot + slot / 2 : null;
  const yPrice = (v: number) => ((price.hi - v) / (price.hi - price.lo || 1)) * 100;

  const Guide = () =>
    guideX === null ? null : (
      <line className="term__guide" x1={guideX} x2={guideX} y1="0" y2="100" vectorEffect="non-scaling-stroke" />
    );

  return (
    <div className="term">
      <div className="term__toolbar">
        <div className="term__ranges" role="group" aria-label="Timeframe">
          {available.map((r) => (
            <button
              key={r.key}
              type="button"
              className="term__range"
              data-active={range === r.key}
              onClick={() => setRange(r.key)}
            >
              {r.key}
            </button>
          ))}
        </div>
        <span className="term__span">
          {n} sessions · {view.candles[0].date} → {view.candles[n - 1].date}
        </span>
      </div>

      <div className="term__panels" ref={wrap} onPointerMove={onMove} onPointerLeave={leave}>
        {/* ---------------------------------------------------------- price */}
        <div className="term__panel term__panel--price">
          <div className="term__axisLabel">
            <span>{price.hi.toFixed(2)}</span>
            <span>{((price.hi + price.lo) / 2).toFixed(2)}</span>
            <span>{price.lo.toFixed(2)}</span>
          </div>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Candlestick price chart">
            {view.candles.map((cd, i) => {
              const up = cd.close >= cd.open;
              const top = yPrice(Math.max(cd.open, cd.close));
              const bottom = yPrice(Math.min(cd.open, cd.close));
              const x = i * slot + slot / 2;
              const w = Math.max(slot * 0.6, 0.08);
              return (
                <g key={cd.date} data-dir={up ? 'up' : 'down'} className="term__candle">
                  <line className="term__wick" x1={x} x2={x} y1={yPrice(cd.high)} y2={yPrice(cd.low)} vectorEffect="non-scaling-stroke" />
                  <rect className="term__body" x={x - w / 2} y={top} width={w} height={Math.max(bottom - top, 0.3)} />
                </g>
              );
            })}
            <Guide />
          </svg>
        </div>

        {/* --------------------------------------------------------- volume */}
        <div className="term__panel term__panel--vol">
          <span className="term__panelTag">Volume</span>
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Volume">
            {view.candles.map((cd, i) => {
              const v = typeof cd.volume === 'number' ? cd.volume : 0;
              const h = (v / maxVol) * 100;
              const w = Math.max(slot * 0.6, 0.08);
              return (
                <rect
                  key={cd.date}
                  className="term__volBar"
                  data-dir={cd.close >= cd.open ? 'up' : 'down'}
                  x={i * slot + slot / 2 - w / 2}
                  y={100 - h}
                  width={w}
                  height={Math.max(h, 0.3)}
                />
              );
            })}
            <Guide />
          </svg>
        </div>

        {/* ------------------------------------------------------------ RSI */}
        <div className="term__panel term__panel--rsi">
          <span className="term__panelTag">RSI · momentum evidence</span>
          {view.rsi ? (
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Relative strength index">
              {view.refs.map((r) => (
                <line key={r} className="term__ref" x1="0" x2="100" y1={100 - r} y2={100 - r} vectorEffect="non-scaling-stroke" />
              ))}
              <path className="term__line" d={path(view.rsi, 0, 100, slot)} vectorEffect="non-scaling-stroke" />
              <Guide />
            </svg>
          ) : (
            <p className="small muted term__none">RSI unavailable for this window.</p>
          )}
          {view.rsi ? (
            <>
              <span className="term__refTag" style={{ top: `${100 - view.refs[1]}%` }}>{view.refs[1]} reference</span>
              <span className="term__refTag" style={{ top: `${100 - view.refs[0]}%` }}>{view.refs[0]} reference</span>
            </>
          ) : null}
        </div>

        {/* ----------------------------------------------------------- MACD */}
        <div className="term__panel term__panel--macd">
          <span className="term__panelTag">MACD · trend and momentum evidence</span>
          {macdBounds && view.macd && view.signal && view.hist ? (
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="MACD">
              {(() => {
                const { lo, hi } = macdBounds;
                const span = hi - lo || 1;
                const zero = 100 - ((0 - lo) / span) * 100;
                const w = Math.max(slot * 0.5, 0.06);
                return (
                  <>
                    <line className="term__zero" x1="0" x2="100" y1={zero} y2={zero} vectorEffect="non-scaling-stroke" />
                    {view.hist!.map((v, i) =>
                      v === null || !Number.isFinite(v) ? null : (
                        <rect
                          key={i}
                          className="term__histBar"
                          data-dir={v >= 0 ? 'up' : 'down'}
                          x={i * slot + slot / 2 - w / 2}
                          y={Math.min(100 - ((v - lo) / span) * 100, zero)}
                          width={w}
                          height={Math.max(Math.abs(zero - (100 - ((v - lo) / span) * 100)), 0.2)}
                        />
                      ),
                    )}
                    <path className="term__line" d={path(view.macd!, lo, hi, slot)} vectorEffect="non-scaling-stroke" />
                    <path className="term__line term__line--signal" d={path(view.signal!, lo, hi, slot)} vectorEffect="non-scaling-stroke" />
                    <Guide />
                  </>
                );
              })()}
            </svg>
          ) : (
            <p className="small muted term__none">MACD unavailable for this window.</p>
          )}
        </div>

        {/* -------------------------------------------------------- tooltip */}
        {c ? (
          <div
            className="term__tip"
            style={{
              left: `${Math.min(Math.max(cursor.x + 14, 8), 640)}px`,
              top: `${Math.max(cursor.y - 10, 8)}px`,
            }}
            role="status"
          >
            <div className="term__tipDate">{pretty(c.date)}</div>
            <dl className="term__tipGrid">
              <div><dt>O</dt><dd>{inr(c.open)}</dd></div>
              <div><dt>H</dt><dd>{inr(c.high)}</dd></div>
              <div><dt>L</dt><dd>{inr(c.low)}</dd></div>
              <div><dt>C</dt><dd className={c.close >= c.open ? 'up' : 'down'}>{inr(c.close)}</dd></div>
              {typeof c.volume === 'number' ? (
                <div><dt>Vol</dt><dd>{vol(c.volume)}</dd></div>
              ) : null}
              {typeof c.turnover === 'number' ? (
                <div><dt>Value</dt><dd>{`₹${vol(c.turnover)}`}</dd></div>
              ) : null}
            </dl>
            {view.rsi ? (
              <div className="term__tipRow">
                <span>RSI</span>
                <span>{view.rsi[hover!] === null ? 'no value yet' : view.rsi[hover!]!.toFixed(2)}</span>
              </div>
            ) : null}
            {view.macd ? (
              <div className="term__tipRow">
                <span>MACD</span>
                <span>
                  {view.macd[hover!] === null
                    ? 'no value yet'
                    : `${view.macd[hover!]!.toFixed(2)} · sig ${view.signal![hover!]?.toFixed(2) ?? '—'} · hist ${view.hist![hover!]?.toFixed(2) ?? '—'}`}
                </span>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <p className="term__foot">
        RSI and MACD are derived from the closing prices shown above; the exchange publishes
        neither. Both are evidence about observed price behaviour and neither proposes an
        action. Hover any session to read its stored values.
      </p>
    </div>
  );
}
