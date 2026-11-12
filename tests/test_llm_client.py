"""Checks the real HTTP client against a local stand-in for an OpenAI-compatible server (the API shape Groq,
Gemini and Ollama share). No internet or API key needed.

    python -m tests.test_llm_client
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sahra import llm  # noqa: E402

SEEN = []


class FakeOpenAI(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        if body.get("response_format"):                       # pretend this model rejects JSON mode
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'{"error":"response_format not supported"}')
            return
        content = '<think>The traveller wants a gate.</think> Sure: {"action": "finish", "intent": "flight", ' \
                  '"flight_no": "SA204"} done'
        out = {"choices": [{"message": {"role": "assistant", "content": content}}]}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(out).encode())


def main():
    srv = HTTPServer(("127.0.0.1", 0), FakeOpenAI)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ.update(SAHRA_LLM="ollama", OLLAMA_HOST=f"http://127.0.0.1:{srv.server_port}", SAHRA_LLM_MODEL="qwen3:4b")
    checks = []
    reply = llm.chat_json([{"role": "user", "content": "gate?"}])
    checks.append(("parses JSON after <think> and chatter", reply == {"action": "finish", "intent": "flight",
                                                                    "flight_no": "SA204"}))
    checks.append(("retries without JSON mode after HTTP 400", len(SEEN) == 2 and "response_format" not in SEEN[1]))
    checks.append(("sends model name and temperature 0", SEEN[0]["model"] == "qwen3:4b" and SEEN[0]["temperature"] == 0))
    srv.shutdown()
    srv.server_close()
    os.environ["OLLAMA_HOST"] = "http://127.0.0.1:9"              # nothing listening
    try:
        llm.chat_json([{"role": "user", "content": "x"}])
        checks.append(("server down raises LLMError", False))
    except llm.LLMError:
        checks.append(("server down raises LLMError", True))
    for name, ok in checks:
        print(("✓ " if ok else "✗ ") + name)
    return all(ok for _, ok in checks)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
