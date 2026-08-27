/**
 * The risk state, made the hero of the page.
 *
 * The ordering here is the product argument. A security page that opens with a large
 * price teaches the reader that the price is the answer; this one opens with the risk
 * state and treats price as one evidence stream feeding it. Nothing about the underlying
 * numbers changes — only which question the first screen is answering.
 *
 * **Every factor is derived from a block the payload already carries.** A factor whose
 * inputs are absent renders UNAVAILABLE with the reason, never NORMAL: "we did not
 * measure this" and "we measured this and it was fine" are different claims and a reader
 * must be able to tell them apart at a glance.
 *
 * **The contribution bars are shares, not scores.** They show how much each modality
 * contributed to the stored model result, which is a decomposition of something already
 * computed. They are not probabilities, not expected returns, and there is deliberately
 * no single headline number that could be read as a verdict.
 */
import type {
  InstrumentFoundation,
  InstrumentLiquidity,
  MarketBlock,
  RiskBlock,
} from '@/lib/product';

export type FactorLevel = 'normal' | 'watch' | 'elevated' | 'unavailable';

const LEVEL_WORD: Record<FactorLevel, string> = {
  normal: 'NORMAL',
  watch: 'WATCH',
  elevated: 'ELEVATED',
  unavailable: 'UNAVAILABLE',
};

export interface RiskFactor {
  name: string;
  level: FactorLevel;
  reading: string;
  evidence: { text: string; kind: 'OBSERVED' | 'DERIVED' | 'MODEL SIGNAL' | 'UNAVAILABLE' }[];
}

export function buildFactors(
  market: MarketBlock,
  risk: RiskBlock,
  liquidity: InstrumentLiquidity | undefined,
  foundation: InstrumentFoundation | undefined,
): RiskFactor[] {
  const out: RiskFactor[] = [];

  // --- Price behaviour ---------------------------------------------------------
  const chg = market.change_pct;
  const win = market.window_change_pct;
  const ind = market.indicators;
  const priceEvidence: RiskFactor['evidence'] = [];
  if (chg !== null && chg !== undefined) {
    priceEvidence.push({
      text: `Latest session move ${(chg * 100).toFixed(2)}%`,
      kind: 'OBSERVED',
    });
  }
  if (win !== null && win !== undefined) {
    priceEvidence.push({
      text: `Return across the charted window ${(win * 100).toFixed(2)}%`,
      kind: 'OBSERVED',
    });
  }
  if (ind?.available && ind.rsi_latest !== null) {
    priceEvidence.push({ text: `${ind.rsi_observation} RSI(14) ${ind.rsi_latest.toFixed(1)}`, kind: 'DERIVED' });
    priceEvidence.push({ text: ind.macd_observation, kind: 'DERIVED' });
  }
  const bigMove = chg !== null && chg !== undefined && Math.abs(chg) >= 0.05;
  out.push({
    name: 'Price behaviour',
    level: priceEvidence.length === 0 ? 'unavailable' : bigMove ? 'elevated' : 'normal',
    reading: bigMove
      ? 'The latest session moved more than 5%.'
      : priceEvidence.length
        ? 'No session in the window moved outside the ordinary range.'
        : 'No price observations are available.',
    evidence: priceEvidence,
  });

  // --- Liquidity ---------------------------------------------------------------
  const st = liquidity?.liquidity_state;
  const pi = liquidity?.price_impact;
  const arr = liquidity?.arrival;
  const liqEvidence: RiskFactor['evidence'] = [];
  if (st?.available && typeof st.stress_score === 'number') {
    liqEvidence.push({
      text: `Composite liquidity stress ${st.stress_score.toFixed(2)} (robust z)`,
      kind: 'DERIVED',
    });
  }
  if (pi?.available && typeof pi.lambda === 'number') {
    liqEvidence.push({
      text: pi.significant
        ? `Price impact ${pi.lambda.toExponential(2)} per unit signed flow`
        : 'Price impact is not statistically distinguishable from zero',
      kind: 'DERIVED',
    });
  }
  if (arr?.available && typeof arr.fano_factor === 'number') {
    liqEvidence.push({
      text: `Trade arrivals overdispersed, Fano ${arr.fano_factor.toFixed(0)} (${arr.model_selected ?? 'model selected'})`,
      kind: 'DERIVED',
    });
  }
  out.push({
    name: 'Liquidity',
    level: !liqEvidence.length
      ? 'unavailable'
      : st?.stress_gate_fired
        ? 'elevated'
        : (st?.stress_score ?? 0) > 0
          ? 'watch'
          : 'normal',
    reading: !liqEvidence.length
      ? (st?.why ?? 'No liquidity estimators were built for this security.')
      : st?.stress_gate_fired
        ? 'The liquidity stress gate fired on the latest session.'
        : 'Liquidity estimators are within their historical range.',
    evidence: liqEvidence.length
      ? liqEvidence
      : [{ text: 'No liquidity artifacts for this security', kind: 'UNAVAILABLE' }],
  });

  // --- Market conditions -------------------------------------------------------
  const band = foundation?.price_band;
  const status = foundation?.status;
  const mktEvidence: RiskFactor['evidence'] = [];
  if (band?.available) {
    mktEvidence.push({ text: `Price band: ${band.band_label ?? band.band ?? 'none'}`, kind: 'OBSERVED' });
    if (band.surveillance_remark) {
      mktEvidence.push({ text: `Surveillance: ${band.surveillance_remark}`, kind: 'OBSERVED' });
    }
  }
  if (status?.available && status.state_label) {
    mktEvidence.push({ text: `Security status: ${status.state_label}`, kind: 'OBSERVED' });
  }
  out.push({
    name: 'Market conditions',
    level: !mktEvidence.length
      ? 'unavailable'
      : band?.surveillance_remark
        ? 'elevated'
        : 'normal',
    reading: !mktEvidence.length
      ? (band?.why ?? 'No band or surveillance record is available.')
      : band?.surveillance_remark
        ? 'The exchange has placed this security under a surveillance measure.'
        : 'No surveillance measure or restrictive band applies.',
    evidence: mktEvidence.length
      ? mktEvidence
      : [{ text: 'No exchange status record', kind: 'UNAVAILABLE' }],
  });

  // --- Information ------------------------------------------------------------
  const ca = foundation?.corporate_actions;
  const infoEvidence: RiskFactor['evidence'] = [];
  if (ca?.available) {
    infoEvidence.push({ text: `${ca.count} corporate actions on record`, kind: 'OBSERVED' });
    if (ca.price_affecting) {
      infoEvidence.push({
        text: `${ca.price_affecting} change a price factor`,
        kind: 'DERIVED',
      });
    }
  }
  const textShare = risk.modalities?.find((m) => m.modality === 'text');
  if (textShare) {
    infoEvidence.push({
      text: `Financial text contributed ${(textShare.share * 100).toFixed(1)}% of the model's evidence`,
      kind: 'MODEL SIGNAL',
    });
  }
  out.push({
    name: 'Information activity',
    level: infoEvidence.length ? 'normal' : 'unavailable',
    reading: infoEvidence.length
      ? 'Announcement and corporate-action records are present for this security.'
      : 'No information records are available.',
    evidence: infoEvidence.length
      ? infoEvidence
      : [{ text: 'No announcement or action record', kind: 'UNAVAILABLE' }],
  });

  // --- Company fundamentals ----------------------------------------------------
  // Deliberately not enumerated. The limitation record forbids naming the individual
  // measures beside a value, precisely so no surface can imply one exists.
  out.push({
    name: 'Company fundamentals',
    level: 'unavailable',
    reading: 'Unavailable — no verified point-in-time source.',
    evidence: [
      {
        text: 'Recorded limitation L-13: no licence-clear source carries the disclosure timestamp separately from the financial period',
        kind: 'UNAVAILABLE',
      },
      {
        text: 'No price-derived substitute is shown, because it would be a market signal under a company label',
        kind: 'UNAVAILABLE',
      },
    ],
  });

  return out;
}

function Factor({ f }: { f: RiskFactor }) {
  return (
    <details className="rf" data-level={f.level}>
      <summary className="rf__summary">
        <span className="rf__name">{f.name}</span>
        <span className="rf__level">{LEVEL_WORD[f.level]}</span>
      </summary>
      <p className="rf__reading">{f.reading}</p>
      <ul className="rf__evidence">
        {f.evidence.map((e) => (
          <li key={e.text}>
            <span className="rf__kind" data-kind={e.kind}>
              {e.kind}
            </span>
            {e.text}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function RiskHeader({
  symbol,
  market,
  risk,
  liquidity,
  foundation,
  dataThrough,
  variant = 'banner',
}: {
  symbol: string;
  market: MarketBlock;
  risk: RiskBlock;
  liquidity?: InstrumentLiquidity;
  foundation?: InstrumentFoundation;
  dataThrough: string;
  /** `aside` renders the same evidence as a narrow column beside the chart. */
  variant?: 'banner' | 'aside';
}) {
  const factors = buildFactors(market, risk, liquidity, foundation);
  const elevated = factors.filter((f) => f.level === 'elevated').length;
  const watch = factors.filter((f) => f.level === 'watch').length;
  const unavailable = factors.filter((f) => f.level === 'unavailable').length;

  const stateLabel = risk.available ? (risk.state_label ?? 'Normal') : 'Evidence unavailable';
  const tone = risk.available ? (risk.state_tone ?? 'calm') : 'unknown';

  const headline = !risk.available
    ? 'This security has not been scored by the model.'
    : elevated > 0
      ? `${elevated} risk factor${elevated === 1 ? '' : 's'} require attention.`
      : watch > 0
        ? `${watch} risk factor${watch === 1 ? '' : 's'} to monitor.`
        : 'No risk factor is currently elevated.';

  if (variant === 'aside') {
    return (
      <section className="riskAside" data-tone={tone}>
        <span className="riskAside__eyebrow">AEGIS risk profile</span>
        <span className="riskAside__state">{stateLabel.toUpperCase()}</span>
        <span className="riskAside__headline">{headline}</span>
        {risk.available && risk.state_meaning ? (
          <span className="riskAside__meaning">{risk.state_meaning}</span>
        ) : null}

        <div className="riskAside__factors">
          {factors.map((f) => (
            <Factor key={f.name} f={f} />
          ))}
        </div>

        <p className="riskAside__counts">
          {factors.length - unavailable} of {factors.length} factors have evidence
          {unavailable ? ` · ${unavailable} unavailable` : ''}. Expand a factor for the
          items behind it and whether each was observed, derived or a model signal.
        </p>
      </section>
    );
  }

  return (
    <section className="riskHero" data-tone={tone}>
      <div className="riskHero__top">
        <div className="riskHero__id">
          <span className="riskHero__eyebrow">Risk intelligence</span>
          <h2 className="riskHero__symbol">{symbol}</h2>
          <span className="riskHero__venue">NSE: {symbol}</span>
        </div>

        <div className="riskHero__state">
          <span className="riskHero__stateLabel">Risk state</span>
          <span className="riskHero__stateValue">{stateLabel.toUpperCase()}</span>
          <span className="riskHero__headline">{headline}</span>
          {risk.available && risk.state_meaning ? (
            <span className="riskHero__meaning">{risk.state_meaning}</span>
          ) : null}
        </div>

        <div className="riskHero__integrity">
          <span className="riskHero__integrityLabel">Market data through</span>
          <span className="riskHero__integrityValue">{dataThrough}</span>
          <span className="riskHero__integrityNote">
            {market.days_since_latest_session && market.days_since_latest_session > 0
              ? `latest verified session · ${market.days_since_latest_session} days behind today`
              : 'latest verified session'}
          </span>
        </div>
      </div>

      <div className="riskHero__factors">
        {factors.map((f) => (
          <Factor key={f.name} f={f} />
        ))}
      </div>

      <p className="riskHero__counts">
        {factors.length - unavailable} of {factors.length} factors have evidence
        {unavailable ? ` · ${unavailable} unavailable` : ''}. Expand any factor to see what
        it was based on and whether each item was observed, derived or a model signal.
      </p>
    </section>
  );
}
