"""Privacy by design: hashing, masking and redaction. Raw names / booking refs never enter agent state, logs or an LLM."""
import hashlib
import re

from . import config

# 6-char booking reference: letters + digits mixed (flight numbers like SA204 are 5 chars, so they never match)
REF_RE = re.compile(r"\b(?=[A-Za-z0-9]{6}\b)(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{6}\b")
PHONE_RE = re.compile(r"\+?\d[\d\s-]{8,}\d")
FLIGHT_LIKE = re.compile(r"[A-Za-z]{2}\d{4}")   # SA1234 is a flight number, not a booking reference
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:[ -](?:Al-)?[A-Z][a-z]+)+\b")
SAFE_PHRASES = {"Food Court", "Central Plaza", "Duty Free", "Family Zone", "Prayer Room", "Check-in Hall", "Passport Control",
                "Sahra Air", "Dunes Express", "Oasis Regional", "Lost Found", "Arrivals Hall", "Hand Luggage"}


def pax_id(booking_ref: str, last_name: str) -> str:
    raw = f"{booking_ref.strip().upper()}|{last_name.strip().lower()}|{config.PRIVACY_SALT}"
    return "PAX-" + hashlib.sha256(raw.encode()).hexdigest()[:10]


def mask_contact(channel: str, phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    return f"{channel}:+{digits[:3]} •• ••• {digits[-3:]}" if digits else f"{channel}:unknown"


SELF_NAME_RE = re.compile(r"\b(my name is|i am|i'm|im|this is)\s+([A-Z][a-z]+)", re.I)
NOT_NAMES = {"lost", "at", "near", "in", "on", "flying", "going", "here", "looking", "travelling", "traveling", "with",
             "from", "sorry", "not", "so", "very", "late", "stuck", "waiting", "trying", "sure", "the", "a", "an",
             "blind", "deaf", "sick", "ok", "okay", "fine", "new", "alone", "outside", "inside", "by", "next"}


def redact_for_log(text: str) -> str:
    if not text:
        return ""
    t = REF_RE.sub(lambda m: m.group(0) if FLIGHT_LIKE.fullmatch(m.group(0)) else "[REF]", text)
    t = PHONE_RE.sub(lambda m: m.group(0) if DATE_RE.fullmatch(m.group(0).strip()) else "[PHONE]", t)
    t = NAME_RE.sub(lambda m: m.group(0) if m.group(0) in SAFE_PHRASES else "[NAME]", t)
    return SELF_NAME_RE.sub(lambda m: m.group(0) if m.group(2).lower() in NOT_NAMES or not m.group(2)[0].isupper()
                            else f"{m.group(1)} [NAME]", t)


redact_for_llm = redact_for_log


def pii_hit(text: str) -> bool:
    """Guard check: an outbound message must never carry a booking ref or phone number."""
    t = DATE_RE.sub("", text or "")   # dates (e.g. 'reviewed 2026-09-01') are not phone numbers
    refs = [m.group(0) for m in REF_RE.finditer(t) if not FLIGHT_LIKE.fullmatch(m.group(0))]
    return bool(refs or PHONE_RE.search(t))
