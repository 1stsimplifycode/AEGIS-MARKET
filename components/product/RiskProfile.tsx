/**
 * The risk-dimension strip and the evidence balance beneath it.
 *
 * Both are assembled from blocks the payload already carries — the scored risk state,
 * the Week 2 liquidity estimators, the Week 1 foundation. Nothing is computed here and no
 * dimension is invented: a dimension whose inputs are missing renders as INSUFFICIENT
 * EVIDENCE, which is a different statement from "low risk" and is kept visibly different.
 *
 * **Colour is a state, not an instruction.** Amber means an indicator is mixed or worth
 * monitoring; red means one is deteriorating; grey means there is not enough to say. None
 * of them means anything about what a reader should do, and every one is accompanied by
 * the word for the state so the page is readable without relying on colour at all.
 *
 * **The balance section is not a verdict.** It lists what the evidence supports on one
 * side, what it counts against on the other, and what remains unresolved — then stops.
 * There is deliberately no aggregate score: a single headline number invites being read
 * as a verdict whatever it is labelled, which is the reading this project refuses.
 */
import type { InstrumentLiquidity, MarketBlock, RiskBlock } from '@/lib/product';

type State = 'improving' | 'monitor' | 'deteriorating' | 'unknown';

const STATE_WORD: Record<State, string> = {
  improving: 'IMPROVING',
  monitor: 'MONITOR',
  deteriorating: 'DETERIORATING',
  unknown: 'INSUFFICIENT EVIDENCE',
};

interface Dimension {
  name: string;
  state: State;
  reading: string;
  evidence: string[];
  asOf?: string | null;
}

function Row({ d }: { d: Dimension }) {
  return (
    <article className="riskDim" data-state={d.state}>
      <div className="riskDim__head">
        <span className="riskDim__name">{d.name}</span>
        <span className="riskDim__state">{STATE_WORD[d.state]}</span>
      </div>
      <p className="riskDim__reading">{d.reading}</p>
      {d.evidence.length ? (
        <ul className="riskDim__evidence">
          {d.evidence.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      ) : null}
      {d.asOf ? <span className="riskDim__asOf">as of {d.asOf}</span> : null}
    </article>
  );
}

function buildDimensions(
  market: MarketBlock,
  risk: RiskBlock,
  liquidity: InstrumentLiquidity | undefined,
): Dimension[] {
  const out: Dimension[] = [];

  // Market/evidence state — the scored panel, when one exists for this symbol.
  if (risk.available && risk.state_label) {
    const tone = risk.state_tone;
    out.push({
      name: 'Evidence state',
      state: tone === 'calm' ? 'improving' : tone === 'high' ? 'deteriorating' : 'monitor',
      reading: risk.state_meaning ?? risk.state_label,
      evidence: [
        risk.sessions_scored ? `${risk.sessions_scored} sessions scored` : '',
        risk.uncertainty !== undefined
          ? `model uncertainty ${risk.uncertainty.toFixed(2)}`
          : '',
        risk.coverage !== undefined && risk.coverage !== null
          ? `evidence coverage ${(risk.coverage * 100).toFixed(0)}%`
          : '',
      ].filter(Boolean),
      asOf: risk.scored_to ?? null,
    });
  } else {
    out.push({
      name: 'Evidence state',
      state: 'unknown',
      reading: risk.why ?? 'This security has not been scored.',
      evidence: [],
    });
  }

  // Liquidity — Week 2 estimators, each rendered only when the artifact carries it.
  const state = liquidity?.liquidity_state;
  if (state?.available && typeof state.stress_score === 'number') {
    const s = state.stress_score;
    out.push({
      name: 'Liquidity',
      state: state.stress_gate_fired ? 'deteriorating' : s > 0 ? 'monitor' : 'improving',
      reading:
        state.stress_gate_fired === true
          ? 'The liquidity stress gate fired on the latest session.'
          : `Composite liquidity stress is ${s.toFixed(2)} in robust-z units.`,
      evidence: [
        state.sessions ? `${state.sessions} sessions in the state vector` : '',
        state.sessions_stressed !== undefined
          ? `${state.sessions_stressed} stressed sessions`
          : '',
        state.primary_driver ? `primary driver ${state.primary_driver}` : '',
      ].filter(Boolean),
      asOf: state.latest_session ?? null,
    });
  } else {
    out.push({
      name: 'Liquidity',
      state: 'unknown',
      reading: state?.why ?? 'No liquidity state vector was built for this security.',
      evidence: [],
    });
  }

  // Volatility — realised variance, when estimated.
  const rv = liquidity?.realised_variance;
  if (rv?.available && typeof rv.annualised_volatility === 'number') {
    out.push({
      name: 'Volatility',
      state: 'monitor',
      reading: `Realised volatility is ${(rv.annualised_volatility * 100).toFixed(1)}% annualised.`,
      evidence: [
        rv.sampling_minutes ? `sampled at ${rv.sampling_minutes} minutes` : '',
        rv.n_returns ? `${rv.n_returns} returns` : '',
        rv.relative_standard_error !== undefined
          ? `relative standard error ${(rv.relative_standard_error * 100).toFixed(1)}%`
          : '',
      ].filter(Boolean),
    });
  } else {
    out.push({
      name: 'Volatility',
      state: 'unknown',
      reading: rv?.why ?? 'Realised variance was not estimated for this security.',
      evidence: [],
    });
  }

  // Price impact — Kyle's lambda, only when the fit is significant enough to quote.
  const pi = liquidity?.price_impact;
  if (pi?.available && typeof pi.lambda === 'number') {
    out.push({
      name: 'Price impact',
      state: pi.significant ? 'monitor' : 'unknown',
      reading: pi.significant
        ? `Price moves ${pi.lambda.toExponential(2)} per unit of signed flow.`
        : 'The price-impact fit is not statistically distinguishable from zero.',
      evidence: [
        pi.n_obs ? `${pi.n_obs} observations` : '',
        pi.t_stat !== undefined ? `t = ${pi.t_stat.toFixed(2)}` : '',
        pi.r_squared !== undefined ? `R² = ${pi.r_squared.toFixed(3)}` : '',
      ].filter(Boolean),
    });
  } else {
    out.push({
      name: 'Price impact',
      state: 'unknown',
      reading: pi?.why ?? 'Price impact was not estimated for this security.',
      evidence: [],
    });
  }

  // Momentum — derived indicator, labelled as derived.
  const ind = market.indicators;
  if (ind?.available && ind.rsi_latest !== null) {
    out.push({
      name: 'Technical momentum',
      state: 'monitor',
      reading: `${ind.rsi_observation} RSI(14) is ${ind.rsi_latest.toFixed(1)}.`,
      evidence: [ind.macd_observation, 'derived from closing prices, not exchange-published'],
      asOf: market.latest_session ?? market.last_session,
    });
  } else {
    out.push({
      name: 'Technical momentum',
      state: 'unknown',
      reading: ind?.why_unavailable ?? 'Indicators are not available from this source.',
      evidence: [],
    });
  }

  return out;
}

export function RiskProfile({
  market,
  risk,
  liquidity,
}: {
  market: MarketBlock;
  risk: RiskBlock;
  liquidity?: InstrumentLiquidity;
}) {
  const dims = buildDimensions(market, risk, liquidity);
  const known = dims.filter((d) => d.state !== 'unknown');
  const deteriorating = dims.filter((d) => d.state === 'deteriorating');
  const improving = dims.filter((d) => d.state === 'improving');
  const unresolved = dims.filter((d) => d.state === 'unknown');

  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        <h2>Risk profile</h2>
        <span className="home__asof">
          {known.length} of {dims.length} dimensions have evidence
        </span>
      </div>

      <p className="riskProfile__legend">
        Colour describes the state of the evidence, not an action. Every state is written
        out in words so the page reads the same without colour.
      </p>

      <div className="riskProfile__grid">
        {dims.map((d) => (
          <Row key={d.name} d={d} />
        ))}
      </div>

      <div className="evidenceBalance">
        <h3 className="evidenceBalance__title">Evidence balance</h3>
        <div className="evidenceBalance__cols">
          <div>
            <span className="evidenceBalance__head">Supporting evidence</span>
            {improving.length ? (
              <ul>
                {improving.map((d) => (
                  <li key={d.name}>
                    <strong>{d.name}</strong> — {d.reading}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="small muted">No dimension is currently improving.</p>
            )}
          </div>
          <div>
            <span className="evidenceBalance__head">Risk evidence</span>
            {deteriorating.length ? (
              <ul>
                {deteriorating.map((d) => (
                  <li key={d.name}>
                    <strong>{d.name}</strong> — {d.reading}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="small muted">No dimension is currently deteriorating.</p>
            )}
          </div>
          <div>
            <span className="evidenceBalance__head">Unresolved</span>
            {unresolved.length ? (
              <ul>
                {unresolved.map((d) => (
                  <li key={d.name}>
                    <strong>{d.name}</strong> — {d.reading}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="small muted">Every dimension has evidence.</p>
            )}
          </div>
        </div>
        <p className="evidenceBalance__note">
          Company fundamentals are absent from every dimension above; see the financial
          health section for why. No aggregate score is produced from these dimensions —
          the reader weighs them.
        </p>
      </div>
    </section>
  );
}
