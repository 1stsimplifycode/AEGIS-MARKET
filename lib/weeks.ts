/**
 * The weekly registry, read from the bundle `scripts/export_modules.py` wrote.
 *
 * Server side only. The registry is the manifest's `weeks:` block passed through
 * `backend/registry.py`, so the schema a form draws itself from is the same schema the
 * backend validates against. Every page that renders controls reads them from here.
 */
import { getBundle } from './data';
import type { WeekRecord } from './runTypes';

export * from './runTypes';

export async function getWeeks(): Promise<{
  available: boolean;
  generatedAt: string | null;
  rows: WeekRecord[];
  note?: string;
}> {
  const bundle = await getBundle<WeekRecord>('weeks.json');
  return {
    available: bundle.dataAvailable && bundle.rows.length > 0,
    generatedAt: bundle.generatedAt,
    rows: bundle.rows,
    note: bundle.note,
  };
}

export async function getWeek(week: number): Promise<WeekRecord | null> {
  const { rows } = await getWeeks();
  return rows.find((r) => r.week === week) ?? null;
}

/** The week a module belongs to, for the cross-link on a module page. */
export async function weekOfModule(moduleId: string): Promise<WeekRecord | null> {
  const { rows } = await getWeeks();
  return (
    rows.find((r) => r.stats_module === moduleId || r.multimodal_module === moduleId) ?? null
  );
}

/**
 * What a module page needs in order to render its run panel.
 *
 * Returns `null` for a module the weekly registry does not cover, which is the correct
 * answer for one: a page cannot offer to run something the backend has no declaration for.
 */
export async function getModuleExecution(moduleId: string): Promise<{
  inputs: WeekRecord['input_schema'][string];
  execution: WeekRecord['execution'][string];
  summary: string;
  week: number;
} | null> {
  const week = await weekOfModule(moduleId);
  if (!week) return null;
  const execution = week.execution[moduleId];
  const mod = week.modules.find((m) => m.module_id === moduleId);
  if (!execution || !mod) return null;
  return {
    inputs: week.input_schema[moduleId] ?? [],
    execution,
    summary: mod.analysis.summary,
    week: week.week,
  };
}

/**
 * Just enough about a week to name it, and nothing about what it computes.
 *
 * The gated page describes a week it must not reveal. Reading the full registry to do that
 * hands the whole table — every week's headline metrics, series keys and visual
 * declarations — to the renderer, and in development that lands in the page's own payload.
 * No computed value is in there, but a page whose entire job is to withhold week 16 should
 * not be shipping week 16's feature declaration to get its title.
 *
 * So this returns the four fields a title needs and drops the rest before anything renders.
 */
export interface WeekSummary {
  week: number;
  title: string;
  question: string;
  route: string;
}

export async function getWeekSummaries(): Promise<WeekSummary[]> {
  // Its own bundle, not a projection of the full one. The development server streams the
  // file a server component read into that page's payload, so narrowing the *return* type
  // would not narrow what ships — only reading a smaller file does.
  const bundle = await getBundle<WeekSummary>('week_titles.json');
  return bundle.rows;
}
