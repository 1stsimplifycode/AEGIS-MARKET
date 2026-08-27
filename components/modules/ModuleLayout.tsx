import { NoData } from '@/components/ui/Primitives';
import { listModules, type ResearchModule } from '@/lib/modules';

import { ModuleCard } from './ModuleCard';
import { ModuleNav } from './ModuleNav';

/**
 * The frame every module page sits in: all 32 modules on the left, the module on the
 * right. Fetched once on the server and handed to the client nav, so navigating between
 * modules never refetches the list.
 */
export async function ModuleLayout({ children }: { children: React.ReactNode }) {
  const modules = await listModules();
  if (modules.length === 0) {
    return (
      <NoData
        what="Module manifest"
        note={
          'Run python scripts/export_modules.py to populate public/data/modules.json ' +
          'from research_modules.yaml and the executed artifacts.'
        }
      />
    );
  }
  return (
    <div className="moduleLayout">
      <ModuleNav modules={modules} />
      <div className="moduleLayout__main">{children}</div>
    </div>
  );
}

/** The category index: every module in it, as a card. */
export function ModuleIndex({
  modules,
  label,
  lede,
}: {
  modules: ResearchModule[];
  label: string;
  lede: string;
}) {
  const verified = modules.filter((m) => m.product.status === 'VERIFIED').length;
  const limited = modules.filter((m) => m.product.status === 'LIMITED').length;
  const unavailable = modules.filter((m) => m.product.status === 'UNAVAILABLE').length;

  return (
    <>
      <h1>{label}</h1>
      <p className="lede">{lede}</p>

      <div className="grid">
        <div className="card">
          <div className="card__label">Modules</div>
          <div className="card__value">{modules.length}</div>
          <div className="card__note">each with a product and a research view</div>
        </div>
        <div className="card">
          <div className="card__label">Verified</div>
          <div className="card__value">{verified}</div>
          <div className="card__note">ran, and the research status is supported</div>
        </div>
        <div className="card">
          <div className="card__label">Limited</div>
          <div className="card__value">{limited}</div>
          <div className="card__note">ran, and a limitation bounds the result</div>
        </div>
        <div className="card">
          <div className="card__label">Unavailable</div>
          <div className="card__value">{unavailable}</div>
          <div className="card__note">outputs absent from this build</div>
        </div>
      </div>

      <h2>All {label.toLowerCase()} modules</h2>
      <div className="moduleGrid">
        {modules.map((m) => (
          <ModuleCard key={m.id} module={m} />
        ))}
      </div>

      <section className="boundary">
        <h3>How to read a module page</h3>
        <p style={{ margin: 0 }}>
          Product mode answers what the module observed, how far the observation goes and
          what bounds it. Research mode answers the same question with the experiment
          metadata, the artifact paths, the statistical test and the limitations behind
          it. Both read the same exported record, so neither can show a number the other
          does not have.
        </p>
      </section>
    </>
  );
}
