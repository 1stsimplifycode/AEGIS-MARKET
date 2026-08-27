import type { InstrumentFoundation } from '@/lib/product';

/**
 * The Week 1 market-intelligence foundation, as the instrument page shows it.
 *
 * Two rules govern everything here, and both exist because the alternative misleads:
 *
 * 1. An unavailable value is *rendered*, not hidden. "Circuit band — not available,
 *    because NSE publishes no historical band series" is information; an absent row
 *    reads as "there is nothing to say", which is a different and false claim.
 * 2. Every value carries its basis. A number NSE published and a number this project
 *    assumed look identical on a screen, so the difference is written next to them.
 */

function Basis({ value }: { value?: string }) {
  if (!value) return null;
  const exchange = value === 'EXCHANGE_PUBLISHED';
  return (
    <span className={`basis ${exchange ? 'basis--exchange' : 'basis--derived'}`}>
      {exchange ? 'Exchange-published' : value.replace(/_/g, ' ').toLowerCase()}
    </span>
  );
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

export function Foundation({ foundation }: { foundation?: InstrumentFoundation }) {
  if (!foundation) return null;
  const { status, price_band: band, corporate_actions: actions, point_in_time: pit } =
    foundation;

  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        <h2>What the exchange says about this security</h2>
        <span className="home__asof">Reference data, with its provenance</span>
      </div>

      <div className="cardRow">
        {status.available ? (
          <article className="tile">
            <span className="tile__label">Status</span>
            <span className="tile__value">{status.state_label}</span>
            <span className="tile__note">
              {status.meaning} <Basis value={status.basis} />
            </span>
          </article>
        ) : (
          <Unavailable what="Status" why={status.why} />
        )}

        {band.available ? (
          <article className="tile">
            <span className="tile__label">Circuit band</span>
            <span className="tile__value">{band.band_label}</span>
            <span className="tile__note">
              Series {band.series || '—'}
              {band.surveillance_remark ? ` · ${band.surveillance_remark}` : ''}{' '}
              <Basis value={band.basis} />
            </span>
          </article>
        ) : (
          <Unavailable what="Circuit band" why={band.why} />
        )}

        <article className="tile">
          <span className="tile__label">Listed since</span>
          <span className="tile__value">{status.listing_date ?? '—'}</span>
          <span className="tile__note">
            {status.listing_date
              ? <>NSE listing roster <Basis value="EXCHANGE_PUBLISHED" /></>
              : 'Not in the current listing roster.'}
          </span>
        </article>

        <article className="tile">
          <span className="tile__label">Corporate actions</span>
          <span className="tile__value">{actions.count ?? 0}</span>
          <span className="tile__note">
            {actions.price_affecting ?? 0} moved the quoted price{' '}
            <Basis value={actions.basis} />
          </span>
        </article>
      </div>

      {pit.available ? (
        <p className="instrument__pit">
          <strong>Point in time.</strong> {pit.explanation} {pit.visible_sessions} sessions
          were knowable at that instant
          {pit.withheld_by_knowledge_bound
            ? `, and ${pit.withheld_by_knowledge_bound} that had already happened were not, because their data was not published yet`
            : ''}
          . Read through <code>{pit.read_path}</code>.
        </p>
      ) : null}

      {actions.available && actions.actions && actions.actions.length > 0 ? (
        <div className="tableWrap">
          <table className="dataTable">
            <caption>
              Corporate actions NSE announced for this security. The price factor is the
              multiple by which the quoted price mechanically fell; a factor of 1 means the
              action did not move the price, which is the case for an ordinary dividend.
            </caption>
            <thead>
              <tr>
                <th scope="col">Ex-date</th>
                <th scope="col">Action</th>
                <th scope="col">Price factor</th>
                <th scope="col">Reconciliation</th>
              </tr>
            </thead>
            <tbody>
              {actions.actions.slice(0, 8).map((a) => (
                <tr key={`${a.ex_date}-${a.subject}`}>
                  <td>{a.ex_date}</td>
                  <td>{a.subject}</td>
                  <td>
                    {a.price_factor && Math.abs(a.price_factor - 1) > 1e-6
                      ? `×${a.price_factor.toFixed(2)}`
                      : '—'}
                  </td>
                  <td>{a.status.replace(/_/g, ' ').toLowerCase()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {status.available && !status.in_current_roster ? (
        <p className="instrument__note">
          This security is no longer in NSE&rsquo;s listing roster, and its history is kept
          rather than removed &mdash; that is what makes the universe survivorship-free.
          No delisting date is shown: {status.date_note}
        </p>
      ) : null}
    </section>
  );
}
