"""Stage 2 + Stage 6 guardrails — deterministic Python only. No LLM ever decides what is safe to send."""
import re

from .privacy import pii_hit

INJECTION = [
    r"ignore (all |any |the )?(previous|prior|above|earlier|your) (instructions|rules|prompts?)",
    r"disregard (the |all |your )?(rules|instructions|guardrails|policy)",
    r"system prompt", r"you are now", r"developer mode", r"jailbreak", r"pretend (to be|you are)",
    r"\b(announce|broadcast|send|message)\b.{0,50}\b(all|every|everyone)\b.{0,20}\bpassengers?\b",
    r"bypass (the )?(guard|approval|safety|rules)", r"act as (an? )?(admin|staff|operator|supervisor)",
    r"drop table", r"<script", r"تجاهل (جميع |كل )?التعليمات", r"पिछले निर्देशों को अनदेखा",
]
INJ_RE = [re.compile(p, re.I) for p in INJECTION]

ALLOWED_STATES = {"flight": {"CONFIRMED"}, "individual": {"CONFIRMED"}, "chat": {"CONFIRMED", "SINGLE_SOURCE"}}


def injection_hit(text: str):
    for rx in INJ_RE:
        if rx.search(text or ""):
            return rx.pattern
    return None


def check(draft: dict):
    """Return (decision, reasons). Decisions: SEND | APPROVAL | HOLD."""
    allowed = ALLOWED_STATES[draft["audience"]]
    bad = [f for f, v in draft.get("facts", {}).items() if v["state"] not in allowed]
    if bad:
        return "HOLD", [f"Unverified data would be stated ({', '.join(bad)}) — rule: never invent or guess"]
    if draft["audience"] == "flight" and not draft.get("texts"):
        return "HOLD", ["No approved text could be produced"]
    texts = list(draft.get("texts", {}).values()) or [draft.get("text", "")]
    if any(pii_hit(t) for t in texts):
        return "HOLD", ["Message contains a booking reference or phone number — privacy rule"]
    if draft["audience"] == "flight":
        return "APPROVAL", [f"Whole-flight broadcast to {draft['recipient_count']} passengers requires staff approval"]
    return "SEND", ["Single recipient · verified data only · no personal data"]
