/** Shared types. These mirror the Python contracts under `research/`. */

export type RiskState =
  | 'NORMAL'
  | 'EARLY_WARNING'
  | 'EMERGING'
  | 'ACTIVE'
  | 'ESCALATING'
  | 'PEAK'
  | 'RESOLVING'
  | 'RESOLVED';

export const RISK_STATE_ORDER: RiskState[] = [
  'NORMAL',
  'EARLY_WARNING',
  'EMERGING',
  'ACTIVE',
  'ESCALATING',
  'PEAK',
  'RESOLVING',
  'RESOLVED',
];

/**
 * Product-facing wording for each state. The lifecycle is described in the vocabulary of
 * observation — onset, escalation, peak, resolution — and never in the vocabulary of
 * transactions. A state is a statement about evidence over time, not an instruction.
 */
export const RISK_STATE_COPY: Record<RiskState, { label: string; meaning: string }> = {
  NORMAL: { label: 'Normal', meaning: 'No elevated integrity-risk evidence.' },
  EARLY_WARNING: {
    label: 'Watch',
    meaning: 'Evidence is above background but has not persisted.',
  },
  EMERGING: {
    label: 'Emerging',
    meaning: 'Evidence has persisted long enough to open a risk window.',
  },
  ACTIVE: { label: 'Active', meaning: 'The risk window is open and stable.' },
  ESCALATING: { label: 'Escalating', meaning: 'Evidence is strengthening.' },
  PEAK: { label: 'Peak', meaning: 'The strongest point of this risk window.' },
  RESOLVING: { label: 'Resolving', meaning: 'Evidence is receding.' },
  RESOLVED: { label: 'Resolved', meaning: 'The risk window has closed.' },
};

export const RISK_STATE_COLOR: Record<RiskState, string> = {
  NORMAL: '#4d4d4d',
  EARLY_WARNING: '#56b4e9',
  EMERGING: '#e69f00',
  ACTIVE: '#d55e00',
  ESCALATING: '#b22222',
  PEAK: '#7a0000',
  RESOLVING: '#009e73',
  RESOLVED: '#0072b2',
};

export type Modality =
  | 'text'
  | 'image'
  | 'audio'
  | 'video'
  | 'market'
  | 'microstructure'
  | 'regime'
  | 'propagation';

/** One instrument-day assessment. Deliberately carries no actionable field. */
export interface RiskAssessment {
  instrument: string;
  date: string;
  integrityRisk: number;
  uncertainty: number;
  coverage: number;
  riskState: RiskState;
  regime?: number | null;
  modalityContribution?: Partial<Record<Modality, number>>;
  modalityWeight?: Partial<Record<Modality, number>>;
}

export interface RiskWindow {
  instrument: string;
  tEntry: string;
  tExit: string | null;
  tPeak: string;
  peakScore: number;
  censored: boolean;
}

export interface EvidenceItem {
  modality: Modality;
  eventTime: string;
  knowledgeTime: string;
  source: string;
  licenceStatus: string;
  summary: string;
  embedUrl?: string;
  referenceUrl?: string;
}

export interface AffectiveTrace {
  date: string;
  valence: number;
  arousal: number;
  uncertainty: number;
  urgency: number;
  hype: number;
  narrativeIntensity: number;
}

export interface ExperimentRecord {
  experimentId: string;
  arm: string;
  status: string;
  fusion: string;
  modalities: string;
  auprc?: number;
  auroc?: number;
  f1?: number;
  ece?: number;
  ciLow?: number;
  ciHigh?: number;
}

export interface StatisticRecord {
  arm: string;
  comparison: string;
  deltaAuprc: number;
  pValue: number | null;
  adjustedP: number | null;
  significant: boolean;
  test: string;
  description: string;
}

export interface FigureRecord {
  figureId: string;
  number: string | null;
  title: string;
  caption: string;
  placement: 'MAIN' | 'SUPPLEMENTARY' | 'INTERNAL';
  experimentId: string;
  runId: string;
  commit: string | null;
  sourceData: string;
  generationScript: string;
  outputFormats: string[];
}

export interface ProvenanceRow {
  source: string;
  modality: string;
  licence: string;
  coverage: string;
  status: string;
}

export interface CoverageSummary {
  modality: Modality | string;
  coverage: number;
  status: string;
  note?: string;
}

/** The universe actually driving the product, with its provenance. */
export interface UniverseInfo {
  id: string;
  name: string;
  kind: 'point_in_time_proxy' | 'static_list' | 'index_membership';
  effectiveDate: string | null;
  datasetVersion: string;
  memberCount: number;
  distinctMembersEver: number | null;
  rebalances: number | null;
  meanEntriesPerRebalance: number | null;
  isIndexMembership: boolean;
  caveat: string;
}

/** Statistical grouping used in place of sectors, which are not licence-clear. */
export interface ClusterInfo {
  id: string;
  label: string;
  members: string[];
  meanAbsCorrelation: number | null;
  basis: string;
}

// -- research: limitations, claims, angles ------------------------------------------------

export type ResearchStatus =
  | 'SUPPORTED'
  | 'PARTIAL'
  | 'NOT_SUPPORTED'
  | 'NOT_RUN'
  | 'NOT_MEASURED'
  | 'BLOCKED'
  | 'OPEN_QUESTION'
  | 'FUTURE_VALIDATION'
  | 'FAILED_SANITY_CHECK'
  | 'MEASURED';

export const STATUS_TONE: Record<ResearchStatus, 'good' | 'warn' | 'bad' | 'neutral'> = {
  SUPPORTED: 'good',
  MEASURED: 'good',
  PARTIAL: 'warn',
  OPEN_QUESTION: 'warn',
  FUTURE_VALIDATION: 'warn',
  NOT_MEASURED: 'neutral',
  NOT_RUN: 'neutral',
  BLOCKED: 'neutral',
  NOT_SUPPORTED: 'bad',
  FAILED_SANITY_CHECK: 'bad',
};

export interface ExperimentSpec {
  id: string;
  hypothesis: string;
  independent_variable: string;
  dependent_variable: string;
  control: string;
  treatment: string;
  dataset: string;
  evaluation_period: string;
  metrics: string[];
  statistical_test: string;
  expected_interpretation: string;
  threats_to_validity: string[];
  status: ResearchStatus;
  required_data: string[];
  result_artifact: string | null;
}

export interface ResearchQuestion {
  id: string;
  question: string;
  limitation_id: string;
  status: ResearchStatus;
  experiments: ExperimentSpec[];
  current_evidence: string | null;
  what_remains_unresolved: string | null;
}

export interface LimitationRecord {
  id: string;
  title: string;
  category: string;
  severity: string;
  description: string;
  why_it_exists: string;
  current_status: ResearchStatus;
  current_substitute: string | null;
  invalidated_claims: string[];
  still_valid: string[];
  research_questions: ResearchQuestion[];
  required_data: string[];
  future_validation: string;
  forbidden_phrasings: string[];
  scope_note: string;
}

export interface ClaimRecord {
  id: string;
  claim: string;
  status: ResearchStatus;
  scope: string;
  evidence: string;
  dataset: string;
  experiment: string;
  limitations: string[];
  overclaim_examples: string[];
  figure_ids: string[];
  note: string;
}

export const SCOPE_LABEL: Record<string, string> = {
  SYNTHETIC_VALIDATION: 'Synthetic-validation result',
  VALIDATION: 'Validation result',
  OUT_OF_SAMPLE_HOLDOUT: 'Out-of-sample holdout result',
  ANALYTIC: 'Analytic result',
  ENGINEERING: 'Engineering property',
};

export interface ModalityInfoRow {
  modality: string;
  total_auprc: number | null;
  unique: number | null;
  redundant: number | null;
  conflict_rate: number | null;
  missing_rate: number | null;
}

/**
 * One instrument's risk trajectory across the analysis window.
 *
 * The arrays are parallel and share an index: `dates[i]`, `risk[i]`, `phase[i]` and
 * `state[i]` all describe the same session. `changePoints` holds indices into them.
 */
export interface LifecycleTrajectory {
  symbol: string;
  n_sessions: number;
  dates: string[];
  risk: (number | null)[];
  uncertainty: (number | null)[];
  phase: string[];
  state: string[];
  band: string[];
  change_points: number[];
  first_date: string;
  last_date: string;
  final_band: string;
  final_risk: number | null;
}
