"""Optional LLM intent fallback (Groq / Gemini / Ollama), stdlib only.

Used ONLY to classify a question the rule router could not place. It never writes the answer, never sees
flight data, and only receives redacted text. If no key is set or the call fails, we simply return None.
"""
import json
import os
import urllib.request

ALLOWED = ["medical", "assistance", "privacy", "visa", "security", "lost", "baggage", "walk", "flight", "facility",
           "greeting", "unknown"]
PROMPT = ("You route airport traveller questions. Reply with JSON only: {\"intent\": one of %s}. "
          "Choose 'medical' for any health emergency and 'assistance' for mobility help. Question: %s")


def provider():
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("OLLAMA_HOST") or os.getenv("SAHRA_USE_OLLAMA"):
        return "ollama"
    return None


def available():
    return provider() is not None


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def classify(redacted_text: str):
    p = provider()
    prompt = PROMPT % (ALLOWED, json.dumps(redacted_text))
    try:
        if p == "groq":
            out = _post("https://api.groq.com/openai/v1/chat/completions",
                        {"model": os.getenv("SAHRA_LLM_MODEL", "llama-3.3-70b-versatile"), "temperature": 0,
                         "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}},
                        {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"})
            txt = out["choices"][0]["message"]["content"]
        elif p == "gemini":
            model = os.getenv("SAHRA_LLM_MODEL", "gemini-2.0-flash")
            out = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                        f"?key={os.environ['GEMINI_API_KEY']}",
                        {"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}, {})
            txt = out["candidates"][0]["content"]["parts"][0]["text"]
        elif p == "ollama":
            host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            out = _post(f"{host}/api/chat", {"model": os.getenv("SAHRA_LLM_MODEL", "qwen3:4b"), "stream": False,
                                             "format": "json", "messages": [{"role": "user", "content": prompt}]}, {})
            txt = out["message"]["content"]
        else:
            return None
        intent = json.loads(txt).get("intent")
        return intent if intent in ALLOWED else None
    except Exception:
        return None
