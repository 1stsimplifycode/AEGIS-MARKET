import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

/**
 * The product's capabilities and the week each one joins the demonstration.
 *
 * Read from `public/data/capabilities.json`, which `scripts/export_modules.py` writes from
 * the manifest's `product_capabilities:` block. The bundle carries no active week: which
 * of these are locked depends on the week a run is started at, and that is decided per
 * request. Keeping the two apart is what lets the pages stay statically prerendered while
 * the locks still change with `AEGIS_ACTIVE_WEEK`.
 *
 * Server-side only — it touches the filesystem. The navigation receives the result as a
 * prop rather than importing it, so no client bundle pulls `node:fs` in behind it.
 */
export interface ProductCapability {
  id: string;
  name: string;
  href: string;
  enabled_from_week: number;
  summary: string;
  /** "nav" for the primary navigation, "analysis" for a section of /analysis. */
  surfaces?: string[];
}

export async function getCapabilities(): Promise<ProductCapability[]> {
  try {
    const raw = await readFile(
      join(process.cwd(), 'public', 'data', 'capabilities.json'),
      'utf-8',
    );
    // `rows` is the envelope every exported bundle uses; a second shape would be a
    // second reader and a test that only covers one of them.
    const parsed = JSON.parse(raw) as { rows?: ProductCapability[] };
    return parsed.rows ?? [];
  } catch {
    // No bundle means the export has not run. The navigation then shows its ordinary
    // entries and no capability progression, which is a smaller product rather than a
    // broken one — and never a locked capability nobody can explain.
    return [];
  }
}

/** The capabilities that appear on one surface. One registry, filtered, never a second. */
export async function getCapabilitiesOn(surface: string): Promise<ProductCapability[]> {
  const all = await getCapabilities();
  return all.filter((c) => (c.surfaces ?? ['nav']).includes(surface));
}
