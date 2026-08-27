'use client';

/**
 * The index chart: four views of one backend series.
 *
 * Level, daily change, volatility and drawdown are **columns the backend already
 * computed** and shipped with the series. This component chooses which column to draw and
 * calculates none of them — a percentage worked out in the browser is a number with no
 * pipeline behind it, and every number here has one.
 *
 * The range control selects a window of those points. Selecting is not computing: no
 * value changes when the range does, only which of them are on screen.
 *
 * Hovering reads out the session under the cursor. It is a `pointermove` on the plot area
 * rather than a hit-test per point, so it behaves the same with five hundred points as
 * with fifty, and it works with touch.
 */
import { useMemo, useRef, useState } from 'react';

export interface IndexPoint {
  date: string;
  close: number;
  return_pct: number | null;
  volatility_20d: number | null;
  drawdown: number | null;
}

export interface IndexView {
  key: 'close' | 'return_pct' | 'volatility_20d' | 'drawdown';
  label: string;
  unit: 'points' | 'percent';
  note: string;
}

const RANGES: { key: string; label: string; sessions: number | null }[] = [
  { key: '3m', label: '3M', sessions: 63 },
  { key: '6m', label: '6M', sessions: 126 },
  { key: '1y', label: '1Y', sessions: 252 },
  { key: 'all', label: 'All', sessions: null },
];

function format(value: number | null, unit: IndexView['unit']): string {
  if (value === null || Number.isNaN(value)) return '—';
  if (unit === 'percent') {
    const shown = (value * 100).toFixed(2);
    return `${value > 0 ? '+' : ''}${shown}%`;
  }
  return value.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function IndexChart({
  points,
  views,
  height = 280,
}: {
  points: IndexPoint[];
  views: IndexView[];
  height?: number;
}) {
  const [viewKey, setViewKey] = useState<IndexView['key']>('close');
  const [rangeKey, setRangeKey] = useState('all');
  const [hover, setHover] = useState<number | null>(null);
  const plot = useRef<HTMLDivElement>(null);

  const view = views.find((v) => v.key === viewKey) ?? views[0];

  const shown = useMemo(() => {
    const range = RANGES.find((r) => r.key === rangeKey);
    const window = range?.sessions ? points.slice(-range.sessions) : points;
    // A view whose column is blank early in the series (volatility needs 20 sessions)
    // drops those points rather than drawing them at zero, which would read as calm.
    return window.filter((p) => p[view.key] !== null && p[view.key] !== undefined);
  }, [points, rangeKey, view.key]);

  const geometry = useMemo(() => {
    if (shown.length < 2) return null;
    const values = shown.map((p) => p[view.key] as number);
    const low = Math.min(...values);
    const high = Math.max(...values);
    const span = high - low || 1;
    const step = 100 / (values.length - 1);
    const path = values
      .map(
        (v, i) =>
          `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(3)},${(
            100 -
            ((v - low) / span) * 100
          ).toFixed(3)}`,
      )
      .join(' ');
    const zeroAt =
      low < 0 && high > 0 ? 100 - ((0 - low) / span) * 100 : null;
    return { values, low, high, span, step, path, zeroAt };
  }, [shown, view.key]);

  const active = hover !== null && shown[hover] ? shown[hover] : null;
  const rising =
    geometry && geometry.values[geometry.values.length - 1] >= geometry.values[0];

  return (
    <figure className="indexChart">
      <div className="indexChart__controls">
        <div className="segmented" role="group" aria-label="Chart view">
          {views.map((v) => (
            <button
              key={v.key}
              type="button"
              className={v.key === viewKey ? 'segmented__btn is-active' : 'segmented__btn'}
              aria-pressed={v.key === viewKey}
              onClick={() => {
                setViewKey(v.key);
                setHover(null);
              }}
            >
              {v.label}
            </button>
          ))}
        </div>
        <div className="segmented segmented--quiet" role="group" aria-label="Date range">
          {RANGES.map((r) => (
            <button
              key={r.key}
              type="button"
              className={r.key === rangeKey ? 'segmented__btn is-active' : 'segmented__btn'}
              aria-pressed={r.key === rangeKey}
              onClick={() => {
                setRangeKey(r.key);
                setHover(null);
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="indexChart__readout" aria-live="polite">
        {active ? (
          <>
            <strong>{format(active[view.key], view.unit)}</strong>
            <span>{active.date}</span>
          </>
        ) : (
          <>
            <strong>
              {geometry ? format(shown[shown.length - 1][view.key], view.unit) : '—'}
            </strong>
            <span>
              {shown.length ? `${shown[0].date} → ${shown[shown.length - 1].date}` : '—'}
            </span>
          </>
        )}
      </div>

      {geometry ? (
        <div
          className="indexChart__plot"
          data-dir={rising ? 'up' : 'down'}
          style={{ height }}
          ref={plot}
          onPointerMove={(e) => {
            const box = plot.current?.getBoundingClientRect();
            if (!box || box.width === 0) return;
            const fraction = (e.clientX - box.left) / box.width;
            const i = Math.round(fraction * (shown.length - 1));
            setHover(Math.max(0, Math.min(shown.length - 1, i)));
          }}
          onPointerLeave={() => setHover(null)}
        >
          <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {geometry.zeroAt !== null ? (
              <line
                className="indexChart__zero"
                x1="0"
                x2="100"
                y1={geometry.zeroAt}
                y2={geometry.zeroAt}
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
            <path
              className="indexChart__line"
              d={geometry.path}
              vectorEffect="non-scaling-stroke"
            />
            {hover !== null ? (
              <line
                className="indexChart__cursor"
                x1={hover * geometry.step}
                x2={hover * geometry.step}
                y1="0"
                y2="100"
                vectorEffect="non-scaling-stroke"
              />
            ) : null}
          </svg>
          <span className="indexChart__high">{format(geometry.high, view.unit)}</span>
          <span className="indexChart__low">{format(geometry.low, view.unit)}</span>
        </div>
      ) : (
        <p className="small muted">
          Not enough sessions carry a value for {view.label.toLowerCase()} in this range.
        </p>
      )}

      <figcaption>
        <span className="indexChart__axis">
          <span>{shown.length ? shown[0].date : ''}</span>
          <span>{shown.length} sessions</span>
          <span>{shown.length ? shown[shown.length - 1].date : ''}</span>
        </span>
        <span className="indexChart__note">{view.note}</span>
      </figcaption>
    </figure>
  );
}
