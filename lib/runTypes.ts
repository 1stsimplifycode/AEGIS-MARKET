/**
 * The backend response contract, in TypeScript.
 *
 * A mirror of `backend/contract.py` and `backend/registry.py`. It is a mirror rather than
 * a generated file because there are two of them and one round of drift would be caught
 * by `tsc` immediately; a code generator would be more machinery than the problem needs.
 *
 * No filesystem access here, deliberately: the run panel is a client component, and the
 * types and copy it needs must not drag `node:fs` into the browser bundle. `lib/weeks.ts`
 * does the reading and re-exports this file.
 */

export type RunMode = 'LIVE_COMPUTATION' | 'VERIFIED_ARTIFACT';

/**
 * Statuses the backend returns. `OK` is the only success; the rest are refusals a reader
 * is owed an explanation for, and the panel renders each of them as an explanation rather
 * than as an empty state.
 */
export type RunStatus =
  | 'OK'
  | 'FAILED'
  | 'BLOCKED'
  | 'INPUTS_MISSING'
  | 'INSUFFICIENT_DATA'
  | 'PROTECTED'
  | 'NOT_YET_EXECUTED'
  | 'INVALID_INPUT'
  | 'UNKNOWN_MODULE'
  | 'UNKNOWN_ROUTE'
  | 'UNKNOWN_WEEK'
  | 'TIMEOUT'
  | 'BACKEND_UNAVAILABLE'
  | 'FORBIDDEN_ORIGIN'
  | 'UNAUTHORISED'
  | 'METHOD_NOT_ALLOWED'
  | 'PARTIAL';

export interface RunMetric {
  key: string;
  label: string;
  value: number | string | boolean | null;
  display: string;
  format: string;
  note: string;
  /** Repository-relative artifact the value was read from. Empty for a live computation. */
  source: string;
}

export interface RunSeries {
  key: string;
  label: string;
  columns: string[];
  rows: (number | string | boolean | null)[][];
  note: string;
  truncated: boolean;
  total_rows: number | null;
}

export interface RunError {
  code: RunStatus | string;
  reason: string;
  remedy: string;
  detail?: Record<string, unknown>;
}

export interface RunLimitation {
  id: string;
  title: string;
  scope_note: string;
  status: string;
}

export interface RunResponse {
  backend_version: string;
  module_id: string;
  week: number | null;
  category: string;
  name: string;
  status: RunStatus;
  mode: RunMode;
  mode_label: string;
  mode_meaning: string;
  experiment_id: string | null;
  dataset: Record<string, unknown>;
  inputs: Record<string, unknown>;
  metrics: RunMetric[];
  series: RunSeries[];
  uncertainty: Record<string, unknown>;
  observations: string[];
  figures: { figure?: string; url?: string | null; caption?: string | null }[];
  tables: { table?: string; caption?: string | null }[];
  provenance: Record<string, unknown>;
  limitations: RunLimitation[];
  message: string;
  elapsed_s: number;
  error: RunError | null;
}

export interface WeekRunResponse {
  backend_version: string;
  week: number;
  title: string;
  question: string;
  summary: string;
  stats_module: string;
  multimodal_module: string;
  status: RunStatus;
  modes: Record<string, RunMode>;
  results: Record<string, RunResponse>;
  elapsed_s: number;
  reading: string;
  error?: RunError | null;
}

/** One declared parameter, exactly as `backend/registry.py` will validate it. */
export interface InputSpec {
  name: string;
  kind:
    | 'date'
    | 'int'
    | 'float'
    | 'bool'
    | 'select'
    | 'multiselect'
    | 'symbols'
    | 'text'
    /** Text with a file picker beside it. The service validates it as text. */
    | 'document';
  label: string;
  default: unknown;
  note: string;
  options: string[];
  minimum: number | string | null;
  maximum: number | string | null;
  max_items: number | null;
  required: boolean;
}

export interface ExecutionSpec {
  mode: 'LIVE' | 'ARTIFACT';
  is_live: boolean;
  protected: boolean;
  typical_seconds: number;
  artifact_reason: string;
}

export interface WeekModule {
  module_id: string;
  index: number;
  category: string;
  name: string;
  /** What the product calls it. The identifier stays the identifier. */
  product_name: string;
  purpose: string;
  research_question: string;
  route: string;
  icon: string;
  status: string;
  wrapper_status: string;
  experiment_id: string | null;
  limitations: string[];
  outputs: string[];
  canonical: string[];
  adapter: string;
  protected: boolean;
  analysis: {
    mode: 'LIVE' | 'ARTIFACT';
    is_live: boolean;
    typical_seconds: number;
    summary: string;
    inputs: InputSpec[];
    artifact_reason: string;
  };
}

/**
 * What a week *shows*, declared in the manifest beside the modules it describes.
 *
 * Which figures lead and which series is the picture is a product decision, and putting
 * it here rather than inside a component is what makes it checkable: a test runs each
 * module and asserts every declared key is one the module actually returns.
 */
export interface WeekFeatureSpec {
  product_question?: string;
  story?: string;
  headline?: { module: string; metric: string; label: string }[];
  primary_visual?: WeekVisualSpec;
  secondary_visual?: WeekVisualSpec;
}

export interface WeekVisualSpec {
  module: string;
  series: string;
  label_column: string;
  value_column: string;
  kind: 'bars' | 'line';
  caption?: string;
}

export interface WeekRecord {
  week: number;
  title: string;
  question: string;
  summary: string;
  feature?: WeekFeatureSpec;
  stats_module: string;
  multimodal_module: string;
  route: string;
  backend_routes: {
    week: string;
    run_week: string;
    modules: Record<string, string>;
    run_module: Record<string, string>;
  };
  input_schema: Record<string, InputSpec[]>;
  output_schema: string[];
  product_view: Record<string, string>;
  research_view: Record<string, string>;
  artifact_sources: Record<string, string[]>;
  execution: Record<string, ExecutionSpec>;
  modules: WeekModule[];
}

/**
 * How each mode is described wherever a result appears.
 *
 * The two are never allowed to look alike. A replayed artifact is a real result and is
 * shown as one; what it is not is a computation that happened because someone pressed a
 * button, and a badge that read the same for both would erase exactly that difference.
 */
export const MODE_COPY: Record<
  RunMode,
  { badge: string; tone: 'live' | 'artifact'; short: string }
> = {
  LIVE_COMPUTATION: {
    badge: 'Live computation',
    tone: 'live',
    short: 'Computed now, on the data you selected.',
  },
  VERIFIED_ARTIFACT: {
    badge: 'Verified experiment result',
    tone: 'artifact',
    short: 'Replayed from a stored, provenance-stamped run. Nothing was computed now.',
  },
};

/** Statuses that are a refusal to be explained rather than a failure to be reported. */
export const REFUSALS: ReadonlySet<string> = new Set([
  'PROTECTED',
  'INPUTS_MISSING',
  'INSUFFICIENT_DATA',
  'NOT_YET_EXECUTED',
  'INVALID_INPUT',
  'BLOCKED',
  'BACKEND_UNAVAILABLE',
]);

export const STATUS_COPY: Record<string, { label: string; kind: 'ok' | 'refused' | 'failed' }> =
  {
    OK: { label: 'Completed', kind: 'ok' },
    PARTIAL: { label: 'Partly completed', kind: 'refused' },
    INVALID_INPUT: { label: 'Selection rejected', kind: 'refused' },
    INSUFFICIENT_DATA: { label: 'Too little data in that selection', kind: 'refused' },
    INPUTS_MISSING: { label: 'Required data not present', kind: 'refused' },
    PROTECTED: { label: 'Protected artifact', kind: 'refused' },
    NOT_YET_EXECUTED: { label: 'Not yet executed', kind: 'refused' },
    BLOCKED: { label: 'Blocked', kind: 'refused' },
    BACKEND_UNAVAILABLE: { label: 'Execution unavailable here', kind: 'refused' },
    UNKNOWN_MODULE: { label: 'No such module', kind: 'failed' },
    UNKNOWN_WEEK: { label: 'No such week', kind: 'failed' },
    UNKNOWN_ROUTE: { label: 'No such endpoint', kind: 'failed' },
    TIMEOUT: { label: 'Timed out', kind: 'failed' },
    FAILED: { label: 'Failed', kind: 'failed' },
  };

export function statusCopy(status: string): { label: string; kind: 'ok' | 'refused' | 'failed' } {
  return STATUS_COPY[status] ?? { label: status, kind: 'failed' };
}

/** Default request body for a module, taken from its declared schema. */
export function defaultsFor(inputs: InputSpec[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const i of inputs) {
    if (i.default === null || i.default === undefined) continue;
    out[i.name] = i.default;
  }
  return out;
}
