'use client';

/**
 * The funds ledger, and the two simulated movements a reader can make.
 *
 * Deposit and withdraw go to the backend, write a ledger entry with a running balance, and
 * are audited like every other state change. They are labelled simulated at every step —
 * the word appears on the control, in the response and in the ledger row — because a
 * funding button is exactly the kind of thing someone could mistake for real.
 */
import { useCallback, useEffect, useState } from 'react';

interface Entry {
  entry_id: string;
  at: string;
  kind: string;
  amount: number;
  balance: number;
  blocked: number;
  reference: string | null;
  reason: string;
}

interface State {
  available: number;
  blocked: number;
  total: number;
  note: string;
  ledger?: Entry[];
}

const money = (n: number) =>
  `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

export function FundsPanel() {
  const [state, setState] = useState<State | null>(null);
  const [amount, setAmount] = useState('50000');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/aegis/funds', { cache: 'no-store' });
      const payload = await response.json();
      if (payload?.error) setError(payload.error.reason);
      else setState(payload as State);
    } catch {
      setError('The analysis backend did not answer, so funds are unavailable.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const adjust = useCallback(
    async (kind: 'DEPOSIT' | 'WITHDRAWAL') => {
      setBusy(true);
      setError(null);
      try {
        const response = await fetch('/api/aegis/funds/adjust', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            kind,
            amount: Number(amount),
            reason: `Simulated ${kind.toLowerCase()} from the funds page.`,
          }),
        });
        const payload = await response.json();
        if (payload?.error) setError(payload.error.reason);
        await load();
      } catch {
        setError('The analysis backend did not answer, so nothing changed.');
      } finally {
        setBusy(false);
      }
    },
    [amount, load],
  );

  if (!state && !error) return <p className="small muted">Loading funds…</p>;

  return (
    <>
      {error ? (
        <p className="orderBook__error" role="status">
          {error}
        </p>
      ) : null}

      {state ? (
        <>
          <div className="cardRow">
            <article className="tile">
              <span className="tile__label">Available</span>
              <span className="tile__value">{money(state.available)}</span>
              <span className="tile__note">simulated</span>
            </article>
            <article className="tile">
              <span className="tile__label">Blocked as margin</span>
              <span className="tile__value">{money(state.blocked)}</span>
              <span className="tile__note">against open orders</span>
            </article>
            <article className="tile">
              <span className="tile__label">Total</span>
              <span className="tile__value">{money(state.total)}</span>
            </article>
          </div>

          <section className="home__section">
            <h2>Simulated funding</h2>
            <div className="ticket__actions">
              <label className="field field--inline">
                <span>Amount</span>
                <input
                  value={amount}
                  inputMode="decimal"
                  onChange={(e) => setAmount(e.target.value)}
                  aria-label="Amount"
                />
              </label>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void adjust('DEPOSIT')}
                disabled={busy}
              >
                Add simulated funds
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => void adjust('WITHDRAWAL')}
                disabled={busy}
              >
                Withdraw
              </button>
            </div>
            <p className="home__caveat">{state.note}</p>
          </section>

          {state.ledger?.length ? (
            <section className="home__section">
              <h2>Ledger</h2>
              <div className="tableWrap">
                <table className="dense">
                  <thead>
                    <tr>
                      <th scope="col">When</th>
                      <th scope="col">Kind</th>
                      <th scope="col">Amount</th>
                      <th scope="col">Balance</th>
                      <th scope="col">Blocked</th>
                      <th scope="col">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.ledger.map((e) => (
                      <tr key={e.entry_id}>
                        <td className="mono small">{e.at}</td>
                        <td className="mono small">{e.kind}</td>
                        <td className="num mono" data-sign={e.amount >= 0}>
                          {e.amount.toFixed(2)}
                        </td>
                        <td className="num mono">{e.balance.toFixed(2)}</td>
                        <td className="num mono">{e.blocked.toFixed(2)}</td>
                        <td className="small">{e.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </>
  );
}
