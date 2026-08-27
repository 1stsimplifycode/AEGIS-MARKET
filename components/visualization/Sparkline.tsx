/**
 * Server-rendered inline SVG charts.
 *
 * No charting library and no client JavaScript: these render on the server, ship as
 * markup, and cost nothing at request time. That matters because the product surface must
 * stay inside a Vercel request budget while the research pipeline does the heavy work
 * elsewhere.
 */

export interface Band {
  from: string;
  to: string | null;
  label?: string;
  color?: string;
}

export interface Marker {
  at: string;
  label?: string;
  color?: string;
  dash?: string;
}

interface TraceProps {
  dates: string[];
  values: (number | null)[];
  /** Optional half-width band drawn around the value, e.g. uncertainty. */
  spread?: (number | null)[];
  bands?: Band[];
  markers?: Marker[];
  height?: number;
  yMin?: number;
  yMax?: number;
  color?: string;
  label?: string;
  /** Horizontal reference lines, e.g. entry and exit thresholds. */
  hlines?: { at: number; label?: string }[];
}

const W = 720;
const PAD = { top: 10, right: 8, bottom: 22, left: 34 };

export function Trace({
  dates,
  values,
  spread,
  bands = [],
  markers = [],
  height = 170,
  yMin = 0,
  yMax = 1,
  color = 'var(--accent)',
  label,
  hlines = [],
}: TraceProps) {
  const n = dates.length;
  if (n < 2) {
    return <p className="muted">Not enough observations to draw a trace.</p>;
  }
  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;

  const x = (i: number) => PAD.left + (i / (n - 1)) * innerW;
  const y = (v: number) =>
    PAD.top + innerH - ((v - yMin) / Math.max(1e-9, yMax - yMin)) * innerH;

  const indexOf = (d: string) => {
    const i = dates.indexOf(d);
    if (i >= 0) return i;
    // Nearest preceding date, so a marker on a non-trading day still lands sensibly.
    let best = -1;
    for (let k = 0; k < n; k += 1) if (dates[k] <= d) best = k;
    return best;
  };

  const path = values
    .map((v, i) => (v === null || Number.isNaN(v) ? null : `${x(i)},${y(v)}`))
    .reduce<string[]>((acc, pt, i) => {
      if (pt === null) return acc;
      acc.push(`${acc.length === 0 || values[i - 1] === null ? 'M' : 'L'}${pt}`);
      return acc;
    }, [])
    .join(' ');

  let bandPath = '';
  if (spread) {
    const upper: string[] = [];
    const lower: string[] = [];
    values.forEach((v, i) => {
      const s = spread[i];
      if (v === null || s === null || s === undefined) return;
      upper.push(`${x(i)},${y(Math.min(yMax, v + s / 2))}`);
      lower.unshift(`${x(i)},${y(Math.max(yMin, v - s / 2))}`);
    });
    if (upper.length > 1) bandPath = `M${upper.join(' L')} L${lower.join(' L')} Z`;
  }

  const ticks = [yMin, (yMin + yMax) / 2, yMax];

  return (
    <figure style={{ margin: '8px 0 0' }}>
      <svg
        viewBox={`0 0 ${W} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={label ?? 'time series'}
        style={{ overflow: 'visible' }}
      >
        {bands.map((b, i) => {
          const i0 = indexOf(b.from);
          const i1 = b.to ? indexOf(b.to) : n - 1;
          if (i0 < 0) return null;
          return (
            <rect
              key={`band-${i}`}
              x={x(i0)}
              y={PAD.top}
              width={Math.max(1, x(Math.max(i1, i0)) - x(i0))}
              height={innerH}
              fill={b.color ?? '#d55e00'}
              opacity={0.13}
            />
          );
        })}

        {ticks.map((t) => (
          <g key={`t-${t}`}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(t)}
              y2={y(t)}
              stroke="var(--border)"
              strokeWidth={0.6}
            />
            <text x={PAD.left - 5} y={y(t) + 3} textAnchor="end" fontSize={9}
                  fill="var(--muted)">
              {t.toFixed(1)}
            </text>
          </g>
        ))}

        {hlines.map((h) => (
          <g key={`h-${h.at}`}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={y(h.at)}
              y2={y(h.at)}
              stroke="var(--muted)"
              strokeWidth={0.7}
              strokeDasharray="3 3"
            />
            {h.label ? (
              <text x={W - PAD.right} y={y(h.at) - 3} textAnchor="end" fontSize={8.5}
                    fill="var(--muted)">
                {h.label}
              </text>
            ) : null}
          </g>
        ))}

        {bandPath ? <path d={bandPath} fill={color} opacity={0.16} /> : null}
        <path d={path} fill="none" stroke={color} strokeWidth={1.6} />

        {markers.map((m, i) => {
          const idx = indexOf(m.at);
          if (idx < 0) return null;
          return (
            <g key={`m-${i}`}>
              <line
                x1={x(idx)}
                x2={x(idx)}
                y1={PAD.top}
                y2={PAD.top + innerH}
                stroke={m.color ?? '#009e73'}
                strokeWidth={1.1}
                strokeDasharray={m.dash ?? '4 2'}
              />
              {m.label ? (
                <text x={x(idx) + 3} y={PAD.top + 9} fontSize={8.5}
                      fill={m.color ?? '#009e73'}>
                  {m.label}
                </text>
              ) : null}
            </g>
          );
        })}

        <text x={PAD.left} y={height - 6} fontSize={9} fill="var(--muted)">
          {dates[0]}
        </text>
        <text x={W - PAD.right} y={height - 6} fontSize={9} fill="var(--muted)"
              textAnchor="end">
          {dates[n - 1]}
        </text>
      </svg>
      {label ? (
        <figcaption className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          {label}
        </figcaption>
      ) : null}
    </figure>
  );
}

/** Horizontal bars for a small labelled series, e.g. modality contribution. */
export function Bars({
  items,
  label,
  color = 'var(--accent)',
  negativeColor = 'var(--warn)',
}: {
  items: { name: string; value: number | null }[];
  label?: string;
  color?: string;
  negativeColor?: string;
}) {
  const present = items.filter(
    (i) => i.value !== null && i.value !== undefined && !Number.isNaN(i.value),
  ) as { name: string; value: number }[];
  if (present.length === 0) return <p className="muted">No values to plot.</p>;

  const max = Math.max(...present.map((i) => Math.abs(i.value)), 1e-9);
  const rowH = 18;
  const height = present.length * rowH + 8;
  const labelW = 118;
  const zero = present.some((i) => i.value < 0) ? labelW + (W - labelW) / 2 : labelW;
  const scale = (v: number) => (Math.abs(v) / max) * (W - zero - 12);

  return (
    <figure style={{ margin: '8px 0 0' }}>
      <svg viewBox={`0 0 ${W} ${height}`} width="100%" height={height} role="img"
           aria-label={label ?? 'bar chart'}>
        {present.map((it, i) => {
          const w = scale(it.value);
          const neg = it.value < 0;
          return (
            <g key={it.name} transform={`translate(0,${i * rowH + 4})`}>
              <text x={labelW - 6} y={rowH * 0.62} textAnchor="end" fontSize={10}
                    fill="var(--text)">
                {it.name}
              </text>
              <rect
                x={neg ? zero - w : zero}
                y={3}
                width={Math.max(1, w)}
                height={rowH - 8}
                fill={neg ? negativeColor : color}
                opacity={0.82}
              />
              <text x={(neg ? zero - w : zero + w) + (neg ? -4 : 4)} y={rowH * 0.62}
                    textAnchor={neg ? 'end' : 'start'} fontSize={9}
                    fill="var(--muted)">
                {it.value.toFixed(3)}
              </text>
            </g>
          );
        })}
        <line x1={zero} x2={zero} y1={0} y2={height} stroke="var(--border)"
              strokeWidth={0.8} />
      </svg>
      {label ? (
        <figcaption className="muted" style={{ fontSize: 11, marginTop: 2 }}>
          {label}
        </figcaption>
      ) : null}
    </figure>
  );
}
