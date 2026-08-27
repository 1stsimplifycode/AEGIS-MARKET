/**
 * Module types and the copy that names them, with no filesystem dependency.
 *
 * Split out from `lib/modules.ts` because the client components — the sidebar, the
 * module card, the shell that switches between the two experiences — need these types
 * and these labels, and importing them from the data module would drag `node:fs` into
 * the browser bundle. Nothing here reads anything; `lib/modules.ts` does the reading and
 * re-exports this file so a server component still has one import.
 */

export type ModuleCategory = 'STATS' | 'MULTIMODAL' | 'SCENARIO';

/** Product vocabulary. Says what a reader can do with the module. */
export type ProductStatus = 'VERIFIED' | 'EXPERIMENTAL' | 'LIMITED' | 'UNAVAILABLE';

/** How far the evidence goes, which is a different question from whether it ran. */
export type Confidence = 'HIGH' | 'MODERATE' | 'LOW' | 'UNRESOLVED';

export interface ModuleMetric {
  label: string;
  format: string;
  note: string | null;
  /** The declared lookup into an artifact. Shown in Research mode so a reader can check. */
  expression: string;
  value: number | string | null;
  display: string | null;
  source: string | null;
  /** Set when the artifact does not contain what the expression names. */
  unavailable: string | null;
}

export interface ModuleFigure {
  figure: string;
  available: boolean;
  url?: string | null;
  caption: string | null;
  source_data?: string | null;
  source_dir?: string;
  git_commit?: string | null;
  bytes?: number;
}

export interface ModuleTable {
  table: string;
  available: boolean;
  caption: string | null;
  source: string | null;
  rows: number | null;
  path?: string;
  git_commit?: string | null;
  columns?: string[];
}

export interface ModuleInput {
  kind: string;
  label: string;
  note: string;
}

/** A media asset this project generated, copied into `public/media/` by the exporter. */
export interface ModuleMediaAsset {
  name: string;
  kind: string;
  url: string;
  bytes: number;
  source: string;
}

export interface ModuleLimitation {
  id: string;
  title: string;
  scope_note: string;
  status: string;
  description: string;
}

export interface ModuleClaim {
  id: string;
  claim: string;
  status: string;
  scope: string;
  evidence: string;
  statistical_test: string;
  metric: string;
  dataset: string;
  experiment: string;
  artifacts: string[];
  limitations: string[];
}

export interface ModulePreview {
  columns: string[];
  rows: (string | number | null)[][];
  total_rows: number;
  truncated: boolean;
  path: string;
}

export interface ModuleRun {
  at: string | null;
  status: string | null;
  message: string | null;
  elapsed_s: number | null;
  git_commit: string | null;
  runs_recorded: number;
}

export interface ResearchModule {
  id: string;
  category: ModuleCategory;
  index: number;
  slug: string;
  /** The research name, used wherever the module is cited. */
  name: string;
  /**
   * The name the product experience shows.
   *
   * `STATS-11` is a precise identifier and a useless label; "How confident the signal is"
   * is the reverse. Both are declared in the manifest so they cannot drift, and each is
   * shown where it belongs rather than one standing in for the other.
   */
  product_name: string;
  route: string;
  icon: string;
  product: {
    headline: string;
    question: string;
    actions: string[];
    observation: string;
    risk: string;
    confidence: Confidence;
    status: ProductStatus;
    visual: string;
    metrics: ModuleMetric[];
    inputs: ModuleInput[];
    media: ModuleMediaAsset[];
  };
  research: {
    status: string;
    wrapper_status: string;
    purpose: string;
    research_question: string;
    notes: string;
    experiment_id: string | null;
    adapter: string;
    canonical: string[];
    inputs: string[];
    outputs: string[];
    depends_on: string[];
    metrics: ModuleMetric[];
    previews: ModulePreview[];
    limitations: ModuleLimitation[];
    claims: ModuleClaim[];
    last_run: ModuleRun | null;
  };
  figures: ModuleFigure[];
  tables: ModuleTable[];
  unavailable_metrics: { label: string; reason: string; expression: string }[];
}

export const CATEGORY_COPY: Record<
  ModuleCategory,
  { label: string; base: string; lede: string }
> = {
  STATS: {
    label: 'Statistics',
    base: '/stats',
    lede:
      'Sixteen modules that characterise the data, validate the model against it, and ' +
      'say how much of any difference is real.',
  },
  MULTIMODAL: {
    label: 'Multimodal',
    base: '/multimodal',
    lede:
      'Sixteen modules covering the modality pipeline end to end: ingestion, feature ' +
      'extraction, alignment, fusion, information decomposition and explanation.',
  },
  SCENARIO: {
    label: 'Scenario Lab',
    base: '/scenario',
    lede:
      'Eight modules that put the fitted models under stated conditions and compare ' +
      'the outcomes. Every condition declares its baseline, its assumption and how its ' +
      'rows were obtained, because a counterfactual is not an event.',
  },
};

export const CONFIDENCE_COPY: Record<Confidence, { label: string; meaning: string }> = {
  HIGH: {
    label: 'High confidence',
    meaning: 'Measured directly, and the measurement is stable across seeds.',
  },
  MODERATE: {
    label: 'Moderate confidence',
    meaning: 'Measured, and bounded by a limitation that changes how far it reaches.',
  },
  LOW: {
    label: 'Low confidence',
    meaning:
      'Measured on data whose construction bounds what the number can be read to mean.',
  },
  UNRESOLVED: {
    label: 'Unresolved',
    meaning:
      'The experiment ran and did not separate the alternatives. That is a result, ' +
      'not a gap.',
  },
};

export const PRODUCT_STATUS_COPY: Record<ProductStatus, string> = {
  VERIFIED: 'Ran, produced its declared outputs, and its research status is supported.',
  EXPERIMENTAL: 'Ran, and its research position is still an open question.',
  LIMITED: 'Ran, and a documented limitation bounds what its result covers.',
  UNAVAILABLE: 'Its outputs are not present in this build.',
};

export const CONFIDENCE_TONE: Record<Confidence, 'good' | 'warn' | 'bad' | 'neutral'> = {
  HIGH: 'good',
  MODERATE: 'neutral',
  LOW: 'warn',
  UNRESOLVED: 'warn',
};

export const PRODUCT_STATUS_TONE: Record<
  ProductStatus,
  'good' | 'warn' | 'bad' | 'neutral'
> = {
  VERIFIED: 'good',
  EXPERIMENTAL: 'neutral',
  LIMITED: 'warn',
  UNAVAILABLE: 'bad',
};

