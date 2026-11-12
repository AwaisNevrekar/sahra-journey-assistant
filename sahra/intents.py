"""Stage 3 helper — deterministic intent router (EN / AR / HI). An optional LLM is consulted only for 'unknown'.

Order matters: safety first (medical, assistance, privacy), then refusals (visa), then the specific
intents, then the broad ones. tests/question_bank.py holds ~100 real phrasings that must route correctly.
"""
import re

from . import db, wayfinding

ALLOWED = ["medical", "assistance", "privacy", "visa", "security", "lost", "baggage", "directions", "walk", "flight",
           "facility", "greeting", "unknown"]

KW = {
    "medical": ["chest pain", "heart attack", "unconscious", "fainted", "faint", "bleeding", "can't breathe",
                "cannot breathe", "not breathing", "trouble breathing", "seizure", "ambulance", "doctor", "medical emergency",
                "collapsed", "allergic reaction", "injured", "very sick", "feel sick", "feeling sick", "feel very sick",
                "vomiting", "hurt myself", "emergency", "إسعاف", "طبيب", "ألم في الصدر", "نزيف", "إغماء", "حالة طارئة",
                "مريض جدا", "एम्बुलेंस", "डॉक्टर", "सीने में दर्द", "बेहोश", "खून", "बहुत बीमार"],
    "assistance": ["wheelchair", "reduced mobility", "prm", "can't walk", "cannot walk", "difficulty walking",
                   "help walking", "trouble walking", "walking aid", "cane", "crutches", "walker", "elderly", "blind",
                   "visually impaired", "deaf", "hearing impaired", "buggy", "special assistance", "need assistance",
                   "need help getting", "help my", "carry my", "كرسي متحرك", "ذوي الهمم", "مساعدة خاصة", "لا أستطيع المشي",
                   "كبير السن", "व्हीलचेयर", "चल नहीं सकती", "चल नहीं सकता", "सहायता चाहिए", "बुजुर्ग"],
    "privacy": ["passenger list", "manifest", "booking reference of", "booking details of", "pnr of", "his booking",
                "her booking", "their booking", "his seat", "her seat", "who is on flight", "who is travelling",
                "who is on", "is he on", "is she on", "قائمة الركاب", "حجزه", "حجزها", "यात्री सूची", "उसकी बुकिंग"],
    "visa": ["visa", "transit visa", "immigration rule", "immigration requirement", "entry requirement", "residence permit",
             "overstay", "deport", "تأشيرة", "فيزا", "الهجرة", "الإقامة", "वीज़ा", "वीजा", "इमिग्रेशन"],
    "security": [" ml", "ml ", "liquid", "perfume", "aerosol", "power bank", "powerbank", "battery", "batteries",
                 "lithium", "lighter", "knife", "scissors", "razor", "allowed in cabin", "allowed on board",
                 "hand luggage", "carry-on", "carry on", "security rule", "can i bring", "can i take", "سوائل", "عطر",
                 "بطارية", "سكين", "مقص", "حقيبة اليد", "तरल", "परफ्यूम", "पावर बैंक", "चाकू", "कैंची", "हैंड बैगेज"],
    "lost": ["lost my", "left my", "forgot my", "forgotten my", "missing item", "can't find my", "cannot find my",
             "cant find my", "lost property", "is missing", "are missing", "went missing", "dropped my", "فقدت", "نسيت",
             "ضاع", "ضاعت", "खो गया", "खो गई", "भूल गया", "भूल गई"],
    "baggage": ["belt", "carousel", "baggage", "luggage", "my bags", "my bag", "my suitcase", "reclaim", "حزام", "الأمتعة", "الحقائب",
                "بيلت", "बेल्ट", "सामान", "बैगेज"],
    "walk": ["how long", "how far", "how many minutes", "walking time", "time to reach", "time to walk", "when should i leave",
             "when to leave", "when do i leave", "do i have time", "enough time", "make it", "in time", "كم من الوقت",
             "كم تبعد", "المشي", "متى أتحرك", "متى أغادر", "कितना समय", "कितनी दूर", "चलने", "कब निकल", "समय पर पहुँच"],
    "flight": ["gate", "boarding", "delay", "delayed", "late", "status", "on time", "cancel", "departure", "depart",
               "leave", "flight", "بوابة", "البوابة", "رحلة", "الرحلة", "رحلتي", "الصعود", "تأخير", "متأخرة", "ملغاة",
               "गेट", "उड़ान", "फ्लाइट", "बोर्डिंग", "देरी", "लेट", "रद्द"],
    "facility": ["wifi", "wi-fi", "internet", "prayer", "pray", "mosque", "namaz", "family zone", "play area", "nursing",
                 "baby changing", "واي فاي", "صلاة", "مصلى", "नमाज़", "नमाज", "वाई-फाई", "वाईफाई"],
    "greeting": ["hello", "hi", "hey", "salam", "marhaba", "good morning", "good evening", "thanks", "thank you", "thx",
                 "what can you do", "who are you", "how does this work", "help", "مرحبا", "السلام عليكم", "شكرا",
                 "नमस्ते", "धन्यवाद", "शुक्रिया"],
}

# "I am lost" (the person, not an item) and "where is / how do I get to ..."
PERSON_LOST = re.compile(
    r"\b(i'?m|i am|im|we'?re|we are|we're)\s+(so\s+|completely\s+|totally\s+|a bit\s+|kind of\s+|a little\s+)?lost\b|"
    r"\blost my way\b|\b(don'?t|do not|dont)\s+know where\s+(i|we)\s+(am|are)\b|\bwhere am i\b|"
    r"(?:can'?t|cannot|cant)\s+find\s+(?:my|the)?\s*(?:gate|way|flight|terminal)\b|"
    r"تائه|تهت|ضعت|لا أعرف أين أنا|لا اعرف اين انا|ضللت الطريق|"
    r"मैं\s+खो\s+(?:गया|गई)|रास्ता\s+भूल|रास्ता\s+नहीं\s+मिल|मुझे\s+नहीं\s+पता\s+मैं\s+कहाँ", re.I)
WHERE_Q = re.compile(
    r"\bwhere\s+(?:is|are|'s|can i find|can i|do i find|do i go|should i go|to)\b|\bwhere'?s\b|"
    r"\bhow\s+(?:do|can|should)\s+(?:i|we)\s+(?:get|go)\s+(?:to|there)\b|\bhow\s+to\s+(?:get|go)\s+to\b|\bwhich\s+way\b|"
    r"\bdirections?\b|\bway\s+to\b|\btake\s+me\s+to\b|\bshow\s+me\s+(?:the\s+way|where)\b|"
    r"(?:can'?t|cannot|cant)\s+find\s+(?:gate|the)\b|"
    r"أين|اين|كيف أصل|كيف اصل|كيف أذهب|طريق|"
    r"कहाँ|कहां|कैसे\s+(?:पहुँच|पहुंच|जाऊँ|जाऊं|जाएँ|जाएं)|रास्ता", re.I)
NAME_PROBE_RE = re.compile(
    r"\b(?:[Ii]s|[Ww]as)\s+(?:mr\.?\s+|mrs\.?\s+|ms\.?\s+|miss\s+)?[A-Z][a-z]+(?:[ -][A-Z][a-z'-]+)+\s+"
    r"(?:on|booked|travell?ing|flying|in)\b")
FLIGHT_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2})\s?(\d{2,4})(?![0-9])")
FAMILY_HINT = ["kids", "children", "child", "baby", "stroller", "pram", "family", "أطفال", "طفل", "बच्चे", "बच्चों"]
BAG_WORDS = ["bag", "bags", "luggage", "suitcase", "baggage", "الحقائب", "حقيبتي", "सामान", "बैग"]


def detect_lang(text: str) -> str:
    if re.search(r"[؀-ۿ]", text or ""):
        return "ar"
    if re.search(r"[ऀ-ॿ]", text or ""):
        return "hi"
    return "en"


def _has(text_low, words):
    for w in words:
        if not w.strip():
            continue
        if w.isascii() and w == w.strip():
            if re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", text_low):
                return True
        elif w in text_low:
            return True
    return False


def extract_flight(text: str):
    codes = db.airline_codes()
    for a, n in FLIGHT_RE.findall(text or ""):
        if a.upper() in codes:
            return f"{a.upper()}{n}"
    return None


def flight_by_city(text: str):
    """'my flight to London' → SA204, only when exactly one departure goes there today (schedule lookup, not a guess)."""
    low = (text or "").lower()
    hits = [f["flight_no"] for f in db.all_flights() if f["direction"] == "DEP"
            and re.search(rf"\b(?:to|for)\s+{re.escape(f['city'].lower())}\b", low)]
    return hits[0] if len(hits) == 1 else None


def classify(text: str):
    raw = text or ""
    low = f" {raw.lower()} "
    flight = extract_flight(raw) or flight_by_city(raw)
    origin, dest = wayfinding.parse_places(raw)
    ents = {"flight_no": flight, "location": wayfinding.parse_location(raw), "origin": origin, "destination": dest,
            "mobility": None}
    if _has(low, KW["assistance"]):
        ents["mobility"] = "reduced_mobility"
    elif _has(low, FAMILY_HINT):
        ents["mobility"] = "family"

    if _has(low, KW["medical"]):
        return "medical", ents
    if _has(low, KW["assistance"]) and not _has(low, ["help desk", "information desk"]):
        return "assistance", ents
    if NAME_PROBE_RE.search(raw) or _has(low, KW["privacy"]):
        return "privacy", ents
    if _has(low, KW["visa"]):
        return "visa", ents

    person_lost = bool(PERSON_LOST.search(raw))
    where_q = bool(WHERE_Q.search(raw))
    bag_question = _has(low, BAG_WORDS) and (flight or _has(low, ["belt", "carousel", "reclaim", "claim", "حزام", "बेल्ट"]))
    if person_lost:
        return "directions", ents
    if where_q and not bag_question and (dest or re.search(r"\b(my gate|gate|go|my flight|there)\b|बोर्डिंग|गेट|البوابة", low)):
        return "directions", ents
    if _has(low, KW["security"]) or re.search(r"\d+\s?ml\b", low):
        return "security", ents
    if _has(low, KW["lost"]):
        return "lost", ents
    if _has(low, KW["baggage"]) and not _has(low, ["hand luggage", "carry-on", "carry on"]):
        return "baggage", ents
    gate_only = not flight and dest and dest[0] == "node" and wayfinding.is_gate(dest[1])
    if dest and dest[0] == "dest" and origin and not flight:      # "I need to pray, I'm at gate B10"
        return "directions", ents
    if _has(low, KW["walk"]):
        return ("directions" if gate_only else "walk"), ents
    if flight or _has(low, KW["flight"]):
        return ("directions" if gate_only else "flight"), ents
    if _has(low, KW["facility"]):
        return "facility", ents
    if dest:
        return "directions", ents
    if _has(low, KW["greeting"]):
        return "greeting", ents
    return "unknown", ents
