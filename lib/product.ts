/**
 * The product's data layer: backend first, stored snapshot second, and it says which.
 *
 * Two sources, one shape. `backend/product.py` builds these read models from the panels
 * directly; `scripts/export_product.py` writes the same models to `public/data/market.json`
 * at export time. A page asks this module and gets whichever is available, together with
 * a `source` that says what it got — because "the market" from a live service and "the
 * market" from a snapshot taken last Tuesday are different claims, and only one of them
 * is entitled to the present tense.
 *
 * Nothing here computes a market number. If a value is on the screen, a panel produced it.
 */
import type { DirectionBlock } from '@/components/product/DirectionStrip';
import type { AnnouncementsBlock } from '@/components/product/EventFeed';

import { getBundle } from './data';

export type Tone = 'calm' | 'watch' | 'elevated' | 'high';
export type ProductSource = 'live' | 'snapshot' | 'unavailable';

export interface PricePoint {
  date: string;
  close: number;
  /**
   * Real OHLC from the panel, optional only because an older exported bundle may predate
   * these fields. They are never synthesised from `close`: a candle needs a genuine open,
   * high and low or it is not drawn.
   */
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  turnover?: number | null;
}

export interface RiskPoint {
  date: string;
  risk: number;
  uncertainty: number;
}

export interface ModalityShare {
  modality: string;
  label: string;
  contribution: number;
  weight: number | null;
  share: number;
}

export interface MarketBlock {
  available: boolean;
  last_session: string;
  close: number;
  change: number | null;
  change_pct: number | null;
  window_change_pct: number | null;
  sessions: number;
  volume: number;
  turnover: number;
  history_from: string;
  series: PricePoint[];
  source: string;

  /**
   * Recency, kept deliberately separate from coverage.
   *
   * `coverage_from` is where the history begins; `latest_session` is when the most recent
   * observation happened. Conflating them lets a page imply it is current when it is not,
   * so `recency_label` switches to "Latest available market data" whenever the panel is
   * behind today, and `days_since_latest_session` says by how much.
   */
  latest_session?: string;
  previous_session?: string | null;
  window_from?: string;
  window_to?: string;
  window_sessions?: number;
  coverage_from?: string;
  coverage_sessions?: number;
  checked_at?: string;
  days_since_latest_session?: number;
  is_current_as_of_today?: boolean;
  recency_label?: string;
  recency_note?: string;
  ohlc_source?: string;
  ohlc_complete?: boolean;

  /** Indicators DERIVED from these closes. The exchange publishes none of them. */
  indicators?: IndicatorSeries;
  /** Which way the observed price moved, as a tally of independent readings. */
  direction?: DirectionBlock;
}

export interface IndicatorSeries {
  indicators_version: string;
  conventions: Record<string, unknown>;
  dates: string[];
  /** Aligned point-for-point with `dates`; leading entries are null, never back-filled. */
  rsi: (number | null)[];
  macd: (number | null)[];
  macd_signal: (number | null)[];
  macd_histogram: (number | null)[];
  rsi_latest: number | null;
  rsi_observation: string;
  rsi_reference_levels: number[];
  macd_latest: number | null;
  macd_signal_latest: number | null;
  macd_histogram_latest: number | null;
  macd_observation: string;
  available: boolean;
  why_unavailable: string | null;
}

export interface RiskBlock {
  available: boolean;
  why?: string;
  state?: string;
  state_label?: string;
  state_tone?: Tone;
  state_meaning?: string;
  score?: number;
  uncertainty?: number;
  coverage?: number | null;
  sessions_scored?: number;
  scored_from?: string;
  scored_to?: string;
  modalities?: ModalityShare[];
  series?: RiskPoint[];
  provenance?: Record<string, unknown>;
}

/**
 * The Week 1 market-intelligence foundation for one instrument.
 *
 * Every field here is served from an artifact the C1-C7 test suite asserts against, so a
 * value rendered on the page is one the research layer stands behind. Anything the
 * exchange does not publish arrives as `available: false` with a `why`, and is rendered
 * as an explicit "not available" rather than omitted -- a blank field reads as "nothing
 * to report", which is a different claim.
 */
export interface SecurityStatus {
  available: boolean;
  why?: string;
  state?: string;
  state_label?: string;
  meaning?: string;
  basis?: string;
  first_observed_session?: string;
  last_observed_session?: string;
  sessions_observed?: number;
  listing_date?: string | null;
  listing_date_basis?: string;
  in_current_roster?: boolean;
  trade_for_trade_sessions?: number;
  delisted_on?: string | null;
  suspended_on?: string | null;
  date_note?: string;
}

export interface PriceBand {
  available: boolean;
  why?: string;
  band?: string | null;
  band_label?: string;
  series?: string;
  surveillance_remark?: string | null;
  basis?: string;
  source?: string;
  temporal_coverage?: string;
}

export interface CorporateAction {
  ex_date: string;
  subject: string;
  action_type: string;
  price_factor: number | null;
  status: string;
  raw_return: number | null;
  adjusted_return: number | null;
}

export interface CorporateActionContext {
  available: boolean;
  why?: string;
  count?: number;
  price_affecting?: number;
  actions?: CorporateAction[];
  basis?: string;
  source?: string;
  note?: string;
}

export interface PointInTimeView {
  available: boolean;
  why?: string;
  as_of?: { decision_time: string; knowledge_cutoff: string };
  strict?: boolean;
  visible_sessions?: number;
  latest_visible_session?: string | null;
  latest_visible_close?: number | null;
  withheld_by_knowledge_bound?: number;
  explanation?: string;
  read_path?: string;
}

export interface InstrumentFoundation {
  week1_version: string;
  symbol: string;
  status: SecurityStatus;
  corporate_actions: CorporateActionContext;
  price_band: PriceBand;
  point_in_time: PointInTimeView;
}

export interface LiquidityMetric {
  available: boolean;
  why?: string;
}

/** Week 2 estimators for one security. Every value is read from the built artifacts. */
export interface InstrumentLiquidity {
  week2_version: string;
  symbol: string;
  realised_variance: LiquidityMetric & {
    annualised_volatility?: number;
    sampling_minutes?: number;
    n_returns?: number;
    relative_standard_error?: number;
    sessions?: number;
  };
  price_impact: LiquidityMetric & {
    lambda?: number;
    standard_error?: number;
    t_stat?: number;
    n_obs?: number;
    r_squared?: number;
    significant?: boolean;
  };
  arrival: LiquidityMetric & {
    mean_daily_trades?: number;
    fano_factor?: number;
    model_selected?: string;
    overdispersed?: boolean;
  };
  liquidity_state: LiquidityMetric & {
    stress_score?: number;
    stress_gate_fired?: boolean;
    latest_session?: string;
    sessions?: number;
    sessions_stressed?: number;
    primary_driver?: string;
    attribution?: Record<string, number>;
    components?: Record<
      string,
      { value: number | null; robust_z: number | null; label: string }
    >;
  };
}

export interface Instrument {
  found: boolean;
  symbol: string;
  tracked: boolean;
  tracked_rank: number | null;
  market: MarketBlock;
  risk: RiskBlock;
  announcements?: AnnouncementsBlock;
  foundation?: InstrumentFoundation;
  liquidity?: InstrumentLiquidity;
  observations: string[];
}

export interface MarketOverview {
  market: {
    available: boolean;
    last_session: string;
    instruments_traded: number;
    advancing: number;
    declining: number;
    unchanged: number;
    median_change_pct: number | null;
    turnover: number;
    source: string;
    note: string;
  };
  tracked: {
    name: string;
    instruments: number;
    advancing: number;
    declining: number;
    median_change_pct: number | null;
    caveat: string;
  };
  risk_mix: {
    available: boolean;
    states: { state: string; label: string; tone: Tone; instruments: number }[];
    instruments: number;
    note: string;
    provenance?: Record<string, unknown>;
  };
}

export interface AttentionRow {
  symbol: string;
  state: string;
  state_label: string;
  state_tone: Tone;
  score: number;
  uncertainty: number;
  date: string;
}

export interface SearchRow {
  symbol: string;
  tracked: boolean;
  analysed: boolean;
  state: string | null;
  state_label: string | null;
  state_tone: Tone | null;
  change_pct: number | null;
  turnover: number;
}

export interface Sourced<T> {
  source: ProductSource;
  /** The session the numbers describe. Present whether live or from a snapshot. */
  asOf: string | null;
  /** When a snapshot was taken. Null for a live read. */
  snapshotAt?: string | null;
  data: T | null;
  note?: string;
}

interface MarketBundleMeta {
  last_session: string;
  n_instruments: number;
  snapshot_window: number;
  overview: MarketOverview;
  attention: { available: boolean; rows: AttentionRow[]; total: number; scored: number };
  directory: { results: SearchRow[] };
  note: string;
}

const TIMEOUT_MS = Number(process.env.AEGIS_BACKEND_TIMEOUT_MS ?? 8000);

function backendBase(): string | null {
  const raw = process.env.AEGIS_BACKEND_URL?.trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null;
  } catch {
    return null;
  }
}

/**
 * Ask the analysis service, or return null.
 *
 * A short timeout on purpose. This runs while a page is rendering, and a reader waiting
 * eight seconds for a home page has already formed an opinion about the product; the
 * stored snapshot beneath it is a better answer than a slow one.
 */
async function fromBackend<T>(path: string): Promise<T | null> {
  const base = backendBase();
  if (!base) return null;
  const headers: Record<string, string> = {};
  const token = process.env.AEGIS_BACKEND_TOKEN?.trim();
  if (token) headers.Authorization = `Bearer ${token}`;
  try {
    const res = await fetch(`${base}/api/${path}`, {
      headers,
      cache: 'no-store',
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

async function snapshot(): Promise<{
  meta: MarketBundleMeta | null;
  rows: Instrument[];
  generatedAt: string | null;
}> {
  const bundle = await getBundle<Instrument>('market.json');
  return {
    meta: (bundle.meta as unknown as MarketBundleMeta) ?? null,
    rows: bundle.rows,
    generatedAt: bundle.generatedAt,
  };
}

const MISSING =
  'No market snapshot has been exported and no analysis backend is reachable. Run ' +
  'python scripts/export_product.py, or start the backend with run_dev.bat.';

export async function getOverview(): Promise<Sourced<MarketOverview>> {
  const live = await fromBackend<MarketOverview>('market/overview');
  if (live?.market) {
    return { source: 'live', asOf: live.market.last_session, data: live };
  }
  const { meta, generatedAt } = await snapshot();
  if (meta?.overview) {
    return {
      source: 'snapshot',
      asOf: meta.last_session,
      snapshotAt: generatedAt,
      data: meta.overview,
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: MISSING };
}

export async function getAttention(limit = 8): Promise<Sourced<AttentionRow[]>> {
  const live = await fromBackend<{ rows: AttentionRow[] }>(
    `market/attention?limit=${limit}`,
  );
  if (live?.rows) {
    const { meta } = await snapshot();
    return { source: 'live', asOf: meta?.last_session ?? null, data: live.rows };
  }
  const { meta, generatedAt } = await snapshot();
  if (meta?.attention?.rows) {
    return {
      source: 'snapshot',
      asOf: meta.last_session,
      snapshotAt: generatedAt,
      data: meta.attention.rows.slice(0, limit),
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: MISSING };
}

export async function getInstrument(symbol: string): Promise<Sourced<Instrument>> {
  const clean = symbol.toUpperCase().trim();
  const live = await fromBackend<Instrument>(`instruments/${encodeURIComponent(clean)}`);
  if (live?.found) {
    return { source: 'live', asOf: live.market.last_session, data: live };
  }
  const { rows, meta, generatedAt } = await snapshot();
  const found = rows.find((r) => r.symbol === clean);
  if (found) {
    return {
      source: 'snapshot',
      asOf: meta?.last_session ?? found.market.last_session,
      snapshotAt: generatedAt,
      data: found,
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: MISSING };
}

/** Every instrument the product can open, for the directory and for static params. */
export async function listInstrumentSymbols(): Promise<string[]> {
  const { rows } = await snapshot();
  return rows.map((r) => r.symbol).sort();
}

/**
 * Instruments matching a term.
 *
 * Served from the snapshot rather than the backend: this runs on a prerendered page and
 * the snapshot already holds every instrument the product can open. A search that reached
 * across the network would be slower and would find nothing extra.
 */
export async function searchInstruments(
  query: string,
  limit = 24,
): Promise<{ rows: Instrument[]; total: number; asOf: string | null }> {
  const { rows, meta } = await snapshot();
  const q = query.trim().toUpperCase();
  const matched = q
    ? rows.filter((r) => r.symbol.includes(q))
    : rows.filter((r) => r.tracked);
  matched.sort((a, b) => {
    const starts = Number(b.symbol.startsWith(q)) - Number(a.symbol.startsWith(q));
    if (starts !== 0) return starts;
    return (b.market?.turnover ?? 0) - (a.market?.turnover ?? 0);
  });
  return {
    rows: matched.slice(0, limit),
    total: matched.length,
    asOf: meta?.last_session ?? null,
  };
}

/* -- indices ---------------------------------------------------------------------- */

/**
 * An index is not an instrument and not a universe.
 *
 * The type is carried through from `research/data/instruments.py` so the distinction
 * survives the trip to the browser. A page that renders an `INDEX` is rendering a
 * published benchmark with a level; a page that renders a `UNIVERSE_PROXY` is rendering a
 * set of instruments this project selected, which has no level at all. Nothing in this
 * file lets one stand in for the other.
 */
export type InstrumentKind = 'INDEX' | 'EQUITY' | 'UNIVERSE_PROXY' | 'MEDIA_EVENT';

/** How current a number is. An end-of-day report is not a live quote and never says so. */
export type Recency = 'LIVE' | 'DELAYED' | 'LATEST_AVAILABLE_SESSION' | 'HISTORICAL';

export interface IndexProvenance {
  source: string;
  source_url: string;
  access_type: 'PUBLIC' | 'LICENSED' | 'DERIVED';
  redistribution_status: 'VERIFIED' | 'RESTRICTED' | 'UNKNOWN';
  license_note: string;
  frequency: string;
  field_note: string;
}

export interface IndexCoverage {
  index_id: string;
  available: boolean;
  display_name?: string;
  instrument_type?: string;
  sessions?: number;
  first_session?: string;
  last_session?: string;
  history_limit_note?: string;
  unavailable_fields?: Record<string, string>;
  provenance?: IndexProvenance | null;
  index_version?: string;
  ingested_at?: string;
  why?: string;
}

export interface IndexConstituents {
  available: boolean;
  count: number | null;
  why: string;
  what_would_be_needed: string;
  not_substituted_by: Record<string, string>;
  declared_unavailable_in_registry: boolean;
}

export interface IndexDetail {
  available: boolean;
  instrument_id: string;
  instrument_type: InstrumentKind;
  display_name: string;
  description: string;
  last_session: string;
  close: number;
  change: number | null;
  change_pct: number | null;
  previous_close: number | null;
  volatility_20d: number | null;
  drawdown: number | null;
  high_52w: number | null;
  low_52w: number | null;
  window_sessions: number;
  window_change_pct: number | null;
  series: PricePoint[];
  coverage: IndexCoverage;
  provenance: IndexProvenance | null;
  available_fields: string[];
  unavailable_fields: Record<string, string>;
  recency: Recency;
  recency_note: string;
  constituents: IndexConstituents;
  why?: string;
  remedy?: string;
}

export interface IndexSummary {
  instrument_id: string;
  instrument_type: InstrumentKind;
  display_name: string;
  close: number;
  change_pct: number | null;
  last_session: string;
  series: PricePoint[];
}

interface IndexBundle {
  indices?: { available: boolean; rows: IndexSummary[]; primary: string };
  index_detail?: Record<string, IndexDetail>;
}

export const PRIMARY_INDEX = 'NIFTY50';

/** Everything a reader might type that means the benchmark. Never the proxy. */
export const INDEX_ALIASES: Record<string, string> = {
  NIFTY: PRIMARY_INDEX,
  NIFTY50: PRIMARY_INDEX,
  'NIFTY 50': PRIMARY_INDEX,
  '^NSEI': PRIMARY_INDEX,
  NSEI: PRIMARY_INDEX,
  BANKNIFTY: 'NIFTYBANK',
  NIFTYBANK: 'NIFTYBANK',
  'NIFTY BANK': 'NIFTYBANK',
  FINNIFTY: 'NIFTYFINSERVICE',
  MIDCPNIFTY: 'NIFTYMIDCAP50',
  NIFTYNXT50: 'NIFTYNEXT50',
  'NIFTY NEXT 50': 'NIFTYNEXT50',
};

export function resolveIndexId(term: string): string | null {
  const key = term.trim().toUpperCase();
  return INDEX_ALIASES[key] ?? INDEX_ALIASES[key.replace(/\s+/g, '')] ?? null;
}

export async function getIndex(
  indexId: string = PRIMARY_INDEX,
): Promise<Sourced<IndexDetail>> {
  const live = await fromBackend<IndexDetail>(`indices/${encodeURIComponent(indexId)}`);
  if (live?.available) {
    return { source: 'live', asOf: live.last_session, data: live };
  }
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as IndexBundle | null)?.index_detail?.[indexId];
  if (stored?.available) {
    return {
      source: 'snapshot',
      asOf: stored.last_session,
      snapshotAt: generatedAt,
      data: stored,
    };
  }
  return {
    source: 'unavailable',
    asOf: null,
    data: null,
    note:
      stored?.why ??
      'No index panel has been built. Point AEGIS_NSE_ARCHIVE at a downloaded NSE ' +
        'archive and run python scripts/build_index_panel.py.',
  };
}

export async function getIndices(): Promise<Sourced<IndexSummary[]>> {
  const live = await fromBackend<{ rows: IndexSummary[] }>('indices');
  if (live?.rows?.length) {
    return { source: 'live', asOf: live.rows[0].last_session, data: live.rows };
  }
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as IndexBundle | null)?.indices;
  if (stored?.rows?.length) {
    return {
      source: 'snapshot',
      asOf: stored.rows[0].last_session,
      snapshotAt: generatedAt,
      data: stored.rows,
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: 'No index panel.' };
}

/** How a level should be written: an index level is not money and carries no symbol. */
export function level(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return value.toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export const RECENCY_COPY: Record<Recency, string> = {
  LIVE: 'Live',
  DELAYED: 'Delayed',
  LATEST_AVAILABLE_SESSION: 'Latest available session',
  HISTORICAL: 'Historical',
};

export interface IndexSeriesPoint {
  date: string;
  close: number;
  return_pct: number | null;
  volatility_20d: number | null;
  drawdown: number | null;
}

export interface IndexSeriesView {
  key: 'close' | 'return_pct' | 'volatility_20d' | 'drawdown';
  label: string;
  unit: 'points' | 'percent';
  note: string;
}

export interface IndexSeries {
  available: boolean;
  instrument_id: string;
  display_name: string;
  sessions: number;
  from: string;
  to: string;
  full_from: string;
  full_to: string;
  series: IndexSeriesPoint[];
  views: IndexSeriesView[];
  recency: Recency;
  why?: string;
}

export interface IndexContext {
  available: boolean;
  instrument_id: string;
  display_name: string;
  window: { from: string; to: string; sessions: number };
  market_context: {
    level: string;
    documents: number;
    instruments_with_documents: number;
    by_kind: { doc_kind: string; documents: number }[];
    panel_sessions: number;
    panel_instruments: number;
    reading: string;
  };
  instrument_evidence: {
    level: string;
    assessed_from: string | null;
    assessed_to: string | null;
    assessed_rows: number;
    overlapping_sessions: number;
    reading: string;
  };
  coverage_note: string;
}

interface IndexExtras {
  index_series?: Record<string, IndexSeries>;
  index_context?: Record<string, IndexContext>;
}

export async function getIndexSeries(
  indexId: string = PRIMARY_INDEX,
): Promise<Sourced<IndexSeries>> {
  const live = await fromBackend<IndexSeries>(
    `indices/${encodeURIComponent(indexId)}/series`,
  );
  if (live?.available) return { source: 'live', asOf: live.to, data: live };
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as IndexExtras | null)?.index_series?.[indexId];
  if (stored?.available) {
    return { source: 'snapshot', asOf: stored.to, snapshotAt: generatedAt, data: stored };
  }
  return { source: 'unavailable', asOf: null, data: null, note: 'No index series.' };
}

export async function getIndexContext(
  indexId: string = PRIMARY_INDEX,
): Promise<Sourced<IndexContext>> {
  const live = await fromBackend<IndexContext>(
    `indices/${encodeURIComponent(indexId)}/context`,
  );
  if (live?.available) return { source: 'live', asOf: live.window.to, data: live };
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as IndexExtras | null)?.index_context?.[indexId];
  if (stored?.available) {
    return {
      source: 'snapshot',
      asOf: stored.window.to,
      snapshotAt: generatedAt,
      data: stored,
    };
  }
  return { source: 'unavailable', asOf: null, data: null, note: 'No index context.' };
}


/* -- evidence alignment ------------------------------------------------------------ */

/**
 * Whether two sources can be spoken about together.
 *
 * Computed by the backend on every request from the sessions each source holds — never
 * stored, never assumed. A pair reading NOT_ALIGNED today becomes ALIGNED on its own when
 * an overlapping source is ingested, and nothing in this file needs to change for that.
 */
export type AlignmentStatus = 'ALIGNED' | 'PARTIAL' | 'NOT_ALIGNED' | 'UNKNOWN';

export interface CoverageWindow {
  source_id: string;
  kind: string;
  label: string;
  start: string | null;
  end: string | null;
  sessions: number;
  note: string;
}

export interface AlignmentPair {
  alignment_version: string;
  source_a: CoverageWindow;
  source_b: CoverageWindow;
  index_start: string | null;
  index_end: string | null;
  evidence_start: string | null;
  evidence_end: string | null;
  overlap_start: string | null;
  overlap_end: string | null;
  overlap_sessions: number;
  coverage_ratio: number;
  alignment_status: AlignmentStatus;
  thresholds: { aligned_at: number; minimum_sessions: number };
  summary: string;
  permits: {
    combined_analysis: boolean;
    combined_analysis_with_caveat: boolean;
    side_by_side_presentation: boolean;
    temporal_association: boolean;
    note: string;
  };
  coverage_ratio_note: string;
  why_it_matters?: string;
}

export interface AlignmentMatrix {
  available: boolean;
  alignment_version: string;
  pairs: AlignmentPair[];
  headline: AlignmentPair | null;
  counts: { pairs: number; aligned: number; partial: number; not_aligned: number };
  sources: CoverageWindow[];
  reading: string;
  future_path: string;
}

interface AlignmentBundle {
  alignment?: AlignmentMatrix;
}

export const ALIGNMENT_COPY: Record<
  AlignmentStatus,
  { label: string; tone: Tone; product: string }
> = {
  ALIGNED: {
    label: 'Aligned',
    tone: 'calm',
    product: 'These cover the same sessions and can be read together.',
  },
  PARTIAL: {
    label: 'Partly aligned',
    tone: 'watch',
    product: 'These share only part of their period, so anything combining them covers only the shared part.',
  },
  NOT_ALIGNED: {
    label: 'Not aligned',
    tone: 'elevated',
    product: 'These cover different periods, so results are shown separately.',
  },
  UNKNOWN: {
    label: 'Not measured',
    tone: 'watch',
    product: 'One of these holds no sessions yet, so the relationship cannot be measured.',
  },
};

export async function getAlignment(): Promise<Sourced<AlignmentMatrix>> {
  const live = await fromBackend<AlignmentMatrix>('alignment');
  if (live?.pairs?.length) {
    return { source: 'live', asOf: live.headline?.index_end ?? null, data: live };
  }
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as AlignmentBundle | null)?.alignment;
  if (stored?.pairs?.length) {
    return {
      source: 'snapshot',
      asOf: stored.headline?.index_end ?? null,
      snapshotAt: generatedAt,
      data: stored,
    };
  }
  return {
    source: 'unavailable',
    asOf: null,
    data: null,
    note: 'Alignment has not been computed. Start the backend, or run ' +
      'python scripts/export_product.py.',
  };
}

/** The pair a caller cares about, by source identifiers, in either order. */
export function findPair(
  matrix: AlignmentMatrix | null,
  a: string,
  b: string,
): AlignmentPair | null {
  if (!matrix) return null;
  return (
    matrix.pairs.find(
      (p) =>
        (p.source_a.source_id === a && p.source_b.source_id === b) ||
        (p.source_a.source_id === b && p.source_b.source_id === a),
    ) ?? null
  );
}

/* -- evidence for a market period --------------------------------------------------- */

/**
 * What this project holds for the sessions an index covers, one card per source.
 *
 * A product read model over the alignment layer. Every status arrives computed for that
 * specific pair, so the file contains no threshold, no session count and no verdict of
 * its own — pointing it at a different dataset changes what it renders, not what it says.
 */
export interface EvidenceSource {
  source_id: string;
  product_label: string;
  research_label: string;
  product_blurb: string;
  href: string;
  kind: string;
  status: AlignmentStatus;
  badge: string;
  mark: 'check' | 'partial' | 'cross' | 'unknown';
  tone: Tone;
  product_status: string;
  period: string;
  period_from: string | null;
  period_to: string | null;
  source_sessions: number;
  index_sessions: number;
  shared_sessions: number;
  overlap_from: string | null;
  overlap_to: string | null;
  coverage_ratio: number;
  summary: string;
  permits: AlignmentPair['permits'];
  source_note: string;
}

export interface EvidenceSummary {
  available: boolean;
  index_id: string;
  index_label: string;
  index_from: string | null;
  index_to: string | null;
  index_sessions: number;
  index_period: string;
  sources: EvidenceSource[];
  counts: { aligned: number; partial: number; not_aligned: number; total: number };
  headline: string;
  experiments_using_index: {
    count: number;
    answer: boolean;
    product_note: string;
    research_note: string;
  };
  why?: string;
  remedy?: string;
}

interface EvidenceBundle {
  evidence?: Record<string, EvidenceSummary>;
}

export async function getEvidenceSummary(
  indexId: string = PRIMARY_INDEX,
): Promise<Sourced<EvidenceSummary>> {
  const live = await fromBackend<EvidenceSummary>(
    `evidence/${encodeURIComponent(indexId)}`,
  );
  if (live?.available) {
    return { source: 'live', asOf: live.index_to, data: live };
  }
  const { meta, generatedAt } = await snapshot();
  const stored = (meta as unknown as EvidenceBundle | null)?.evidence?.[indexId];
  if (stored?.available) {
    return {
      source: 'snapshot',
      asOf: stored.index_to,
      snapshotAt: generatedAt,
      data: stored,
    };
  }
  return {
    source: 'unavailable',
    asOf: null,
    data: null,
    note:
      stored?.why ??
      'Evidence coverage has not been computed. Start the backend, or run ' +
        'python scripts/export_product.py.',
  };
}

/** One source's card, by identifier. Null when that source is not in the summary. */
export function findEvidence(
  summary: EvidenceSummary | null,
  sourceId: string,
): EvidenceSource | null {
  return summary?.sources.find((s) => s.source_id === sourceId) ?? null;
}

/* -- presentation helpers -------------------------------------------------------- */

export function inr(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

/**
 * Rupees at the scale Indian markets actually quote them.
 *
 * A session's turnover runs to twelve digits, and `₹104976.4 cr` is a number nobody
 * reads — the scale it belongs to is lakh crore, which is how the exchange, the press and
 * anyone looking at this page would say it out loud.
 */
export function compactInr(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const round = (n: number) => n.toLocaleString('en-IN', { maximumFractionDigits: 2 });
  if (value >= 1e12) return `₹${round(value / 1e12)} lakh cr`;
  if (value >= 1e7) return `₹${round(value / 1e7)} cr`;
  if (value >= 1e5) return `₹${round(value / 1e5)} lakh`;
  return inr(value);
}

export function signedPct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  const shown = (value * 100).toFixed(digits);
  return `${value >= 0 ? '+' : ''}${shown}%`;
}

export function direction(value: number | null | undefined): 'up' | 'down' | 'flat' {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) {
    return 'flat';
  }
  return value > 0 ? 'up' : 'down';
}

/** How a sourced payload should describe itself, in one short clause. */
export function sourceNote(s: Sourced<unknown>): string {
  if (s.source === 'live') return `Read from the analysis service · session ${s.asOf}`;
  if (s.source === 'snapshot') {
    return `Stored snapshot · session ${s.asOf}`;
  }
  return 'No data available';
}
