import Link from 'next/link';

import type {
  ScenarioComparisonRow,
  ScenarioLab as Lab,
  ScenarioMoneyRow,
  ScenarioSpecRecord,
  ScenarioUncertaintyRow,
} from '@/lib/scenarios';
import { METHOD_COPY, baselineOf, inr, separatedFromZero } from '@/lib/scenarios';

/**
 * The Scenario Lab: baseline against every stated condition, in one table.
 *
 * Both experiences are rendered and CSS keyed on `data-mode` decides which is shown, the
 * same arrangement the module pages use. Product mode gives the comparison and the
 * plain-language reading; Research mode adds the assumption, the interval, the method and
 * the provenance of each row.
 *
 * Three rules this component exists to enforce, none of which is optional:
 *
 * * **Method is always visible.** Every scenario carries an Observed or Simulated badge,
 *   because a counterfactual read as an event is the failure this whole track guards.
 * * **No scenario is marked best.** The table compares; it never ranks. A row with the
 *   largest effect is labelled as the largest effect and nothing more.
 * * **No currency figure appears without its caveat.** The notional and the simulation
 *   caveat are rendered in the same block as the number, not in a footnote.
 */
export function ScenarioLab({ lab }: { lab: Lab }) {
  const market = lab.comparison.filter((r) => r.family === 'market');
  const transaction = lab.comparison.filter((r) => r.family === 'transaction');

  return (
    <div className="scenarioLab">
      <div className="modeOnly modeOnly--product">
        <ProductLab lab={lab} market={market} transaction={transaction} />
      </div>
      <div className="modeOnly modeOnly--research">
        <ResearchLab lab={lab} market={market} transaction={transaction} />
      </div>
    </div>
  );
}

/* -- shared pieces ------------------------------------------------------------------- */

function MethodBadge({ method }: { method: ScenarioComparisonRow['simulation_method'] }) {
  const copy = METHOD_COPY[method];
  if (!copy) return null;
  return (
    <span className={`methodBadge methodBadge--${copy.tone}`} title={copy.meaning}>
      {copy.short}
    </span>
  );
}

function DeltaCell({ row }: { row: ScenarioComparisonRow }) {
  if (row.is_baseline) return <span className="muted">reference</span>;
  const d = row.delta_risk_mean;
  if (d === null || d === undefined) return <span className="muted">—</span>;
  const sep = separatedFromZero(row.ci_low, row.ci_high);
  return (
    <>
      <span className={d >= 0 ? 'delta delta--up' : 'delta delta--down'}>
        {d >= 0 ? '+' : ''}
        {d.toFixed(4)}
      </span>
      <span className="delta__note">
        {sep === null
          ? 'no sampling interval'
          : sep
            ? 'interval excludes zero'
            : 'unresolved'}
      </span>
    </>
  );
}

/** The comparison table §26 asks for: conditions across, quantities down. */
function ComparisonTable({
  rows,
  caption,
}: {
  rows: ScenarioComparisonRow[];
  caption: string;
}) {
  if (rows.length === 0) return null;
  const base = baselineOf(rows);
  const ordered = base ? [base, ...rows.filter((r) => !r.is_baseline)] : rows;

  return (
    <div className="tableWrap">
      <table className="scenarioTable">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Quantity</th>
            {ordered.map((r) => (
              <th key={r.scenario_id} scope="col">
                <span className="scenarioTable__id">{r.scenario_id}</span>
                <span className="scenarioTable__name">{r.name}</span>
                <MethodBadge method={r.simulation_method} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Estimated risk</th>
            {ordered.map((r) => (
              <td key={r.scenario_id} className="num">
                {r.risk_mean.toFixed(4)}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Uncertainty</th>
            {ordered.map((r) => (
              <td key={r.scenario_id} className="num">
                {r.uncertainty_mean.toFixed(4)}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Rows evaluated</th>
            {ordered.map((r) => (
              <td key={r.scenario_id} className="num">
                {r.n_rows.toLocaleString()}
              </td>
            ))}
          </tr>
          <tr>
            <th scope="row">Change from baseline</th>
            {ordered.map((r) => (
              <td key={r.scenario_id} className="num scenarioTable__delta">
                <DeltaCell row={r} />
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function MoneyPanel({ money }: { money: ScenarioMoneyRow[] }) {
  if (money.length === 0) return null;
  const caveat = money[0].caveat;
  return (
    <section className="moneyPanel">
      <h3>Simulated currency figures</h3>
      <div className="moneyPanel__grid">
        {money.map((m) => (
          <div key={`${m.family}-${m.scenario_id}`} className="moneyPanel__item">
            <div className="moneyPanel__id mono">{m.scenario_id}</div>
            <div className="moneyPanel__amount">{inr(m.amount_inr)}</div>
            {m.amount_ci_low_inr !== null && m.amount_ci_high_inr !== null ? (
              <div className="moneyPanel__ci">
                95% CI {inr(m.amount_ci_low_inr)} to {inr(m.amount_ci_high_inr)}
              </div>
            ) : (
              <div className="moneyPanel__ci muted">
                no sampling interval on these rows
              </div>
            )}
            <div className="moneyPanel__quantity">{m.quantity}</div>
            {m.coverage !== null && m.coverage !== undefined ? (
              <div className="moneyPanel__load">
                {(m.coverage * 100).toFixed(1)}% of labelled-elevated value, at{' '}
                {m.review_load_cases} cases referred
              </div>
            ) : null}
          </div>
        ))}
      </div>
      <p className="moneyPanel__caveat">{caveat}</p>
    </section>
  );
}

/* -- product ------------------------------------------------------------------------- */

function ProductLab({
  lab,
  market,
  transaction,
}: {
  lab: Lab;
  market: ScenarioComparisonRow[];
  transaction: ScenarioComparisonRow[];
}) {
  const established = lab.uncertainty.filter(
    (u) => separatedFromZero(u.ci_low, u.ci_high) === true,
  ).length;
  const unresolved = lab.uncertainty.filter(
    (u) => separatedFromZero(u.ci_low, u.ci_high) === false,
  ).length;

  return (
    <>
      <section className="module__lead">
        <h2 className="module__question">What would happen under different conditions?</h2>
        <p className="module__observation">
          The Scenario Lab puts the models the rest of this project fitted under stated
          conditions and compares the outcomes. It answers what the model would report, not
          what anyone should do, and it performs no action of any kind.
        </p>
      </section>

      <div className="grid">
        <div className="card">
          <div className="card__label">Conditions declared</div>
          <div className="card__value">{lab.catalogue.length}</div>
          <div className="card__note">across market and transaction domains</div>
        </div>
        <div className="card">
          <div className="card__label">Differences established</div>
          <div className="card__value">{established}</div>
          <div className="card__note">interval excludes zero</div>
        </div>
        <div className="card">
          <div className="card__label">Unresolved</div>
          <div className="card__value">{unresolved}</div>
          <div className="card__note">measured, and not separated from zero</div>
        </div>
        <div className="card">
          <div className="card__label">Scenarios that failed</div>
          <div className="card__value">{lab.n_failed}</div>
          <div className="card__note">recorded rather than substituted</div>
        </div>
      </div>

      <section>
        <h3>NIFTY-50 market conditions</h3>
        <ComparisonTable
          rows={market}
          caption="Market scenarios compared against the baseline"
        />
      </section>

      {transaction.length ? (
        <section>
          <h3>Transaction conditions</h3>
          <ComparisonTable
            rows={transaction}
            caption="Transaction scenarios compared against the baseline"
          />
          <p className="muted small" style={{ marginTop: 8 }}>
            Every transaction figure comes from a declared synthetic development fixture.
            It exercises the pipeline and is not a measurement of any payments system.
          </p>
        </section>
      ) : null}

      <MoneyPanel money={lab.money} />

      <section className="boundary">
        <h3>How to read this</h3>
        <p style={{ margin: 0 }}>{lab.reading}</p>
        <p style={{ margin: '8px 0 0' }}>
          <Link href="/scenario?mode=research">
            View the assumptions, the intervals and the provenance →
          </Link>
        </p>
      </section>
    </>
  );
}

/* -- research ------------------------------------------------------------------------ */

function AssumptionList({ spec }: { spec: ScenarioSpecRecord }) {
  return (
    <dl className="claims__meta">
      <div>
        <dt>Baseline</dt>
        <dd>{spec.baseline_definition}</dd>
      </div>
      <div>
        <dt>Assumption</dt>
        <dd>
          {spec.intervention_assumption ||
            'none — this is the reference the others are measured against'}
        </dd>
      </div>
      <div>
        <dt>Method</dt>
        <dd>{METHOD_COPY[spec.simulation_method]?.meaning ?? spec.simulation_method}</dd>
      </div>
      <div>
        <dt>Affected features</dt>
        <dd className="mono small">{spec.affected_features.join(', ') || '—'}</dd>
      </div>
      <div>
        <dt>Expected effect</dt>
        <dd>{spec.expected_effect}</dd>
      </div>
      <div>
        <dt>Stated assumptions</dt>
        <dd>
          {spec.assumptions.length ? (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {spec.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          ) : (
            'none'
          )}
        </dd>
      </div>
      <div>
        <dt>Constraints</dt>
        <dd>
          {spec.constraints.length ? (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {spec.constraints.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : (
            'none'
          )}
        </dd>
      </div>
      <div>
        <dt>Condition seed</dt>
        <dd className="mono small">{spec.random_seed}</dd>
      </div>
    </dl>
  );
}

function UncertaintyTable({ rows }: { rows: ScenarioUncertaintyRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Scenario</th>
            <th>Headline quantity</th>
            <th className="num">Estimate</th>
            <th className="num">95% interval</th>
            <th className="num">p</th>
            <th>Decided by</th>
            <th className="num">Assumptions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((u) => {
            const sep = separatedFromZero(u.ci_low, u.ci_high);
            return (
              <tr key={`${u.family}-${u.scenario_id}`}>
                <td className="mono">{u.scenario_id}</td>
                <td className="small">{u.headline_metric}</td>
                <td className="num">
                  {u.estimate === null ? '—' : u.estimate.toFixed(5)}
                </td>
                <td className="num">
                  {u.ci_low === null || u.ci_high === null ? (
                    <span className="muted">none</span>
                  ) : (
                    `${u.ci_low.toFixed(5)} to ${u.ci_high.toFixed(5)}`
                  )}
                </td>
                <td className="num">
                  {u.p_value === null ? '—' : u.p_value.toFixed(4)}
                </td>
                <td className="small muted">{u.interval_method ?? '—'}</td>
                <td className="num">
                  {u.n_assumptions}
                  {sep === false ? (
                    <span className="chip chip--warn" style={{ marginLeft: 6 }}>
                      unresolved
                    </span>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ResearchLab({
  lab,
  market,
  transaction,
}: {
  lab: Lab;
  market: ScenarioComparisonRow[];
  transaction: ScenarioComparisonRow[];
}) {
  return (
    <>
      <section className="module__lead">
        <h2 className="module__question">
          Under what stated conditions, and with what uncertainty?
        </h2>
        <p>
          Every scenario is executed by the same fitting harness, the same perturbation
          primitives, the same exposure policy and the same bootstrap machinery the
          headline results use. The model is fitted once on the clean training split and
          scores every condition, so a scenario isolates a change in conditions rather
          than letting the model adapt to one.
        </p>
        <p className="muted small">
          Scenario version <span className="mono">{lab.scenario_version}</span> · run{' '}
          <span className="mono">{lab.run_at ?? 'not recorded'}</span> · commit{' '}
          <span className="mono">{lab.git_commit?.slice(0, 8) ?? 'n/a'}</span> · seeds{' '}
          <span className="mono">{lab.seeds.join(', ') || 'not recorded'}</span> ·{' '}
          <Link href="/scenario?mode=product">See the product view →</Link>
        </p>
      </section>

      <section>
        <h3>Uncertainty around every difference</h3>
        <UncertaintyTable rows={lab.uncertainty} />
      </section>

      <section>
        <h3>Market comparison</h3>
        <ComparisonTable rows={market} caption="Market scenarios" />
      </section>

      {transaction.length ? (
        <section>
          <h3>Transaction comparison</h3>
          <ComparisonTable rows={transaction} caption="Transaction scenarios" />
        </section>
      ) : null}

      <MoneyPanel money={lab.money} />

      <section>
        <h3>Every scenario, with the assumption it rests on</h3>
        <div className="claims">
          {lab.catalogue.map((spec) => (
            <article key={`${spec.family}-${spec.scenario_id}`} className="claims__item">
              <div className="claims__head">
                <span className="mono">{spec.scenario_id}</span>
                <span className="chip">{spec.family}</span>
                <MethodBadge method={spec.simulation_method} />
                {spec.is_baseline ? <span className="chip">baseline</span> : null}
              </div>
              <p className="claims__text">{spec.name}</p>
              <AssumptionList spec={spec} />
              {spec.note ? <p className="muted small">{spec.note}</p> : null}
            </article>
          ))}
        </div>
      </section>

      {lab.problems.length ? (
        <section className="boundary">
          <h3>Problems reported by the run</h3>
          <ul>
            {lab.problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="boundary">
        <h3>What a scenario is not</h3>
        <p style={{ margin: 0 }}>
          A counterfactual simulation is not causal inference. These results say what a
          fitted model would have estimated under a stated assumption; establishing what
          would have happened in the world additionally requires an identification
          strategy, and none of these has one. That boundary is registered as limitation{' '}
          <Link href="/research/limitations/L-24">L-24</Link>.
        </p>
      </section>
    </>
  );
}
