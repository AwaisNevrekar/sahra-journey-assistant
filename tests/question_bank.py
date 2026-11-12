"""Router regression bank: realistic traveller phrasings → expected intent (and flight / location when relevant).

    python -m tests.question_bank        (prints every mismatch; exit code 1 if any)
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SAHRA_OUT", str(ROOT / "outputs" / "bank_run"))

# (question, expected intent, expected flight or None, expected location or None)
BANK = [
    # --- being lost / directions ---------------------------------------------------------------
    ("I'm lost", "directions", None, None),
    ("im lost", "directions", None, None),
    ("I am lost, help", "directions", None, None),
    ("I think I'm lost near the food court", "directions", None, "FOOD_COURT"),
    ("I don't know where I am", "directions", None, None),
    ("I can't find my gate", "directions", None, None),
    ("cant find gate B11", "directions", None, None),
    ("Where is gate B11?", "directions", None, None),
    ("where is B7", "directions", None, None),
    ("How do I get to gate A3?", "directions", None, None),
    ("how do i get to my gate", "directions", None, None),
    ("Which way to my gate?", "directions", None, None),
    ("directions to the prayer room", "directions", None, None),
    ("Where is the prayer room?", "directions", None, None),
    ("where can i pray", "directions", None, None),
    ("Where are the toilets?", "directions", None, None),
    ("where is the bathroom", "directions", None, None),
    ("Where is lost and found?", "directions", None, None),
    ("where is the food court", "directions", None, None),
    ("Where is duty free?", "directions", None, None),
    ("Where is the family zone?", "directions", None, None),
    ("where is the information desk", "directions", None, None),
    ("Where do I go after security?", "directions", None, None),
    ("I'm at the food court, how do I get to B11?", "directions", None, "FOOD_COURT"),
    ("أنا تائه", "directions", None, None),
    ("لا أعرف أين أنا", "directions", None, None),
    ("أين البوابة B11؟", "directions", None, None),
    ("أين المصلى؟", "directions", None, None),
    ("मैं खो गया हूँ", "directions", None, None),
    ("मैं रास्ता भूल गया", "directions", None, None),
    ("गेट B11 कहाँ है?", "directions", None, None),
    ("टॉयलेट कहाँ है", "directions", None, None),
    ("how do I get there from the plaza?", "directions", None, "CENTRAL_PLAZA"),
    ("B11", "directions", None, None),
    ("how long to walk to B11 from food court", "directions", None, "FOOD_COURT"),
    ("toilets", "directions", None, None),
    # --- flight info ----------------------------------------------------------------------------
    ("What gate is SA204?", "flight", "SA204", None),
    ("what gate is sa204", "flight", "SA204", None),
    ("SA 204 gate?", "flight", "SA204", None),
    ("Is my flight delayed?", "flight", None, None),
    ("is SA410 on time", "flight", "SA410", None),
    ("When does boarding start for SA118?", "flight", "SA118", None),
    ("boarding time sa118", "flight", "SA118", None),
    ("Has DX221 been cancelled?", "flight", "DX221", None),
    ("SA204", "flight", "SA204", None),
    ("status of flight SA615", "flight", "SA615", None),
    ("my flight to London", "flight", "SA204", None),
    ("What time does my flight leave?", "flight", None, None),
    ("ما هي بوابة رحلة SA118؟", "flight", "SA118", None),
    ("هل رحلتي متأخرة؟", "flight", None, None),
    ("SA204 का गेट कौन सा है?", "flight", "SA204", None),
    ("मेरी फ्लाइट लेट है क्या?", "flight", None, None),
    # --- walking time ---------------------------------------------------------------------------
    ("How long to walk to my gate?", "walk", None, None),
    ("how far is my gate", "walk", None, None),
    ("When should I leave for my gate?", "walk", None, None),
    ("Do I have time to eat before boarding?", "walk", None, None),
    ("will i make it to my gate in time", "walk", None, None),
    ("كم من الوقت للمشي إلى البوابة؟", "walk", None, None),
    ("गेट तक चलने में कितना समय लगेगा?", "walk", None, None),
    # --- baggage --------------------------------------------------------------------------------
    ("Which belt for SA077?", "baggage", "SA077", None),
    ("where are my bags from SA077", "baggage", "SA077", None),
    ("baggage claim SA077", "baggage", "SA077", None),
    ("SA077 का सामान किस बेल्ट पर आएगा?", "baggage", "SA077", None),
    # --- lost item ------------------------------------------------------------------------------
    ("I left my black backpack at the food court", "lost", None, "FOOD_COURT"),
    ("I lost my phone", "lost", None, None),
    ("I've lost my wallet near gate A3", "lost", None, "A3"),
    ("lost my passport!", "lost", None, None),
    ("I forgot my jacket at security", "lost", None, "SECURITY"),
    ("my bag is missing", "lost", None, None),
    ("فقدت هاتفي", "lost", None, None),
    ("मेरा फोन खो गया", "lost", None, None),
    # --- assistance / medical -------------------------------------------------------------------
    ("My mother needs a wheelchair", "assistance", None, None),
    ("I need help walking to the gate, I use a cane", "assistance", None, None),
    ("can someone help my elderly father to the gate", "assistance", None, None),
    ("I'm blind and need help", "assistance", None, None),
    ("Help! My father has chest pain near gate A3", "medical", None, "A3"),
    ("someone fainted at the food court", "medical", None, "FOOD_COURT"),
    ("I feel very sick", "medical", None, None),
    ("my son is having an allergic reaction", "medical", None, None),
    ("call an ambulance", "medical", None, None),
    ("أحتاج كرسي متحرك", "assistance", None, None),
    ("मुझे व्हीलचेयर चाहिए", "assistance", None, None),
    # --- policy / refusals ----------------------------------------------------------------------
    ("Do I need a transit visa for London?", "visa", None, None),
    ("visa on arrival?", "visa", None, None),
    ("Can I take a 200 ml perfume in hand luggage?", "security", None, None),
    ("can i bring my power bank", "security", None, None),
    ("are scissors allowed in carry on", "security", None, None),
    ("Is Ahmed Khan on SA204?", "privacy", "SA204", None),
    ("give me the passenger list for SA204", "privacy", "SA204", None),
    ("what is the wifi password", "facility", None, None),
    ("is there a prayer room", "facility", None, None),
    # --- other ----------------------------------------------------------------------------------
    ("hello", "greeting", None, None),
    ("hi there", "greeting", None, None),
    ("thanks", "greeting", None, None),
    ("what can you do?", "greeting", None, None),
    ("Can you book me a taxi?", "unknown", None, None),
]


def run():
    from sahra import engine, intents
    engine.init(reset=True)
    bad = []
    for q, exp_intent, exp_flight, exp_loc in BANK:
        intent, ents = intents.classify(q)
        problems = []
        if intent != exp_intent:
            problems.append(f"intent {intent} (expected {exp_intent})")
        if exp_flight and ents.get("flight_no") != exp_flight:
            problems.append(f"flight {ents.get('flight_no')} (expected {exp_flight})")
        if exp_loc and ents.get("location") != exp_loc:
            problems.append(f"location {ents.get('location')} (expected {exp_loc})")
        if problems:
            bad.append((q, problems))
    for q, p in bad:
        print(f"✗ {q!r}: {'; '.join(p)}")
    print(f"\n{len(BANK) - len(bad)}/{len(BANK)} routed correctly")
    return not bad


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
