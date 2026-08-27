import Link from 'next/link';
import type { ReactNode } from 'react';

import type { ResearchModule } from '@/lib/moduleTypes';
import { CATEGORY_COPY, CONFIDENCE_COPY } from '@/lib/moduleTypes';

import {
  ActionList,
  ClaimPanel,
  EvidenceCard,
  ExperimentMetadata,
  FigureViewer,
  InputPanel,
  LimitationPanel,
  MetricGrid,
  ProvenancePanel,
  ResearchMetricTable,
  StatusPair,
  TableList,
  UncertaintyCard,
} from './Panels';
import {
  hasChart,
  MediaGallery,
  ModalityStrip,
  ModuleVisual,
  TablePreview,
} from './Visuals';

/**
 * One module, two experiences, one set of numbers.
 *
 * Both views are rendered into the page and one is hidden by CSS keyed on the
 * `data-mode` attribute the boot script sets before first paint. Three consequences,
 * each of which is why it is done this way rather than by branching in JavaScript:
 *
 * * **No flash.** A `?mode=research` link paints research mode directly instead of
 *   painting product mode and swapping after hydration.
 * * **No JavaScript requirement.** Both experiences are in the prerendered HTML, so the
 *   page is complete before any script runs, and the research evidence is reachable by
 *   anything that reads HTML.
 * * **They cannot disagree.** Both views read the same record in the same render. There
 *   is one number and two depths of presentation, which is the whole design.
 *
 * Product mode never states more than research mode supports. Where research mode says a
 * difference is inside the seed noise floor, product mode says the comparison is
 * unresolved: it simplifies the language and never the meaning.
 */
export function ModuleShell({
  module: mod,
  runner,
}: {
  module: ResearchModule;
  /**
   * The interactive run panel, when the module declares one. Rendered once, outside the
   * two mode blocks, so switching depth mid-session keeps the result on screen: the panel
   * holds client state, and rendering it inside each block would give the two modes two
   * separate panels that disagree about what has been run.
   */
  runner?: ReactNode;
}) {
  const category = CATEGORY_COPY[mod.category];

  return (
    <article className="module" data-module={mod.id}>
      <header className="module__head">
        <div className="module__crumbs">
          <Link href={category.base}>{category.label}</Link>
          <span aria-hidden="true">›</span>
          <span className="modeOnly modeOnly--inline modeOnly--research mono">{mod.id}</span>
          <span className="modeOnly modeOnly--inline modeOnly--product">{mod.product_name}</span>
        </div>
        <div className="module__title">
          <span className="module__icon" aria-hidden="true">
            {mod.icon}
          </span>
          <div>
            {/* One heading, two names. The identifier is precise and unreadable; the
                product name is readable and uncitable. Each mode gets the one it needs
                and neither has to stand in for the other. */}
            <h1 className="modeOnly modeOnly--product">{mod.product_name}</h1>
            <h1 className="modeOnly modeOnly--research">{mod.name}</h1>
            <p className="module__sub">{mod.product.headline}</p>
          </div>
        </div>
        <StatusPair module={mod} />
      </header>

      {runner ? <div className="module__runner">{runner}</div> : null}

      <div className="modeOnly modeOnly--product">
        <ProductView module={mod} />
      </div>
      <div className="modeOnly modeOnly--research">
        <ResearchView module={mod} />
      </div>
    </article>
  );
}

/* -- product ------------------------------------------------------------------------- */

function ProductView({ module: mod }: { module: ResearchModule }) {
  const researchHref = `${mod.route}?mode=research`;
  return (
    <div className="module__body">
      <section className="module__lead">
        <h2 className="module__question">{mod.product.question}</h2>
        <p className="module__observation">{mod.product.observation}</p>
      </section>

      <section className="module__primary">
        <h3>From the last full pipeline run</h3>
        <p className="module__storedNote">
          These are the values the research pipeline last wrote for this capability. Run
          it above to compute the same analysis on a slice you choose.
        </p>
        {/* A module without a chartable series shows its numbers as the primary view
            rather than as a bar chart of the same values beneath a metric grid: the same
            result rendered twice reads as two results. */}
        {hasChart(mod) ? (
          <ModuleVisual module={mod} />
        ) : (
          <MetricGrid metrics={mod.product.metrics} />
        )}
      </section>

      {mod.category === 'MULTIMODAL' ? <ModalityStrip module={mod} /> : null}
      {mod.product.media.length ? <MediaGallery assets={mod.product.media} /> : null}

      {hasChart(mod) ? (
        <section>
          <h3>Current result</h3>
          <MetricGrid metrics={mod.product.metrics} />
        </section>
      ) : null}

      <div className="split">
        <div>
          <ActionList actions={mod.product.actions} />
          <InputPanel inputs={mod.product.inputs} />
        </div>
        <div>
          <UncertaintyCard module={mod} />
          <EvidenceCard module={mod} researchHref={researchHref} />
        </div>
      </div>
    </div>
  );
}

/* -- research ------------------------------------------------------------------------ */

function ResearchView({ module: mod }: { module: ResearchModule }) {
  const productHref = `${mod.route}?mode=product`;
  const conf = CONFIDENCE_COPY[mod.product.confidence];
  return (
    <div className="module__body">
      <section className="module__lead">
        <h2 className="module__question">{mod.research.research_question}</h2>
        <p>{mod.research.purpose}</p>
        <p className="muted small">
          The product view of this module states the same result as{' '}
          <em>“{mod.product.observation}”</em> and its confidence as{' '}
          <em>{conf.label.toLowerCase()}</em>.{' '}
          <Link href={productHref}>See the product view →</Link>
        </p>
      </section>

      <section>
        <h3>Experiment metadata</h3>
        <ExperimentMetadata module={mod} run={mod.research.last_run} />
      </section>

      <section>
        <h3>Metrics, with the artifact each was read from</h3>
        <ResearchMetricTable
          metrics={[...mod.product.metrics, ...mod.research.metrics]}
        />
      </section>

      {mod.research.previews.length ? (
        <section>
          <h3>Result tables</h3>
          {mod.research.previews.map((p) => (
            <TablePreview key={p.path} preview={p} limit={14} />
          ))}
        </section>
      ) : null}

      <section>
        <h3>Figures</h3>
        <FigureViewer figures={mod.figures} />
      </section>

      <section>
        <h3>Paper tables</h3>
        <TableList tables={mod.tables} />
      </section>

      <section>
        <h3>Claims resting on this evidence</h3>
        <ClaimPanel claims={mod.research.claims} />
      </section>

      <section>
        <h3>Limitations</h3>
        <LimitationPanel limitations={mod.research.limitations} />
      </section>

      <section>
        <h3>Artifact provenance</h3>
        <ProvenancePanel module={mod} />
      </section>
    </div>
  );
}
