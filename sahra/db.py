"""SQLite store: feeds, state, approvals, tickets, outbox and the audit log (Stages 5, 8, 9)."""
import json
import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS flights(flight_no TEXT PRIMARY KEY, airline TEXT, direction TEXT, city TEXT, scheduled TEXT);
CREATE TABLE IF NOT EXISTS feed_records(source TEXT, flight_no TEXT, record TEXT, updated_at TEXT, PRIMARY KEY(source, flight_no));
CREATE TABLE IF NOT EXISTS queue_feed(checkpoint TEXT PRIMARY KEY, wait_min INTEGER, updated_at TEXT);
CREATE TABLE IF NOT EXISTS passengers(pax_id TEXT PRIMARY KEY, flight_no TEXT, lang TEXT, mobility TEXT, opted_in INTEGER,
    channel TEXT, contact_masked TEXT, last_seen_zone TEXT, last_seen_at TEXT);
CREATE TABLE IF NOT EXISTS flight_state(flight_no TEXT PRIMARY KEY, status TEXT, gate TEXT, boarding_time TEXT,
    est_time TEXT, belt TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS disagreements(flight_no TEXT, field TEXT, values_key TEXT, since TEXT, PRIMARY KEY(flight_no, field));
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, event_id TEXT, stage TEXT, kind TEXT,
    summary TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, event_id TEXT, audience TEXT, flight_no TEXT,
    recipient TEXT, channel TEXT, lang TEXT, kind TEXT, text TEXT, approved_by TEXT, approval_id TEXT);
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, thread_id TEXT UNIQUE, created_at TEXT, deadline TEXT, flight_no TEXT,
    change_types TEXT, summary TEXT, recipients INTEGER, langs TEXT, previews TEXT, status TEXT, decided_by TEXT,
    decided_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, created_at TEXT, event_id TEXT, team TEXT, priority TEXT, kind TEXT,
    summary TEXT, status TEXT, dedupe_key TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS found_items(id TEXT PRIMARY KEY, category TEXT, description TEXT, zone TEXT, found_at TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS lost_reports(id TEXT PRIMARY KEY, created_at TEXT, event_id TEXT, category TEXT, description TEXT,
    zone TEXT, match_id TEXT);
CREATE TABLE IF NOT EXISTS nudges(dedupe_key TEXT PRIMARY KEY, created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY, data TEXT);
"""


def connect():
    config.OUT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def tx():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def q(sql, params=()):
    with tx() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def one(sql, params=()):
    rows = q(sql, params)
    return rows[0] if rows else None


def ex(sql, params=()):
    with tx() as c:
        c.execute(sql, params)


def init_schema():
    with tx() as c:
        c.executescript(SCHEMA)


def reset_files():
    for p in (config.DB_PATH, config.CKPT_PATH):
        for suffix in ("", "-wal", "-shm"):
            f = p.with_name(p.name + suffix)
            if f.exists():
                f.unlink()


# --- settings / ids ---------------------------------------------------------------
def get_setting(key, default=None):
    r = one("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else default


def set_setting(key, value):
    ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def next_id(prefix):
    with tx() as c:
        key = f"counter:{prefix}"
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        n = int(r["value"]) + 1 if r else 1
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(n)))
    return f"{prefix}-{n:04d}"


def _now_iso():
    from . import clock
    return clock.now().isoformat()


# --- Stage 9: audit log ------------------------------------------------------------
def log(event_id, stage, kind, summary, detail=None):
    ex("INSERT INTO audit_log(ts,event_id,stage,kind,summary,detail) VALUES(?,?,?,?,?,?)",
       (_now_iso(), event_id, stage, kind, summary, json.dumps(detail or {}, ensure_ascii=False, default=str)))


# --- flights & feeds -----------------------------------------------------------------
def get_flight(fn):
    return one("SELECT * FROM flights WHERE flight_no=?", (fn,))


def all_flights():
    return q("SELECT * FROM flights ORDER BY scheduled")


def airline_codes():
    return {r["flight_no"][:2] for r in all_flights()}


def upsert_feed(rec):
    ex("INSERT INTO feed_records(source,flight_no,record,updated_at) VALUES(?,?,?,?) "
       "ON CONFLICT(source,flight_no) DO UPDATE SET record=excluded.record, updated_at=excluded.updated_at",
       (rec["source"], rec["flight_no"], json.dumps(rec), rec["updated_at"]))


def get_feed(source, fn):
    return one("SELECT * FROM feed_records WHERE source=? AND flight_no=?", (source, fn))


def all_feeds():
    return q("SELECT * FROM feed_records")


def upsert_queue(cp, wait_min, updated_at):
    ex("INSERT INTO queue_feed VALUES(?,?,?) ON CONFLICT(checkpoint) DO UPDATE SET wait_min=excluded.wait_min, "
       "updated_at=excluded.updated_at", (cp, wait_min, updated_at))


def get_queue(cp):
    return one("SELECT * FROM queue_feed WHERE checkpoint=?", (cp,))


# --- passengers (pseudonymised) ----------------------------------------------------
def get_pax(pax_id):
    return one("SELECT * FROM passengers WHERE pax_id=?", (pax_id,))


def pax_for_flight(fn, opted_only=True):
    sql = "SELECT * FROM passengers WHERE flight_no=?" + (" AND opted_in=1" if opted_only else "")
    return q(sql, (fn,))


def all_pax():
    return q("SELECT * FROM passengers")


def count_pax(fn):
    return one("SELECT COUNT(*) n FROM passengers WHERE flight_no=?", (fn,))["n"]


# --- Stage 5: remembered flight state & disagreements ---------------------------------
def get_flight_state(fn):
    return one("SELECT * FROM flight_state WHERE flight_no=?", (fn,))


def update_flight_state(fn, values):
    cur = get_flight_state(fn) or {}
    merged = {k: values.get(k, cur.get(k)) for k in ("status", "gate", "boarding_time", "est_time", "belt")}
    ex("INSERT INTO flight_state VALUES(?,?,?,?,?,?,?) ON CONFLICT(flight_no) DO UPDATE SET status=excluded.status, "
       "gate=excluded.gate, boarding_time=excluded.boarding_time, est_time=excluded.est_time, belt=excluded.belt, "
       "updated_at=excluded.updated_at",
       (fn, merged["status"], merged["gate"], merged["boarding_time"], merged["est_time"],
        None if merged["belt"] is None else str(merged["belt"]), _now_iso()))


def get_disagreement(fn, field):
    return one("SELECT * FROM disagreements WHERE flight_no=? AND field=?", (fn, field))


def set_disagreement(fn, field, values_key, since):
    ex("INSERT INTO disagreements VALUES(?,?,?,?) ON CONFLICT(flight_no,field) DO UPDATE SET values_key=excluded.values_key, "
       "since=excluded.since", (fn, field, values_key, since))


def clear_disagreement(fn, field):
    ex("DELETE FROM disagreements WHERE flight_no=? AND field=?", (fn, field))


# --- Stage 7: approvals -------------------------------------------------------------
def create_approval_once(thread_id, **kw):
    existing = one("SELECT * FROM approvals WHERE thread_id=?", (thread_id,))
    if existing:
        return existing["id"], False
    aid = next_id("APR")
    ex("INSERT INTO approvals(id,thread_id,created_at,deadline,flight_no,change_types,summary,recipients,langs,previews,status) "
       "VALUES(?,?,?,?,?,?,?,?,?,?,'PENDING')",
       (aid, thread_id, _now_iso(), kw["deadline"], kw["flight_no"], json.dumps(kw["change_types"]), kw["summary"],
        kw["recipients"], json.dumps(kw["langs"]), json.dumps(kw["previews"], ensure_ascii=False)))
    return aid, True


def get_approval(aid):
    return one("SELECT * FROM approvals WHERE id=?", (aid,))


def approval_by_thread(thread_id):
    return one("SELECT * FROM approvals WHERE thread_id=?", (thread_id,))


def approvals(status=None):
    if status:
        return q("SELECT * FROM approvals WHERE status=? ORDER BY created_at", (status,))
    return q("SELECT * FROM approvals ORDER BY created_at DESC")


def update_approval(aid, **kw):
    sets = ", ".join(f"{k}=?" for k in kw)
    ex(f"UPDATE approvals SET {sets} WHERE id=?", (*kw.values(), aid))


# --- tickets (human hand-offs & staff alerts) ---------------------------------------------
def create_ticket(event_id, team, priority, kind, summary, dedupe_key=None):
    if dedupe_key and one("SELECT id FROM tickets WHERE dedupe_key=?", (dedupe_key,)):
        return None
    tid = next_id("TKT")
    ex("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,'OPEN',?)",
       (tid, _now_iso(), event_id, team, priority, kind, summary, dedupe_key))
    log(event_id, "Hand-off", "ESCALATION", f"{tid} → {team} [{priority}] {summary}", {"ticket": tid, "kind": kind})
    return tid


def tickets(status=None):
    if status:
        return q("SELECT * FROM tickets WHERE status=? ORDER BY created_at DESC", (status,))
    return q("SELECT * FROM tickets ORDER BY created_at DESC")


def close_ticket(tid, by):
    ex("UPDATE tickets SET status='DONE' WHERE id=?", (tid,))
    log(None, "Staff", "STAFF_ACTION", f"{tid} closed by {by}")


# --- Stage 8: outbox (every outbound message) ------------------------------------------
def insert_outbox(rows, nudge_keys=()):
    with tx() as c:
        for r in rows:
            c.execute("INSERT INTO outbox(ts,event_id,audience,flight_no,recipient,channel,lang,kind,text,approved_by,approval_id) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (r["ts"], r["event_id"], r["audience"], r.get("flight_no"), r["recipient"], r["channel"], r["lang"],
                       r["kind"], r["text"], r.get("approved_by"), r.get("approval_id")))
        for k in nudge_keys:
            c.execute("INSERT OR IGNORE INTO nudges VALUES(?,?)", (k, rows[0]["ts"] if rows else ""))


def outbox(limit=500):
    return q("SELECT * FROM outbox ORDER BY id DESC LIMIT ?", (limit,))


def nudge_sent(key):
    return one("SELECT 1 x FROM nudges WHERE dedupe_key=?", (key,)) is not None


# --- lost & found ---------------------------------------------------------------------------
def found_items():
    return q("SELECT * FROM found_items WHERE status='HELD'")


def add_lost_report(event_id, category, description, zone, match_id):
    rid = next_id("LR")
    ex("INSERT INTO lost_reports VALUES(?,?,?,?,?,?,?)", (rid, _now_iso(), event_id, category, description, zone, match_id))
    return rid


# --- chat session memory (Stage 5 for travellers) ---------------------------------------------
def session_get(sid):
    r = one("SELECT data FROM sessions WHERE session_id=?", (sid,))
    return json.loads(r["data"]) if r else {}


def session_set(sid, data):
    ex("INSERT INTO sessions VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET data=excluded.data",
       (sid, json.dumps(data)))


def get_announced(fn):
    """Values passengers were last told (start-of-day schedule or last approved broadcast)."""
    return json.loads(get_setting(f"announced:{fn}", "{}"))


def set_announced(fn, values):
    cur = get_announced(fn)
    cur.update({k: v for k, v in values.items() if v is not None})
    set_setting(f"announced:{fn}", json.dumps(cur))


def audit(limit=1000):
    return q("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
