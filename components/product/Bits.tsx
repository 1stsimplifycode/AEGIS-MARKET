/**
 * The product's vocabulary, as components.
 *
 * Every piece here is built for the same job: say the answer, in the fewest words that
 * remain true, and put the way to go deeper next to it rather than the depth itself.
 * A reader who wants the number gets the number; a reader who wants to know where it came
 * from finds a control, not a paragraph.
 *
 * These are server components. Only `Disclosure` and the search box need the client, and
 * they live apart for that reason.
 */
import Link from 'next/link';

import type { ModalityShare, Sourced, Tone } from '@/lib/product';
import { direction, signedPct, sourceNote } from '@/lib/product';

/** The headline verdict: one word, one colour, one sentence of meaning. */
export function SignalBadge({
  label,
  tone,
  meaning,
  size = 'large',
}: {
  label: string;
  tone: Tone;
  meaning?: string;
  size?: 'large' | 'small';
}) {
  return (
    <div className={`signal signal--${size}`} data-tone={tone}>
      <span className="signal__dot" aria-hidden="true" />
      <span className="signal__label">{label}</span>
      {meaning && size === 'large' ? (
        <span className="signal__meaning">{meaning}</span>
      ) : null}
    </div>
  );
}

/** A number with its name under it. The number is the point, so it is the large thing. */
export function Figure({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: 'up' | 'down' | 'flat';
}) {
  return (
    <div className="figure" data-tone={tone ?? 'flat'}>
      <span className="figure__value">{value}</span>
      <span className="figure__label">{label}</span>
      {sub ? <span className="figure__sub">{sub}</span> : null}
    </div>
  );
}

export function Change({ value }: { value: number | null | undefined }) {
  return (
    <span className="change" data-dir={direction(value)}>
      {signedPct(value)}
    </span>
  );
}

/**
 * How much each kind of evidence carried, as bars.
 *
 * Shares, not scores. A reader comparing "financial text 0.62" against "price and volume
 * 0.31" would be comparing two numbers on scales they have no way to know; the share of
 * the total is the comparison they actually mean, and it is the one that can be drawn.
 */
/**
 * A share, written so a measured value never reads as an unmeasured one.
 *
 * `toFixed(0)` turned every share under half a percent into "0%", and three modalities sat
 * there: video at 0.46%, image at 0.32%, audio at 0.26%. Each had been measured, each had
 * a positive contribution, and the chart said they added nothing — which is a different
 * finding from the one the experiment produced, and the more damaging one, because it
 * reads as "this evidence is worthless" rather than "this evidence is largely redundant".
 *
 * So the precision follows the magnitude: small numbers get the digits that distinguish
 * them from zero, large ones do not carry noise they have not earned.
 */
export function shareLabel(share: number): string {
  if (!Number.isFinite(share) || share <= 0) return '0%';
  const pct = share * 100;
  if (pct < 1) return `${pct.toFixed(2)}%`;
  if (pct < 10) return `${pct.toFixed(1)}%`;
  return `${pct.toFixed(0)}%`;
}

export function SignalBars({
  modalities,
  limit = 6,
}: {
  modalities: ModalityShare[];
  limit?: number;
}) {
  const shown = modalities.slice(0, limit);
  const widest = Math.max(...shown.map((m) => m.share), 0.0001);
  return (
    <ul className="bars">
      {shown.map((m) => (
        <li className="bars__row" key={m.modality}>
          <span className="bars__label">{m.label}</span>
          <span className="bars__track">
            <span
              className="bars__fill"
              style={{ width: `${Math.max(2, (m.share / widest) * 100)}%` }}
            />
          </span>
          <span className="bars__value">{shareLabel(m.share)}</span>
        </li>
      ))}
    </ul>
  );
}

/** A price line. Small, unlabelled, and there to show shape rather than to be read off. */
export function Spark({
  points,
  height = 44,
}: {
  points: { close: number }[];
  height?: number;
}) {
  if (points.length < 2) return null;
  const values = points.map((p) => p.close);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const step = 100 / (values.length - 1);
  const path = values
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(2)},${(
      100 - ((v - low) / span) * 100
    ).toFixed(2)}`)
    .join(' ');
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg
      className="spark"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      height={height}
      aria-hidden="true"
      data-dir={rising ? 'up' : 'down'}
    >
      <path d={path} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** A larger price chart with a value axis, for the instrument page. */
/** One session's candle, with the real four prices. */
export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  turnover?: number | null;
}

/**
 * Keep only sessions that carry a genuine, self-consistent OHLC quartet.
 *
 * A row missing an open, or whose high sits below its close, is dropped rather than
 * repaired. Repairing it would put a candle on the screen that no exchange published, and
 * the count of drawn candles is reported so a gap is visible instead of silent.
 */
export function toCandles(
  points: {
    date: string;
    close: number;
    open?: number | null;
    high?: number | null;
    low?: number | null;
    volume?: number | null;
    turnover?: number | null;
  }[],
): Candle[] {
  const out: Candle[] = [];
  for (const p of points) {
    const { open, high, low, close } = p;
    if (
      typeof open !== 'number' ||
      typeof high !== 'number' ||
      typeof low !== 'number' ||
      typeof close !== 'number' ||
      !Number.isFinite(open) ||
      !Number.isFinite(high) ||
      !Number.isFinite(low) ||
      !Number.isFinite(close)
    ) {
      continue;
    }
    if (high < Math.max(open, close) || low > Math.min(open, close) || high < low) {
      continue;
    }
    out.push({
      date: p.date,
      open,
      high,
      low,
      close,
      volume: p.volume ?? null,
      turnover: p.turnover ?? null,
    });
  }
  return out;
}

const inrCompact = (n: number) =>
  n >= 1e7 ? `${(n / 1e7).toFixed(2)} Cr` : n >= 1e5 ? `${(n / 1e5).toFixed(2)} L` : n.toFixed(0);

/**
 * An OHLC candlestick chart drawn from real sessions.
 *
 * Each candle is one trading session: a wick from low to high, a body between open and
 * close, green when the session closed at or above its open and red when it closed below.
 * Nothing is interpolated between sessions, so a market holiday leaves no candle rather
 * than a straight line implying a price nobody traded at.
 */
export function CandleChart({
  candles,
  height = 260,
  droppedSessions = 0,
}: {
  candles: Candle[];
  height?: number;
  droppedSessions?: number;
}) {
  if (candles.length < 2) {
    return (
      <p className="small muted">
        Not enough sessions with complete open/high/low/close to draw candles.
      </p>
    );
  }
  const low = Math.min(...candles.map((c) => c.low));
  const high = Math.max(...candles.map((c) => c.high));
  const span = high - low || 1;
  const pad = span * 0.04;
  const yLow = low - pad;
  const ySpan = high + pad - yLow || 1;
  const y = (v: number) => ((high + pad - v) / ySpan) * 100;

  const slot = 100 / candles.length;
  const bodyW = Math.max(slot * 0.62, 0.12);
  const mid = (i: number) => i * slot + slot / 2;

  const first = candles[0];
  const last = candles[candles.length - 1];
  const rising = last.close >= first.open;
  const ticks = [high + pad, (high + pad + yLow) / 2, yLow];

  return (
    <figure className="candleChart" data-dir={rising ? 'up' : 'down'}>
      <div className="candleChart__plot" style={{ height }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img"
             aria-label={`Candlestick chart, ${candles.length} sessions from ${first.date} to ${last.date}`}>
          {ticks.map((t, i) => (
            <line key={i} className="candleChart__grid" x1="0" x2="100"
                  y1={y(t).toFixed(2)} y2={y(t).toFixed(2)} vectorEffect="non-scaling-stroke" />
          ))}
          {candles.map((c, i) => {
            const up = c.close >= c.open;
            const top = y(Math.max(c.open, c.close));
            const bottom = y(Math.min(c.open, c.close));
            const h = Math.max(bottom - top, 0.35);
            const x = mid(i);
            return (
              <g key={c.date} className="candleChart__candle" data-dir={up ? 'up' : 'down'}>
                <title>
                  {`${c.date}\nOpen  ${c.open.toFixed(2)}\nHigh  ${c.high.toFixed(2)}\nLow   ${c.low.toFixed(2)}\nClose ${c.close.toFixed(2)}`}
                  {c.volume ? `\nVolume ${inrCompact(c.volume)}` : ''}
                  {c.turnover ? `\nTurnover Rs ${inrCompact(c.turnover)}` : ''}
                </title>
                <line className="candleChart__wick" x1={x} x2={x}
                      y1={y(c.high).toFixed(2)} y2={y(c.low).toFixed(2)}
                      vectorEffect="non-scaling-stroke" />
                <rect className="candleChart__body" x={(x - bodyW / 2).toFixed(3)}
                      y={top.toFixed(2)} width={bodyW.toFixed(3)} height={h.toFixed(2)} />
              </g>
            );
          })}
        </svg>
        <span className="candleChart__high">{high.toFixed(2)}</span>
        <span className="candleChart__mid">{((high + low) / 2).toFixed(2)}</span>
        <span className="candleChart__low">{low.toFixed(2)}</span>
      </div>
      <figcaption className="candleChart__axis">
        <span>{first.date}</span>
        <span className="candleChart__legend">
          <i data-dir="up" /> close ≥ open
          <i data-dir="down" /> close &lt; open
          {droppedSessions > 0 ? ` · ${droppedSessions} session(s) without complete OHLC not drawn` : ''}
        </span>
        <span>{last.date}</span>
      </figcaption>
    </figure>
  );
}

export function PriceChart({
  points,
  height = 200,
}: {
  points: { date: string; close: number }[];
  height?: number;
}) {
  if (points.length < 2) {
    return <p className="small muted">Not enough sessions to draw a chart.</p>;
  }
  const values = points.map((p) => p.close);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const step = 100 / (values.length - 1);
  const line = values
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(2)},${(
      100 - ((v - low) / span) * 100
    ).toFixed(2)}`)
    .join(' ');
  const area = `${line} L100,100 L0,100 Z`;
  const rising = values[values.length - 1] >= values[0];

  return (
    <figure className="priceChart" data-dir={rising ? 'up' : 'down'}>
      <div className="priceChart__plot" style={{ height }}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path className="priceChart__area" d={area} />
          <path className="priceChart__line" d={line} vectorEffect="non-scaling-stroke" />
        </svg>
        <span className="priceChart__high">{high.toFixed(2)}</span>
        <span className="priceChart__low">{low.toFixed(2)}</span>
      </div>
      <figcaption className="priceChart__axis">
        <span>{points[0].date}</span>
        <span>{points[points.length - 1].date}</span>
      </figcaption>
    </figure>
  );
}

/**
 * Where a block of numbers came from and how current it is.
 *
 * Small, quiet, and always present. The product's whole claim to be trustworthy rests on
 * a reader being able to find this without going looking for it, and on it distinguishing
 * a live read from a stored one every single time.
 */
export function SourceLine({ of }: { of: Sourced<unknown> }) {
  return (
    <p className="sourceLine" data-source={of.source}>
      {sourceNote(of)}
    </p>
  );
}

/** The one primary action on a card: go deeper, in the product's own words. */
export function Deeper({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link className="deeper" href={href}>
      {children} <span aria-hidden="true">→</span>
    </Link>
  );
}

export function Empty({ title, note }: { title: string; note: string }) {
  return (
    <div className="productEmpty">
      <h3>{title}</h3>
      <p>{note}</p>
    </div>
  );
}
