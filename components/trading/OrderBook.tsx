'use client';

/**
 * The order book, and the two actions an open order still has.
 *
 * Fill and cancel go to the backend and come back with the order's new state; nothing is
 * decided here. A fill is what makes the lifecycle observable in a demonstration — there is
 * no exchange to fill an order, so somebody has to ask for it, and asking is honest in a
 * way that a timer quietly filling orders would not be.
 */
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

interface Order {
  order_id: string;
  symbol: string;
  side: string;
  quantity: number;
  filled: number;
  order_type: string;
  status: string;
  reference_price: number;
  reference_session: string;
  created_at: string;
  rejected_reason: string | null;
}

const OPEN_STATES = new Set(['OPEN', 'PARTIALLY_FILLED', 'ACCEPTED']);

export function OrderBook() {
  const [orders, setOrders] = useState<Order[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/aegis/orders', { cache: 'no-store' });
      const payload = await response.json();
      setOrders(payload.orders ?? []);
      setError(payload.orders ? null : (payload.error?.reason ?? 'No order book.'));
    } catch {
      setError('The analysis backend did not answer, so the order book is unavailable.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const act = useCallback(
    async (orderId: string, action: 'fill' | 'cancel') => {
      setBusy(orderId);
      setError(null);
      try {
        const response = await fetch(`/api/aegis/orders/${orderId}/${action}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: '{}',
        });
        const payload = await response.json();
        if (payload?.error) setError(payload.error.reason);
        await load();
      } catch {
        setError('The analysis backend did not answer, so nothing changed.');
      } finally {
        setBusy(null);
      }
    },
    [load],
  );

  if (orders === null && !error) {
    return <p className="small muted">Loading the order book…</p>;
  }

  return (
    <div className="orderBook">
      {error ? (
        <p className="orderBook__error" role="status">
          {error}
        </p>
      ) : null}

      {orders && orders.length === 0 ? (
        <p className="small muted">
          No orders yet. The ticket above places a simulated one.
        </p>
      ) : null}

      {orders && orders.length > 0 ? (
        <div className="tableWrap">
          <table className="dense">
            <thead>
              <tr>
                <th scope="col">Order</th>
                <th scope="col">Security</th>
                <th scope="col">Side</th>
                <th scope="col">Qty</th>
                <th scope="col">Type</th>
                <th scope="col">Status</th>
                <th scope="col">Reference</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.order_id} data-status={o.status}>
                  <th scope="row" className="mono small">
                    <Link href={`/trading/orders/${o.order_id}`}>{o.order_id}</Link>
                  </th>
                  <td>{o.symbol}</td>
                  <td>
                    <span className={`side side--${o.side.toLowerCase()}`}>{o.side}</span>
                  </td>
                  <td className="num">
                    {o.filled}/{o.quantity}
                  </td>
                  <td className="small">{o.order_type.replace('_', ' ')}</td>
                  <td>
                    <span className="status" data-status={o.status}>
                      {o.status.replace('_', ' ')}
                    </span>
                    {o.rejected_reason ? (
                      <span className="status__why">{o.rejected_reason}</span>
                    ) : null}
                  </td>
                  <td className="num mono small">
                    {o.reference_price}
                    <span className="muted"> · {o.reference_session}</span>
                  </td>
                  <td className="orderBook__actions">
                    {OPEN_STATES.has(o.status) ? (
                      <>
                        <button
                          type="button"
                          className="btn btn--tiny"
                          onClick={() => void act(o.order_id, 'fill')}
                          disabled={busy === o.order_id}
                        >
                          Fill
                        </button>
                        <button
                          type="button"
                          className="btn btn--tiny btn--ghost"
                          onClick={() => void act(o.order_id, 'cancel')}
                          disabled={busy === o.order_id}
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <span className="small muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
