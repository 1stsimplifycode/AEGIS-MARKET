/**
 * Recent exchange events for one issuer: announcements and corporate actions, merged.
 *
 * The point of this panel is the question "what happened recently, and when exactly" —
 * which the rest of the page cannot answer without the reader hunting. So each row leads
 * with its date, and where the corporate-announcements feed supplied a dissemination
 * instant, the time is shown to the minute beside it. Where it did not, the row says the
 * time is unavailable rather than quietly showing the session date as though it were one.
 *
 * **No impact badge.** Nothing in this project scores an individual announcement, so
 * nothing here labels one as material, positive or negative. A coloured chip would be a
 * claim the system cannot support, and it is the sort of claim a reader would carry away
 * from the page whether or not the rest of it was hedged.
 *
 * Corporate actions do carry a status, because that one is computed: a price factor was
 * either reconciled against the panel's own returns or it was not, and CONFIRMED versus
 * NO_PRICE_EFFECT is the outcome of that check.
 */
import type { CorporateActionContext } from '@/lib/product';

export interface AnnouncementItem {
  session: string;
  subject: string | null;
  title: string;
  title_from_body: boolean;
  layout: string;
  body: string;
  disseminated_at: string | null;
  publication_time_available: boolean;
  source: string;
}

export interface AnnouncementsBlock {
  available: boolean;
  why?: string;
  count?: number;
  total_for_symbol?: number;
  items?: AnnouncementItem[];
  corpus_coverage?: string;
  basis?: string;
  impact_scored?: boolean;
  impact_note?: string;
}

function timeOf(iso: string | null): string | null {
  if (!iso) return null;
  const m = iso.match(/\d{2}:\d{2}/);
  return m ? m[0] : null;
}

export function EventFeed({
  announcements,
  corporateActions,
  windowFrom,
}: {
  announcements?: AnnouncementsBlock;
  corporateActions?: CorporateActionContext;
  windowFrom?: string | null;
}) {
  const items = announcements?.items ?? [];
  const actions = (corporateActions?.actions ?? []).slice(0, 8);

  return (
    <section className="instrument__block">
      <div className="home__sectionHead">
        <h2>Recent exchange events</h2>
        <span className="home__asof">
          {announcements?.available
            ? `${items.length} of ${announcements.total_for_symbol} announcements`
            : 'announcements not available'}
        </span>
      </div>

      <div className="eventFeed">
        <div className="eventFeed__col">
          <h3 className="eventFeed__title">Announcements</h3>
          {announcements?.available && items.length ? (
            <>
              <ol className="eventFeed__list">
                {items.slice(0, 12).map((it, i) => (
                  <li className="eventFeed__item" key={`${it.session}-${i}`}>
                    <div className="eventFeed__when">
                      <span className="eventFeed__date">{it.session}</span>
                      <span className="eventFeed__time">
                        {it.publication_time_available
                          ? `${timeOf(it.disseminated_at)} IST`
                          : 'time not published'}
                      </span>
                    </div>
                    <div className="eventFeed__what">
                      <p className="eventFeed__headline">{it.title}</p>
                      <span className="eventFeed__meta">
                        {it.source}
                        {it.title_from_body ? ' · title taken from the body text' : ''}
                      </span>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="eventFeed__note">
                {announcements.impact_note}
                {announcements.corpus_coverage
                  ? ` Corpus covers ${announcements.corpus_coverage}.`
                  : ''}
              </p>
            </>
          ) : (
            <p className="small muted">
              {announcements?.why ?? 'No announcement corpus is available.'}
            </p>
          )}
        </div>

        <div className="eventFeed__col">
          <h3 className="eventFeed__title">Corporate actions</h3>
          {corporateActions?.available && actions.length ? (
            <>
              <table className="eventFeed__table">
                <thead>
                  <tr>
                    <th>Ex-date</th>
                    <th>Action</th>
                    <th>Factor</th>
                    <th>Reconciliation</th>
                  </tr>
                </thead>
                <tbody>
                  {actions.map((a) => (
                    <tr key={`${a.ex_date}-${a.action_type}`}>
                      <td>
                        {a.ex_date}
                        {windowFrom && a.ex_date >= windowFrom ? (
                          <span className="eventFeed__inWindow" title="Falls inside the charted window">
                            {' '}
                            •
                          </span>
                        ) : null}
                      </td>
                      <td>
                        <span className="eventFeed__type">{a.action_type}</span>
                        <span className="eventFeed__subject">{a.subject}</span>
                      </td>
                      <td className="num">
                        {a.price_factor !== null ? a.price_factor.toFixed(4) : '—'}
                      </td>
                      <td>
                        <span className="eventFeed__status" data-status={a.status}>
                          {a.status.replace(/_/g, ' ').toLowerCase()}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="eventFeed__note">
                {corporateActions.count} action{corporateActions.count === 1 ? '' : 's'} on
                record, {corporateActions.price_affecting} of which change a price factor.
                A dot marks an ex-date inside the charted window.
              </p>
            </>
          ) : (
            <p className="small muted">
              {corporateActions?.why ?? 'No corporate actions on record.'}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
