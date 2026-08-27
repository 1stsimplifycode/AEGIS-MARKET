"""Persistent state for the operational side of the product.

Everything the research half of AEGIS-Market shows is computed from data on disk. The
operational half — orders, positions, funds, cases, notifications — has no data on disk,
because this repository is a research project and there is no broker, no exchange, no bank
and no depository behind it.

That leaves two honest options and one dishonest one. The dishonest one is a button that
moves a number in React and forgets it on refresh, which looks like a working platform and
is not. The honest ones are to say the capability is unavailable, or to simulate it
properly: real identifiers, real state machines, real validation, real history, real
audit,
and state that survives a restart. This module is the second.

Three rules it exists to hold:

**Simulated is labelled, everywhere.** Every order, execution and fund movement carries
``simulated = 1`` and the reason. Nothing here may be presented as an instruction that
reached a market.

**Prices are never invented.** A simulated fill uses the last close this repository
actually has, and says which session that was. Inventing an intraday print to make a fill
look realistic would be fabricating market data, which is the one thing the whole project
refuses to do.

**Every state change is audited.** Not as a display — as a row, written in the same
transaction as the change it describes, so an audit trail cannot disagree with the
state it is supposed to explain.

SQLite because it is in the standard library, gives real transactions, and puts the state
in one file a reader can open and inspect. The file lives outside the repository tree's
tracked content and is created on first use.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Where the simulated state lives. Overridable so tests get their own file rather than
#: sharing — and mutating — whatever the developer has been clicking through.
ENV_PATH = "AEGIS_STATE_DB"
DEFAULT_PATH = REPO_ROOT / ".aegis-state" / "product.db"

#: The single demonstration account. There is no identity provider behind this product, so
#: there is one account and it says so rather than implying a login system exists.
DEMO_ACCOUNT = "DEMO-0001"

#: What a simulated account starts with. A round, obviously notional figure: a number that
#: looked like a real opening balance would invite someone to read it as one.
OPENING_BALANCE = 1_000_000.0

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id   TEXT PRIMARY KEY,
    opened_at    TEXT NOT NULL,
    simulated    INTEGER NOT NULL DEFAULT 1,
    note         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS funds (
    entry_id     TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    at           TEXT NOT NULL,
    kind         TEXT NOT NULL,          -- OPENING | DEPOSIT | WITHDRAWAL | BLOCK
                                         -- | RELEASE | DEBIT | CREDIT
    amount       REAL NOT NULL,          -- signed, in rupees
    balance      REAL NOT NULL,          -- running available balance after this entry
    blocked      REAL NOT NULL,          -- running blocked margin after this entry
    reference    TEXT,                   -- order id, where the entry has one
    reason       TEXT NOT NULL,
    simulated    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orders (
    order_id     TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    side         TEXT NOT NULL,          -- BUY | SELL
    quantity     INTEGER NOT NULL,
    filled       INTEGER NOT NULL DEFAULT 0,
    order_type   TEXT NOT NULL,          -- MARKET | LIMIT | STOP_LOSS
    limit_price  REAL,
    trigger_price REAL,
    validity     TEXT NOT NULL,          -- DAY | IOC
    status       TEXT NOT NULL,
    reference_price REAL,                -- the close this order was validated against
    reference_session TEXT,              -- which session that close belongs to
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    rejected_reason TEXT,
    simulated    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS order_events (
    event_id     TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL,
    at           TEXT NOT NULL,
    from_status  TEXT,
    to_status    TEXT NOT NULL,
    actor        TEXT NOT NULL,
    reason       TEXT NOT NULL,
    detail       TEXT
);

CREATE TABLE IF NOT EXISTS executions (
    execution_id TEXT PRIMARY KEY,
    order_id     TEXT NOT NULL,
    account_id   TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    side         TEXT NOT NULL,
    quantity     INTEGER NOT NULL,
    price        REAL NOT NULL,
    session      TEXT NOT NULL,
    at           TEXT NOT NULL,
    basis        TEXT NOT NULL,          -- how the price was arrived at, in words
    simulated    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    name         TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_items (
    watchlist_id TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    added_at     TEXT NOT NULL,
    PRIMARY KEY (watchlist_id, symbol)
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL,
    at           TEXT NOT NULL,
    kind         TEXT NOT NULL,          -- ORDER | RISK | SYSTEM | RESEARCH
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,
    link         TEXT,
    read_at      TEXT
);

CREATE TABLE IF NOT EXISTS audit (
    audit_id     TEXT PRIMARY KEY,
    at           TEXT NOT NULL,
    account_id   TEXT NOT NULL,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    object_type  TEXT NOT NULL,
    object_id    TEXT NOT NULL,
    previous     TEXT,
    current      TEXT,
    reason       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_orders_account ON orders(account_id, created_at);
CREATE INDEX IF NOT EXISTS ix_events_order ON order_events(order_id, at);
CREATE INDEX IF NOT EXISTS ix_exec_account ON executions(account_id, at);
CREATE INDEX IF NOT EXISTS ix_audit_object ON audit(object_type, object_id, at);
CREATE INDEX IF NOT EXISTS ix_funds_account ON funds(account_id, at);
"""


def db_path() -> Path:
    raw = os.environ.get(ENV_PATH, "").strip()
    return Path(raw) if raw else DEFAULT_PATH


def now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    """A readable identifier. Short enough to quote in a conversation about an order."""
    return "%s-%s" % (prefix, uuid.uuid4().hex[:10].upper())


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    return conn


def connection() -> sqlite3.Connection:
    """One connection per thread. The server is threaded and SQLite objects are not."""
    path = str(db_path())
    existing = getattr(_local, "conn", None)
    if existing is not None and getattr(_local, "path", None) == path:
        return existing
    if existing is not None:
        existing.close()
    conn = _connect()
    _local.conn = conn
    _local.path = path
    return conn


def reset_connection() -> None:
    """Drop this thread's handle. Used by tests that point the store at a new file."""
    existing = getattr(_local, "conn", None)
    if existing is not None:
        existing.close()
    _local.conn = None
    _local.path = None


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """A unit of work.

    Audit rows are written inside this, beside the change they describe. An audit trail
    written afterwards is one that can be missing for exactly the changes somebody would
    most want explained.
    """
    conn = connection()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


# ------------------------------------------------------------------- account ----

def ensure_account(account_id: str = DEMO_ACCOUNT) -> dict:
    """The demonstration account, created on first use with its opening balance."""
    conn = connection()
    row = conn.execute("SELECT * FROM accounts WHERE account_id = ?",
                       (account_id,)).fetchone()
    if row is not None:
        return dict(row)

    with transaction() as tx:
        stamp = now()
        tx.execute(
            "INSERT OR IGNORE INTO accounts (account_id, opened_at, simulated, note) "
            "VALUES (?, ?, 1, ?)",
            (account_id, stamp,
             "Simulated account. There is no broker, exchange, bank or depository behind "
             "this product; nothing here reaches a market."),
        )
        already = tx.execute(
            "SELECT COUNT(*) AS n FROM funds WHERE account_id = ?", (account_id,)
        ).fetchone()["n"]
        if not already:
            tx.execute(
                "INSERT INTO funds (entry_id, account_id, at, kind, amount, balance, "
                "blocked, reference, reason, simulated) "
                "VALUES (?, ?, ?, 'OPENING', ?, ?, 0, NULL, ?, 1)",
                (new_id("FND"), account_id, stamp, OPENING_BALANCE, OPENING_BALANCE,
                 "Opening balance for the simulated account."),
            )
            _audit(tx, account_id, "system", "ACCOUNT_OPENED", "account", account_id,
                   None, {"opening_balance": OPENING_BALANCE},
                   "Simulated account created on first use.")
    return dict(conn.execute("SELECT * FROM accounts WHERE account_id = ?",
                             (account_id,)).fetchone())


# --------------------------------------------------------------------- audit ----

def _audit(tx: sqlite3.Connection, account_id: str, actor: str, action: str,
           object_type: str, object_id: str, previous: Any, current: Any,
           reason: str) -> str:
    audit_id = new_id("AUD")
    tx.execute(
        "INSERT INTO audit (audit_id, at, account_id, actor, action, object_type, "
        "object_id, previous, current, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (audit_id, now(), account_id, actor, action, object_type, object_id,
         None if previous is None else json.dumps(previous, default=str),
         None if current is None else json.dumps(current, default=str),
         reason),
    )
    return audit_id


def audit_trail(object_type: str | None = None, object_id: str | None = None,
                account_id: str = DEMO_ACCOUNT, limit: int = 200) -> list[dict]:
    conn = connection()
    sql = "SELECT * FROM audit WHERE account_id = ?"
    args: list[Any] = [account_id]
    if object_type:
        sql += " AND object_type = ?"
        args.append(object_type)
    if object_id:
        sql += " AND object_id = ?"
        args.append(object_id)
    sql += " ORDER BY at DESC, rowid DESC LIMIT ?"
    args.append(int(limit))
    return [
        {**dict(r),
         "previous": json.loads(r["previous"]) if r["previous"] else None,
         "current": json.loads(r["current"]) if r["current"] else None}
        for r in conn.execute(sql, args).fetchall()
    ]


def record_audit(actor: str, action: str, object_type: str, object_id: str,
                 reason: str, previous: Any = None, current: Any = None,
                 account_id: str = DEMO_ACCOUNT) -> str:
    """An audit row for something that happened outside a larger transaction."""
    ensure_account(account_id)
    with transaction() as tx:
        return _audit(tx, account_id, actor, action, object_type, object_id,
                      previous, current, reason)


# --------------------------------------------------------------------- funds ----

def funds_state(account_id: str = DEMO_ACCOUNT) -> dict:
    ensure_account(account_id)
    conn = connection()
    row = conn.execute(
        "SELECT balance, blocked FROM funds WHERE account_id = ? "
        "ORDER BY at DESC, rowid DESC LIMIT 1", (account_id,)
    ).fetchone()
    balance = float(row["balance"]) if row else 0.0
    blocked = float(row["blocked"]) if row else 0.0
    return {
        "account_id": account_id,
        "available": round(balance, 2),
        "blocked": round(blocked, 2),
        "total": round(balance + blocked, 2),
        "currency": "INR",
        "simulated": True,
        "note": ("Simulated funds. No banking integration exists in this environment; "
                 "no money moves."),
    }


def _fund_entry(tx: sqlite3.Connection, account_id: str, kind: str, amount: float,
                blocked_delta: float, reason: str, reference: str | None = None) -> dict:
    row = tx.execute(
        "SELECT balance, blocked FROM funds WHERE account_id = ? "
        "ORDER BY at DESC, rowid DESC LIMIT 1", (account_id,)
    ).fetchone()
    balance = float(row["balance"]) if row else 0.0
    blocked = float(row["blocked"]) if row else 0.0
    balance = round(balance + amount, 2)
    blocked = round(blocked + blocked_delta, 2)
    if balance < -0.005:
        raise ValueError("insufficient simulated funds")
    entry_id = new_id("FND")
    tx.execute(
        "INSERT INTO funds (entry_id, account_id, at, kind, amount, balance, blocked, "
        "reference, reason, simulated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
        (entry_id, account_id, now(), kind, amount, balance, blocked, reference, reason),
    )
    return {"entry_id": entry_id, "balance": balance, "blocked": blocked}


def funds_ledger(account_id: str = DEMO_ACCOUNT, limit: int = 100) -> list[dict]:
    ensure_account(account_id)
    conn = connection()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM funds WHERE account_id = ? ORDER BY at DESC, rowid DESC LIMIT ?",
        (account_id, int(limit))).fetchall()]


def adjust_funds(kind: str, amount: float, reason: str,
                 account_id: str = DEMO_ACCOUNT) -> dict:
    """A simulated deposit or withdrawal, audited like everything else."""
    if kind not in ("DEPOSIT", "WITHDRAWAL"):
        raise ValueError("kind must be DEPOSIT or WITHDRAWAL")
    if not (amount > 0):
        raise ValueError("amount must be positive")
    ensure_account(account_id)
    signed = amount if kind == "DEPOSIT" else -amount
    with transaction() as tx:
        before = funds_state(account_id)
        entry = _fund_entry(tx, account_id, kind, signed, 0.0, reason)
        _audit(tx, account_id, "user", "FUNDS_" + kind, "funds", entry["entry_id"],
               {"available": before["available"]}, {"available": entry["balance"]},
               reason)
    return funds_state(account_id)


# ----------------------------------------------------------------- positions ----

def positions(account_id: str = DEMO_ACCOUNT) -> list[dict]:
    """Holdings, derived from the executions that produced them.

    Derived rather than stored: a position table that can disagree with the trades behind
    it is a reconciliation problem waiting to happen, and this is small enough not to need
    one.
    """
    ensure_account(account_id)
    conn = connection()
    rows = conn.execute(
        "SELECT symbol, side, quantity, price FROM executions WHERE account_id = ? "
        "ORDER BY at", (account_id,)).fetchall()
    book: dict[str, dict] = {}
    for r in rows:
        pos = book.setdefault(r["symbol"], {"symbol": r["symbol"], "quantity": 0,
                                            "cost": 0.0, "realised": 0.0})
        qty, price = int(r["quantity"]), float(r["price"])
        if r["side"] == "BUY":
            pos["cost"] += qty * price
            pos["quantity"] += qty
        else:
            if pos["quantity"] > 0:
                average = pos["cost"] / pos["quantity"]
                closing = min(qty, pos["quantity"])
                pos["realised"] += (price - average) * closing
                pos["cost"] -= average * closing
                pos["quantity"] -= closing
    out = []
    for pos in book.values():
        if pos["quantity"] == 0 and abs(pos["realised"]) < 0.005:
            continue
        average = pos["cost"] / pos["quantity"] if pos["quantity"] else 0.0
        out.append({
            "symbol": pos["symbol"],
            "quantity": pos["quantity"],
            "average_price": round(average, 2),
            "invested": round(pos["cost"], 2),
            "realised_pnl": round(pos["realised"], 2),
            "simulated": True,
        })
    return sorted(out, key=lambda p: -abs(p["invested"]))


# ---------------------------------------------------------------- watchlists ----

DEFAULT_WATCHLIST = "My watchlist"


def _ensure_default_watchlist(tx, account_id: str) -> str:
    row = tx.execute(
        "SELECT watchlist_id FROM watchlists WHERE account_id = ? "
        "ORDER BY created_at LIMIT 1", (account_id,)).fetchone()
    if row is not None:
        return row["watchlist_id"]
    watchlist_id = new_id("WLS")
    tx.execute(
        "INSERT INTO watchlists (watchlist_id, account_id, name, created_at) "
        "VALUES (?, ?, ?, ?)",
        (watchlist_id, account_id, DEFAULT_WATCHLIST, now()))
    _audit(tx, account_id, "system", "WATCHLIST_CREATED", "watchlist", watchlist_id,
           None, {"name": DEFAULT_WATCHLIST}, "First watchlist created on demand.")
    return watchlist_id


def watchlists(account_id: str = DEMO_ACCOUNT) -> dict:
    """Every watchlist and its symbols.

    Server-side rather than in the browser: a watchlist held only in `localStorage` is
    lost with the tab, invisible to the backend that could act on it, and not something
    the product can honestly call saved.
    """
    ensure_account(account_id)
    with transaction() as tx:
        _ensure_default_watchlist(tx, account_id)
    conn = connection()
    lists = [dict(r) for r in conn.execute(
        "SELECT * FROM watchlists WHERE account_id = ? ORDER BY created_at",
        (account_id,)).fetchall()]
    for row in lists:
        row["symbols"] = [
            r["symbol"] for r in conn.execute(
                "SELECT symbol FROM watchlist_items WHERE watchlist_id = ? "
                "ORDER BY added_at", (row["watchlist_id"],)).fetchall()]
    return {"status": "OK", "watchlists": lists,
            "symbols": sorted({s for row in lists for s in row["symbols"]})}


def create_watchlist(name: str, account_id: str = DEMO_ACCOUNT) -> dict:
    clean = (name or "").strip()[:48]
    if not clean:
        raise ValueError("a watchlist needs a name")
    ensure_account(account_id)
    with transaction() as tx:
        watchlist_id = new_id("WLS")
        tx.execute(
            "INSERT INTO watchlists (watchlist_id, account_id, name, created_at) "
            "VALUES (?, ?, ?, ?)", (watchlist_id, account_id, clean, now()))
        _audit(tx, account_id, "user", "WATCHLIST_CREATED", "watchlist", watchlist_id,
               None, {"name": clean}, "Watchlist created.")
    return watchlists(account_id)


def rename_watchlist(watchlist_id: str, name: str,
                     account_id: str = DEMO_ACCOUNT) -> dict:
    clean = (name or "").strip()[:48]
    if not clean:
        raise ValueError("a watchlist needs a name")
    conn = connection()
    row = conn.execute(
        "SELECT name FROM watchlists WHERE watchlist_id = ? AND account_id = ?",
        (watchlist_id, account_id)).fetchone()
    if row is None:
        raise ValueError("no such watchlist")
    with transaction() as tx:
        tx.execute("UPDATE watchlists SET name = ? WHERE watchlist_id = ?",
                   (clean, watchlist_id))
        _audit(tx, account_id, "user", "WATCHLIST_RENAMED", "watchlist", watchlist_id,
               {"name": row["name"]}, {"name": clean}, "Watchlist renamed.")
    return watchlists(account_id)


def delete_watchlist(watchlist_id: str, account_id: str = DEMO_ACCOUNT) -> dict:
    conn = connection()
    row = conn.execute(
        "SELECT name FROM watchlists WHERE watchlist_id = ? AND account_id = ?",
        (watchlist_id, account_id)).fetchone()
    if row is None:
        raise ValueError("no such watchlist")
    with transaction() as tx:
        tx.execute("DELETE FROM watchlist_items WHERE watchlist_id = ?", (watchlist_id,))
        tx.execute("DELETE FROM watchlists WHERE watchlist_id = ?", (watchlist_id,))
        _audit(tx, account_id, "user", "WATCHLIST_DELETED", "watchlist", watchlist_id,
               {"name": row["name"]}, None, "Watchlist deleted.")
    return watchlists(account_id)


def watch(symbol: str, watchlist_id: str | None = None,
          account_id: str = DEMO_ACCOUNT) -> dict:
    clean = (symbol or "").strip().upper()[:24]
    if not clean:
        raise ValueError("a symbol is required")
    ensure_account(account_id)
    with transaction() as tx:
        target = watchlist_id or _ensure_default_watchlist(tx, account_id)
        tx.execute(
            "INSERT OR IGNORE INTO watchlist_items (watchlist_id, symbol, added_at) "
            "VALUES (?, ?, ?)", (target, clean, now()))
        _audit(tx, account_id, "user", "WATCHLIST_ADDED", "watchlist", target,
               None, {"symbol": clean}, "%s added to a watchlist." % clean)
    return watchlists(account_id)


def unwatch(symbol: str, watchlist_id: str | None = None,
            account_id: str = DEMO_ACCOUNT) -> dict:
    clean = (symbol or "").strip().upper()[:24]
    ensure_account(account_id)
    with transaction() as tx:
        target = watchlist_id or _ensure_default_watchlist(tx, account_id)
        tx.execute("DELETE FROM watchlist_items WHERE watchlist_id = ? AND symbol = ?",
                   (target, clean))
        _audit(tx, account_id, "user", "WATCHLIST_REMOVED", "watchlist", target,
               {"symbol": clean}, None, "%s removed from a watchlist." % clean)
    return watchlists(account_id)
