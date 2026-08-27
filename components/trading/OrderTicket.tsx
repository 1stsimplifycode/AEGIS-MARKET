'use client';

/**
 * The order ticket: review, then place.
 *
 * Two steps on purpose. Review runs the pre-trade checks and writes nothing — it answers
 * "what would happen" without anything having happened. Place runs them again server-side
 * and commits the result. The client never decides whether an order is acceptable; it asks,
 * and shows what came back.
 *
 * Every check is shown, including the ones that passed. A ticket that only surfaces the
 * failing check answers "no" without answering "why not", and "why was my order rejected"
 * is the question this workflow exists to be able to answer.
 *
 * Nothing here reaches a market. The response says so and so does the panel.
 */
import Link from 'next/link';
import { useCallback, useState } from 'react';

import {
  DEFAULT_ORDER_SIDE,
  ORDER_SIDES,
  type OrderSide,
} from '@/lib/orderSides';

interface Check {
  check: string;
  passed: boolean;
  detail: string;
  code: string;
  remedy: string;
}

interface Preview {
  status: string;
  symbol: string;
  side: string;
  quantity: number;
  reference_price: number;
  reference_session: string;
  estimated_notional: number;
  checks: Check[];
  would_accept: boolean;
  blocking: Check[];
  note: string;
}

interface Placed {
  status: string;
  order: { order_id: string; status: string; rejected_reason: string | null };
  events: { to_status: string; reason: string; at: string }[];
}

interface Refusal {
  code: string;
  reason: string;
  remedy: string;
}

const TYPES = ['MARKET', 'LIMIT', 'STOP_LOSS'] as const;
const VALIDITIES = ['DAY', 'IOC'] as const;

export function OrderTicket({ symbol: initial = '' }: { symbol?: string }) {
  const [symbol, setSymbol] = useState(initial);
  const [side, setSide] = useState<OrderSide>(DEFAULT_ORDER_SIDE);
  const [quantity, setQuantity] = useState('10');
  const [orderType, setOrderType] = useState<(typeof TYPES)[number]>('MARKET');
  const [limitPrice, setLimitPrice] = useState('');
  const [triggerPrice, setTriggerPrice] = useState('');
  const [validity, setValidity] = useState<(typeof VALIDITIES)[number]>('DAY');

  const [busy, setBusy] = useState<'review' | 'place' | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [placed, setPlaced] = useState<Placed | null>(null);
  const [refusal, setRefusal] = useState<Refusal | null>(null);

  const body = useCallback(
    () => ({
      symbol: symbol.trim().toUpperCase(),
      side,
      quantity: Number(quantity),
      order_type: orderType,
      limit_price: limitPrice === '' ? null : Number(limitPrice),
      trigger_price: triggerPrice === '' ? null : Number(triggerPrice),
      validity,
    }),
    [symbol, side, quantity, orderType, limitPrice, triggerPrice, validity],
  );

  const call = useCallback(
    async (path: string, phase: 'review' | 'place') => {
      setBusy(phase);
      setRefusal(null);
      if (phase === 'review') setPlaced(null);
      try {
        const response = await fetch(`/api/aegis/orders/${path}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body()),
        });
        const payload = await response.json();
        if (payload?.error) {
          setRefusal(payload.error as Refusal);
          return;
        }
        if (phase === 'review') setPreview(payload as Preview);
        else setPlaced(payload as Placed);
      } catch {
        setRefusal({
          code: 'BACKEND_UNAVAILABLE',
          reason: 'The analysis backend did not answer, so nothing was submitted.',
          remedy: 'Start it with run_dev.bat and try again.',
        });
      } finally {
        setBusy(null);
      }
    },
    [body],
  );

  const dirty = () => {
    setPreview(null);
    setPlaced(null);
    setRefusal(null);
  };

  return (
    <section className="ticket">
      <header className="ticket__head">
        <h2>Order ticket</h2>
        <span className="pill pill--sim">Simulated</span>
      </header>

      <div className="ticket__grid">
        <label className="field">
          <span>Security</span>
          <input
            value={symbol}
            onChange={(e) => {
              setSymbol(e.target.value);
              dirty();
            }}
            placeholder="RELIANCE"
            aria-label="Security"
            autoCapitalize="characters"
          />
        </label>

        <fieldset className="field field--side">
          {/*
            The user's instruction, recorded. The system never fills this in, never
            proposes a value and never ranks the two — see lib/orderSides.ts.
          */}
          <legend>Side (you choose)</legend>
          {ORDER_SIDES.map((s) => (
            <button
              key={s}
              type="button"
              className={side === s ? `sideBtn is-${s.toLowerCase()}` : 'sideBtn'}
              aria-pressed={side === s}
              onClick={() => {
                setSide(s);
                dirty();
              }}
            >
              {s}
            </button>
          ))}
        </fieldset>

        <label className="field">
          <span>Quantity</span>
          <input
            value={quantity}
            inputMode="numeric"
            onChange={(e) => {
              setQuantity(e.target.value);
              dirty();
            }}
            aria-label="Quantity"
          />
        </label>

        <label className="field">
          <span>Order type</span>
          <select
            value={orderType}
            onChange={(e) => {
              setOrderType(e.target.value as (typeof TYPES)[number]);
              dirty();
            }}
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace('_', ' ')}
              </option>
            ))}
          </select>
        </label>

        {orderType === 'LIMIT' ? (
          <label className="field">
            <span>Limit price</span>
            <input
              value={limitPrice}
              inputMode="decimal"
              onChange={(e) => {
                setLimitPrice(e.target.value);
                dirty();
              }}
              aria-label="Limit price"
            />
          </label>
        ) : null}

        {orderType === 'STOP_LOSS' ? (
          <label className="field">
            <span>Trigger price</span>
            <input
              value={triggerPrice}
              inputMode="decimal"
              onChange={(e) => {
                setTriggerPrice(e.target.value);
                dirty();
              }}
              aria-label="Trigger price"
            />
          </label>
        ) : null}

        <label className="field">
          <span>Validity</span>
          <select
            value={validity}
            onChange={(e) => {
              setValidity(e.target.value as (typeof VALIDITIES)[number]);
              dirty();
            }}
          >
            {VALIDITIES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="ticket__actions">
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => void call('preview', 'review')}
          disabled={busy !== null || !symbol.trim()}
          aria-busy={busy === 'review'}
        >
          {busy === 'review' ? 'Checking…' : 'Review order'}
        </button>
        <button
          type="button"
          className="btn btn--primary"
          onClick={() => void call('place', 'place')}
          disabled={busy !== null || !preview}
          aria-busy={busy === 'place'}
        >
          {busy === 'place' ? 'Submitting…' : 'Submit'}
        </button>
        <span className="ticket__hint">
          Review runs the pre-trade checks and writes nothing.
        </span>
      </div>

      {refusal ? (
        <div className="ticket__refusal" role="status">
          <strong>{refusal.reason}</strong>
          <span>{refusal.remedy}</span>
          <span className="mono small">{refusal.code}</span>
        </div>
      ) : null}

      {preview ? (
        <div className="ticket__preview">
          <div className="ticket__summary">
            <span>
              {preview.side} {preview.quantity} {preview.symbol}
            </span>
            <span className="mono">
              ≈ ₹{preview.estimated_notional.toLocaleString('en-IN')}
            </span>
            <span className="small muted">
              against the close of {preview.reference_price} on{' '}
              {preview.reference_session}
            </span>
          </div>
          <ul className="checks">
            {preview.checks.map((c) => (
              <li key={c.check} data-passed={c.passed}>
                <span aria-hidden="true">{c.passed ? '✓' : '✗'}</span>
                <span className="checks__name">{c.check}</span>
                <span className="checks__detail">{c.detail}</span>
                {!c.passed && c.remedy ? (
                  <span className="checks__remedy">{c.remedy}</span>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="small muted">{preview.note}</p>
        </div>
      ) : null}

      {placed ? (
        <div className="ticket__placed" data-status={placed.order.status}>
          <p className="ticket__placedHead">
            <span className="mono">{placed.order.order_id}</span> ·{' '}
            <strong>{placed.order.status}</strong>
          </p>
          {placed.order.rejected_reason ? (
            <p className="ticket__rejected">{placed.order.rejected_reason}</p>
          ) : null}
          <ol className="lifecycle">
            {placed.events.map((e, i) => (
              <li key={i}>
                <span className="lifecycle__state">{e.to_status}</span>
                <span className="lifecycle__reason">{e.reason}</span>
              </li>
            ))}
          </ol>
          <p className="small">
            <Link href={`/trading/orders/${placed.order.order_id}`}>
              Open the order, its timeline and its audit trail →
            </Link>
          </p>
        </div>
      ) : null}
    </section>
  );
}
