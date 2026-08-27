/**
 * The Scenario Lab bundle.
 *
 * Read from `public/data/scenarios.json`, which `scripts/export_modules.py` wrote from
 * the artifacts `scripts/run_scenarios.py` produced. As with the module records, Product
 * mode and Research mode read this same object and differ only in how much of it they
 * render.
 *
 * The catalogue travels with the outcomes rather than beside them. That is the whole
 * design constraint of this track: a scenario outcome shown without the assumption it
 * rests on is a claim about the world, and none of these are.
 */
import { getBundle } from './data';

export type SimulationMethod =
  | 'OBSERVED_STRATUM'
  | 'COUNTERFACTUAL'
  | 'POLICY_COUNTERFACTUAL';

/**
 * What each method commits to. Rendered wherever a scenario is shown, because the
 * difference between "these rows occurred" and "this is what the model would have said"
 * is the single thing a reader must not lose.
 */
export const METHOD_COPY: Record<
  SimulationMethod,
  { label: string; short: string; meaning: string; tone: 'observed' | 'simulated' }
> = {
  OBSERVED_STRATUM: {
    label: 'Observed condition',
    short: 'Observed',
    meaning:
      'Rows that really occurred and satisfy the stated condition. Nothing is ' +
      'simulated; the condition selects rows and never alters one.',
    tone: 'observed',
  },
  COUNTERFACTUAL: {
    label: 'Counterfactual condition',
    short: 'Simulated',
    meaning:
      'Rows altered under a stated assumption and re-scored. This did not happen. The ' +
      'outcome is what the model would have reported if the assumption held.',
    tone: 'simulated',
  },
  POLICY_COUNTERFACTUAL: {
    label: 'Policy comparison',
    short: 'Simulated',
    meaning:
      'Identical rows, identical model, identical scores. Only a declared decision rule ' +
      'differs, so the difference is attributable to that rule under that policy.',
    tone: 'simulated',
  },
};

export interface ScenarioSpecRecord {
  scenario_id: string;
  name: string;
  family: string;
  baseline_definition: string;
  intervention_assumption: string;
  affected_features: string[];
  constraints: string[];
  expected_effect: string;
  simulation_method: SimulationMethod;
  random_seed: number;
  assumptions: string[];
  parameters: Record<string, unknown>;
  note: string;
  is_baseline: boolean;
}

export interface ScenarioComparisonRow {
  scenario_id: string;
  name: string;
  family: string;
  simulation_method: SimulationMethod;
  is_baseline: boolean;
  status: string;
  n_rows: number;
  risk_mean: number;
  uncertainty_mean: number;
  elevated_rate: number;
  delta_risk_mean?: number | null;
  delta_uncertainty_mean?: number | null;
  ci_low?: number | null;
  ci_high?: number | null;
  interval_method?: string | null;
  spec?: ScenarioSpecRecord | null;
  [key: string]: unknown;
}

export interface ScenarioUncertaintyRow {
  scenario_id: string;
  family: string;
  simulation_method: SimulationMethod;
  headline_metric: string;
  estimate: number | null;
  ci_low: number | null;
  ci_high: number | null;
  p_value: number | null;
  interval_method: string | null;
  n_assumptions: number;
  assumptions: string;
}

export interface ScenarioMoneyRow {
  scenario_id: string;
  scenario_name: string;
  family: string;
  quantity: string;
  amount_inr: number;
  amount_ci_low_inr: number | null;
  amount_ci_high_inr: number | null;
  notional_inr?: number | null;
  notional_label?: string | null;
  caveat: string;
  reading?: string | null;
  coverage?: number | null;
  review_load_cases?: number | null;
  is_baseline_policy?: boolean | null;
  [key: string]: unknown;
}

export interface ScenarioLab {
  available: boolean;
  scenario_version: string | null;
  run_at: string | null;
  git_commit: string | null;
  seeds: number[];
  notional: { inr?: number; label?: string; caveat?: string };
  catalogue: ScenarioSpecRecord[];
  comparison: ScenarioComparisonRow[];
  uncertainty: ScenarioUncertaintyRow[];
  money: ScenarioMoneyRow[];
  ablation: Record<string, unknown>[];
  robustness: Record<string, unknown>[];
  transaction_corpus: Record<string, unknown> | null;
  n_failed: number;
  problems: string[];
  reading: string;
  not_available_note: string;
}

export async function getScenarioLab(): Promise<ScenarioLab | null> {
  const bundle = await getBundle<ScenarioComparisonRow>('scenarios.json');
  const lab = (bundle.meta as unknown as { scenario_lab?: ScenarioLab } | undefined) ??
    undefined;
  return lab?.scenario_lab ?? null;
}

/** Rupees, the way a reader in India reads them, with the unit stated. */
export function inr(amount: number | null | undefined): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return 'n/a';
  const a = Math.abs(amount);
  const sign = amount < 0 ? '−' : '';
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)} crore`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(2)} lakh`;
  return `${sign}₹${a.toFixed(0)}`;
}

/**
 * Whether an interval separates the difference from zero.
 *
 * Returns `null` rather than `false` when there is no interval at all: "we did not
 * measure this" and "we measured it and it was not separated" are different statements,
 * and collapsing them is how an absent interval becomes an implied null result.
 */
export function separatedFromZero(
  lo: number | null | undefined,
  hi: number | null | undefined,
): boolean | null {
  if (lo === null || lo === undefined || hi === null || hi === undefined) return null;
  if (Number.isNaN(lo) || Number.isNaN(hi)) return null;
  return lo > 0 || hi < 0;
}

export function scenariosByFamily(
  lab: ScenarioLab,
  family: string,
): ScenarioComparisonRow[] {
  return lab.comparison.filter((r) => r.family === family);
}

export function baselineOf(rows: ScenarioComparisonRow[]): ScenarioComparisonRow | null {
  return rows.find((r) => r.is_baseline) ?? null;
}
