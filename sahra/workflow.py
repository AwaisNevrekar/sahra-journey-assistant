"""The 10-stage LangGraph workflow.

 1 Trigger        flight-feed update · traveller question · scheduled proactive scan
 2 Validate       Pydantic schemas, freshness, prompt-injection filter
 3 Coordinator    routes the event (rule router; optional LLM only for unknown questions)
 4 Workers        4a feed reconciler · 4b journey solver · 4c responder · 4d human hand-off · 4e lost & found
                  4f official-info/policy · 4g proactive nudge scan
 5 Remember       change detection vs. stored flight state · chat session memory
 6 Guard          code-only rules on every outbound draft
 7 Approval       whole-flight broadcasts pause (LangGraph interrupt) for staff sign-off; timeout = do not send
 8 Write gateway  re-checks live data, then writes every outbound message in one transaction
 9 Log            final outcome in the audit log
10 Demo           Streamlit dashboard (app.py)
"""
import json
import operator
from datetime import timedelta
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from . import clock, compose, config, db, guards, intents, llm, privacy
from . import messages as M
from . import reconcile as rc
from . import wayfinding as wf
from .schemas import FeedRecord, QuestionIn

OFFICIAL = json.loads((config.DATA / "official_info.json").read_text(encoding="utf-8"))["entries"]
ROUTES = {"medical": "handoff", "assistance": "handoff", "unknown": "handoff", "lost": "lost", "visa": "policy",
          "security": "policy", "facility": "policy", "privacy": "policy", "greeting": "policy", "flight": "flight",
          "walk": "flight", "baggage": "flight"}


class S(TypedDict, total=False):
    event: dict
    event_id: str
    lang: str
    blocked: bool
    route: str
    intent: str
    entities: dict
    flight_no: str
    reconciled: dict
    journey: dict
    drafts: list
    tickets: list
    approval: dict
    outcome: str
    trace: Annotated[list, operator.add]


def _t(stage, summary):
    return {"stage": stage, "summary": summary, "at": clock.hhmm(clock.now())}


def _session(s):
    return s["event"].get("session") or {}


def _chat_draft(s, text, kind, facts=None):
    sess = _session(s)
    return {"audience": "chat", "recipient": "chat:" + sess.get("session_id", "anon")[:8], "channel": "chat",
            "lang": s.get("lang", "en"), "kind": kind, "text": text, "facts": facts or {}}


# ---------------------------------------------------------------- 1
def n1_trigger(s: S):
    ev, eid = s["event"], s["event_id"]
    if ev["type"] == "feed_update":
        r = ev.get("record", {})
        summary = f"Feed update from {r.get('source', '?')} for {r.get('flight_no', '?')}"
    elif ev["type"] == "question":
        summary = "Traveller question received"
    else:
        summary = "Scheduled proactive journey scan"
    db.log(eid, "1 Trigger", "TRIGGER", summary, {"type": ev["type"], "text": privacy.redact_for_log(ev.get("text", ""))})
    return {"drafts": [], "tickets": [], "trace": [_t("1 Trigger", summary)]}


# ---------------------------------------------------------------- 2
def n2_validate(s: S):
    ev, eid = s["event"], s["event_id"]
    stage = "2 Validate & sanitise"
    if ev["type"] == "feed_update":
        raw = ev.get("record", {})
        try:
            rec = FeedRecord(**raw)
            if not db.get_flight(rec.flight_no):
                raise ValueError(f"flight {rec.flight_no} is not in today's schedule")
        except (ValidationError, ValueError) as e:
            errs = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()) \
                if isinstance(e, ValidationError) else str(e)
            db.log(eid, stage, "BLOCKED", f"Feed record rejected — {errs}", {"record": raw})
            tid = db.create_ticket(eid, "OPS_CONTROL", "MEDIUM", "FEED_REJECTED",
                                   f"Rejected malformed {raw.get('source')} record for {raw.get('flight_no')}: {errs}")
            return {"blocked": True, "outcome": "FEED_REJECTED_NO_CHANGE", "tickets": [tid],
                    "trace": [_t(stage, f"Rejected malformed record: {errs}. Stored data unchanged; ops alerted.")]}
        db.upsert_feed(rec.to_store())
        db.log(eid, stage, "FEED_READ", f"Accepted {rec.source} record for {rec.flight_no}", {"record": rec.to_store()})
        return {"flight_no": rec.flight_no,
                "trace": [_t(stage, f"{rec.source} record for {rec.flight_no} passed schema + timestamp checks")]}

    if ev["type"] == "question":
        sess = _session(s)
        text = ev.get("text", "")
        pref = sess.get("lang_pref")
        lang = pref if pref in config.SUPPORTED_LANGS else intents.detect_lang(text)
        try:
            QuestionIn(text=text, session_id=sess.get("session_id", "anon"))
        except ValidationError:
            d = _chat_draft({**s, "lang": lang}, M.t("blocked", lang), "blocked")
            db.log(eid, stage, "BLOCKED", "Question rejected (empty or too long)")
            return {"blocked": True, "lang": lang, "outcome": "BLOCKED_INVALID", "drafts": [d],
                    "trace": [_t(stage, "Rejected: empty or over 500 characters")]}
        hit = guards.injection_hit(text)
        if hit:
            d = _chat_draft({**s, "lang": lang}, M.t("blocked", lang), "blocked")
            db.log(eid, stage, "BLOCKED", f"Prompt-injection / unauthorised broadcast attempt blocked", {"pattern": hit})
            return {"blocked": True, "lang": lang, "outcome": "BLOCKED_INJECTION", "drafts": [d],
                    "trace": [_t(stage, "Blocked: prompt-injection / broadcast-request pattern. Nothing else runs.")]}
        return {"lang": lang, "trace": [_t(stage, f"Input OK · language={lang} · no injection patterns")]}

    return {"trace": [_t(stage, "Scan request OK")]}


# ---------------------------------------------------------------- 3
def n3_coordinator(s: S):
    ev, eid = s["event"], s["event_id"]
    stage = "3 Coordinator"
    if ev["type"] == "feed_update":
        msg = f"Feed event → reconcile {s['flight_no']} and check for passenger-relevant changes"
        db.log(eid, stage, "DECISION", msg)
        return {"route": "feed", "trace": [_t(stage, msg)]}
    if ev["type"] == "tick":
        db.log(eid, stage, "DECISION", "Scan → proactive nudge worker")
        return {"route": "tick", "trace": [_t(stage, "Proactive scan → journey nudge worker")]}

    sess = _session(s)
    intent, ents = intents.classify(ev["text"])
    via = "rules"
    if intent == "unknown" and llm.available():
        li = llm.classify(privacy.redact_for_llm(ev["text"]))
        if li and li != "unknown":
            intent, via = li, f"LLM ({llm.provider()}, redacted text)"
    memory = db.session_get(sess.get("session_id", "anon"))
    flight = ents.get("flight_no") or sess.get("flight_no") or memory.get("last_flight")
    route = ROUTES[intent]
    msg = f"Intent '{intent}' via {via} → {route} worker" + (f" · flight {flight}" if flight else "")
    db.log(eid, stage, "DECISION", msg, {"intent": intent, "entities": ents})
    return {"route": route, "intent": intent, "entities": ents, "flight_no": flight, "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 4a
def n4a_reconcile(s: S):
    eid, fn = s["event_id"], s.get("flight_no")
    stage = "4a Feed reconciler"
    if not fn:
        return {"reconciled": None, "trace": [_t(stage, "No flight identified — nothing to read")]}
    rec = rc.reconcile(fn)
    if not rec["exists"]:
        db.log(eid, stage, "DECISION", f"{fn} not in today's schedule")
        return {"reconciled": rec, "trace": [_t(stage, f"{fn} is not in today's schedule")]}
    for src, i in rec["sources"].items():
        state = "missing" if not i["present"] else f"{i['age_min']} min old" + ("" if i["fresh"] else " → STALE, ignored")
        db.log(eid, stage, "FEED_READ", f"Read {src} feed for {fn}: {state}", i)
    new_t = rc.raise_data_alerts(rec, eid)
    states = ", ".join(f"{k}={rec['fields'][k]['state']}" for k in rec["key_fields"])
    msg = f"{fn}: {states} → overall {rec['quality']}" + (f" · staff alerted {', '.join(new_t)}" if new_t else "")
    db.log(eid, stage, "DECISION", msg, {"fields": rec["fields"]})
    return {"reconciled": rec, "tickets": (s.get("tickets") or []) + new_t, "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 4b
def n4b_journey(s: S):
    eid, rec = s["event_id"], s.get("reconciled")
    stage = "4b Journey solver"
    sess, ents = _session(s), s.get("entities") or {}
    if not rec or not rec.get("exists") or rec["direction"] != "DEP" or s.get("intent") == "baggage":
        return {"journey": None, "trace": [_t(stage, "Not needed for this request")]}
    origin = ents.get("location") or sess.get("location")
    if s.get("intent") != "walk" and not (sess.get("pax_id") and origin and sess.get("flight_no") == rec["flight_no"]):
        return {"journey": None, "trace": [_t(stage, "Not needed for this request")]}
    if not origin:
        return {"journey": {"needs_location": True}, "trace": [_t(stage, "Location unknown → ask traveller")]}
    g, b = rec["fields"]["gate"], rec["fields"]["boarding_time"]
    if g["state"] not in compose.CHAT_OK or b["state"] not in compose.CHAT_OK:
        msg = "Gate/boarding not verified → no walking plan (won't plan to an unverified gate)"
        db.log(eid, stage, "DECISION", msg)
        return {"journey": None, "trace": [_t(stage, msg)]}
    mobility = ents.get("mobility") or sess.get("mobility") or "standard"
    p = wf.plan(origin, g["value"], b["value"], mobility)
    msg = (f"{p['origin_label']} → Gate {p['gate']}: {p['distance_m']} m, {p['walk_min']} min ({mobility}), "
           f"queues +{p['queue_min']} min" + (f", unknown at {', '.join(p['queues_unknown'])}" if p["queues_unknown"] else "")
           + f" → leave by {clock.hhmm(p['leave_by'])} [{p['status']}]")
    db.log(eid, stage, "DECISION", msg, p)
    return {"journey": p, "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 4c
def n4c_respond(s: S):
    eid, lang, rec = s["event_id"], s.get("lang", "en"), s.get("reconciled")
    stage = "4c Responder"
    if not rec:
        d = _chat_draft(s, M.t("need_flight", lang), "clarify")
        return {"drafts": [d], "outcome": "ASKED_FOR_FLIGHT", "trace": [_t(stage, "Asked traveller for flight number")]}
    text, facts = compose.flight_answer(rec, lang, s.get("journey"))
    tickets = list(s.get("tickets") or [])
    j = s.get("journey") or {}
    if j.get("status") == "AT_RISK":
        tid = db.create_ticket(eid, "GATE_TEAM", "HIGH", "AT_RISK_PASSENGER",
                               f"Passenger for {rec['flight_no']} at {j['origin_label']} may miss boarding at Gate {j['gate']}",
                               dedupe_key=f"atrisk|{_session(s).get('pax_id', eid)}|{rec['flight_no']}")
        tickets += [tid] if tid else []
    if not rec.get("exists"):
        outcome = "ANSWERED_FLIGHT_NOT_FOUND"
    elif not facts:
        outcome = "REFUSED_TO_GUESS"
    elif rec["quality"] in ("CONFIRMED", "SINGLE_SOURCE"):
        outcome = "ANSWERED"
    else:
        outcome = "ANSWERED_PARTIAL_NO_GUESS"
    d = _chat_draft(s, text, "answer", facts)
    msg = f"Reply built from template with {len(facts)} verified field(s); withheld: " + (
        ", ".join(k for k in rec.get("key_fields", []) if k not in facts) or "none")
    db.log(eid, stage, "DECISION", msg)
    return {"drafts": [d], "tickets": tickets, "outcome": outcome, "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 4d
def n4d_handoff(s: S):
    eid, lang, intent = s["event_id"], s.get("lang", "en"), s["intent"]
    stage = "4d Human hand-off"
    sess, ents = _session(s), s.get("entities") or {}
    loc = ents.get("location") or sess.get("location")
    where = wf.label(loc) if loc else M.t("where_unknown", lang)
    where_staff = wf.label(loc) if loc else "location not given"
    q = privacy.redact_for_log(s["event"]["text"])
    flight = f" · flight {s['flight_no']}" if s.get("flight_no") else ""
    if intent == "medical":
        tid = db.create_ticket(eid, "MEDICAL + DUTY_MANAGER", "URGENT", "MEDICAL",
                               f"Medical request at {where_staff}{flight}: \"{q}\"")
        text, outcome = M.t("handoff_medical", lang, ticket=tid, where=where), "ESCALATED_MEDICAL_URGENT"
    elif intent == "assistance":
        tid = db.create_ticket(eid, "PRM_ASSIST", "HIGH", "ASSISTANCE",
                               f"Reduced-mobility assistance at {where_staff}{flight}: \"{q}\"")
        text, outcome = M.t("handoff_assist", lang, ticket=tid, where=where), "ESCALATED_ASSISTANCE"
    else:
        tid = db.create_ticket(eid, "INFO_DESK", "NORMAL", "UNANSWERED_QUESTION", f"Traveller asked: \"{q}\"")
        text, outcome = M.t("handoff_unknown", lang, ticket=tid), "ESCALATED_UNKNOWN"
    msg = f"No automated decision — handed to humans immediately ({tid})"
    return {"drafts": [_chat_draft(s, text, "handoff")], "tickets": [tid], "outcome": outcome, "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 4e
LOST_CATS = {"bag": ["backpack", "bag", "handbag", "suitcase", "حقيبة", "बैग"], "phone": ["phone", "mobile", "هاتف", "फोन"],
             "wallet": ["wallet", "purse", "محفظة", "बटुआ"], "jacket": ["jacket", "coat", "سترة", "जैकेट"],
             "passport": ["passport", "جواز", "पासपोर्ट"], "laptop": ["laptop", "حاسوب", "लैपटॉप"]}
COLOURS = ["black", "white", "blue", "grey", "gray", "red", "green", "brown"]


def n4e_lost(s: S):
    eid, lang = s["event_id"], s.get("lang", "en")
    stage = "4e Lost & found matcher"
    text = s["event"]["text"].lower()
    cat = next((c for c, words in LOST_CATS.items() if any(w in text for w in words)), "other")
    zone = (s.get("entities") or {}).get("location")
    colours = {c for c in COLOURS if c in text}
    match = None
    for item in db.found_items():
        if item["category"] != cat:
            continue
        score = (2 if zone and item["zone"] == zone else 0) + len(colours & set(item["description"].split()))
        if score >= 2:
            match = item["id"]
            break
    rid = db.add_lost_report(eid, cat, privacy.redact_for_log(s["event"]["text"]), zone, match)
    tid = db.create_ticket(eid, "LOST_FOUND", "NORMAL", "LOST_ITEM",
                           f"Report {rid}: {cat} lost at {wf.label(zone) if zone else 'unknown place'}"
                           + (f" — possible match {match}, verify ownership in person" if match else " — no match yet"))
    text_out = M.t("lost_logged", lang, ref=rid, match=M.t("lost_match" if match else "lost_nomatch", lang))
    msg = f"Category={cat}, zone={zone or '?'} → " + (f"possible match {match}; staff must verify ownership" if match else "no match")
    db.log(eid, stage, "DECISION", msg)
    return {"drafts": [_chat_draft(s, text_out, "lost")], "tickets": [tid],
            "outcome": "LOGGED_MATCH_TO_STAFF" if match else "LOGGED_NO_MATCH", "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 4f
def n4f_policy(s: S):
    eid, lang, intent = s["event_id"], s.get("lang", "en"), s["intent"]
    stage = "4f Official info & policy"
    low = " " + s["event"]["text"].lower() + " "
    if intent == "privacy":
        text, outcome, msg = M.t("refuse_privacy", lang), "REFUSED_PRIVACY", "Refused: request for another person's travel data"
    elif intent == "visa":
        text, outcome, msg = M.t("refuse_visa", lang), "REFUSED_VISA_REFERRED_OFFICIAL", \
            "Refused: visa/immigration is not answered beyond official sources"
    elif intent == "greeting":
        text, outcome, msg = M.t("greeting", lang), "ANSWERED", "Greeting / help menu"
    else:
        topic = "security" if intent == "security" else "facility"
        entry = next((e for e in OFFICIAL if e["topic"] == topic and any(k in low for k in e["keywords"])), None)
        if entry:
            body = entry["text"].get(lang, entry["text"]["en"])
            key = "official_info" if topic == "security" else "facility_info"
            text = M.t(key, lang, source=entry["source"], reviewed=entry.get("reviewed", ""), text=body)
            outcome, msg = "ANSWERED_OFFICIAL_ONLY", f"Quoted published entry {entry['id']} verbatim — no interpretation"
        else:
            text, outcome, msg = M.t("no_official", lang), "REFUSED_NO_OFFICIAL_SOURCE", "No published entry → refused to guess"
    kind = "REFUSAL" if outcome.startswith("REFUSED") else "DECISION"
    db.log(eid, stage, kind, msg)
    return {"drafts": [_chat_draft(s, text, "policy")], "outcome": outcome, "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 4g
def n4g_nudge_scan(s: S):
    eid = s["event_id"]
    stage = "4g Proactive nudge scan"
    now = clock.now()
    drafts, tickets, skipped, checked = [], [], [], 0
    cache = {}
    for p in db.all_pax():
        if not p["opted_in"] or not p["last_seen_zone"] or not p["last_seen_at"]:
            continue
        if clock.minutes_since(p["last_seen_at"]) > config.LOCATION_MAX_AGE_MIN:
            continue
        fn = p["flight_no"]
        rec = cache.get(fn) or cache.setdefault(fn, rc.reconcile(fn))
        if rec["direction"] != "DEP" or rec["fields"]["status"].get("value") in ("CANCELLED", "DEPARTED", "GATE_CLOSED"):
            continue
        checked += 1
        g, b = rec["fields"]["gate"], rec["fields"]["boarding_time"]
        if g["state"] != "CONFIRMED" or b["state"] != "CONFIRMED":
            skipped.append(f"{fn} ({rec['quality']})")
            continue
        told = db.get_announced(fn)
        if told.get("gate") != g["value"] or told.get("boarding_time") != b["value"]:
            # a change exists that staff have not yet approved for announcement → don't leak it via personal nudges
            skipped.append(f"{fn} (change awaiting staff-approved announcement)")
            continue
        plan = wf.plan(p["last_seen_zone"], g["value"], b["value"], p["mobility"])
        if plan["status"] == "ON_TRACK":
            continue
        key = f"nudge|{p['pax_id']}|{fn}|{g['value']}|{b['value']}"
        if db.nudge_sent(key):
            continue
        lang = p["lang"] if p["lang"] in config.SUPPORTED_LANGS else "en"
        text = M.t("nudge", lang, flight=fn, boarding=clock.hhmm(b["value"]), gate=g["value"], walk=plan["walk_min"],
                   origin=plan["origin_label"])
        if plan["status"] == "AT_RISK":
            text = M.t("at_risk", lang, gate=g["value"], boarding=clock.hhmm(b["value"]), walk=plan["walk_min"])
            tid = db.create_ticket(eid, "GATE_TEAM", "HIGH", "AT_RISK_PASSENGER",
                                   f"{fn}: passenger {p['pax_id']} at {plan['origin_label']} may miss boarding at Gate {g['value']}",
                                   dedupe_key=f"atrisk|{p['pax_id']}|{fn}")
            tickets += [tid] if tid else []
        if p["mobility"] == "reduced_mobility":
            text += M.t("nudge_prm", lang)
            tid = db.create_ticket(eid, "PRM_ASSIST", "HIGH", "PRM_EN_ROUTE",
                                   f"{fn}: reduced-mobility passenger {p['pax_id']} at {plan['origin_label']} must leave now "
                                   f"for Gate {g['value']} ({plan['walk_min']} min walk) — offer buggy",
                                   dedupe_key=f"prm|{p['pax_id']}|{fn}|{g['value']}")
            tickets += [tid] if tid else []
        drafts.append({"audience": "individual", "recipient": p["contact_masked"], "pax_id": p["pax_id"],
                       "channel": p["contact_masked"].split(":")[0], "lang": lang, "kind": "NUDGE", "flight_no": fn,
                       "text": text, "nudge_key": key,
                       "facts": {"gate": {"state": "CONFIRMED", "value": g["value"]},
                                 "boarding_time": {"state": "CONFIRMED", "value": b["value"]}}})
    msg = (f"Checked {checked} located passengers · {len(drafts)} due a leave-now/at-risk nudge"
           + (f" · skipped (data not confirmed or not yet announced): {', '.join(sorted(set(skipped)))}" if skipped else ""))
    db.log(eid, stage, "DECISION", msg)
    return {"drafts": drafts, "tickets": tickets, "outcome": f"NUDGES_SENT:{len(drafts)}" if drafts else "NO_ACTION_NEEDED",
            "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 5
def n5_state(s: S):
    eid = s["event_id"]
    stage = "5 Remember state"
    if s.get("route") == "feed":
        rec = s["reconciled"]
        changes = rc.detect_changes(rec)
        drafts = compose.broadcast_drafts(rec, changes) if changes else []
        if changes:
            msg = "Change detected: " + "; ".join(d["summary"] for d in drafts) + f" → {len(drafts)} broadcast draft(s)"
            outcome = None
        else:
            msg = f"No passenger-relevant change (quality {rec['quality']}); confirmed values remembered"
            outcome = "CONFLICT_ESCALATED_NO_BROADCAST" if rec["quality"] == "CONFLICT" else \
                ("SYNCING_WAIT_NO_BROADCAST" if rec["quality"] == "SYNCING" else "STATE_UPDATED_NO_BROADCAST")
        db.log(eid, stage, "DECISION", msg, {"changes": changes})
        return {"drafts": drafts, **({"outcome": outcome} if outcome else {}), "trace": [_t(stage, msg)]}
    if s["event"]["type"] == "question" and s.get("flight_no"):
        sid = _session(s).get("session_id", "anon")
        mem = db.session_get(sid)
        mem["last_flight"] = s["flight_no"]
        db.session_set(sid, mem)
        return {"trace": [_t(stage, f"Session remembers flight {s['flight_no']} for follow-up questions")]}
    return {"trace": [_t(stage, "Nothing new to remember")]}


# ---------------------------------------------------------------- 6
def n6_guard(s: S):
    eid = s["event_id"]
    stage = "6 Guard (code only)"
    drafts, tickets, notes = s.get("drafts") or [], list(s.get("tickets") or []), []
    for d in drafts:
        dec, reasons = guards.check(d)
        if dec == "HOLD" and d["audience"] == "chat":
            d.update(text=M.t("held_fallback", d["lang"]), facts={})
            dec, reasons = "SEND", reasons + ["replaced with safe fallback"]
        if dec == "HOLD" and d["audience"] == "flight":
            tid = db.create_ticket(eid, "OPS_CONTROL", "HIGH", "BROADCAST_HELD",
                                   f"{d['flight_no']} {d['summary']}: broadcast held — {reasons[0]}",
                                   dedupe_key=f"held|{d['flight_no']}|{d['summary']}")
            tickets += [tid] if tid else []
        d["decision"], d["reasons"] = dec, reasons
        db.log(eid, stage, "DECISION", f"{d['audience']} {d['kind']}: {dec} — {reasons[0]}")
        notes.append(f"{d['audience']}/{d['kind']} → {dec}")
    msg = "; ".join(notes) or "No outbound drafts"
    return {"drafts": drafts, "tickets": tickets, "trace": [_t(stage, msg)]}


def route_after_guard(s: S):
    return "approval" if any(d.get("decision") == "APPROVAL" for d in s.get("drafts") or []) else "send"


# ---------------------------------------------------------------- 7
def n7_approval(s: S):
    eid, drafts = s["event_id"], s["drafts"]
    stage = "7 Staff approval"
    pend = [d for d in drafts if d["decision"] == "APPROVAL"]
    fn = pend[0]["flight_no"]
    previews = {f"{d['summary']} [{l}]": t for d in pend for l, t in d["texts"].items()}
    aid, created = db.create_approval_once(
        eid, flight_no=fn, change_types=[d["kind"] for d in pend], summary="; ".join(d["summary"] for d in pend),
        recipients=max(d["recipient_count"] for d in pend), langs=sorted({l for d in pend for l in d["langs"]}),
        previews=previews, deadline=(clock.now() + timedelta(minutes=config.APPROVAL_TIMEOUT_MIN)).isoformat())
    if created:
        db.log(eid, stage, "APPROVAL", f"{aid}: waiting for staff approval to broadcast to {fn} "
                                       f"(expires in {config.APPROVAL_TIMEOUT_MIN} min, default = do not send)")

    resp = interrupt({"approval_id": aid, "flight_no": fn})   # ⏸ durable pause (Stage 9 wait & resume)

    decision, staff, note = resp.get("decision"), resp.get("staff_id", "?"), resp.get("note", "")
    new = {"approve": "SEND", "reject": "REJECTED"}.get(decision, "EXPIRED")
    for d in drafts:
        if d["decision"] == "APPROVAL":
            d["decision"] = new
            d["approved_by"], d["approval_id"] = (staff, aid) if new == "SEND" else (None, aid)
    db.update_approval(aid, status={"SEND": "APPROVED", "REJECTED": "REJECTED", "EXPIRED": "EXPIRED"}[new],
                       decided_by=staff, decided_at=clock.now().isoformat(), note=note)
    tickets = list(s.get("tickets") or [])
    if new == "EXPIRED":
        tid = db.create_ticket(eid, "DUTY_MANAGER", "HIGH", "APPROVAL_TIMEOUT",
                               f"{aid} for {fn} ({pend[0]['summary']}) was not approved in time — NOT sent. "
                               "Screens/PA remain the source; decide manually.")
        tickets.append(tid)
    msg = {"SEND": f"{aid} approved by {staff}", "REJECTED": f"{aid} rejected by {staff}" + (f" ({note})" if note else ""),
           "EXPIRED": f"{aid} timed out → safe default: NOT sent, duty manager alerted"}[new]
    db.log(eid, stage, "APPROVAL", msg)
    outcome = {"SEND": None, "REJECTED": "BROADCAST_REJECTED_NOT_SENT", "EXPIRED": "BROADCAST_EXPIRED_NOT_SENT"}[new]
    return {"drafts": drafts, "tickets": tickets, "approval": {"id": aid, "decision": new, "by": staff},
            **({"outcome": outcome} if outcome else {}), "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 8
def n8_gateway(s: S):
    eid = s["event_id"]
    stage = "8 Write gateway"
    ts = clock.now().isoformat()
    rows, nudge_keys, notes, outcome = [], [], [], s.get("outcome")
    for d in s.get("drafts") or []:
        if d.get("decision") != "SEND":
            continue
        if d["audience"] == "flight":
            fresh = rc.reconcile(d["flight_no"])
            stale = [f for f, v in d["facts"].items()
                     if fresh["fields"][f]["state"] != "CONFIRMED" or fresh["fields"][f]["value"] != v["value"]]
            if stale:
                d["decision"] = "ABORTED_STALE"
                db.update_approval(d["approval_id"], status="ABORTED_STALE",
                                   note=f"live data changed before sending ({', '.join(stale)})")
                db.log(eid, stage, "DECISION", f"Re-check failed for {d['flight_no']} ({', '.join(stale)} changed) → NOT sent; "
                                               "newer feed event drafts a fresh message")
                notes.append(f"{d['flight_no']} broadcast aborted (data changed after approval)")
                outcome = "BROADCAST_ABORTED_STALE_DATA"
                continue
            recips = db.pax_for_flight(d["flight_no"], opted_only=True)
            for p in recips:
                lang = p["lang"] if p["lang"] in d["texts"] else "en"
                rows.append({"ts": ts, "event_id": eid, "audience": "flight", "flight_no": d["flight_no"],
                             "recipient": p["contact_masked"], "channel": p["contact_masked"].split(":")[0], "lang": lang,
                             "kind": d["kind"], "text": d["texts"][lang], "approved_by": d["approved_by"],
                             "approval_id": d["approval_id"]})
            db.update_approval(d["approval_id"], status="SENT")
            db.set_announced(d["flight_no"], {f: v["value"] for f, v in d["facts"].items()})
            notes.append(f"{d['kind']} sent to {len(recips)} passengers on {d['flight_no']} (approved by {d['approved_by']})")
            outcome = "BROADCAST_SENT"
        else:
            rows.append({"ts": ts, "event_id": eid, "audience": d["audience"], "flight_no": d.get("flight_no"),
                         "recipient": d["recipient"], "channel": d.get("channel", "chat"), "lang": d["lang"],
                         "kind": d["kind"], "text": d["text"], "approved_by": "AUTO (guard passed)"})
            if d.get("nudge_key"):
                nudge_keys.append(d["nudge_key"])
    if rows:
        db.insert_outbox(rows, nudge_keys)   # one atomic transaction
        for kind in sorted({r["kind"] for r in rows}):
            n = sum(1 for r in rows if r["kind"] == kind)
            db.log(eid, stage, "MESSAGE_SENT", f"{n} × {kind} message(s) written to outbox", {"count": n})
    individual = sum(1 for r in rows if r["audience"] == "individual")
    if individual:
        notes.append(f"{individual} individual nudge(s) sent")
    if any(r["audience"] == "chat" for r in rows):
        notes.append("reply delivered to traveller")
    msg = "; ".join(notes) or "Nothing to send"
    return {"drafts": s.get("drafts") or [], **({"outcome": outcome} if outcome else {}), "trace": [_t(stage, msg)]}


# ---------------------------------------------------------------- 9
def n9_log(s: S):
    outcome = s.get("outcome") or "NO_ACTION"
    tickets = [t for t in (s.get("tickets") or []) if t]
    msg = f"Outcome {outcome}" + (f" · human tickets: {', '.join(tickets)}" if tickets else "")
    db.log(s["event_id"], "9 Log & report", "OUTCOME", msg, {"outcome": outcome, "tickets": tickets})
    return {"outcome": outcome, "trace": [_t("9 Log & report", msg)]}


def build_graph():
    g = StateGraph(S)
    for name, fn in [("n1_trigger", n1_trigger), ("n2_validate", n2_validate), ("n3_coordinator", n3_coordinator),
                     ("n4a_reconcile", n4a_reconcile), ("n4b_journey", n4b_journey), ("n4c_respond", n4c_respond),
                     ("n4d_handoff", n4d_handoff), ("n4e_lost", n4e_lost), ("n4f_policy", n4f_policy),
                     ("n4g_nudge_scan", n4g_nudge_scan), ("n5_state", n5_state), ("n6_guard", n6_guard),
                     ("n7_approval", n7_approval), ("n8_gateway", n8_gateway), ("n9_log", n9_log)]:
        g.add_node(name, fn)
    g.add_edge(START, "n1_trigger")
    g.add_edge("n1_trigger", "n2_validate")
    g.add_conditional_edges("n2_validate", lambda s: "blocked" if s.get("blocked") else "ok",
                            {"blocked": "n6_guard", "ok": "n3_coordinator"})
    g.add_conditional_edges("n3_coordinator", lambda s: s["route"],
                            {"feed": "n4a_reconcile", "flight": "n4a_reconcile", "tick": "n4g_nudge_scan",
                             "handoff": "n4d_handoff", "lost": "n4e_lost", "policy": "n4f_policy"})
    g.add_conditional_edges("n4a_reconcile", lambda s: "feed" if s["route"] == "feed" else "flight",
                            {"feed": "n5_state", "flight": "n4b_journey"})
    g.add_edge("n4b_journey", "n4c_respond")
    for n in ("n4c_respond", "n4d_handoff", "n4e_lost", "n4f_policy", "n4g_nudge_scan"):
        g.add_edge(n, "n5_state")
    g.add_edge("n5_state", "n6_guard")
    g.add_conditional_edges("n6_guard", route_after_guard, {"approval": "n7_approval", "send": "n8_gateway"})
    g.add_edge("n7_approval", "n8_gateway")
    g.add_edge("n8_gateway", "n9_log")
    g.add_edge("n9_log", END)
    return g
