/**
 * The non-advisory notice (spec section 3).
 *
 * The exact wording is asserted by `tests/unit/test_non_advisory.py`, which also scans
 * every page for the presence of this component. Do not paraphrase it: the test compares
 * the string literally, and a paraphrase would silently disable the guarantee.
 */
export const NON_ADVISORY_TEXT =
  'AEGIS-Market provides research-oriented market-integrity risk analysis and ' +
  'does not provide financial advice or recommendations to buy, sell, or hold securities.';

export function NonAdvisoryNotice({ compact = false }: { compact?: boolean }) {
  return (
    <aside
      role="note"
      aria-label="Non-advisory notice"
      className={compact ? 'notice notice--compact' : 'notice'}
    >
      <div className="notice__inner">
        <span className="notice__badge">Research use only</span>
        <p className="notice__text">{NON_ADVISORY_TEXT}</p>
      </div>
    </aside>
  );
}

export default NonAdvisoryNotice;

/**
 * The canonical scope denial for the position-lifecycle surfaces.
 *
 * It has to name the things it rules out, or it says nothing a reader can check. But
 * naming them is exactly what the lifecycle scan in `tests/unit/test_non_advisory.py`
 * forbids, so the enumeration lives here once and the scan strips this literal string.
 * Any other occurrence of these words anywhere in the app is therefore a real finding.
 * Do not paraphrase it and do not inline it: a copy would trip the scan, and a
 * paraphrase would leave the scan with nothing to strip.
 */
export const LIFECYCLE_SCOPE_TEXT =
  'This framework is observational. It produces no entry price, exit price, target, ' +
  'position size or allocation, and none is derivable from it.';

export function LifecycleScopeNotice() {
  return (
    <aside role="note" aria-label="Lifecycle scope notice" className="notice notice--compact">
      <span className="notice__badge">Scope</span>
      <p className="notice__text">{LIFECYCLE_SCOPE_TEXT}</p>
    </aside>
  );
}
