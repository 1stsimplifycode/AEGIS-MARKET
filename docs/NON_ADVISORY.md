# Non-advisory policy

AEGIS-Market provides research-oriented market-integrity risk analysis and does not provide
financial advice or recommendations to buy, sell, or hold securities.

That sentence is not decoration. It is the exact string asserted by
`tests/unit/test_non_advisory.py`, which also scans the entire product surface for advisory
language on every test run.

## What the system communicates

Integrity risk · risk state · evidence · uncertainty · coverage · temporal risk window ·
propagation · resolution · explanation · research consequence.

## What it never communicates

Buy, sell or hold instructions · target prices · expected profit · best or worst
instruments · personalised allocation · portfolio construction · order routing · anything
that reads as a transaction instruction.

## How the prohibition is enforced

**1. The output contract has no actionable field.** `RiskAssessment` in
`research/core/contracts.py` carries `integrity_risk`, `uncertainty`, `coverage`,
`risk_state`, `regime`, evidence, affect, propagation and explanation. A test asserts the
absence of `action`, `signal`, `recommendation`, `weight`, `allocation`, `target_price`,
`position` and `order`.

**2. The surface is scanned, not reviewed.** A regex sweep over `app/`, `components/` and
`lib/` fails the build on advisory vocabulary. Word boundaries are used so legitimate
domain vocabulary survives — "buyback" is a corporate action and passes; "buy" does not.

**3. The notice is inherited, not copy-pasted.** It renders once in the root layout. The
test verifies the root layout renders it *and* that no nested layout introduces its own
`<html>` element that would bypass it.

**4. The exposure gate is quarantined.** `research/risk/gate.py` implements a hypothetical
research exposure policy used solely to measure whether integrity-risk information would
have changed tail outcomes. It is not exposed to any product surface, its output carries a
disclaimer field, and a test asserts both.

## Why the gate is not advice

The gate exists to answer one measurement question: *under a fixed, pre-declared policy,
does capping exposure by integrity risk change tail loss?* It is a control-versus-treatment
comparison on historical data. Specifically:

- the base policy is equal-weight, which embeds no view about any instrument;
- released capital is **not** redeployed, precisely so the comparison does not become an
  allocation strategy;
- control and treatment differ in exactly one thing — whether the cap is applied;
- outputs are tail statistics (CVaR, drawdown, turnover, cost, opportunity cost), not
  positions;
- the cap is monotone non-increasing in risk, a property verified over a dense grid.

None of that is a recommendation to anyone, and the reported figures are not achievable
returns.

## Language discipline in the research modules

The research modules legitimately use words like "exposure" and "weight" because they
implement the measurement above. What is forbidden is a *user-facing instruction*. The
scan therefore targets the product surface and the output contract, and separately asserts
that the gate module declares itself non-advisory.

## On affect and manipulation

Emotion is not manipulation. Sentiment is not manipulation. Hype is not manipulation.
Volatility is not manipulation. Affective dimensions are observable properties of evidence
to be weighed alongside market and structural signals. The system reports what the evidence
shows and never infers an author's or speaker's hidden mental state.
