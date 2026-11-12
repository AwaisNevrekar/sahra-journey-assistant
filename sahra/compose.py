"""Stage 4c — Builds passenger messages from verified facts only. Each draft carries the facts it used,
so the Stage 6 guard can prove nothing unverified is being said."""
from . import clock, db
from . import messages as M

CHAT_OK = {"CONFIRMED", "SINGLE_SOURCE"}


def flight_answer(rec, lang, journey=None):
    fn = rec["flight_no"]
    if not rec.get("exists"):
        return M.t("flight_not_found", lang, flight=fn), {}
    d, f = rec["direction"], rec["fields"]
    facts, parts, unconfirmed, unknown, single = {}, [], [], [], {}
    order = ["gate", "boarding_time", "status", "est_time"] if d == "DEP" else ["belt", "status", "est_time"]
    for fld in order:
        e = f[fld]
        if e["state"] in CHAT_OK:
            key = f"frag_{fld}_{d}" if fld == "est_time" else f"frag_{fld}"
            parts.append(M.t(key, lang, v=M.fmt(fld, e["value"], lang)))
            facts[fld] = {"state": e["state"], "value": e["value"]}
            if e["state"] == "SINGLE_SOURCE":
                single[e["source"]] = e["age_min"]
        elif fld in rec["key_fields"]:
            (unconfirmed if e["state"] in ("SYNCING", "CONFLICT") else unknown).append(fld)

    if not parts:
        return M.t("data_unknown", lang, flight=fn), {}
    head = M.t("head_dep" if d == "DEP" else "head_arr", lang, flight=fn, city=rec["city"])
    lines = [head + ": " + " · ".join(parts)]
    if f["status"].get("value") == "CANCELLED" and "status" in facts:
        lines.append(M.t("cancelled_advice", lang, airline=rec["airline"]))
    if unconfirmed:
        line = M.t("unconfirmed", lang, fields=M.fields_label(unconfirmed, lang), flight=fn)
        if any(f[x]["state"] == "CONFLICT" for x in unconfirmed):
            line += " " + M.t("staff_alerted", lang)
        lines.append(line)
    if unknown:
        lines.append(M.t("unknown_fields", lang, fields=M.fields_label(unknown, lang), flight=fn))
    for src, age in single.items():
        lines.append(M.t("single_source_note", lang, source=src, age=round(age)))
    if journey:
        lines.append(journey_text(journey, lang))
    return "\n".join(lines), facts


def journey_text(j, lang):
    if j.get("needs_location"):
        return M.t("ask_location", lang)
    if j.get("status") == "AT_RISK":
        return M.t("at_risk", lang, gate=j["gate"], boarding=clock.hhmm(j["boarding"]), walk=j["walk_min"])
    if j.get("status") == "LEAVE_NOW":
        return M.t("leave_now", lang, gate=j["gate"], boarding=clock.hhmm(j["boarding"]), walk=j["walk_min"])
    queue = "".join(M.t("queue_known", lang, q=k["wait_min"], cp=k["checkpoint"]) for k in j["queues_known"])
    queue += "".join(M.t("queue_unknown", lang, cp=u) for u in j["queues_unknown"])
    return M.t("walk_plan", lang, origin=j["origin_label"], gate=j["gate"], walk=j["walk_min"], distance=j["distance_m"],
               queue=queue, leave_by=clock.hhmm(j["leave_by"]), boarding=clock.hhmm(j["boarding"]))


def broadcast_drafts(rec, changes):
    """One draft per change, pre-translated for every language on the flight."""
    fn, f = rec["flight_no"], rec["fields"]
    recipients = db.pax_for_flight(fn, opted_only=True)
    langs = sorted({p["lang"] if p["lang"] in M.T["bc_gate"] else "en" for p in recipients}) or ["en"]
    told = db.get_announced(fn)          # what passengers were last told, so "was ..." is never a value they never saw
    drafts = []
    for ch in changes:
        ch = dict(ch)
        field = {"GATE_CHANGE": "gate", "DELAY": "est_time"}.get(ch["type"])
        if field and told.get(field):
            ch["old"] = told[field]
        if ch["type"] == "GATE_CHANGE":
            need = ["gate", "boarding_time"]
            key, kw = "bc_gate", lambda l: dict(new=ch["new"], old=ch["old"], boarding=M.fmt("boarding_time", f["boarding_time"]["value"]))
            summary = f"Gate change {ch['old']} → {ch['new']}"
        elif ch["type"] == "DELAY":
            need = ["est_time", "boarding_time"]
            key, kw = "bc_delay", lambda l: dict(new=clock.hhmm(ch["new"]), old=clock.hhmm(ch["old"]),
                                                  boarding=M.fmt("boarding_time", f["boarding_time"]["value"]))
            summary = f"Delay: departure {clock.hhmm(ch['old'])} → {clock.hhmm(ch['new'])}"
        else:
            need = ["status"]
            key, kw = "bc_cancel", lambda l: dict(airline=rec["airline"])
            summary = "Cancellation"
        facts = {x: {"state": f[x]["state"], "value": f[x]["value"]} for x in need}
        texts = {}
        if all(v["state"] == "CONFIRMED" for v in facts.values()):
            texts = {l: M.t(key, l, flight=fn, city=rec["city"], **kw(l)) for l in langs}
        drafts.append({"audience": "flight", "flight_no": fn, "kind": ch["type"], "summary": summary, "change": ch,
                       "facts": facts, "texts": texts, "langs": langs, "recipient_count": len(recipients)})
    return drafts
