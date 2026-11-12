"""LLM access for the Stage 3 planner — stdlib only, one OpenAI-compatible client for Groq, Gemini and Ollama.

The model only ever *plans* (which tool next, which worker at the end). It never writes passenger text, never
sees names or booking references (text is redacted first), and every plan it makes is checked by code.

Choose a provider with environment variables (or a .env file in the project folder):
    GROQ_API_KEY=...                       → Groq   (default model llama-3.3-70b-versatile)
    GEMINI_API_KEY=...                     → Gemini (default model gemini-2.5-flash)
    SAHRA_LLM=ollama                       → local Ollama at OLLAMA_HOST (default model qwen3:4b)
    SAHRA_LLM_MODEL=...                    → override the model name
    SAHRA_LLM=off                          → force the rule planner
"""
import json
import os
import re
import urllib.error
import urllib.request

ENDPOINTS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "llama-3.3-70b-versatile"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY",
               "gemini-2.5-flash"),
    "ollama": (None, None, "qwen3:4b"),
}

FAKE_QUEUE = []        # tests: SAHRA_LLM=fake pops scripted replies (dict, str, or an Exception to raise)
FAKE_CALLS = []        # tests: every message list the fake model received


class LLMError(Exception):
    pass


def provider():
    forced = os.getenv("SAHRA_LLM", "").strip().lower()
    if forced in ("off", "none", "rules"):
        return None
    if forced in ("groq", "gemini", "ollama", "fake"):
        return forced
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("SAHRA_USE_OLLAMA"):
        return "ollama"
    return None


def available():
    return provider() is not None


def model_name():
    p = provider()
    if p == "fake":
        return "scripted-test-model"
    return os.getenv("SAHRA_LLM_MODEL") or (ENDPOINTS[p][2] if p else "")


def describe():
    p = provider()
    return f"{p} · {model_name()}" if p else "rules (no AI model configured)"


def _extract_json(text):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)          # qwen3 thinking blocks
    start = text.find("{")
    if start < 0:
        raise LLMError("model reply contained no JSON object")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise LLMError("model reply was not a JSON object")
    return obj


def _post(url, body, key):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=float(os.getenv("SAHRA_LLM_TIMEOUT", "20"))) as r:
        return json.loads(r.read().decode())


def chat_json(messages):
    """Send a chat and return the model's reply parsed as one JSON object. Raises LLMError on any failure."""
    p = provider()
    if p is None:
        raise LLMError("no provider configured")
    if p == "fake":
        FAKE_CALLS.append(messages)
        if not FAKE_QUEUE:
            raise LLMError("fake model has no scripted reply left")
        nxt = FAKE_QUEUE.pop(0)
        if isinstance(nxt, Exception):
            raise LLMError(str(nxt))
        return nxt if isinstance(nxt, dict) else _extract_json(nxt)
    url, key_env, _ = ENDPOINTS[p]
    if p == "ollama":
        url = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/v1/chat/completions"
    key = os.getenv(key_env) if key_env else None
    body = {"model": model_name(), "messages": messages, "temperature": 0, "response_format": {"type": "json_object"}}
    try:
        try:
            out = _post(url, body, key)
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
            body.pop("response_format")                       # some models reject JSON mode; ask plainly instead
            out = _post(url, body, key)
        return _extract_json(out["choices"][0]["message"]["content"])
    except LLMError:
        raise
    except Exception as e:                                    # network, auth, quota, bad JSON → caller falls back
        raise LLMError(f"{type(e).__name__}: {str(e)[:160]}")
