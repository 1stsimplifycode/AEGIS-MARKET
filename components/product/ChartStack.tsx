/**
 * The market chart stack: candles, volume, RSI and MACD over one shared time axis.
 *
 * The panels are stacked deliberately rather than tabbed. An indicator read apart from the
 * price it was computed from invites the reader to treat it as a standalone verdict, which
 * is exactly the reading this project refuses; placed beneath the candles on the same
 * x-axis it stays what it is, a transformation of those closes.
 *
 * **Alignment is structural, not coincidental.** Every panel receives the same number of
 * slots as there are candles and indexes them the same way, so column *i* is the same
 * session in all four. Indicator values are null for their warm-up period and are simply
 * not plotted there — the line starts where the data starts rather than being pulled back
 * to the left edge.
 *
 * **Nothing here decides anything.** The RSI reference lines are drawn and labelled as
 * reference levels; no zone is shaded to suggest an action, and the observations rendered
 * beneath each panel are sentences about where a value sits.
 */
import type { IndicatorSeries } from '@/lib/product';

import type { Candle } from './Bits';

const compact = (n: number) =>
  n >= 1e7 ? `${(n / 1e7).toFixed(1)}Cr` : n >= 1e5 ? `${(n / 1e5).toFixed(1)}L` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : n.toFixed(0);

/** Volume bars, coloured by the same up/down rule the candles use. */
function VolumePanel({ candles, height }: { candles: Candle[]; height: number }) {
  const vols = candles.map((c) => (typeof c.volume === 'number' ? c.volume : 0));
  const max = Math.max(...vols, 1);
  const slot = 100 / candles.length;
  const w = Math.max(slot * 0.62, 0.12);
  if (!vols.some((v) => v > 0)) {
    return <p className="small muted">Volume is not available for these sessions.</p>;
  }
  return (
    <div className="chartStack__panel">
      <div className="chartStack__panelHead">
        <span className="chartStack__panelName">Volume</span>
        <span className="chartStack__panelMeta">peak {compact(max)}</span>
      </div>
      <div className="chartStack__plot" style={{ height }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Volume by session">
          {candles.map((c, i) => {
            const v = vols[i];
            const h = (v / max) * 100;
            return (
              <rect
                key={c.date}
                className="chartStack__vol"
                data-dir={c.close >= c.open ? 'up' : 'down'}
                x={(i * slot + slot / 2 - w / 2).toFixed(3)}
                y={(100 - h).toFixed(2)}
                width={w.toFixed(3)}
                height={Math.max(h, 0.3).toFixed(2)}
              >
                <title>{`${c.date}\nVolume ${compact(v)}`}</title>
              </rect>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function polyline(values: (number | null)[], lo: number, hi: number, slot: number) {
  const span = hi - lo || 1;
  const out: string[] = [];
  let started = false;
  values.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) {
      started = false;
      return;
    }
    const x = i * slot + slot / 2;
    const y = 100 - ((v - lo) / span) * 100;
    out.push(`${started ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`);
    started = true;
  });
  return out.join(' ');
}

function RsiPanel({ ind, height }: { ind: IndicatorSeries; height: number }) {
  const slot = 100 / ind.dates.length;
  const [lower, upper] = ind.rsi_reference_levels;
  const y = (v: number) => 100 - v; // RSI is already 0..100
  return (
    <div className="chartStack__panel">
      <div className="chartStack__panelHead">
        <span className="chartStack__panelName">RSI(14)</span>
        <span className="chartStack__panelMeta">
          {ind.rsi_latest !== null ? ind.rsi_latest.toFixed(1) : 'not available'}
        </span>
      </div>
      <div className="chartStack__plot" style={{ height }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Relative strength index">
          <line className="chartStack__ref" x1="0" x2="100" y1={y(upper)} y2={y(upper)} vectorEffect="non-scaling-stroke" />
          <line className="chartStack__ref" x1="0" x2="100" y1={y(lower)} y2={y(lower)} vectorEffect="non-scaling-stroke" />
          <path className="chartStack__line" d={polyline(ind.rsi, 0, 100, slot)} vectorEffect="non-scaling-stroke" />
        </svg>
        <span className="chartStack__tick" style={{ top: `${y(upper)}%` }}>{upper} reference</span>
        <span className="chartStack__tick" style={{ top: `${y(lower)}%` }}>{lower} reference</span>
      </div>
      <p className="chartStack__observation">{ind.rsi_observation}</p>
    </div>
  );
}

function MacdPanel({ ind, height }: { ind: IndicatorSeries; height: number }) {
  const slot = 100 / ind.dates.length;
  const all = [...ind.macd, ...ind.macd_signal, ...ind.macd_histogram].filter(
    (v): v is number => typeof v === 'number' && Number.isFinite(v),
  );
  if (!all.length) {
    return <p className="small muted">Not enough sessions to compute MACD.</p>;
  }
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const span = hi - lo || 1;
  const zeroY = 100 - ((0 - lo) / span) * 100;
  const w = Math.max(slot * 0.5, 0.1);
  return (
    <div className="chartStack__panel">
      <div className="chartStack__panelHead">
        <span className="chartStack__panelName">MACD(12,26,9)</span>
        <span className="chartStack__panelMeta">
          {ind.macd_latest !== null ? `MACD ${ind.macd_latest.toFixed(2)}` : 'not available'}
          {ind.macd_signal_latest !== null ? ` · signal ${ind.macd_signal_latest.toFixed(2)}` : ''}
        </span>
      </div>
      <div className="chartStack__plot" style={{ height }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="MACD">
          <line className="chartStack__zero" x1="0" x2="100" y1={zeroY.toFixed(2)} y2={zeroY.toFixed(2)} vectorEffect="non-scaling-stroke" />
          {ind.macd_histogram.map((v, i) => {
            if (v === null || !Number.isFinite(v)) return null;
            const yv = 100 - ((v - lo) / span) * 100;
            const top = Math.min(yv, zeroY);
            const h = Math.max(Math.abs(zeroY - yv), 0.25);
            return (
              <rect
                key={ind.dates[i]}
                className="chartStack__hist"
                data-dir={v >= 0 ? 'up' : 'down'}
                x={(i * slot + slot / 2 - w / 2).toFixed(3)}
                y={top.toFixed(2)}
                width={w.toFixed(3)}
                height={h.toFixed(2)}
              >
                <title>{`${ind.dates[i]}\nHistogram ${v.toFixed(3)}`}</title>
              </rect>
            );
          })}
          <path className="chartStack__line" d={polyline(ind.macd, lo, hi, slot)} vectorEffect="non-scaling-stroke" />
          <path className="chartStack__line chartStack__line--signal" d={polyline(ind.macd_signal, lo, hi, slot)} vectorEffect="non-scaling-stroke" />
        </svg>
      </div>
      <p className="chartStack__observation">
        {ind.macd_observation}
        <span className="chartStack__legend">
          <i className="chartStack__swatch" data-line="macd" /> MACD
          <i className="chartStack__swatch" data-line="signal" /> signal
        </span>
      </p>
    </div>
  );
}

export function ChartStack({
  candles,
  indicators,
}: {
  candles: Candle[];
  indicators?: IndicatorSeries;
}) {
  const aligned =
    indicators && indicators.dates.length === candles.length ? indicators : undefined;
  return (
    <div className="chartStack">
      <VolumePanel candles={candles} height={90} />
      {aligned && aligned.available ? (
        <>
          <RsiPanel ind={aligned} height={110} />
          <MacdPanel ind={aligned} height={110} />
        </>
      ) : (
        <p className="small muted">
          {indicators?.why_unavailable ??
            (indicators
              ? 'Indicator series does not align with the price window, so RSI and MACD are not drawn.'
              : 'RSI and MACD are not available from this source.')}
        </p>
      )}
      <p className="chartStack__provenance">
        RSI and MACD are derived from the closing prices above. They are not published by
        the exchange and are shown as observations, not as instructions.
      </p>
    </div>
  );
}
