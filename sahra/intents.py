"""Stage 3 helper — deterministic intent router (EN / AR / HI). An optional LLM is consulted only for 'unknown'."""
import re

from . import db, wayfinding

ALLOWED = ["medical", "assistance", "privacy", "visa", "security", "lost", "baggage", "walk", "flight", "facility",
           "greeting", "unknown"]

KW = {
    "medical": ["chest pain", "heart attack", "unconscious", "fainted", "faint", "bleeding", "can't breathe", "cannot breathe",
                "not breathing", "seizure", "ambulance", "doctor", "medical emergency", "collapsed", "allergic reaction",
                "injured", "very sick", "إسعاف", "طبيب", "ألم في الصدر", "نزيف", "إغماء", "حالة طارئة", "एम्बुलेंस",
                "डॉक्टर", "सीने में दर्द", "बेहोश", "खून"],
    "assistance": ["wheelchair", "reduced mobility", "prm", "can't walk", "cannot walk", "difficulty walking", "walking aid",
                   "blind", "visually impaired", "deaf", "hearing impaired", "buggy", "special assistance", "need assistance",
                   "need help getting", "كرسي متحرك", "ذوي الهمم", "مساعدة خاصة", "لا أستطيع المشي", "व्हीलचेयर",
                   "चल नहीं सकती", "चल नहीं सकता", "सहायता चाहिए"],
    "privacy": ["passenger list", "manifest", "booking reference of", "booking details of", "pnr of", "his booking",
                "her booking", "their booking", "his seat", "her seat", "who is on flight", "who is travelling",
                "is he on", "is she on", "قائمة الركاب", "حجزه", "حجزها", "यात्री सूची", "उसकी बुकिंग"],
    "visa": ["visa", "transit visa", "immigration", "entry requirement", "residence permit", "overstay", "deport",
             "تأشيرة", "فيزا", "الهجرة", "الإقامة", "वीज़ा", "वीजा", "इमिग्रेशन"],
    "security": ["liquid", " ml", "ml ", "perfume", "aerosol", "power bank", "powerbank", "battery", "lithium", "lighter",
                 "knife", "scissors", "razor", "allowed in cabin", "hand luggage", "carry-on", "carry on", "security rule",
                 "سوائل", "عطر", "بطارية", "سكين", "مقص", "حقيبة اليد", "तरल", "परफ्यूम", "पावर बैंक", "चाकू", "कैंची",
                 "हैंड बैगेज"],
    "lost": ["lost my", "left my", "forgot my", "missing item", "can't find my", "cannot find my", "lost property",
             "lost and found", "فقدت", "نسيت", "ضاع", "खो गया", "खो गई", "भूल गया", "भूल गई"],
    "baggage": ["belt", "carousel", "baggage", "luggage", "my bags", "reclaim", "حزام", "الأمتعة", "الحقائب", "बेल्ट",
                "सामान", "बैगेज"],
    "walk": ["how long", "how far", "walk", "walking", "time to reach", "get to my gate", "get to the gate", "reach the gate",
             "minutes to", "when should i leave", "when to leave", "كم من الوقت", "كم تبعد", "المشي", "متى أتحرك",
             "कितना समय", "कितनी दूर", "चलने", "कब निकल"],
    "flight": ["gate", "boarding", "delay", "delayed", "status", "on time", "cancel", "departure", "depart", "flight",
               "بوابة", "البوابة", "رحلة", "الرحلة", "الصعود", "تأخير", "गेट", "उड़ान", "फ्लाइट", "बोर्डिंग", "देरी"],
    "facility": ["wifi", "wi-fi", "internet", "prayer", "pray", "mosque", "namaz", "family zone", "play area", "nursing",
                 "baby changing", "واي فاي", "صلاة", "مصلى", "नमाज़", "नमाज", "वाई-फाई", "वाईफाई"],
    "greeting": ["hello", "hi", "hey", "salam", "marhaba", "مرحبا", "السلام عليكم", "नमस्ते", "help"],
}
NAME_PROBE_RE = re.compile(
    r"\b(?:is|was)\s+(?:mr\.?\s+|mrs\.?\s+|ms\.?\s+|miss\s+)?[A-Z][a-z]+(?:[ -][A-Z][a-z'-]+)*\s+(?:on|booked|travell?ing|flying)\b")
FLIGHT_RE = re.compile(r"\b([A-Za-z]{2})\s?(\d{2,4})\b")
FAMILY_HINT = ["kids", "children", "child", "baby", "stroller", "pram", "family", "أطفال", "طفل", "बच्चे", "बच्चों"]


def detect_lang(text: str) -> str:
    if re.search(r"[؀-ۿ]", text or ""):
        return "ar"
    if re.search(r"[ऀ-ॿ]", text or ""):
        return "hi"
    return "en"


def _has(text_low, words):
    for w in words:
        if w.strip() and len(w.strip()) <= 3 and w.isascii() and w == w.strip():
            if re.search(rf"\b{re.escape(w)}\b", text_low):   # short words: whole-word match only
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


def classify(text: str):
    low = f" {(text or '').lower()} "
    ents = {"flight_no": extract_flight(text), "location": wayfinding.parse_location(text), "mobility": None}
    if _has(low, KW["assistance"]):
        ents["mobility"] = "reduced_mobility"
    elif _has(low, FAMILY_HINT):
        ents["mobility"] = "family"
    if NAME_PROBE_RE.search(text or ""):
        return "privacy", ents
    for intent in ["medical", "assistance", "privacy", "visa", "security", "lost", "baggage", "walk", "flight", "facility"]:
        if _has(low, KW[intent]) or (intent == "security" and re.search(r"\d+\s?ml\b", low)):
            return intent, ents
    if ents["flight_no"]:
        return "flight", ents
    if _has(low, KW["greeting"]):
        return "greeting", ents
    return "unknown", ents
