'use client';

/**
 * A module in a list.
 *
 * The card carries the same status pair the module page shows, so nothing about a
 * module's standing is discovered only by opening it. The link preserves the current
 * mode, because someone browsing in research mode wants the research view of whatever
 * they open next.
 */
import Link from 'next/link';

import { useMode } from '@/lib/mode';
import type { ResearchModule } from '@/lib/moduleTypes';
import { CONFIDENCE_COPY, CONFIDENCE_TONE, PRODUCT_STATUS_COPY } from '@/lib/moduleTypes';

function formatRun(at: string | null | undefined): string {
  if (!at) return 'not recorded';
  const d = new Date(at);
  return Number.isNaN(d.getTime())
    ? at
    : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

export function ModuleCard({ module: mod }: { module: ResearchModule }) {
  const { mode } = useMode();
  const headline = mod.product.metrics.find((m) => !m.unavailable);
  const tone = CONFIDENCE_TONE[mod.product.confidence];

  return (
    <Link href={`${mod.route}?mode=${mode}`} className="moduleCard">
      <div className="moduleCard__top">
        <span className="moduleCard__icon" aria-hidden="true">
          {mod.icon}
        </span>
        <span className="mono moduleCard__id modeOnly modeOnly--inline modeOnly--research">{mod.id}</span>
        <span
          className={`chip chip--${
            mod.product.status === 'VERIFIED'
              ? 'good'
              : mod.product.status === 'UNAVAILABLE'
                ? 'bad'
                : 'warn'
          }`}
          title={PRODUCT_STATUS_COPY[mod.product.status]}
        >
          {mod.product.status}
        </span>
      </div>

      <h3 className="moduleCard__name">
        <span className="modeOnly modeOnly--inline modeOnly--product">{mod.product_name}</span>
        <span className="modeOnly modeOnly--inline modeOnly--research">{mod.name}</span>
      </h3>
      <p className="moduleCard__desc">{mod.product.headline}</p>

      {headline ? (
        <div className="moduleCard__metric">
          <span className="moduleCard__metricValue">{headline.display}</span>
          <span className="moduleCard__metricLabel">{headline.label}</span>
        </div>
      ) : (
        <div className="moduleCard__metric moduleCard__metric--none">
          <span className="moduleCard__metricLabel">no scalar result</span>
        </div>
      )}

      <dl className="moduleCard__facts">
        <div>
          <dt>Last run</dt>
          <dd>{formatRun(mod.research.last_run?.at)}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>
            {mod.research.outputs.length} artifact
            {mod.research.outputs.length === 1 ? '' : 's'}
          </dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd className={`moduleCard__conf moduleCard__conf--${tone}`}>
            {CONFIDENCE_COPY[mod.product.confidence].label}
          </dd>
        </div>
      </dl>

      <span className="moduleCard__cta">
        Open in {mode === 'research' ? 'research' : 'product'} mode →
      </span>
    </Link>
  );
}
