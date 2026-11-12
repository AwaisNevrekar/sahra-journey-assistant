# ✈️ Sahra Journey Assistant

**Helps travellers reach the right gate on time — and never guesses a gate, status or time.**

Sahra International Airport: 25,000 passengers/day, one terminal, six info-desk staff answering the same questions.
This prototype turns two live flight feeds into timely, safe actions:

- **Travellers** ask in English, Arabic or Hindi: gate, boarding, walking time, baggage belt, lost items, assistance.
- **Every minute** it checks who must leave *now* (gate far away, family pace, reduced mobility) and nudges them.
- **Gate changes, delays, cancellations** are drafted for the whole flight — and wait for a **named staff member to approve**.
- **Conflicting or missing data** is never stated. Staff are alerted instead.
- **Medical, wheelchair and unclear requests** go straight to the right human team.

## Deliverables

| Brief asks for | Where |
|---|---|
| Working prototype (traveller + staff interface) | `streamlit run app.py` |
| One-page flow diagram | `docs/flow_diagram.pdf` / `.png` |
| Test log ≥ 10 cases, ≥ 3 escalate / refuse | `outputs/test_log.md` / `.csv` — **21 cases, 21 pass, 11 escalate / refuse / block** |
| Value estimate | `docs/VALUE_ESTIMATE.md` + live calculator in the app |

## Run it (5 minutes)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scenarios.py                  # runs the 21 test scenarios → outputs/test_log.md
streamlit run app.py                 # opens the dashboard
```

No API key is needed. Everything safety-critical is plain Python. Optional: set `GROQ_API_KEY`, `GEMINI_API_KEY` or
`SAHRA_USE_OLLAMA=1` and the router uses an LLM **only** to classify questions it couldn't place (redacted text, intent only).

Headless demo of the autonomous loop: `python -m sahra.autopilot --reset --minutes 18 --auto-approve DEMO-STAFF`

## 3-minute live demo script

1. **Traveller tab** — click *🛫 Gate SA204* (confirmed answer), then *⚠️ Gate DX330* (feeds disagree → "not confirmed", ops alerted)
   and *❔ OR512 status* (no fresh data → refuses to guess). Open "How I worked this out" to show the steps.
2. Link booking **H8N3ZP / Al-Mansouri** (reduced mobility, Food Court).
3. Turn on **Autopilot** in the sidebar. At 14:02 the display system changes SA204 to B11 — the airline hasn't yet, so nothing is sent.
   At 14:03 the airline confirms → a broadcast appears in the **Staff console** waiting for approval.
4. **Staff console** → preview the EN/AR/HI texts → *Approve & send*. The traveller's "Alerts sent to me" shows the gate change,
   then the proactive **leave-now nudge** with a buggy offer; the PRM team gets a ticket.
5. Ask *🧑‍🦽 Wheelchair*, *🛂 Transit visa*, *🔒 Someone else* — hand-off, refusal, privacy refusal.
6. Leave a broadcast unapproved for 5 minutes → it expires, **is not sent**, duty manager alerted.
7. **Live log** shows every feed read, decision and message. **Value** tab shows the estimate.

## How it works

One LangGraph run per event, 10 stages (see `docs/flow_diagram.pdf`):

| Stage | What happens | Code |
|---|---|---|
| 1 Trigger | feed update · traveller question · every-minute scan | `workflow.n1_trigger` |
| 2 Validate | Pydantic schema, no future timestamps, prompt-injection filter | `schemas.py`, `guards.py` |
| 3 Coordinator | deterministic EN/AR/HI router (optional LLM for unknown only) | `intents.py`, `llm.py` |
| 4a Reconciler | FIDS vs airline per field → CONFIRMED / SINGLE_SOURCE / SYNCING / CONFLICT / UNKNOWN | `reconcile.py` |
| 4b Journey solver | Dijkstra walking route + live queue sensors → leave-by time | `wayfinding.py` |
| 4c Responder | approved templates filled with verified facts only | `compose.py`, `messages.py` |
| 4d–4g | human hand-off · lost & found · official info · proactive nudges | `workflow.py` |
| 5 Remember | change detection; remembers what passengers were last told | `reconcile.detect_changes` |
| 6 Guard | code-only: no unverified fact, no personal data, broadcasts need approval | `guards.check` |
| 7 Approval | durable LangGraph `interrupt()`; approve / reject / 5-min timeout = not sent | `workflow.n7_approval` |
| 8 Write gateway | re-checks live feeds before sending; one atomic outbox write | `workflow.n8_gateway` |
| 9–10 | audit log → Streamlit dashboard | `db.log`, `app.py` |

## Safety rules — how each is handled

| Rule | Handling |
|---|---|
| Never invent status / gate / time | Replies are templates filled only with reconciled values. Guard rejects any draft containing an unverified field. |
| Staff approval before whole-flight messages | Every broadcast pauses for a named staff member. Reject is logged with a reason. No answer in 5 min → **not sent**, duty manager ticket. Live data is re-checked at send time (test T12). |
| Conflicting feeds | Display system and airline feed must agree. < 3 min apart = syncing (wait); ≥ 3 min = conflict → withheld + ops ticket (T04, T07). |
| Visa / immigration / security rules | Visa & immigration: always referred to official sources (T15). Security: quotes published guidance verbatim with source and review date (T16); anything else → "ask a security officer". |
| Personal nudges vs. approval | A leave-now nudge only uses the gate/boarding time passengers were officially told, so a change awaiting staff approval is never leaked through individual messages. |
| Assistance & medical | Immediate ticket to PRM team or medical + duty manager, with location. No automated decision (T13, T14). |
| Privacy | Names & booking refs never stored — salted hash ids, masked phone numbers, redacted logs (T17). The optional LLM sees redacted text only. Booking linking is limited to 3 attempts. |

## Project layout

```
app.py                 Streamlit dashboard (traveller · staff console · live log · tests · value · how it works)
scenarios.py           21 test scenarios → outputs/test_log.md / .csv
sahra/                 workflow.py (LangGraph), engine.py (API), reconcile.py, wayfinding.py, guards.py,
                       intents.py, compose.py, messages.py (EN/AR/HI), privacy.py, db.py, autopilot.py, value.py, config.py
data/                  MOCK flights, two feeds, passengers, terminal map, published info, found items, feed replay
docs/                  flow_diagram.pdf/.png/.svg, make_diagram.py, VALUE_ESTIMATE.md
```

## Going to production

Swap the mock files in `data/` for real connectors (FIDS/AODB, airline DCS, queue sensors, WhatsApp Business API), move
SQLite to Postgres, put the staff console behind SSO, and keep `config.py` thresholds under change control.
All passenger, flight and map data here is fictional.
