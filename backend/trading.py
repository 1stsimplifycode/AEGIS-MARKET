"""The simulated order lifecycle, validated against the market data this repository has.

What makes this a workflow rather than a button: an order is checked before it is
accepted, the check can refuse it and say why, acceptance blocks funds, a fill moves the
position and the ledger, and every one of those transitions is a row somebody can read
back afterwards.

What keeps it honest:

**No invented prices.** A simulated fill happens at the last close in ``cash_panel``, and
the response says which session that close is from. Generating a plausible intraday print
would be fabricating market data — the one thing this project refuses to do anywhere else,
and there is no reason the operational half should get an exemption.

**No claim of execution.** Every order carries ``simulated``, and the refusals and fills
say what they are. Nothing here reaches a market, and nothing here says it did.

**Validation uses real numbers.** Notional is computed from the real close; buying power
comes from the simulated ledger; the risk check reads the same product read model the risk
pages read, so an order refused for risk is refused for a reason the product can show.

The states, and the only transitions allowed between them::

    DRAFT ─→ VALIDATING ─→ ACCEPTED ─→ OPEN ─→ PARTIALLY_FILLED ─→ FILLED
                    │           │        │             │
                    └→ REJECTED └────────┴─────────────┴─→ CANCELLED
"""
from __future__ import annotations

from typing import Any

from backend import store

DRAFT = "DRAFT"
VALIDATING = "VALIDATING"
ACCEPTED = "ACCEPTED"
OPEN = "OPEN"
PARTIALLY_FILLED = "PARTIALLY_FILLED"
FILLED = "FILLED"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"

TERMINAL = {FILLED, REJECTED, CANCELLED}

#: Which transitions the lifecycle permits. A state machine written down is one that can
#: be checked; one that lives in a sequence of `if` statements is one that drifts.
TRANSITIONS: dict[str, set[str]] = {
    DRAFT: {VALIDATING, CANCELLED},
    VALIDATING: {ACCEPTED, REJECTED},
    ACCEPTED: {OPEN, CANCELLED},
    OPEN: {PARTIALLY_FILLED, FILLED, CANCELLED},
    PARTIALLY_FILLED: {FILLED, CANCELLED},
    FILLED: set(),
    REJECTED: set(),
    CANCELLED: set(),
}

SIDES = ("BUY", "SELL")
ORDER_TYPES = ("MARKET", "LIMIT", "STOP_LOSS")
VALIDITIES = ("DAY", "IOC")

#: A simulated account cannot commit more than this share of its buying power to one
#: order. Not a regulatory limit — a demonstration guard, and labelled as one.
MAX_SINGLE_ORDER_SHARE = 0.35

#: How far a limit price may sit from the reference close before the order is refused. The
#: repository has no circuit-limit data, so this is a stated demonstration bound rather
#: than an exchange rule presented as one.
MAX_PRICE_DEVIATION = 0.20


class OrderError(ValueError):
    """A refusal a caller should show, with a reason and a remedy."""

    def __init__(self, code: str, reason: str, remedy: str) -> None:
        self.code = code
        self.reason = reason
        self.remedy = remedy
        super().__init__(reason)


def _market(symbol: str) -> dict:
    """The last close this repository has for a symbol, and the session it belongs to."""
    from scripts.stages import product_views as pv

    detail = pv.instrument(symbol)
    if not detail.get("found"):
        raise OrderError("UNKNOWN_SYMBOL", "%s is not in the active universe." % symbol,
                         "Search for an instrument from the market page.")
    market = detail.get("market") or {}
    if not market.get("available") or market.get("close") in (None, 0):
        raise OrderError(
            "NO_PRICE",
            "There is no price on record for %s, so an order cannot be checked "
            "against one." % symbol,
            "Choose an instrument that carries price history.")
    return {
        "close": float(market["close"]),
        "session": str(market.get("last_session") or "unknown"),
        "risk": detail.get("risk") or {},
    }


def _validate(symbol: str, side: str, quantity: int, order_type: str,
              limit_price: float | None, trigger_price: float | None,
              validity: str) -> None:
    if side not in SIDES:
        raise OrderError("INVALID_INPUT", "Side must be BUY or SELL.", "Choose a side.")
    if order_type not in ORDER_TYPES:
        raise OrderError("INVALID_INPUT",
                         "Order type must be one of %s." % ", ".join(ORDER_TYPES),
                         "Choose an order type.")
    if validity not in VALIDITIES:
        raise OrderError("INVALID_INPUT",
                         "Validity must be one of %s." % ", ".join(VALIDITIES),
                         "Choose a validity.")
    if not isinstance(quantity, int) or quantity <= 0:
        raise OrderError("INVALID_INPUT", "Quantity must be a whole number above zero.",
                         "Enter a quantity.")
    if quantity > 1_000_000:
        raise OrderError("INVALID_INPUT",
                         "Quantity is larger than this simulation accepts.",
                         "Enter a quantity below 1,000,000.")
    if order_type == "LIMIT" and not limit_price:
        raise OrderError("INVALID_INPUT", "A limit order needs a limit price.",
                         "Enter a limit price.")
    if order_type == "STOP_LOSS" and not trigger_price:
        raise OrderError("INVALID_INPUT", "A stop-loss order needs a trigger price.",
                         "Enter a trigger price.")
    for label, value in (("Limit price", limit_price), ("Trigger price", trigger_price)):
        if value is not None and value <= 0:
            raise OrderError("INVALID_INPUT", "%s must be above zero." % label,
                             "Enter a positive price.")


def _pre_trade_checks(symbol: str, side: str, quantity: int, order_type: str,
                      limit_price: float | None, market: dict,
                      account_id: str) -> list[dict]:
    """Every check, with its verdict — including the ones that passed.

    Returned in full rather than as a single yes/no, because "why was my order rejected"
    is a question the product has to be able to answer, and answering it from a boolean is
    not possible.
    """
    close = market["close"]
    price = limit_price if (order_type == "LIMIT" and limit_price) else close
    notional = price * quantity
    funds = store.funds_state(account_id)
    held = {p["symbol"]: p for p in store.positions(account_id)}
    risk = market.get("risk") or {}

    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str, code: str = "",
            remedy: str = "") -> None:
        checks.append({"check": name, "passed": passed, "detail": detail,
                       "code": code, "remedy": remedy})

    add("Price reference",
        True,
        "Checked against the close of %.2f from session %s, the last this repository "
        "holds." % (close, market["session"]))

    deviation = abs(price - close) / close if close else 0.0
    # Two separate things, and conflating them was the defect: the platform's own sanity
    # guard, and the band NSE actually applies. The guard is labelled as a guard. The
    # exchange band is reported beside it when the reference layer has one, and reported
    # as unavailable when it does not -- never defaulted to the guard's value.
    add("Platform guard (not an exchange rule)",
        deviation <= MAX_PRICE_DEVIATION,
        "Order price is %.1f%% from the reference close. This simulator refuses beyond "
        "%.0f%%, which is a demonstration bound chosen by this project and not an NSE "
        "circuit limit." % (deviation * 100, MAX_PRICE_DEVIATION * 100),
        "PRICE_OUT_OF_BAND",
        "Move the price closer to the last close.")

    from scripts.stages import week1_foundation as w1

    band = w1.price_band(symbol)
    if band.get("available"):
        add("Exchange circuit band",
            True,
            "NSE applies a %s band to %s (series %s), from its published securities "
            "list.%s" % (band["band_label"], symbol, band["series"] or "-",
                         " Surveillance: %s." % band["surveillance_remark"]
                         if band.get("surveillance_remark") else ""))
    else:
        add("Exchange circuit band",
            True,
            "NOT AVAILABLE: %s No band is assumed in its place." % band.get("why", ""))

    if side == "BUY":
        add("Buying power",
            notional <= funds["available"] + 0.005,
            "Order needs %.2f against %.2f available." % (notional, funds["available"]),
            "INSUFFICIENT_FUNDS",
            "Reduce the quantity or add simulated funds.")
        cap = (funds["available"] + funds["blocked"]) * MAX_SINGLE_ORDER_SHARE
        add("Single-order exposure",
            notional <= cap + 0.005,
            "Order is %.2f against a per-order demonstration cap of %.2f."
            % (notional, cap),
            "EXPOSURE_CAP",
            "Split the order or reduce the quantity.")
    else:
        holding = held.get(symbol.upper(), {}).get("quantity", 0)
        add("Holding",
            holding >= quantity,
            "Selling %d against %d held." % (quantity, holding),
            "INSUFFICIENT_HOLDING",
            "Reduce the quantity to what the simulated portfolio holds.")

    state = risk.get("state")
    if state:
        add("Risk state",
            True,
            "%s is currently assessed %s. This is recorded with the order, not used to "
            "block it." % (symbol.upper(), risk.get("state_label") or state))
    else:
        add("Risk state", True,
            "No risk assessment covers %s on the scored sessions." % symbol.upper())

    return checks


def _transition(tx, order_id: str, account_id: str, previous: str | None, to: str,
                actor: str, reason: str, detail: dict | None = None) -> None:
    if previous is not None and to not in TRANSITIONS.get(previous, set()):
        raise OrderError("INVALID_TRANSITION",
                         "An order cannot move from %s to %s." % (previous, to),
                         "Reload the order and try again.")
    tx.execute(
        "INSERT INTO order_events (event_id, order_id, at, from_status, to_status, "
        "actor, reason, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (store.new_id("EVT"), order_id, store.now(), previous, to, actor, reason,
         None if detail is None else __import__("json").dumps(detail, default=str)),
    )
    tx.execute("UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
               (to, store.now(), order_id))
    store._audit(tx, account_id, actor, "ORDER_" + to, "order", order_id,
                 {"status": previous}, {"status": to}, reason)


def preview(symbol: str, side: str, quantity: int, order_type: str = "MARKET",
            limit_price: float | None = None, trigger_price: float | None = None,
            validity: str = "DAY", account_id: str = store.DEMO_ACCOUNT) -> dict:
    """Run the pre-trade checks without creating anything.

    The review step of the ticket. It writes no order and no audit row, because looking at
    what would happen is not a thing that happened.
    """
    symbol = (symbol or "").upper()
    _validate(symbol, side, quantity, order_type, limit_price, trigger_price, validity)
    market = _market(symbol)
    checks = _pre_trade_checks(symbol, side, quantity, order_type, limit_price,
                               market, account_id)
    failed = [c for c in checks if not c["passed"]]
    price = limit_price if (order_type == "LIMIT" and limit_price) else market["close"]
    return {
        "status": "OK",
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "order_type": order_type,
        "reference_price": round(market["close"], 2),
        "reference_session": market["session"],
        "estimated_notional": round(price * quantity, 2),
        "checks": checks,
        "would_accept": not failed,
        "blocking": failed,
        "simulated": True,
        "note": ("A simulated order. Nothing here reaches a market, and a fill would use "
                 "the last close on record rather than a live price."),
    }


def place(symbol: str, side: str, quantity: int, order_type: str = "MARKET",
          limit_price: float | None = None, trigger_price: float | None = None,
          validity: str = "DAY", account_id: str = store.DEMO_ACCOUNT) -> dict:
    """Create, validate and — if it passes — accept and open the order."""
    symbol = (symbol or "").upper()
    _validate(symbol, side, quantity, order_type, limit_price, trigger_price, validity)
    market = _market(symbol)
    store.ensure_account(account_id)
    checks = _pre_trade_checks(symbol, side, quantity, order_type, limit_price,
                               market, account_id)
    failed = [c for c in checks if not c["passed"]]
    price = limit_price if (order_type == "LIMIT" and limit_price) else market["close"]
    order_id = store.new_id("ORD")

    with store.transaction() as tx:
        tx.execute(
            "INSERT INTO orders (order_id, account_id, symbol, side, quantity, filled, "
            "order_type, limit_price, trigger_price, validity, status, reference_price, "
            "reference_session, created_at, updated_at, rejected_reason, simulated) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 1)",
            (order_id, account_id, symbol, side, quantity, order_type, limit_price,
             trigger_price, validity, DRAFT, market["close"], market["session"],
             store.now(), store.now()),
        )
        _transition(tx, order_id, account_id, None, DRAFT, "user",
                    "Order ticket submitted.",
                    {"symbol": symbol, "side": side, "quantity": quantity})
        _transition(tx, order_id, account_id, DRAFT, VALIDATING, "system",
                    "Running pre-trade checks.")

        if failed:
            first = failed[0]
            tx.execute("UPDATE orders SET rejected_reason = ? WHERE order_id = ?",
                       (first["detail"], order_id))
            _transition(tx, order_id, account_id, VALIDATING, REJECTED, "system",
                        first["detail"], {"checks": checks})
            _notify(tx, account_id, "ORDER", "Order rejected",
                    "%s %d %s — %s" % (side, quantity, symbol, first["detail"]),
                    "/trading/orders/%s" % order_id)
        else:
            _transition(tx, order_id, account_id, VALIDATING, ACCEPTED, "system",
                        "All pre-trade checks passed.", {"checks": checks})
            if side == "BUY":
                store._fund_entry(tx, account_id, "BLOCK", -price * quantity,
                                  price * quantity,
                                  "Margin blocked for order %s." % order_id, order_id)
            _transition(tx, order_id, account_id, ACCEPTED, OPEN, "system",
                        "Order is open in the simulated book.")
            _notify(tx, account_id, "ORDER", "Order open",
                    "%s %d %s is open." % (side, quantity, symbol),
                    "/trading/orders/%s" % order_id)

    return get(order_id, account_id)


def fill(order_id: str, quantity: int | None = None,
         account_id: str = store.DEMO_ACCOUNT) -> dict:
    """Fill an open order, wholly or in part, at the last close on record."""
    order = _row(order_id, account_id)
    if order["status"] not in (OPEN, PARTIALLY_FILLED):
        raise OrderError("NOT_OPEN",
                         "Only an open order can be filled; this one is %s."
                         % order["status"],
                         "Place a new order.")
    remaining = int(order["quantity"]) - int(order["filled"])
    take = remaining if quantity is None else min(int(quantity), remaining)
    if take <= 0:
        raise OrderError("INVALID_INPUT", "There is nothing left to fill.",
                         "Choose a smaller quantity.")

    market = _market(order["symbol"])
    price = float(order["limit_price"]) if (order["order_type"] == "LIMIT"
                                            and order["limit_price"]) else market["close"]
    basis = ("Simulated fill at the close of %.2f from session %s. This repository holds "
             "no intraday prices, so no intraday price was invented."
             % (market["close"], market["session"]))
    if order["order_type"] == "LIMIT" and order["limit_price"]:
        basis = ("Simulated fill at the limit price of %.2f. The reference close was "
                 "%.2f, session %s." % (price, market["close"], market["session"]))

    filled_after = int(order["filled"]) + take
    to = FILLED if filled_after >= int(order["quantity"]) else PARTIALLY_FILLED

    with store.transaction() as tx:
        tx.execute(
            "INSERT INTO executions (execution_id, order_id, account_id, symbol, side, "
            "quantity, price, session, at, basis, simulated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
            (store.new_id("EXE"), order_id, account_id, order["symbol"], order["side"],
             take, price, market["session"], store.now(), basis),
        )
        tx.execute("UPDATE orders SET filled = ? WHERE order_id = ?",
                   (filled_after, order_id))
        notional = price * take
        if order["side"] == "BUY":
            blocked = float(order["reference_price"]) * take
            store._fund_entry(tx, account_id, "RELEASE", 0.0, -blocked,
                              "Margin released on fill of %s." % order_id, order_id)
            store._fund_entry(tx, account_id, "DEBIT", -0.0, 0.0,
                              "Consideration for %s." % order_id, order_id)
            # The blocked amount returns to available, then the actual consideration
            # leaves it; two entries because that is two things happening.
            store._fund_entry(tx, account_id, "CREDIT", blocked - notional, 0.0,
                              "Difference between blocked margin and fill value for %s."
                              % order_id, order_id)
        else:
            store._fund_entry(tx, account_id, "CREDIT", notional, 0.0,
                              "Proceeds from %s." % order_id, order_id)
        _transition(tx, order_id, account_id, order["status"], to, "system",
                    basis, {"quantity": take, "price": price})
        _notify(tx, account_id, "ORDER",
                "Order filled" if to == FILLED else "Order partially filled",
                "%s %d %s at %.2f (simulated)." % (order["side"], take,
                                                   order["symbol"], price),
                "/trading/orders/%s" % order_id)

    return get(order_id, account_id)


def cancel(order_id: str, reason: str = "Cancelled by the user.",
           account_id: str = store.DEMO_ACCOUNT) -> dict:
    order = _row(order_id, account_id)
    if order["status"] in TERMINAL:
        raise OrderError("NOT_CANCELLABLE",
                         "This order is already %s." % order["status"],
                         "Place a new order instead.")
    with store.transaction() as tx:
        if order["side"] == "BUY" and order["status"] in (ACCEPTED, OPEN,
                                                          PARTIALLY_FILLED):
            outstanding = (int(order["quantity"]) - int(order["filled"])) * \
                float(order["reference_price"])
            if outstanding > 0:
                store._fund_entry(tx, account_id, "RELEASE", outstanding, -outstanding,
                                  "Margin released on cancellation of %s." % order_id,
                                  order_id)
        _transition(tx, order_id, account_id, order["status"], CANCELLED, "user", reason)
        _notify(tx, account_id, "ORDER", "Order cancelled",
                "%s %d %s cancelled." % (order["side"], order["quantity"],
                                         order["symbol"]),
                "/trading/orders/%s" % order_id)
    return get(order_id, account_id)


# ------------------------------------------------------------------ reading ----

def _row(order_id: str, account_id: str) -> dict:
    conn = store.connection()
    row = conn.execute("SELECT * FROM orders WHERE order_id = ? AND account_id = ?",
                       (order_id, account_id)).fetchone()
    if row is None:
        raise OrderError("UNKNOWN_ORDER", "No order %s." % order_id,
                         "Open the order book to see what exists.")
    return dict(row)


def get(order_id: str, account_id: str = store.DEMO_ACCOUNT) -> dict:
    order = _row(order_id, account_id)
    conn = store.connection()
    events = [dict(r) for r in conn.execute(
        "SELECT * FROM order_events WHERE order_id = ? ORDER BY at, rowid",
        (order_id,)).fetchall()]
    fills = [dict(r) for r in conn.execute(
        "SELECT * FROM executions WHERE order_id = ? ORDER BY at, rowid",
        (order_id,)).fetchall()]
    return {
        "status": "OK",
        "order": {**order, "simulated": bool(order["simulated"])},
        "events": events,
        "executions": fills,
        "audit": store.audit_trail("order", order_id, account_id),
        "note": "Simulated order. Nothing here reached a market.",
    }


def book(account_id: str = store.DEMO_ACCOUNT, limit: int = 100) -> dict:
    store.ensure_account(account_id)
    conn = store.connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM orders WHERE account_id = ? ORDER BY created_at DESC, rowid DESC "
        "LIMIT ?", (account_id, int(limit))).fetchall()]
    return {
        "status": "OK",
        "orders": [{**r, "simulated": bool(r["simulated"])} for r in rows],
        "counts": {s: sum(1 for r in rows if r["status"] == s)
                   for s in sorted({r["status"] for r in rows})},
        "simulated": True,
    }


def _notify(tx, account_id: str, kind: str, title: str, body: str,
            link: str | None) -> None:
    tx.execute(
        "INSERT INTO notifications (notification_id, account_id, at, kind, title, body, "
        "link, read_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
        (store.new_id("NTF"), account_id, store.now(), kind, title, body, link),
    )


def portfolio(account_id: str = store.DEMO_ACCOUNT) -> dict:
    """Positions marked against the last close this repository holds.

    Quantities and average prices come from simulated executions; the mark comes from real
    market data. The result is arithmetic on simulated trades against real prices, and the
    response says so rather than leaving a reader to assume either half.
    """
    from scripts.stages import product_views as pv

    held = store.positions(account_id)
    rows, invested, current, realised = [], 0.0, 0.0, 0.0
    for pos in held:
        mark, session = None, None
        try:
            detail = pv.instrument(pos["symbol"])
            market = detail.get("market") or {}
            if market.get("available") and market.get("close"):
                mark = float(market["close"])
                session = market.get("last_session")
        except Exception:                       # noqa: BLE001 - reported as unmarked
            mark = None
        value = (mark * pos["quantity"]) if mark is not None else None
        unrealised = (value - pos["invested"]) if value is not None else None
        invested += pos["invested"]
        current += value if value is not None else pos["invested"]
        realised += pos["realised_pnl"]
        rows.append({
            **pos,
            "last_price": None if mark is None else round(mark, 2),
            "last_session": session,
            "value": None if value is None else round(value, 2),
            "unrealised_pnl": None if unrealised is None else round(unrealised, 2),
            "unmarked_reason": None if mark is not None else
                               "No price on record for this instrument.",
        })
    for row in rows:
        row["weight"] = round(row["value"] / current, 4) if (row["value"] and current) \
            else None
    return {
        "status": "OK",
        "positions": rows,
        "totals": {
            "invested": round(invested, 2),
            "value": round(current, 2),
            "unrealised_pnl": round(current - invested, 2),
            "realised_pnl": round(realised, 2),
        },
        "funds": store.funds_state(account_id),
        "simulated": True,
        "note": ("Positions come from simulated executions; the mark is the last close "
                 "this repository holds for each instrument."),
    }


def notifications(account_id: str = store.DEMO_ACCOUNT, unread_only: bool = False,
                  limit: int = 100) -> dict:
    store.ensure_account(account_id)
    conn = store.connection()
    sql = "SELECT * FROM notifications WHERE account_id = ?"
    args: list[Any] = [account_id]
    if unread_only:
        sql += " AND read_at IS NULL"
    sql += " ORDER BY at DESC, rowid DESC LIMIT ?"
    args.append(int(limit))
    rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
    unread = conn.execute(
        "SELECT COUNT(*) AS n FROM notifications WHERE account_id = ? "
        "AND read_at IS NULL", (account_id,)).fetchone()["n"]
    return {"status": "OK", "notifications": rows, "unread": int(unread)}


def mark_read(notification_id: str | None = None,
              account_id: str = store.DEMO_ACCOUNT) -> dict:
    store.ensure_account(account_id)
    with store.transaction() as tx:
        if notification_id:
            tx.execute("UPDATE notifications SET read_at = ? WHERE notification_id = ? "
                       "AND account_id = ? AND read_at IS NULL",
                       (store.now(), notification_id, account_id))
        else:
            tx.execute("UPDATE notifications SET read_at = ? WHERE account_id = ? "
                       "AND read_at IS NULL", (store.now(), account_id))
    return notifications(account_id)
