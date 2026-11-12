"""Public API used by the Streamlit app, the autopilot and the test runner."""
import json
import sqlite3
import uuid
from datetime import timedelta

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from . import clock, config, db, privacy
from . import reconcile as rc
from .workflow import build_graph

_APP = {}


def app():
    key = str(config.CKPT_PATH)
    if key not in _APP:
        config.OUT.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(key, check_same_thread=False)
        _APP[key] = (build_graph().compile(checkpointer=SqliteSaver(conn)), conn)
    return _APP[key][0]


# ----------------------------------------------------------------- setup
def init(reset=False):
    if reset:
        for g, conn in _APP.values():
            conn.close()
        _APP.clear()
        db.reset_files()
    db.init_schema()
    if db.get_setting("seeded"):
        return
    start = clock.parse(config.DEMO_START)
    clock.set_now(start)
    for f in json.loads((config.DATA / "flights.json").read_text(encoding="utf-8"))["flights"]:
        db.ex("INSERT INTO flights VALUES(?,?,?,?,?)", (f["flight_no"], f["airline"], f["direction"], f["city"], f["scheduled"]))
    seed = json.loads((config.DATA / "feeds_seed.json").read_text(encoding="utf-8"))
    for r in seed["records"]:
        r = dict(r)
        r["updated_at"] = (start - timedelta(minutes=r.pop("minutes_ago"))).isoformat()
        db.upsert_feed(r)
    for qrow in seed["queues"]:
        db.upsert_queue(qrow["checkpoint"], qrow["wait_min"], (start - timedelta(minutes=qrow["minutes_ago"])).isoformat())
    db.set_setting("feed_health", json.dumps(seed["health"]))
    for p in json.loads((config.DATA / "passengers.json").read_text(encoding="utf-8"))["passengers"]:
        seen = (start - timedelta(minutes=p["last_seen_minutes_ago"])).isoformat() if p["last_seen_zone"] else None
        db.ex("INSERT INTO passengers VALUES(?,?,?,?,?,?,?,?,?)",
              (privacy.pax_id(p["booking_ref"], p["last_name"]), p["flight_no"], p["lang"], p["mobility"],
               int(p["opted_in"]), p["channel"], privacy.mask_contact(p["channel"], p["phone"]), p["last_seen_zone"], seen))
    for it in json.loads((config.DATA / "found_items.json").read_text(encoding="utf-8"))["found_items"]:
        db.ex("INSERT INTO found_items VALUES(?,?,?,?,?, 'HELD')",
              (it["id"], it["category"], it["description"], it["zone"],
               (start - timedelta(minutes=it["found_minutes_ago"])).isoformat()))
    for f in db.all_flights():                       # baseline memory = what is confirmed at start
        r = rc.reconcile(f["flight_no"])
        rc.detect_changes(r)
        db.set_announced(f["flight_no"], {k: v["value"] for k, v in r["fields"].items() if v["state"] == "CONFIRMED"})
    db.set_setting("seeded", "1")
    db.log(None, "Setup", "SYSTEM", f"Demo initialised at {config.DEMO_START}")


# ----------------------------------------------------------------- clock & feed heartbeat
def health():
    return json.loads(db.get_setting("feed_health", "{}"))


def set_health(source, key, state):
    h = health()
    h.setdefault(source, {})
    if state == "ok":
        h[source].pop(key, None)
    else:
        h[source][key] = state
    db.set_setting("feed_health", json.dumps(h))
    db.log(None, "Staff", "STAFF_ACTION", f"Simulated feed health: {source}/{key} → {state}")


def heartbeat():
    """Healthy feeds keep re-publishing (same values, new timestamp). Down/frozen ones do not."""
    now = clock.now().isoformat()
    h = health()
    for row in db.all_feeds():
        if h.get(row["source"], {}).get(row["flight_no"]):
            continue
        rec = json.loads(row["record"])
        rec["updated_at"] = now
        db.upsert_feed(rec)
    for cp in ("PASSPORT_CONTROL", "SECURITY"):
        qrow = db.get_queue(cp)
        if qrow and not h.get("QUEUE", {}).get(cp):
            db.upsert_queue(cp, qrow["wait_min"], now)


def advance(minutes=1):
    clock.set_now(clock.now() + timedelta(minutes=minutes))
    heartbeat()


# ----------------------------------------------------------------- run the graph
def _run(event):
    eid = db.next_id("EVT")
    cfg = {"configurable": {"thread_id": eid}}
    app().invoke({"event": event, "event_id": eid}, cfg)
    return _pack(eid, cfg)


def _pack(eid, cfg):
    snap = app().get_state(cfg)
    v = snap.values
    pending = bool(snap.next)
    ap = db.approval_by_thread(eid)
    reply = next((d["text"] for d in v.get("drafts") or [] if d.get("audience") == "chat"), None)
    rec = v.get("reconciled") or {}
    return {"event_id": eid, "outcome": "PENDING_STAFF_APPROVAL" if pending else v.get("outcome"),
            "pending_approval": pending, "approval_id": ap["id"] if ap else None, "reply": reply,
            "lang": v.get("lang"), "intent": v.get("intent"), "trace": v.get("trace", []),
            "quality": rec.get("quality"), "fields": rec.get("fields"), "journey": v.get("journey"),
            "tickets": [t for t in v.get("tickets") or [] if t], "drafts": v.get("drafts") or []}


def ask(text, session=None):
    session = dict(session or {})
    session.setdefault("session_id", "S-" + uuid.uuid4().hex[:8])
    return _run({"type": "question", "text": text, "session": session})


def feed_update(record):
    record = dict(record)
    record.setdefault("updated_at", clock.now().isoformat())
    return _run({"type": "feed_update", "record": record})


def tick():
    return _run({"type": "tick"})


def decide(approval_id, decision, staff_id, note=""):
    ap = db.get_approval(approval_id)
    if not ap or ap["status"] != "PENDING":
        return {"error": f"{approval_id} is not pending"}
    cfg = {"configurable": {"thread_id": ap["thread_id"]}}
    app().invoke(Command(resume={"decision": decision, "staff_id": staff_id, "note": note}), cfg)
    return _pack(ap["thread_id"], cfg)


def expire_overdue():
    out = []
    for ap in db.approvals("PENDING"):
        if clock.now() >= clock.parse(ap["deadline"]):
            out.append(decide(ap["id"], "expire", "SYSTEM_TIMEOUT"))
    return out


# ----------------------------------------------------------------- traveller identity (privacy-preserving)
def verify_booking(booking_ref, last_name, session_id):
    tries_key = f"verify_tries:{session_id}"
    tries = int(db.get_setting(tries_key, "0"))
    if tries >= config.VERIFY_MAX_ATTEMPTS:
        return None, "locked"
    p = db.get_pax(privacy.pax_id(booking_ref, last_name))
    if not p:
        db.set_setting(tries_key, str(tries + 1))
        db.log(None, "Verify", "REFUSAL", f"Booking verification failed for session {session_id[:8]} (attempt {tries + 1})")
        return None, "no_match"
    db.log(None, "Verify", "DECISION", f"Session {session_id[:8]} linked to {p['pax_id']} (no name/ref stored)")
    return {"session_id": session_id, "pax_id": p["pax_id"], "flight_no": p["flight_no"], "lang": p["lang"],
            "mobility": p["mobility"], "location": p["last_seen_zone"]}, "ok"


def flight_board():
    rows = []
    for f in db.all_flights():
        r = rc.reconcile(f["flight_no"])
        fl = r["fields"]
        rows.append({"flight": f["flight_no"], "dir": f["direction"], "city": f["city"], "airline": f["airline"],
                     "gate/belt": fl.get("gate", fl.get("belt"))["value"] or "—",
                     "boarding": clock.hhmm(fl["boarding_time"]["value"]) if "boarding_time" in fl else "—",
                     "status": fl["status"]["value"] or "—", "quality": r["quality"],
                     "FIDS age": r["sources"]["FIDS"]["age_min"], "Airline age": r["sources"]["AIRLINE"]["age_min"],
                     "pax": db.count_pax(f["flight_no"]), "_rec": r})
    return rows
