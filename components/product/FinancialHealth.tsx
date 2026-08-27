/**
 * Financial health — rendered as the absence it is.
 *
 * A risk platform without company fundamentals has a real hole in it, and the honest way
 * to show a hole is to draw it rather than to fill it. This component exists so the
 * section appears in the page's information architecture, states plainly that the data is
 * not available, and says why and what it would take to change that.
 *
 * The alternative — deriving a revenue or leverage proxy from prices — is specifically
 * ruled out by the project's own limitation record: a price-derived stand-in for a
 * fundamental is a market signal wearing a fundamental label, and it would leak
 * look-ahead unless every figure carried its disclosure timestamp separately from its
 * financial period. No licence-clear source with that property was located.
 *
 * The metric names themselves are not written here. The limitation registry lists them as
 * forbidden phrasings precisely so that no surface can print them beside a number and
 * imply one exists.
 */
export function FinancialHealth({ limitationId = 'L-13' }: { limitationId?: string }) {
  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        <h2>Financial health</h2>
        <span className="home__asof">not available</span>
      </div>

      <div className="notAvailable">
        <p className="notAvailable__headline">
          Company fundamentals are <strong>not available</strong> in this system.
        </p>
        <p className="notAvailable__body">
          Point-in-time company financials with disclosure timestamps are required to use
          them without look-ahead: applying a quarter&rsquo;s figures from the quarter end
          rather than the filing date leaks weeks of future information into every
          historical decision. No licence-clear source carrying that property was located,
          so the block is absent rather than approximated.
        </p>
        <p className="notAvailable__body">
          No price-derived substitute is shown. A proxy built from market data would be a
          market signal presented under a financial label, which would misstate what the
          evidence is.
        </p>
        <dl className="notAvailable__meta">
          <div>
            <dt>Status</dt>
            <dd>NOT MEASURED</dd>
          </div>
          <div>
            <dt>Recorded limitation</dt>
            <dd>{limitationId}</dd>
          </div>
          <div>
            <dt>What would close it</dt>
            <dd>
              A licensed point-in-time fundamentals feed carrying the disclosure timestamp
              separately from the financial period.
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
