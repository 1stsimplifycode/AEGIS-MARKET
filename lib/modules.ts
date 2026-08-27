/**
 * Reading the exported module bundles.
 *
 * Server-only: it touches the filesystem through `lib/data`. Every type and label lives
 * in `lib/moduleTypes` and is re-exported here, so a server component imports one module
 * and a client component imports the types directly without pulling `node:fs` in with
 * them.
 */
import { getBundle, type Bundle } from './data';
import type {
  ModuleCategory,
  ModuleFigure,
  ModuleTable,
  ResearchModule,
} from './moduleTypes';

export * from './moduleTypes';

export interface ModuleMeta {
  n_modules?: number;
  by_category?: Record<string, number>;
  n_figures?: number;
  n_tables?: number;
  n_unresolved_metrics?: number;
  manifest_version?: string;
}

export async function getModules(): Promise<Bundle<ResearchModule>> {
  return getBundle<ResearchModule>('modules.json');
}

export async function listModules(category?: ModuleCategory): Promise<ResearchModule[]> {
  const bundle = await getModules();
  const rows = category
    ? bundle.rows.filter((m) => m.category === category)
    : bundle.rows;
  return [...rows].sort((a, b) =>
    a.category === b.category
      ? a.index - b.index
      : a.category.localeCompare(b.category),
  );
}

/**
 * Resolve a module from the last segment of its route.
 *
 * Routes are short and readable (`/stats/universe`), while manifest slugs are long and
 * descriptive (`universe_survivorship`). Matching on the route segment keeps the URL a
 * product decision and the slug a research one, and lets either change without the other.
 */
export async function getModuleByRouteSlug(
  category: ModuleCategory,
  routeSlug: string,
): Promise<ResearchModule | null> {
  const rows = await listModules(category);
  return rows.find((m) => m.route.split('/').pop() === routeSlug) ?? null;
}

export async function routeSlugs(category: ModuleCategory): Promise<string[]> {
  const rows = await listModules(category);
  return rows.map((m) => m.route.split('/').pop()!).filter(Boolean);
}

/** Every figure the export copied into `public/figures/`, with its caption. */
export async function getFigureIndex(): Promise<Bundle<ModuleFigure>> {
  return getBundle<ModuleFigure>('figures_index.json');
}

/** Every generated table, with its caption, source artifact and column list. */
export async function getTableIndex(): Promise<Bundle<ModuleTable>> {
  return getBundle<ModuleTable>('tables_index.json');
}

/** Modules that cite a given figure, so the figure explorer can link back. */
export function modulesCitingFigure(
  modules: ResearchModule[],
  figure: string,
): ResearchModule[] {
  return modules.filter((m) => m.figures.some((f) => f.figure === figure));
}

export function modulesCitingTable(
  modules: ResearchModule[],
  table: string,
): ResearchModule[] {
  return modules.filter((m) => m.tables.some((t) => t.table === table));
}

/**
 * A module by its route slug, its index, or its identifier.
 *
 * `/stats/data-integrity` is what the product links to: a reader scanning a list of
 * capabilities recognises the name and does not recognise a number. `/stats/01` is what a
 * mentor asks for during a weekly demonstration, and `/stats/STATS-01` is what someone
 * arrives with after reading the manifest. All three resolve to one page rather than to a
 * redirect the reader has to wait through.
 */
export async function getModuleBySlugOrIndex(
  category: ModuleCategory,
  slug: string,
): Promise<ResearchModule | null> {
  const modules = await listModules(category);
  const wanted = slug.trim().toLowerCase();

  const byRoute = modules.find((m) => m.route.split('/').pop() === wanted);
  if (byRoute) return byRoute;

  const byId = modules.find((m) => m.id.toLowerCase() === wanted);
  if (byId) return byId;

  const asNumber = Number(wanted);
  if (Number.isInteger(asNumber) && asNumber > 0) {
    return modules.find((m) => m.index === asNumber) ?? null;
  }
  return null;
}

/** Every way a module page may be addressed, for prerendering. */
export async function routeSlugsWithAliases(
  category: ModuleCategory,
): Promise<string[]> {
  const modules = await listModules(category);
  const slugs = new Set<string>();
  for (const m of modules) {
    const tail = m.route.split('/').pop();
    if (tail) slugs.add(tail);
    slugs.add(String(m.index).padStart(2, '0'));
  }
  return [...slugs];
}

/**
 * The modules, named and routable, with no result attached.
 *
 * `listModules` returns every module's exported metrics and series, which the module pages
 * need. A page that only lists what exists does not — and reading the full bundle to build
 * a list puts every module's numbers into that page's payload, including the weeks this
 * demonstration has not reached. Reading a smaller file is what removes the possibility,
 * rather than trusting the bundler to drop what was not rendered.
 */
export interface ModuleIndexRow {
  id: string;
  index: number;
  category: string;
  name: string;
  slug: string;
  route: string;
  icon: string;
  product_name: string;
  product_question: string;
}

export async function listModuleIndex(): Promise<ModuleIndexRow[]> {
  const bundle = await getBundle<ModuleIndexRow>('module_index.json');
  return bundle.rows;
}
