import type { InstrumentLiquidity } from '@/lib/product';

/**
 * The Week 2 liquidity estimators, as the instrument page shows them.
 *
 * Two rules, both because the alternative misleads:
 *
 * 1. Every estimate is shown with its uncertainty. A price-impact coefficient without its
 *    standard error invites a comparison between two securities that the data may not
 *    support, and the interval is what stops that.
 * 2. An estimator that could not be computed is rendered as "not available" with the
 *    reason. Silently omitting it reads as "nothing unusual here", which is a claim.
 */

function Sci({ value, digits = 2 }: { value: number; digits?: number }) {
  if (!Number.isFinite(value)) return <>—</>;
  const exp = Math.floor(Math.log10(Math.abs(value)));
  if (exp <= -4 || exp >= 5) {
    const mant = value / 10 ** exp;
    return (
      <>
        {mant.toFixed(digits)}×10<sup>{exp}</sup>
      </>
    );
  }
  return <>{value.toFixed(Math.max(0, digits - exp))}</>;
}

function Unavailable({ what, why }: { what: string; why?: string }) {
  return (
    <article className="tile tile--muted">
      <span className="tile__label">{what}</span>
      <span className="tile__value">Not available</span>
      <span className="tile__note">{why}</span>
    </article>
  );
}

export function Liquidity({ liquidity }: { liquidity?: InstrumentLiquidity }) {
  if (!liquidity) return null;
  const { realised_variance: rv, price_impact: pi, arrival, liquidity_state: state } =
    liquidity;

  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        <h2>How liquid this security is</h2>
        <span className="home__asof">Week 2 estimators, each with its uncertainty</span>
      </div>

      <div className="cardRow">
        {rv.available ? (
          <article className="tile">
            <span className="tile__label">Realised volatility</span>
            <span className="tile__value">
              {(rv.annualised_volatility! * 100).toFixed(1)}%
            </span>
            <span className="tile__note">
              Annualised, from {rv.n_returns} intraday returns sampled every{' '}
              {rv.sampling_minutes} min · ±
              {(rv.relative_standard_error! * 100).toFixed(0)}% relative
            </span>
          </article>
        ) : (
          <Unavailable what="Realised volatility" why={rv.why} />
        )}

        {pi.available ? (
          <article className="tile">
            <span className="tile__label">Price impact (λ)</span>
            <span className="tile__value">
              <Sci value={pi.lambda!} />
            </span>
            <span className="tile__note">
              ±<Sci value={pi.standard_error!} /> (t={pi.t_stat!.toFixed(1)},{' '}
              {pi.significant ? 'significant' : 'not significant'}) · n={pi.n_obs}
            </span>
          </article>
        ) : (
          <Unavailable what="Price impact" why={pi.why} />
        )}

        {arrival.available ? (
          <article className="tile">
            <span className="tile__label">Trade arrivals</span>
            <span className="tile__value">
              {Math.round(arrival.mean_daily_trades!).toLocaleString()}/day
            </span>
            <span className="tile__note">
              Dispersion {arrival.fano_factor!.toFixed(0)}× Poisson ·{' '}
              {arrival.model_selected === 'negative_binomial'
                ? 'arrivals cluster'
                : 'Poisson is adequate'}
            </span>
          </article>
        ) : (
          <Unavailable what="Trade arrivals" why={arrival.why} />
        )}

        {state.available ? (
          <article className={`tile ${state.stress_gate_fired ? 'tile--alert' : ''}`}>
            <span className="tile__label">Liquidity state</span>
            <span className="tile__value">
              {state.stress_gate_fired ? 'Stressed' : 'Ordinary'}
            </span>
            <span className="tile__note">
              Stress score {state.stress_score!.toFixed(2)} · {state.sessions_stressed} of{' '}
              {state.sessions} sessions stressed
            </span>
          </article>
        ) : (
          <Unavailable what="Liquidity state" why={state.why} />
        )}
      </div>

      {state.available && state.stress_gate_fired && state.attribution ? (
        <div className="tableWrap">
          <table className="dataTable">
            <caption>
              What drove the stress on {state.latest_session}. Each share is the
              component&rsquo;s own robust z-score as a fraction of the total, computed from
              the state vector rather than chosen as an explanation.
            </caption>
            <thead>
              <tr>
                <th scope="col">Estimator</th>
                <th scope="col">Value</th>
                <th scope="col">Robust z</th>
                <th scope="col">Share of stress</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(state.attribution)
                .sort((a, b) => b[1] - a[1])
                .map(([key, share]) => {
                  const c = state.components?.[key];
                  return (
                    <tr key={key}>
                      <td>{c?.label ?? key}</td>
                      <td>{c?.value != null ? <Sci value={c.value} /> : '—'}</td>
                      <td>{c?.robust_z != null ? c.robust_z.toFixed(2) : '—'}</td>
                      <td>{(share * 100).toFixed(0)}%</td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
      ) : null}

      {pi.available ? (
        <p className="instrument__note">
          Trade direction is not published by NSE. The signs behind λ are inferred by the
          tick test, which misclassifies some bars and pulls the coefficient toward zero
          &mdash; so this is a conservative estimate, and it is not an exchange statement
          about order flow.
        </p>
      ) : null}
    </section>
  );
}
