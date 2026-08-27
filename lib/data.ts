/**
 * Data access for both experiences.
 *
 * The deployed app never runs the research pipeline. It reads JSON bundles that
 * `scripts/export_app_data.py` wrote, which is what guarantees the product cannot display
 * a number the research pipeline did not produce.
 *
 * Every accessor degrades to an empty result carrying `dataAvailable: false` and a note
 * saying how to produce the missing artifact. A dashboard that renders nothing and says
 * why is honest; one that renders a plausible placeholder is not.
 */
import { promises as fs } from 'node:fs';
import path from 'node:path';

import type {
  AffectiveTrace,
  ClaimRecord,
  ClusterInfo,
  CoverageSummary,
  EvidenceItem,
  ExperimentRecord,
  FigureRecord,
  LifecycleTrajectory,
  LimitationRecord,
  ModalityInfoRow,
  ProvenanceRow,
  RiskAssessment,
  RiskWindow,
  StatisticRecord,
  UniverseInfo,
} from './types';

const DATA_DIR = path.join(process.cwd(), 'public', 'data');

export interface Bundle<T> {
  dataAvailable: boolean;
  generatedAt: string | null;
  rows: T[];
  meta?: Record<string, unknown>;
  note?: string;
}

async function readJson<T>(file: string): Promise<Bundle<T>> {
  try {
    const raw = await fs.readFile(path.join(DATA_DIR, file), 'utf8');
    const parsed = JSON.parse(raw) as
      | { generated_at?: string; rows?: T[]; meta?: Record<string, unknown> }
      | T[];
    if (Array.isArray(parsed)) {
      return { dataAvailable: true, generatedAt: null, rows: parsed };
    }
    return {
      dataAvailable: true,
      generatedAt: parsed.generated_at ?? null,
      rows: parsed.rows ?? [],
      meta: parsed.meta,
    };
  } catch {
    return {
      dataAvailable: false,
      generatedAt: null,
      rows: [],
      note:
        `No exported artifact ${file}. Run the research pipeline, then ` +
        `python scripts/export_app_data.py to populate public/data/.`,
    };
  }
}

/**
 * Read any exported bundle by filename.
 *
 * Exposed so the module layer can add bundles without this file growing an accessor per
 * file, while every bundle still degrades the same way when its artifact is absent.
 */
export const getBundle = readJson;

export const getAssessments = () => readJson<RiskAssessment>('assessments.json');
export const getWindows = () => readJson<RiskWindow>('windows.json');
export const getEvidence = () => readJson<EvidenceItem>('evidence.json');
export const getAffective = () => readJson<AffectiveTrace>('affective.json');
export const getExperiments = () => readJson<ExperimentRecord>('experiments.json');
export const getStatistics = () => readJson<StatisticRecord>('statistics.json');
export const getFigures = () => readJson<FigureRecord>('figures.json');
export const getProvenance = () => readJson<ProvenanceRow>('provenance.json');
export const getCoverage = () => readJson<CoverageSummary>('coverage.json');
export const getLimitations = () => readJson<LimitationRecord>('limitations.json');
export const getClaims = () => readJson<ClaimRecord>('claims.json');
export const getModalityInfo = () => readJson<ModalityInfoRow>('modality_info.json');

/**
 * The trained audio model's scorecard on held-out speakers.
 *
 * Gated: `audio_model.json` is listed in GATED_BUNDLES, so the middleware refuses it
 * directly and a caller here must already have checked the capability. Read only after
 * that check - reading first and rendering conditionally would put a week-7 result in a
 * week-1 payload.
 */
export const getAudioModel = () =>
  readJson<{ class: string; support: number; precision: number; recall: number; f1: number }>(
    'audio_model.json',
  );

/**
 * The trained video model's scorecard on held-out actors.
 *
 * Gated the same way the audio one is: `video_model.json` is in GATED_BUNDLES, so the
 * middleware refuses it directly and a caller here must already have checked the
 * capability.
 */
export const getVideoModel = () =>
  readJson<{ class: string; support: number; precision: number; recall: number; f1: number }>(
    'video_model.json',
  );
export const getClusters = () => readJson<ClusterInfo>('clusters.json');
export const getPropagationEdges = () =>
  readJson<{ source: string; target: string; weight: number }>('propagation.json');
export const getResearchAngles = () =>
  readJson<Record<string, unknown>>('research_angles.json');
export const getReproducibility = () =>
  readJson<Record<string, unknown>>('reproducibility.json');

/** The active research universe and its provenance (spec section 8). */
export async function getUniverse(): Promise<UniverseInfo> {
  const b = await readJson<UniverseInfo>('universe.json');
  if (b.rows.length) return b.rows[0];
  return {
    id: 'unknown',
    name: 'Universe not exported',
    kind: 'point_in_time_proxy',
    effectiveDate: null,
    datasetVersion: 'unknown',
    memberCount: 0,
    distinctMembersEver: null,
    rebalances: null,
    meanEntriesPerRebalance: null,
    isIndexMembership: false,
    caveat:
      'No universe manifest was exported. The active universe is unknown, so nothing ' +
      'on this page should be attributed to any index.',
  };
}

/** Latest assessment per instrument, most elevated first. */
export async function getMarketOverview(): Promise<Bundle<RiskAssessment>> {
  const all = await getAssessments();
  if (!all.dataAvailable) return all;
  const latest = new Map<string, RiskAssessment>();
  for (const r of all.rows) {
    const prev = latest.get(r.instrument);
    if (!prev || r.date > prev.date) latest.set(r.instrument, r);
  }
  const rows = [...latest.values()].sort((a, b) => b.integrityRisk - a.integrityRisk);
  return { ...all, rows };
}

export async function getInstrumentSeries(
  symbol: string,
): Promise<Bundle<RiskAssessment>> {
  const all = await getAssessments();
  if (!all.dataAvailable) return all;
  const rows = all.rows
    .filter((r) => r.instrument === symbol)
    .sort((a, b) => a.date.localeCompare(b.date));
  return { ...all, rows };
}

export async function listInstruments(): Promise<string[]> {
  const all = await getAssessments();
  return [...new Set(all.rows.map((r) => r.instrument))].sort();
}

export async function getLimitation(id: string): Promise<LimitationRecord | null> {
  const b = await getLimitations();
  return b.rows.find((l) => l.id.toUpperCase() === id.toUpperCase()) ?? null;
}

/** Most recent risk windows across all instruments, newest first. */
export async function getRecentEvents(limit = 60): Promise<Bundle<RiskWindow>> {
  const b = await getWindows();
  if (!b.dataAvailable) return b;
  const rows = [...b.rows]
    .sort((a, b2) => b2.tEntry.localeCompare(a.tEntry))
    .slice(0, limit);
  return { ...b, rows };
}

export function fmt(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
  return value.toFixed(digits);
}

export function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
  return `${(value * 100).toFixed(digits)}%`;
}

export function signed(value: number | null | undefined, digits = 4): string {
  if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}`;
}

export const getLifecycle = () => readJson<Record<string, unknown>>('lifecycle.json');
export const getLifecycleTrajectories = () =>
  readJson<LifecycleTrajectory>('lifecycle_trajectories.json');

/** One instrument's trajectory, or null when the instrument is outside the cohort. */
export async function getTrajectory(
  symbol: string,
): Promise<LifecycleTrajectory | null> {
  const b = await getLifecycleTrajectories();
  return b.rows.find((t) => t.symbol === symbol) ?? null;
}

export const getTrust = () => readJson<Record<string, unknown>>('trust.json');

export const getAffectiveLab = () =>
  readJson<Record<string, unknown>>('affective_lab.json');

export const getRobustnessLab = () =>
  readJson<Record<string, unknown>>('robustness_lab.json');
