/**
 * Primary visualisations for the module pages.
 *
 * Every chart here is drawn from an artifact the research pipeline wrote: either a
 * bounded preview of the module's own output table, or the resolved metrics the exporter
 * looked up. Nothing is simulated, and a module whose artifact is absent renders a
 * statement to that effect rather than an empty axis — an empty chart reads as a result
 * of zero, which is a different claim from "not available".
 *
 * The `visual` key in the manifest picks the shape. Column names are resolved by the
 * spec below rather than declared per module, because the artifacts already have stable
 * column vocabularies and repeating them 32 times in the manifest would be 32 chances to
 * drift.
 */
import type { ModuleMetric, ModulePreview, ResearchModule } from '@/lib/moduleTypes';

interface VisualSpec {
  /** Column holding the row label. First non-numeric column when absent. */
  label?: string;
  /** Candidate value columns, in preference order. First numeric column when none hit. */
  value?: string[];
  kind: 'bars' | 'line' | 'matrix' | 'split-metrics' | 'table' | 'metrics';
  /** Second series, drawn as a paler bar behind the first. */
  compare?: string[];
  unit?: 'fraction' | 'raw';
  sort?: 'value' | 'none';
  /** Keep only rows where this column equals this value. */
  filter?: { column: string; value: string };
  /** Build the row label by joining these columns, when one alone repeats. */
  labelJoin?: string[];
}

const VISUAL_SPEC: Record<string, VisualSpec> = {
  coverage_bars: {
    label: 'block',
    value: ['mean_non_null_fraction'],
    kind: 'bars',
    unit: 'fraction',
    sort: 'value',
  },
  feature_table: { kind: 'table' },
  regime_bars: {
    label: 'regime_id',
    value: ['share'],
    compare: ['positive_rate'],
    kind: 'bars',
    unit: 'fraction',
  },
  baseline_bars: { label: 'model', value: ['auprc'], kind: 'bars', sort: 'value' },
  ablation_bars: { label: 'arm', value: ['auprc'], kind: 'bars', sort: 'value' },
  // The artifact holds several families at once, and the input-degradation family is
  // the one this module leads with; the rest are reachable in the research tables.
  robustness_lines: {
    label: 'corruption',
    labelJoin: ['corruption', 'severity'],
    value: ['auprc'],
    kind: 'bars',
    sort: 'none',
    filter: { column: 'family', value: 'input' },
  },
  alignment_curve: {
    label: 'offset_sessions',
    value: ['auprc'],
    kind: 'line',
    sort: 'none',
  },
  seed_spread: { label: 'arm', value: ['mean'], kind: 'bars', sort: 'value' },
  information_matrix: {
    label: 'modality',
    value: ['unique'],
    compare: ['total_auprc'],
    kind: 'bars',
    sort: 'value',
  },
  confusion: { kind: 'matrix' },
  reliability: { label: 'mean_pred', value: ['observed'], kind: 'line' },
  // The error taxonomy artifact is one row per scored instrument-day, so the split is
  // drawn from the resolved counts rather than from that row table.
  error_split: { kind: 'split-metrics' },
  fusion_compare: { kind: 'metrics' },
  attribution: { kind: 'metrics' },
  episode_stats: { kind: 'metrics' },
  tail_stats: { kind: 'metrics' },
  stat_row: { kind: 'metrics' },
  gate: { kind: 'metrics' },
  provenance: { kind: 'metrics' },
  media_gallery: { kind: 'metrics' },
  affect_distribution: {
    label: 'dimension',
    value: ['mean'],
    compare: ['std'],
    kind: 'bars',
  },
  not_measured: { kind: 'metrics' },

  // Scenario Lab. A scenario table is one row per condition, so the label column is the
  // scenario id in every case and only the value column differs.
  scenario_bars: {
    label: 'scenario_id',
    value: ['risk_mean'],
    kind: 'bars',
    sort: 'none',
  },
  // Filtered to the market family: the transaction rows in the same artifact are a
  // different quantity on a different corpus, and charting them together would invite a
  // comparison that means nothing.
  scenario_money: {
    label: 'scenario_id',
    value: ['amount_inr'],
    kind: 'bars',
    sort: 'value',
    filter: { column: 'family', value: 'market' },
  },
  uncertainty_intervals: {
    label: 'scenario_id',
    value: ['estimate'],
    kind: 'bars',
    sort: 'value',
  },
  scenario_ablation: {
    label: 'scenario_id',
    labelJoin: ['subset', 'scenario_id'],
    value: ['delta_risk_mean'],
    kind: 'bars',
    sort: 'none',
  },
  scenario_robustness: {
    label: 'scenario_id',
    value: ['delta_mean'],
    kind: 'bars',
    sort: 'value',
  },
};

const NUMERIC = /^-?\d+(\.\d+)?([eE][-+]?\d+)?$/;

function isNumeric(v: unknown): boolean {
  if (typeof v === 'number') return Number.isFinite(v);
  return typeof v === 'string' && v.trim() !== '' && NUMERIC.test(v.trim());
}

function num(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string' && NUMERIC.test(v.trim())) return Number(v);
  return null;
}

function columnIndex(preview: ModulePreview, name?: string): number {
  if (!name) return -1;
  return preview.columns.findIndex((c) => c === name);
}

/** Pick the value column: the first named candidate present, else the widest numeric. */
function pickValue(preview: ModulePreview, candidates?: string[]): number {
  for (const c of candidates ?? []) {
    const i = columnIndex(preview, c);
    if (i >= 0) return i;
  }
  for (let i = 0; i < preview.columns.length; i += 1) {
    if (preview.rows.some((r) => isNumeric(r[i]))) return i;
  }
  return -1;
}

function pickLabel(preview: ModulePreview, named?: string, avoid = -1): number {
  const i = columnIndex(preview, named);
  if (i >= 0) return i;
  for (let j = 0; j < preview.columns.length; j += 1) {
    if (j === avoid) continue;
    if (!preview.rows.every((r) => isNumeric(r[j]))) return j;
  }
  return 0;
}

function fmt(v: number, unit?: 'fraction' | 'raw'): string {
  if (unit === 'fraction') return `${(v * 100).toFixed(1)}%`;
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (Math.abs(v) >= 1) return v.toFixed(3);
  return v.toFixed(4);
}

export function NotAvailable({ what, why }: { what: string; why?: string }) {
  return (
    <div className="viz viz--empty">
      <strong>{what} is not available in this build.</strong>
      <p>
        {why ??
          'This view renders exported artifacts only. Nothing is generated at request ' +
            'time, so an absent artifact is shown as absent rather than drawn from ' +
            'nothing.'}
      </p>
    </div>
  );
}

/* -- primitives ---------------------------------------------------------------------- */

interface Row {
  label: string;
  value: number;
  compare: number | null;
}

function rowsFrom(preview: ModulePreview, spec: VisualSpec, limit = 14): Row[] {
  const vi = pickValue(preview, spec.value);
  if (vi < 0) return [];
  const li = pickLabel(preview, spec.label, vi);
  const ci = spec.compare ? pickValue(preview, spec.compare) : -1;
  const fi = spec.filter ? columnIndex(preview, spec.filter.column) : -1;
  const joinIdx = (spec.labelJoin ?? [])
    .map((c) => columnIndex(preview, c))
    .filter((i) => i >= 0);

  const rows: Row[] = [];
  for (const r of preview.rows) {
    if (fi >= 0 && String(r[fi]) !== spec.filter!.value) continue;
    const v = num(r[vi]);
    if (v === null) continue;
    rows.push({
      label: joinIdx.length
        ? joinIdx.map((i) => String(r[i] ?? '')).join(' · ')
        : String(r[li] ?? ''),
      value: v,
      compare: ci >= 0 && ci !== vi ? num(r[ci]) : null,
    });
  }
  if (spec.sort === 'value') rows.sort((a, b) => b.value - a.value);
  return rows.slice(0, limit);
}

export function BarChart({
  rows,
  unit,
  valueLabel,
  compareLabel,
}: {
  rows: Row[];
  unit?: 'fraction' | 'raw';
  valueLabel: string;
  compareLabel?: string;
}) {
  const max = Math.max(...rows.map((r) => Math.max(r.value, r.compare ?? 0)), 0);
  const min = Math.min(...rows.map((r) => Math.min(r.value, r.compare ?? 0)), 0);
  const span = max - min || 1;
  return (
    <div className="viz">
      <div className="viz__legend">
        <span className="viz__key viz__key--primary" /> {valueLabel}
        {compareLabel ? (
          <>
            <span className="viz__key viz__key--compare" /> {compareLabel}
          </>
        ) : null}
      </div>
      <ul className="vizBars">
        {rows.map((r) => (
          <li key={`${r.label}-${r.value}`} className="vizBars__row">
            <span className="vizBars__label" title={r.label}>
              {r.label}
            </span>
            <span className="vizBars__track">
              {r.compare !== null ? (
                <span
                  className="vizBars__fill vizBars__fill--compare"
                  style={{ width: `${(Math.abs(r.compare - min) / span) * 100}%` }}
                />
              ) : null}
              <span
                className="vizBars__fill"
                style={{ width: `${(Math.abs(r.value - min) / span) * 100}%` }}
              />
            </span>
            <span className="vizBars__value">{fmt(r.value, unit)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function LineChart({
  rows,
  valueLabel,
}: {
  rows: Row[];
  valueLabel: string;
}) {
  if (rows.length < 2) return <BarChart rows={rows} valueLabel={valueLabel} />;
  const w = 640;
  const h = 200;
  const pad = 28;
  const values = rows.map((r) => r.value);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const x = (i: number) => pad + (i / (rows.length - 1)) * (w - pad * 2);
  const y = (v: number) => h - pad - ((v - min) / span) * (h - pad * 2);
  const path = rows.map((r, i) => `${i ? 'L' : 'M'}${x(i)},${y(r.value)}`).join(' ');

  return (
    <div className="viz">
      <div className="viz__legend">
        <span className="viz__key viz__key--primary" /> {valueLabel}
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="vizLine"
        role="img"
        aria-label={`${valueLabel} across ${rows.length} conditions`}
      >
        <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} className="vizLine__axis" />
        <line x1={pad} y1={pad} x2={pad} y2={h - pad} className="vizLine__axis" />
        <path d={path} className="vizLine__path" />
        {rows.map((r, i) => (
          <circle key={`${r.label}-${i}`} cx={x(i)} cy={y(r.value)} r={3.5}>
            <title>{`${r.label}: ${fmt(r.value)}`}</title>
          </circle>
        ))}
        <text x={pad} y={pad - 8} className="vizLine__tick">
          {fmt(max)}
        </text>
        <text x={pad} y={h - pad + 16} className="vizLine__tick">
          {fmt(min)}
        </text>
      </svg>
      <div className="viz__axis">
        <span>{rows[0].label}</span>
        <span>{rows[rows.length - 1].label}</span>
      </div>
    </div>
  );
}

export function MatrixGrid({ preview }: { preview: ModulePreview }) {
  const numericCols = preview.columns
    .map((c, i) => ({ c, i }))
    .filter(({ i }) => preview.rows.some((r) => isNumeric(r[i])));
  const labelIdx = pickLabel(preview, undefined, numericCols[0]?.i ?? -1);
  const all = preview.rows.flatMap((r) =>
    numericCols.map(({ i }) => num(r[i]) ?? 0),
  );
  const max = Math.max(...all, 1);

  return (
    <div className="viz">
      <div className="tableWrap">
        <table className="vizMatrix">
          <thead>
            <tr>
              <th />
              {numericCols.map(({ c }) => (
                <th key={c} className="num">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.slice(0, 12).map((r, ri) => (
              <tr key={`${String(r[labelIdx])}-${ri}`}>
                <th scope="row">{String(r[labelIdx] ?? '')}</th>
                {numericCols.map(({ i, c }) => {
                  const v = num(r[i]) ?? 0;
                  return (
                    <td
                      key={c}
                      className="num vizMatrix__cell"
                      style={{ ['--cell' as string]: String(Math.abs(v) / max) }}
                    >
                      {fmt(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SplitBar({ rows }: { rows: Row[] }) {
  const total = rows.reduce((s, r) => s + r.value, 0) || 1;
  return (
    <div className="viz">
      <div className="vizSplit">
        {rows.map((r, i) => (
          <span
            key={r.label}
            className="vizSplit__seg"
            data-seg={i}
            style={{ width: `${(r.value / total) * 100}%` }}
            title={`${r.label}: ${fmt(r.value)}`}
          />
        ))}
      </div>
      <ul className="vizSplit__legend">
        {rows.map((r, i) => (
          <li key={r.label}>
            <span className="viz__key" data-seg={i} /> {r.label}{' '}
            <strong>{fmt(r.value)}</strong>{' '}
            <span className="muted">{((r.value / total) * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TablePreview({
  preview,
  limit = 12,
}: {
  preview: ModulePreview;
  limit?: number;
}) {
  return (
    <div className="viz">
      <div className="tableWrap">
        <table>
          <thead>
            <tr>
              {preview.columns.map((c) => (
                <th key={c} className={c.match(/id|name|class|feature|arm/) ? '' : 'num'}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.slice(0, limit).map((r, ri) => (
              <tr key={ri}>
                {r.map((cell, ci) => (
                  <td key={ci} className={isNumeric(cell) ? 'num' : ''}>
                    {isNumeric(cell) ? fmt(num(cell)!) : String(cell ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="viz__note muted small">
        {preview.truncated
          ? `First ${Math.min(limit, preview.rows.length)} of ${preview.total_rows.toLocaleString()} rows`
          : `${preview.total_rows.toLocaleString()} rows`}{' '}
        from <code>{preview.path}</code>
      </p>
    </div>
  );
}

/** Metrics as a chart when a metric page is the honest primary visualisation. */
export function MetricBars({ metrics }: { metrics: ModuleMetric[] }) {
  const rows = metrics
    .filter((m) => typeof m.value === 'number' && m.value !== null)
    .map((m) => ({
      label: m.label,
      value: Math.abs(m.value as number),
      compare: null,
      display: m.display ?? '',
    }));
  if (rows.length === 0) {
    return (
      <NotAvailable
        what="A chartable value"
        why="This module reports text and status rather than a numeric series. The
        research view carries every field it produced."
      />
    );
  }
  const max = Math.max(...rows.map((r) => r.value)) || 1;
  return (
    <div className="viz">
      <ul className="vizBars">
        {rows.map((r) => (
          <li key={r.label} className="vizBars__row">
            <span className="vizBars__label" title={r.label}>
              {r.label}
            </span>
            <span className="vizBars__track">
              <span
                className="vizBars__fill"
                style={{ width: `${(r.value / max) * 100}%` }}
              />
            </span>
            <span className="vizBars__value">{r.display}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* -- multimodal-specific ------------------------------------------------------------- */

/** Order the modality strip reads in. Text first because it is where the signal starts. */
const MODALITY_ORDER = [
  'text',
  'market',
  'microstructure',
  'image',
  'audio',
  'video',
  'regime',
  'propagation',
];

/**
 * The modality strip: which channels this module touches, how much each contributes,
 * and how often each disagrees with the fused decision.
 *
 * Drawn only when the module's own artifacts carry a per-modality row. A strip invented
 * for modules that do not measure one would make the interface look more multimodal than
 * the evidence is.
 */
export function ModalityStrip({ module: mod }: { module: ResearchModule }) {
  const preview =
    mod.research.previews.find((p) => p.columns.includes('modality')) ??
    mod.research.previews.find((p) => p.columns.includes('block'));
  if (!preview) return null;

  const keyIdx = Math.max(
    preview.columns.indexOf('modality'),
    preview.columns.indexOf('block'),
  );
  const contribIdx = ['unique', 'mean_non_null_fraction', 'total_auprc'].reduce(
    (found, c) => (found >= 0 ? found : preview.columns.indexOf(c)),
    -1,
  );
  const conflictIdx = preview.columns.indexOf('conflict_rate');
  if (keyIdx < 0 || contribIdx < 0) return null;

  const rows = preview.rows
    .map((r) => ({
      name: String(r[keyIdx] ?? ''),
      contribution: num(r[contribIdx]) ?? 0,
      conflict: conflictIdx >= 0 ? num(r[conflictIdx]) : null,
    }))
    .sort((a, b) => {
      const ia = MODALITY_ORDER.indexOf(a.name);
      const ib = MODALITY_ORDER.indexOf(b.name);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  if (rows.length === 0) return null;

  const maxContribution = Math.max(...rows.map((r) => Math.abs(r.contribution)), 1e-9);
  const contributionLabel = preview.columns[contribIdx];

  return (
    <section className="modality">
      <h3>Modalities in play</h3>
      <ul className="modality__list">
        {rows.map((r) => (
          <li key={r.name} className="modality__row">
            <span className="modality__name">{r.name}</span>
            <span className="modality__track" title={`${contributionLabel}: ${fmt(r.contribution)}`}>
              <span
                className="modality__fill"
                style={{
                  width: `${(Math.abs(r.contribution) / maxContribution) * 100}%`,
                }}
              />
            </span>
            <span className="modality__value">{fmt(r.contribution)}</span>
            {r.conflict !== null ? (
              <span className="modality__conflict" title="rate of disagreement with the fused decision">
                disagrees {(r.conflict * 100).toFixed(1)}%
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      <p className="viz__note muted small">
        Bar length is <code>{contributionLabel}</code> from{' '}
        <code>{preview.path}</code>. Where a disagreement rate is shown it is the share of
        rows on which that channel&apos;s own score falls on the opposite side of the
        operating threshold from the fused score.
      </p>
    </section>
  );
}

export interface MediaAsset {
  name: string;
  kind: string;
  url: string;
  bytes: number;
  source: string;
}

/**
 * Generated media only.
 *
 * Everything here was rendered by this repository from market data. No third-party media
 * is copied into the product: where redistribution is not permitted the pipeline keeps
 * reference metadata instead of the file.
 */
export function MediaGallery({ assets }: { assets: MediaAsset[] }) {
  if (assets.length === 0) return null;
  return (
    <section className="media">
      <h3>Generated assets</h3>
      <div className="media__grid">
        {assets.map((a) => (
          <figure key={a.url} className="media__item">
            {a.kind === 'image' ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={a.url} alt={`Rendered chart asset ${a.name}`} loading="lazy" />
            ) : a.kind === 'audio' ? (
              <audio controls preload="none" src={a.url}>
                <track kind="captions" />
              </audio>
            ) : (
              <video controls preload="none" src={a.url} muted playsInline>
                <track kind="captions" />
              </video>
            )}
            <figcaption>
              <span className="mono">{a.name}</span>
              <span className="muted small">
                {a.kind} · {(a.bytes / 1024).toFixed(0)} KB
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
      <p className="viz__note muted small">
        Rendered by this project from the market series. The audio channel is a
        sonification, not speech, and the images are charts rather than photographs.
      </p>
    </section>
  );
}

/* -- dispatch ------------------------------------------------------------------------ */

/**
 * The module's own generated figure is preferred over a redrawn chart wherever one
 * exists: it is the artifact the paper cites, and redrawing it in the browser would
 * create a second rendering of the same numbers that could drift from the first.
 */
/**
 * Whether this module has a chart, or only numbers.
 *
 * The caller uses it to avoid rendering the same figures twice: a module whose primary
 * visual falls back to bars-of-its-own-metrics would otherwise show the metric grid and a
 * bar chart of the identical values one above the other, which reads as two results.
 */
export function hasChart(mod: ResearchModule): boolean {
  const spec = VISUAL_SPEC[mod.product.visual];
  if (!spec || spec.kind === 'metrics') return false;
  if (spec.kind === 'split-metrics') {
    return mod.product.metrics.filter(
      (m) => typeof m.value === 'number' && (m.value as number) > 0,
    ).length > 1;
  }
  return mod.research.previews.length > 0;
}

export function ModuleVisual({ module: mod }: { module: ResearchModule }) {
  const spec = VISUAL_SPEC[mod.product.visual] ?? { kind: 'metrics' as const };

  if (spec.kind === 'split-metrics') {
    const rows = mod.product.metrics
      .filter((m) => typeof m.value === 'number' && (m.value as number) > 0)
      .slice(1) // the first metric is the total these parts divide
      .map((m) => ({ label: m.label, value: m.value as number, compare: null }));
    return rows.length ? (
      <SplitBar rows={rows} />
    ) : (
      <MetricBars metrics={mod.product.metrics} />
    );
  }

  // A module's outputs are often several tables at different grains. Prefer the one that
  // actually carries the columns this visual asks for; falling through to the first
  // output would chart the raw per-row table where a summary was meant.
  const previews = mod.research.previews;
  const preview =
    previews.find(
      (p) =>
        (!spec.label || p.columns.includes(spec.label)) &&
        (spec.value ?? []).some((v) => p.columns.includes(v)),
    ) ??
    previews.find((p) => (spec.value ?? []).some((v) => p.columns.includes(v))) ??
    previews[0];

  if (spec.kind === 'metrics' || !preview) {
    return <MetricBars metrics={mod.product.metrics} />;
  }
  if (spec.kind === 'table') return <TablePreview preview={preview} />;
  if (spec.kind === 'matrix') return <MatrixGrid preview={preview} />;

  const rows = rowsFrom(preview, spec, spec.kind === 'line' ? 40 : 14);
  if (rows.length === 0) return <MetricBars metrics={mod.product.metrics} />;

  const vi = pickValue(preview, spec.value);
  const valueLabel = preview.columns[vi] ?? 'value';
  const ci = spec.compare ? pickValue(preview, spec.compare) : -1;
  const compareLabel = ci >= 0 && ci !== vi ? preview.columns[ci] : undefined;

  if (spec.kind === 'line') return <LineChart rows={rows} valueLabel={valueLabel} />;
  return (
    <BarChart
      rows={rows}
      unit={spec.unit}
      valueLabel={valueLabel}
      compareLabel={compareLabel}
    />
  );
}
