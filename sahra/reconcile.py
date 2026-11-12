"""Stage 4a — Flight-data reconciler (pure code, no LLM).

Reads the display system (FIDS) and the airline feed, and labels every field:
  CONFIRMED      both fresh feeds agree                    -> safe for broadcasts and answers
  SINGLE_SOURCE  only one fresh feed has the value          -> answers only, with the source named
  SYNCING        fresh feeds disagree for < grace minutes  -> never stated to passengers
  CONFLICT       fresh feeds disagree for >= grace minutes -> never stated + staff alert
  UNKNOWN        no fresh value at all                      -> never stated (+ staff alert if departing soon)
"""
import json
from datetime import timedelta

from . import clock, config, db

FIELDS = {"DEP": ["status", "gate", "boarding_time", "est_time"], "ARR": ["status", "belt", "est_time"]}
TIME_FIELDS = {"boarding_time", "est_time"}
SEVERITY = {"CONFIRMED": 0, "SINGLE_SOURCE": 1, "SYNCING": 2, "UNKNOWN": 3, "CONFLICT": 4}
SOURCES = ("FIDS", "AIRLINE")


def _norm(field, v):
    if v is None or v == "":
        return None
    if field in TIME_FIELDS:
        return clock.parse(v).isoformat()
    return str(v).upper()


def key_fields(direction, fields):
    status = fields.get("status", {}).get("value")
    if direction == "ARR":
        return ["status", "belt"]
    if status in ("CANCELLED", "DEPARTED"):
        return ["status"]
    return ["status", "gate", "boarding_time"]


def reconcile(flight_no: str) -> dict:
    f = db.get_flight(flight_no)
    if not f:
        return {"flight_no": flight_no, "exists": False}
    now = clock.now()
    sources = {}
    for src in SOURCES:
        row = db.get_feed(src, flight_no)
        if not row:
            sources[src] = {"present": False, "fresh": False, "age_min": None}
            continue
        age = round((now - clock.parse(row["updated_at"])).total_seconds() / 60, 1)
        sources[src] = {"present": True, "fresh": age <= config.FEED_STALE_MIN, "age_min": age,
                        "updated_at": row["updated_at"], "record": json.loads(row["record"])}

    fields = {}
    for fld in FIELDS[f["direction"]]:
        vals = {s: _norm(fld, info["record"].get(fld)) for s, info in sources.items()
                if info["fresh"] and info["record"].get(fld) not in (None, "")}
        entry = {"values": vals}
        if len(vals) == 2:
            if vals["FIDS"] == vals["AIRLINE"]:
                entry.update(state="CONFIRMED", value=vals["FIDS"])
                db.clear_disagreement(flight_no, fld)
            else:
                vkey = f"{vals['FIDS']}|{vals['AIRLINE']}"
                d = db.get_disagreement(flight_no, fld)
                if not d or d["values_key"] != vkey:
                    # disagreement started (at the latest) when the newer of the two records arrived
                    since = max(clock.parse(sources[s]["updated_at"]) for s in SOURCES)
                    db.set_disagreement(flight_no, fld, vkey, since.isoformat())
                    d = {"since": since.isoformat()}
                lasted = (now - clock.parse(d["since"])).total_seconds() / 60
                entry.update(state="SYNCING" if lasted < config.CONFLICT_GRACE_MIN else "CONFLICT",
                             value=None, disagree_min=round(lasted, 1))
        elif len(vals) == 1:
            src, v = next(iter(vals.items()))
            db.clear_disagreement(flight_no, fld)
            entry.update(state="SINGLE_SOURCE", value=v, source=src, age_min=sources[src]["age_min"])
        else:
            db.clear_disagreement(flight_no, fld)
            entry.update(state="UNKNOWN", value=None)
        fields[fld] = entry

    kf = key_fields(f["direction"], fields)
    quality = max((fields[k]["state"] for k in kf), key=lambda s: SEVERITY[s])
    return {"flight_no": flight_no, "exists": True, "airline": f["airline"], "direction": f["direction"], "city": f["city"],
            "scheduled": f["scheduled"], "sources": {s: {k: v for k, v in i.items() if k != "record"} for s, i in sources.items()},
            "fields": fields, "key_fields": kf, "quality": quality}


def raise_data_alerts(rec: dict, event_id: str) -> list:
    """Staff alerts for persistent conflicts and data gaps (deduplicated)."""
    out = []
    if not rec.get("exists"):
        return out
    fn = rec["flight_no"]
    for fld in rec["key_fields"]:
        e = rec["fields"][fld]
        if e["state"] == "CONFLICT":
            v = e["values"]
            tid = db.create_ticket(
                event_id, "OPS_CONTROL", "HIGH", "FEED_CONFLICT",
                f"{fn} {fld}: display system says {v.get('FIDS')} but airline feed says {v.get('AIRLINE')} "
                f"(for {e['disagree_min']} min). Passengers are told it is 'being confirmed'. Verify with airline station.",
                dedupe_key=f"conflict|{fn}|{fld}|{v.get('FIDS')}|{v.get('AIRLINE')}")
            if tid:
                out.append(tid)
    unknown = [k for k in rec["key_fields"] if rec["fields"][k]["state"] == "UNKNOWN"]
    dep = clock.parse(rec["scheduled"])
    if unknown and rec["direction"] == "DEP" and dep - clock.now() <= timedelta(minutes=config.DATA_GAP_ALERT_MIN):
        why = ", ".join(s + ": " + ("missing" if not i["present"] else "stale (%s min old)" % i["age_min"])
                        for s, i in rec["sources"].items() if not i.get("fresh"))
        tid = db.create_ticket(event_id, "OPS_CONTROL", "MEDIUM", "DATA_GAP",
                               f"{fn} {', '.join(unknown)}: no fresh value ({why or 'field not published'}). "
                               "Assistant is refusing to guess.", dedupe_key=f"gap|{fn}|{'+'.join(unknown)}")
        if tid:
            out.append(tid)
    return out


def detect_changes(rec: dict) -> list:
    """Stage 5 — compare CONFIRMED values with remembered state; update memory; return passenger-relevant changes."""
    fn = rec["flight_no"]
    base = db.get_flight_state(fn) or {}
    conf = {k: v["value"] for k, v in rec["fields"].items() if v["state"] == "CONFIRMED"}
    changes = []
    if conf.get("status") == "CANCELLED" and base.get("status") != "CANCELLED":
        changes.append({"type": "CANCELLATION", "old": base.get("status"), "new": "CANCELLED"})
    else:
        if conf.get("gate") and base.get("gate") and conf["gate"] != base["gate"]:
            changes.append({"type": "GATE_CHANGE", "old": base["gate"], "new": conf["gate"]})
        if conf.get("est_time") and base.get("est_time") and conf["est_time"] != base["est_time"]:
            if clock.parse(conf["est_time"]) - clock.parse(base["est_time"]) >= timedelta(minutes=10):
                changes.append({"type": "DELAY", "old": base["est_time"], "new": conf["est_time"]})
    if conf:
        db.update_flight_state(fn, conf)
    return changes
