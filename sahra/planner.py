"""Stage 3 ⇄ 4 — the planner loop.

Each turn the planner (an AI model, or the rule planner when no model is configured) either calls one
read-only tool or finishes with a routing decision. Tool results go back to the planner (ReAct loop).

Safety stays in code:
  * medical, assistance, privacy and visa requests are routed by rules before any model is asked;
  * answers to the assistant's own follow-up questions are resolved from chat memory by code;
  * every finished plan is checked: known intent, real flight, real place, and nothing the model invented
    (a flight or place must appear in the message, the traveller's context, or a tool result);
  * the model never writes passenger text — workers fill approved templates with verified data.
"""
import json
import re

from . import config, db, intents, llm, privacy
from . import reconcile as rc
from . import wayfinding as wf

MAX_TOOL_CALLS = 4
SAFETY_INTENTS = ("medical", "assistance", "privacy", "visa")
OFFICIAL = json.loads((config.DATA / "official_info.json").read_text(encoding="utf-8"))["entries"]

TOOL_DOCS = {
    "get_context": "No args. The traveller's language, linked flight (if any), known location, and what the assistant "
                   "asked them last.",
    "find_places": "No args. Places named in the traveller's message, each marked as where they ARE (origin) or "
                   "where they want to GO (destination).",
    "find_flight_by_city": "Args {\"city\": str}. Today's departures to that city.",
    "read_flight": "Args {\"flight_no\": str}. Reconciled live data: for each field, whether both feeds agree "
                   "(CONFIRMED) or not.",
    "search_official_info": "Args {\"topic\": str}. Whether published airport guidance exists on a topic.",
}
INTENT_DOCS = {
    "flight": "gate, boarding time, status, delay or cancellation of a flight",
    "walk": "how long to walk to the gate / when to leave",
    "directions": "the person is lost or asks the way to a gate or place (toilets, prayer room, info desk…)",
    "baggage": "baggage belt for an arriving flight, or a question about checked bags",
    "lost": "the person lost or left an ITEM",
    "security": "what may be carried through security (liquids, power banks, sharp items…)",
    "facility": "airport facilities (Wi-Fi, prayer rooms, family zone) without asking the way",
    "visa": "visa, transit or immigration rules", "privacy": "asks about another passenger's booking or presence",
    "medical": "health emergency", "assistance": "wheelchair / reduced-mobility help",
    "greeting": "hello, thanks, what can you do", "unknown": "anything else",
}

SYSTEM_PROMPT = (
    "You are the planning step of Sahra International Airport's passenger assistant. Each turn you either call ONE "
    "tool or finish. You never write the reply to the traveller and never state flight facts yourself — workers do "
    "that from verified data. Reply with ONE JSON object only.\n\n"
    "Tools:\n" + "\n".join(f"- {k}: {v}" for k, v in TOOL_DOCS.items()) + "\n\n"
    "To call a tool: {\"thought\": \"<short>\", \"action\": \"<tool name>\", \"args\": {...}}\n"
    "To finish: {\"thought\": \"<short>\", \"action\": \"finish\", \"intent\": \"<intent>\", "
    "\"flight_no\": <string or null>, \"origin\": <place id or null>, "
    "\"destination\": <{\"node\": \"<place id>\"} or {\"category\": \"<category>\"} or null>, "
    "\"mobility\": <\"standard\"|\"family\"|\"reduced_mobility\"|null>}\n\n"
    "Intents:\n" + "\n".join(f"- {k}: {v}" for k, v in INTENT_DOCS.items()) + "\n\n"
    "Rules: use only flight numbers and place ids that appear in the message, get_context, or a tool result. "
    "If unsure, use fewer facts — workers will ask the traveller. Use at most 3 tool calls.")


# ------------------------------------------------------------------ rule analysis (always computed)
def rule_analysis(text, sess):
    """Deterministic reading of the message, including answers to the assistant's own follow-up question."""
    intent, ents = intents.classify(text)
    ents = dict(ents)
    sid = sess.get("session_id", "anon")
    memory = db.session_get(sid)
    followup = None
    aw = memory.get("awaiting")
    if aw and intent not in SAFETY_INTENTS + ("security", "lost"):
        place = ents.get("origin") or ents.get("location")
        if not place and ents.get("destination"):
            k, v = ents["destination"]
            place = v if k == "node" else (wf.DESTS[v]["nodes"][0] if len(wf.DESTS[v]["nodes"]) == 1 else None)
        if aw == "location" and place:
            ents.update(origin=place, location=place,
                        destination=tuple(memory["dest"]) if memory.get("dest") else None)
            intent, followup = memory.get("for", "directions"), "answer to 'where are you?'"
        elif aw == "destination" and (ents.get("destination") or ents.get("flight_no")):
            ents["origin"] = ents.get("origin") or memory.get("origin")
            intent, followup = "directions", "answer to 'where do you need to go?'"
    memory.pop("awaiting", None)
    db.session_set(sid, memory)
    flight = ents.get("flight_no") or sess.get("flight_no") or memory.get("last_flight")
    return {"intent": intent, "entities": ents, "flight_no": flight, "followup": followup,
            "last_flight": memory.get("last_flight"), "awaiting": aw}


# ------------------------------------------------------------------ tools (read-only)
def _context(ctx):
    sess = ctx["session"]
    return {"language": ctx["lang"], "linked_flight": sess.get("flight_no"),
            "known_location": sess.get("location"), "known_location_name": wf.label(sess["location"]) if sess.get("location") else None,
            "last_flight_discussed": ctx["rule"]["last_flight"], "assistant_last_asked": ctx["rule"]["awaiting"]}


def _places(ctx):
    e = ctx["rule"]["entities"]
    d = e.get("destination")
    dest = None
    if d:
        dest = {"node": d[1], "name": wf.label(d[1])} if d[0] == "node" else {"category": d[1], "name": wf.DESTS[d[1]]["sign"]}
    o = e.get("origin") or e.get("location")
    return {"origin": {"id": o, "name": wf.label(o)} if o else None, "destination": dest}


def _flights_to(city):
    c = (city or "").strip().lower()
    return {"flights": [{"flight_no": f["flight_no"], "airline": f["airline"], "city": f["city"]}
                        for f in db.all_flights() if f["direction"] == "DEP" and f["city"].lower() == c]}


def _read_flight(fn):
    fn = (fn or "").upper().replace(" ", "")
    rec = rc.reconcile(fn)
    if not rec.get("exists"):
        return {"flight_no": fn, "exists": False}
    return {"flight_no": fn, "exists": True, "direction": rec["direction"], "city": rec["city"],
            "data_quality": rec["quality"], "fields": {k: v["state"] for k, v in rec["fields"].items()}}


def _official(topic):
    t = (topic or "").lower()
    hits = [e for e in OFFICIAL if e["topic"] == t or any(k.strip() and k.strip() in t for k in e["keywords"])]
    return {"entries": [{"id": e["id"], "topic": e["topic"]} for e in hits]}


def run_tool(name, args, ctx):
    args = args if isinstance(args, dict) else {}
    if name == "get_context":
        return _context(ctx)
    if name == "find_places":
        return _places(ctx)
    if name == "find_flight_by_city":
        return _flights_to(args.get("city"))
    if name == "read_flight":
        return _read_flight(args.get("flight_no"))
    if name == "search_official_info":
        return _official(args.get("topic"))
    return {"error": f"unknown tool '{name}'"}


# ------------------------------------------------------------------ planners
def rule_next(ctx, steps):
    """Deterministic planner: gathers the same evidence an LLM would, then finishes with the rule analysis."""
    r = ctx["rule"]
    wanted = []
    if r["intent"] in ("flight", "walk", "baggage", "directions") and r["flight_no"]:
        wanted.append(("read_flight", {"flight_no": r["flight_no"]}))
    e = r["entities"]
    if e.get("origin") or e.get("destination") or e.get("location"):
        wanted.append(("find_places", {}))
    if r["intent"] in ("security", "facility"):
        wanted.append(("search_official_info", {"topic": r["intent"]}))
    done = {(s["action"], json.dumps(s.get("args", {}), sort_keys=True)) for s in steps}
    for name, args in wanted:
        if (name, json.dumps(args, sort_keys=True)) not in done:
            return {"thought": "gather evidence", "action": name, "args": args}
    return rule_finish(r)


def rule_finish(r, reason="rule plan"):
    e = r["entities"]
    d = e.get("destination")
    return {"thought": reason, "action": "finish", "intent": r["intent"], "flight_no": r["flight_no"],
            "origin": e.get("origin"),
            "destination": ({"node": d[1]} if d[0] == "node" else {"category": d[1]}) if d else None,
            "mobility": e.get("mobility")}


def llm_next(ctx, steps):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"message": ctx["redacted_text"], "language": ctx["lang"]},
                                                   ensure_ascii=False)}]
    for s in steps:
        msgs.append({"role": "assistant", "content": json.dumps({k: s[k] for k in ("thought", "action", "args") if k in s},
                                                                ensure_ascii=False)})
        msgs.append({"role": "user", "content": json.dumps({"observation": s["observation"]}, ensure_ascii=False)})
    return llm.chat_json(msgs)


# ------------------------------------------------------------------ code check of a finished plan
def _norm(d):
    """('dest','food') and ('node','FOOD_COURT') are the same place."""
    if not d:
        return None
    k, v = d[0], d[1]
    if k == "dest" and v in wf.DESTS and len(wf.DESTS[v]["nodes"]) == 1:
        return ("node", wf.DESTS[v]["nodes"][0])
    return (k, v)


def check_plan(plan, ctx, steps):
    """Return (accepted_plan or None, notes). Nothing the model invented gets through."""
    notes = []
    r, sess = ctx["rule"], ctx["session"]
    intent = plan.get("intent")
    if intent not in intents.ALLOWED:
        return None, [f"unknown intent '{intent}'"]

    seen_flights = {f for f in (r["flight_no"], sess.get("flight_no"), r["last_flight"]) if f}
    rule_dest = _norm(r["entities"].get("destination"))
    seen_places = {p for p in (r["entities"].get("origin"), sess.get("location")) if p}
    loc = r["entities"].get("location")
    if loc and not (rule_dest and rule_dest == ("node", loc)):      # "where is the food court" is not "I'm at it"
        seen_places.add(loc)
    seen_dest = {rule_dest} if rule_dest else set()
    for s in steps:
        obs = s.get("observation") or {}
        for f in obs.get("flights", []):
            seen_flights.add(f["flight_no"])
        if s["action"] == "read_flight" and obs.get("exists"):
            seen_flights.add(obs["flight_no"])

    fn = plan.get("flight_no")
    if fn:
        fn = str(fn).upper().replace(" ", "")
        if not re.fullmatch(r"[A-Z]{2}\d{2,4}", fn) or not db.get_flight(fn):
            return None, [f"flight '{fn}' is not in today's schedule"]
        if fn not in seen_flights:
            return None, [f"flight {fn} was not in the message, context or any tool result (invented)"]
    origin = plan.get("origin")
    if origin:
        if origin not in wf.NODES:
            return None, [f"place '{origin}' is not on the terminal map"]
        if origin not in seen_places:
            return None, [f"origin {origin} was not stated by the traveller (invented)"]
    dest = plan.get("destination")
    dest_t = None
    if isinstance(dest, dict) and dest:
        if dest.get("node"):
            dest_t = ("node", str(dest["node"]).upper() if wf.is_gate(str(dest["node"]).upper()) else dest["node"])
            if dest_t[1] not in wf.NODES:
                return None, [f"destination '{dest_t[1]}' is not on the terminal map"]
        elif dest.get("category"):
            dest_t = ("dest", dest["category"])
            if dest_t[1] not in wf.DESTS:
                return None, [f"destination category '{dest_t[1]}' does not exist"]
        if dest_t and _norm(dest_t) not in seen_dest:
            return None, [f"destination {dest_t[1]} was not asked for by the traveller (invented)"]
    mobility = plan.get("mobility") if plan.get("mobility") in config.SPEEDS_M_PER_MIN else None
    if intent != r["intent"]:
        notes.append(f"model chose '{intent}', rules would have chosen '{r['intent']}'")
    ents = dict(r["entities"])
    ents.update(origin=origin, destination=dest_t, mobility=mobility or r["entities"].get("mobility"))
    if origin:
        ents["location"] = origin
    return {"intent": intent, "flight_no": fn, "entities": ents}, notes


def start(text, sess, lang):
    rule = rule_analysis(text, sess)
    ctx = {"session": sess, "lang": lang, "rule": rule, "redacted_text": privacy.redact_for_llm(text)}
    if rule["intent"] in SAFETY_INTENTS:
        mode = "safety"          # never ask a model about emergencies, assistance, privacy or visas
    elif rule["followup"]:
        mode = "memory"          # the traveller answered our question — resolved by code
    elif llm.available():
        mode = "llm"
    else:
        mode = "rules"
    return ctx, mode
