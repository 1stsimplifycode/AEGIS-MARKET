/**
 * A section of the product that this demonstration has not reached yet.
 *
 * A server component, deliberately. The card is rendered in place of a section whose data
 * was never read, so there is nothing here for a client to be given and nothing to
 * un-hide: the result it stands in for did not leave the server.
 *
 * The wording is the same distinction the rest of the gate carries. This analysis is
 * finished and covered by tests; the demonstration simply starts earlier in the
 * programme. It is not missing, not unimplemented, and not broken — and it is also not
 * "no data", which is a different state with a different cause and its own honest label.
 */
export function LockedSection({
  title,
  week,
  summary,
}: {
  title: string;
  /** The week this capability joins the demonstration, from the manifest. */
  week: number | null;
  summary?: string;
}) {
  return (
    <section className="home__section">
      <div className="home__sectionHead">
        <h2>{title}</h2>
      </div>
      <div className="lockedSection">
        <p className="lockedSection__head">
          <span className="lockedSection__lock" aria-hidden="true">
            🔒
          </span>
          Coming soon
        </p>
        <p className="lockedSection__text">
          {week === null
            ? 'This analysis becomes available later in the capstone progression.'
            : `This analysis becomes available in week ${week} of the capstone progression.`}
        </p>
        {summary ? <p className="lockedSection__summary">{summary}</p> : null}
        <p className="lockedSection__research modeOnly modeOnly--research">
          Implemented in the complete system
          {week === null ? '' : `; enabled from week ${week}`}. Its result was not read for
          this request, so nothing of it is in this page.
        </p>
      </div>
    </section>
  );
}
