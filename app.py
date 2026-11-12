"""Sahra Journey Assistant — Stage 10 dashboard (traveller app + staff console + activity log).

    streamlit run app.py

Design: system type, one accent (oasis teal, primary actions only), status colours that mean only
"how sure are we about this data", and progressive disclosure for everything that isn't the task at hand.
"""
import html
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from sahra import autopilot, clock, config, db, engine
from sahra import messages as M
from sahra import reconcile as rc
from sahra import value
from sahra import wayfinding as wf

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Sahra Journey Assistant", page_icon="✈️", layout="wide")

# ---------------------------------------------------------------- design tokens
# light / dark, each ≥ 4.5:1 on its surface (see README › Design)
st.markdown("""
<style>
:root{
  --text:#1D1D1F; --muted:#6E6E73; --line:rgba(60,60,67,.16); --fill:rgba(118,118,128,.08);
  --ok:#1E7B3C; --info:#0B5CAD; --warn:#8F5300; --bad:#C0281B; --none:#6E6E73;
}
@media (prefers-color-scheme: dark){ :root{
  --text:#F5F5F7; --muted:#A1A1A6; --line:rgba(235,235,245,.18); --fill:rgba(118,118,128,.18);
  --ok:#4CC771; --info:#5AA9F5; --warn:#F2A93B; --bad:#FF6B5E; --none:#A1A1A6; } }
.block-container{padding-top:2.6rem; max-width:1280px;}
h1,h2,h3{letter-spacing:-.015em;}
.title{font-size:1.75rem;font-weight:650;letter-spacing:-.02em;margin:0;}
.subtitle{color:var(--muted);font-size:.95rem;margin:2px 0 6px;}
.muted{color:var(--muted);} .small{font-size:.83rem;}
.section{font-size:1.06rem;font-weight:600;margin:1.3rem 0 .35rem;}
/* status pill: text + colour, never colour alone */
.pill{display:inline-flex;align-items:center;gap:6px;font-size:.8rem;font-weight:600;padding:2px 9px;border-radius:999px;
      background:var(--fill);white-space:nowrap;}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor;}
.CONFIRMED{color:var(--ok);} .SINGLE_SOURCE{color:var(--info);} .SYNCING{color:var(--warn);}
.CONFLICT{color:var(--bad);} .UNKNOWN{color:var(--none);}
/* signature: the boarding-pass gate card */
.pass{border:1px solid var(--line);border-radius:18px;padding:18px 20px;margin:4px 0 14px;}
.pass .row{display:flex;justify-content:space-between;color:var(--muted);font-size:.85rem;}
.pass .main{display:flex;gap:34px;align-items:flex-end;margin:10px 0 12px;}
.pass .lbl{color:var(--muted);font-size:.74rem;text-transform:uppercase;letter-spacing:.06em;}
.pass .gate{font-size:3.1rem;font-weight:650;line-height:1;letter-spacing:-.03em;}
.pass .val{font-size:1.35rem;font-weight:600;}
.pass .foot{border-top:1px dashed var(--line);padding-top:10px;font-size:.9rem;}
.state{display:flex;align-items:center;gap:8px;font-weight:600;}
.state::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor;flex:none;}
.listrow{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--line);font-size:.92rem;}
.step{font-size:.84rem;margin:3px 0;color:var(--muted);} .step b{color:var(--text);font-weight:600;}
.msg{border-left:2px solid var(--line);padding:4px 0 4px 12px;margin:8px 0;}
.rtl{direction:rtl;text-align:right;}
[data-testid="stMetricValue"]{font-size:1.9rem;font-weight:600;}
[data-testid="stMetricLabel"] p{color:var(--muted);}
</style>""", unsafe_allow_html=True)

STATE_TEXT = {"CONFIRMED": "Confirmed", "SINGLE_SOURCE": "One source", "SYNCING": "Syncing", "CONFLICT": "Conflict",
              "UNKNOWN": "No data"}
STATE_SENTENCE = {"CONFIRMED": "Confirmed by the airport and the airline",
                  "SINGLE_SOURCE": "From one source only — check the screens too",
                  "SYNCING": "Being confirmed — the two feeds don't match yet",
                  "CONFLICT": "Being confirmed — the feeds disagree; staff are checking",
                  "UNKNOWN": "No reliable live data — please check the screens"}


@st.cache_resource
def boot():
    engine.init()
    return True


boot()
ss = st.session_state
for k, v in {"sid": "S-" + uuid.uuid4().hex[:8], "chat": [], "linked": None, "autopilot": False, "ap_log": [],
             "staff_id": "DO-104"}.items():
    ss.setdefault(k, v)

LANGS = {"Automatic": None, "English": "en", "العربية": "ar", "हिन्दी": "hi"}
ZONES = ["", "CHECKIN_HALL", "SECURITY_EXIT", "CENTRAL_PLAZA", "FOOD_COURT", "PRAYER_ROOM", "FAMILY_ZONE"] + \
        [f"A{i}" for i in range(1, 7)] + [f"B{i}" for i in range(1, 13)]
MOBILITY = {"Walking": "standard", "With children": "family", "Reduced mobility": "reduced_mobility"}


def pill(state):
    return f"<span class='pill {state}'>{STATE_TEXT[state]}</span>"


def esc(text):
    return html.escape(text or "").replace("\n", "<br>")


def show_text(text, lang):
    st.markdown(f"<div class='{'rtl' if lang == 'ar' else ''}'>{esc(text)}</div>", unsafe_allow_html=True)


def show_trace(res):
    q = res.get("quality")
    st.markdown(f"<div class='step'><b>Outcome</b> {res['outcome']}{' · ' + pill(q) if q else ''}</div>",
                unsafe_allow_html=True)
    for t in res["trace"]:
        st.markdown(f"<div class='step'><b>{esc(t['stage'])}</b> — {esc(t['summary'])}</div>", unsafe_allow_html=True)


def age(m):
    return "missing" if m is None else f"{m:.0f} min old"


def step_clock(n):
    for _ in range(n):
        ss.ap_log = [f"{clock.hhmm(clock.now())} · {a}" for a in autopilot.step()] + ss.ap_log


# ================================================================ sidebar: time & demo controls
with st.sidebar:
    @st.fragment(run_every="4s")
    def live_clock():
        st.markdown(f"<div class='muted small'>Airport time</div>"
                    f"<div style='font-size:2.6rem;font-weight:600;letter-spacing:-.03em;line-height:1.1'>"
                    f"{clock.hhmm(clock.now())}</div>", unsafe_allow_html=True)
        if ss.autopilot:
            acts = autopilot.step()
            if acts:
                ss.ap_log = [f"{clock.hhmm(clock.now())} · {a}" for a in acts] + ss.ap_log
                st.rerun(scope="app")
        nxt = autopilot.pending_replay()
        st.caption(f"Next feed event {clock.hhmm(nxt[0]['at'])} — {nxt[0]['label']}" if nxt
                   else "Scripted feed events finished.")

    live_clock()
    ss.autopilot = st.toggle("Live mode", value=ss.autopilot,
                             help="Advances one airport minute every 4 seconds: reads feeds, sends due reminders, "
                                  "expires unapproved broadcasts.")
    a, b = st.columns(2)
    if a.button("+1 min", width="stretch"):
        step_clock(1)
        st.rerun()
    if b.button("+5 min", width="stretch"):
        step_clock(5)
        st.rerun()
    if ss.ap_log:
        with st.expander("Recent activity"):
            for line in ss.ap_log[:12]:
                st.caption(line)
    with st.expander("Demo bookings"):
        st.caption("Mock data. Only a salted hash is stored.")
        st.code("H8N3ZP  Al-Mansouri  SA204  reduced mobility\nK7P2QX  Rahman       SA204\nR2D9WE  Sharma       SA204  "
                "family · Hindi\nP9Q2MS  Iyer         SA118  family\nE9R2TY  Mostafa      DX330  feeds disagree\n"
                "B6N1ML  Balushi      OR512  feed missing", language=None)
    st.write("")
    if st.button("Reset demo", width="stretch", help="Back to 14:00 with fresh data"):
        engine.init(reset=True)
        st.cache_resource.clear()
        for k in ("chat", "linked", "ap_log"):
            ss.pop(k, None)
        ss.autopilot = False
        st.rerun()

st.markdown("<div class='title'>Sahra Airport</div><div class='subtitle'>Journey assistant — the right gate, on time, "
            "without the queue. It never guesses a gate, status or time.</p>", unsafe_allow_html=True)
tabs = st.tabs(["Traveller", "Staff", "Activity", "Tests", "Value", "How it works"])

# ================================================================ traveller
with tabs[0]:
    chat_col, side = st.columns([3, 2], gap="large")

    with side:
        if ss.linked:
            p = ss.linked
            r = rc.reconcile(p["flight_no"])
            f = r["fields"]
            usable = ("CONFIRMED", "SINGLE_SOURCE")
            gate = f["gate"]["value"] if f["gate"]["state"] in usable else "—"
            board = clock.hhmm(f["boarding_time"]["value"]) if f["boarding_time"]["state"] in usable else "—"
            status = M.fmt("status", f["status"]["value"]) if f["status"]["state"] in usable else "—"
            walk = ""
            pref_zone = ss.get("zone") or p.get("location")
            if pref_zone and gate != "—" and board != "—":
                plan = wf.plan(pref_zone, f["gate"]["value"], f["boarding_time"]["value"],
                               MOBILITY.get(ss.get("mob_label"), p["mobility"]))
                verdict = {"ON_TRACK": f"leave by {clock.hhmm(plan['leave_by'])}", "LEAVE_NOW": "start walking now",
                           "AT_RISK": "you may miss boarding — go now"}[plan["status"]]
                walk = f"<div style='margin-top:6px'>{plan['walk_min']} min walk from {plan['origin_label']} · " \
                       f"<b>{verdict}</b></div>"
            st.markdown(f"""<div class='pass'>
              <div class='row'><span>{r['flight_no']} · {r['airline']}</span><span>to {r['city']}</span></div>
              <div class='main'>
                <div><div class='lbl'>Gate</div><div class='gate'>{gate}</div></div>
                <div><div class='lbl'>Boarding</div><div class='val'>{board}</div></div>
                <div><div class='lbl'>Status</div><div class='val'>{status}</div></div>
              </div>
              <div class='foot'><div class='state {r['quality']}'>{STATE_SENTENCE[r['quality']]}</div>{walk}</div>
            </div>""", unsafe_allow_html=True)
            pax = db.get_pax(p["pax_id"]) or {}
            mine = [m for m in db.outbox() if m["audience"] != "chat" and m["recipient"] == pax.get("contact_masked")]
            st.markdown("<div class='section'>Messages to you</div>", unsafe_allow_html=True)
            if not mine:
                st.caption("Gate changes and leave-now reminders will appear here.")
            for m in mine[:5]:
                st.markdown(f"<div class='msg'><div class='muted small'>{clock.hhmm(m['ts'])} · {m['channel']}</div>"
                            f"<div class='{'rtl' if m['lang'] == 'ar' else ''}'>{esc(m['text'])}</div></div>",
                            unsafe_allow_html=True)
            if st.button("Unlink booking", type="tertiary"):
                ss.linked = None
                st.rerun()
        else:
            st.markdown("<div class='section' style='margin-top:0'>Your flight</div>", unsafe_allow_html=True)
            with st.form("link", border=False):
                c1, c2 = st.columns(2)
                ref = c1.text_input("Booking reference", max_chars=6, placeholder="H8N3ZP")
                last = c2.text_input("Last name", placeholder="Al-Mansouri")
                if st.form_submit_button("Link booking", type="primary"):
                    sess, status = engine.verify_booking(ref, last, ss.sid)
                    if status == "ok":
                        ss.linked = sess
                        st.rerun()
                    st.error("Too many attempts. Please visit the information desk." if status == "locked"
                             else "That booking couldn't be verified. Check the reference and last name.")
            st.caption("Optional. Linking gives you walking times and alerts.")
            st.markdown("<div class='section'>Departures</div>", unsafe_allow_html=True)
            rows = ""
            for b in [x for x in engine.flight_board() if x["dir"] == "DEP"]:
                g = b["_rec"]["fields"]["gate"]
                gtxt = g["value"] if g["state"] in ("CONFIRMED", "SINGLE_SOURCE") else "—"
                rows += (f"<div class='listrow'><span><b>{b['flight']}</b> <span class='muted'>{b['city']}</span></span>"
                         f"<span>{gtxt} &nbsp; {pill(b['quality'])}</span></div>")
            st.markdown(rows, unsafe_allow_html=True)

        with st.expander("Preferences"):
            lang_label = st.selectbox("Language", list(LANGS), key="lang_label")
            default_zone = (ss.linked or {}).get("location") or ""
            st.selectbox("I'm at", ZONES, key="zone", index=ZONES.index(default_zone) if default_zone in ZONES else 0,
                         format_func=lambda z: "Not shared" if not z else wf.label(z))
            default_mob = (ss.linked or {}).get("mobility", "standard")
            st.selectbox("Travelling", list(MOBILITY), key="mob_label",
                         index=list(MOBILITY.values()).index(default_mob))
            large = st.toggle("Larger text", key="large")

    with chat_col:
        quick = {"I'm lost": "I'm lost", "Where are the toilets?": "Where are the toilets?",
                 "Gate SA204": "What gate is SA204?", "Walk to my gate": "How long to walk to my gate?",
                 "Gate DX330": "Which gate is DX330?", "OR512 status": "Is OR512 on time?",
                 "Wheelchair": "My mother needs a wheelchair", "200 ml perfume": "Can I take a 200 ml perfume in hand luggage?",
                 "Transit visa": "Do I need a transit visa for London?", "Someone else's booking": "Is Ahmed Khan on SA204?",
                 "Baggage belt · हिन्दी": "SA077 का सामान किस बेल्ट पर आएगा?",
                 "Lost bag": "I left my black backpack at the food court"}

        def _pick():
            v = ss.get("pill")
            if v:
                ss.pending_q = quick[v]
                ss.pill = None

        if ss.get("large"):
            st.markdown("<style>.stChatMessage p,.stChatMessage div{font-size:1.28rem!important;line-height:1.6;}</style>",
                        unsafe_allow_html=True)
        box = st.container(height=540, border=False)
        with box:
            if not ss.chat:
                st.markdown("<div class='muted' style='padding:40px 0 10px'>Ask about your gate, boarding time, walking "
                            "time, baggage belt, assistance or a lost item — in English, Arabic or Hindi.</div>",
                            unsafe_allow_html=True)
                st.pills("Try", list(quick), key="pill", on_change=_pick, label_visibility="collapsed")
            for m in ss.chat:
                with st.chat_message(m["role"], avatar=":material/person:" if m["role"] == "user" else ":material/flight:"):
                    show_text(m["text"], m.get("lang", "en"))
                    if m.get("res"):
                        with st.expander("How this answer was made"):
                            show_trace(m["res"])
        if ss.chat:
            with st.expander("Examples"):
                st.pills("More examples", list(quick), key="pill", on_change=_pick, label_visibility="collapsed")
        prompt = st.chat_input("Ask a question") or ss.pop("pending_q", None)
        if prompt:
            zone = ss.get("zone") or None
            sess = {"session_id": ss.sid, "lang_pref": LANGS[ss.get("lang_label", "Automatic")],
                    "mobility": MOBILITY[ss.get("mob_label", "Walking")], "location": zone}
            if ss.linked:
                sess.update({k: ss.linked[k] for k in ("pax_id", "flight_no", "lang")})
                sess["location"] = zone or ss.linked.get("location")
            res = engine.ask(prompt, sess)
            ss.chat.append({"role": "user", "text": prompt, "lang": res["lang"]})
            ss.chat.append({"role": "assistant", "text": res["reply"] or "", "lang": res["lang"], "res": res})
            st.rerun()

# ================================================================ staff
with tabs[1]:
    pend = db.approvals("PENDING")
    open_t = db.tickets("OPEN")
    board = engine.flight_board()
    k = st.columns(4)
    k[0].metric("Awaiting approval", len(pend))
    k[1].metric("Open hand-offs", len(open_t), help=f"{sum(t['priority'] in ('URGENT', 'HIGH') for t in open_t)} urgent or high")
    k[2].metric("Flights with data issues", sum(b["quality"] != "CONFIRMED" for b in board))
    k[3].metric("Messages sent", len(db.outbox()))

    st.markdown("<div class='section'>Broadcast approvals</div>", unsafe_allow_html=True)
    st.caption(f"Messages to a whole flight need a named staff member. Not approved in {config.APPROVAL_TIMEOUT_MIN} min "
               "→ not sent, duty manager alerted. Live data is re-checked before sending.")
    if not pend:
        st.markdown("<div class='muted' style='padding:6px 0 4px'>Nothing waiting.</div>", unsafe_allow_html=True)
    for ap in pend:
        left_min = max(0, round((clock.parse(ap["deadline"]) - clock.now()).total_seconds() / 60, 1))
        langs = ", ".join({"en": "English", "ar": "Arabic", "hi": "Hindi"}.get(x, x) for x in json.loads(ap["langs"]))
        with st.container(border=True):
            a, b = st.columns([3, 1.2], vertical_alignment="center")
            a.markdown(f"**{ap['flight_no']} · {ap['summary']}**  \n"
                       f"<span class='muted small'>{ap['recipients']} passengers · {langs} · expires in {left_min} min · "
                       f"{ap['id']}</span>", unsafe_allow_html=True)
            with a.expander("Preview messages"):
                for key, txt in json.loads(ap["previews"] or "{}").items():
                    st.caption(key)
                    show_text(txt, "ar" if "[ar]" in key else "en")
            note = b.text_input("Note", key=f"note{ap['id']}", placeholder="Optional", label_visibility="collapsed")
            c1, c2 = b.columns(2)
            if c1.button("Approve", key=f"ok{ap['id']}", type="primary", width="stretch"):
                st.toast(f"{ap['id']}: {engine.decide(ap['id'], 'approve', ss.staff_id, note)['outcome']}")
                st.rerun()
            if c2.button("Reject", key=f"no{ap['id']}", width="stretch"):
                st.toast(f"{ap['id']}: {engine.decide(ap['id'], 'reject', ss.staff_id, note)['outcome']}")
                st.rerun()

    st.markdown("<div class='section'>Flights</div>", unsafe_allow_html=True)
    df = pd.DataFrame([{"Flight": b["flight"], "City": b["city"], "Gate / belt": b["gate/belt"], "Boarding": b["boarding"],
                        "Status": (b["status"] or "—").replace("_", " ").title(), "Data": STATE_TEXT[b["quality"]],
                        "Display feed": age(b["FIDS age"]), "Airline feed": age(b["Airline age"])} for b in board])
    st.dataframe(df, width="stretch", hide_index=True)
    for b in [x for x in board if x["quality"] != "CONFIRMED"]:
        bad = {k2: v for k2, v in b["_rec"]["fields"].items() if v["state"] != "CONFIRMED"}
        detail = "; ".join(f"{k2.replace('_', ' ')} {STATE_TEXT[v['state']].lower()}"
                           + (f" (display {v['values'].get('FIDS')}, airline {v['values'].get('AIRLINE')})"
                              if v["state"] in ("CONFLICT", "SYNCING") else "") for k2, v in bad.items())
        st.markdown(f"<div class='step'>{pill(b['quality'])} <b>{b['flight']}</b> — {esc(detail)}</div>",
                    unsafe_allow_html=True)

    st.markdown("<div class='section'>Hand-offs</div>", unsafe_allow_html=True)
    if open_t:
        tdf = pd.DataFrame(open_t)[["id", "created_at", "priority", "team", "summary"]]
        tdf["created_at"] = tdf["created_at"].map(clock.hhmm)
        tdf.columns = ["Ticket", "Time", "Priority", "Team", "Details"]
        st.dataframe(tdf, width="stretch", hide_index=True)
        c1, c2 = st.columns([3, 1])
        done = c1.selectbox("Ticket", [t["id"] for t in open_t], label_visibility="collapsed")
        if c2.button("Mark done", width="stretch"):
            db.close_ticket(done, ss.staff_id)
            st.rerun()
    else:
        st.markdown("<div class='muted'>No open hand-offs.</div>", unsafe_allow_html=True)

    with st.expander("Settings and feed simulator"):
        ss.staff_id = st.text_input("Staff ID (recorded on every decision)", ss.staff_id, max_chars=40)
        st.caption("Send a record as the display system (FIDS) or the airline would.")
        flights = [f["flight_no"] for f in db.all_flights()]
        statuses = ["ON_TIME", "BOARDING", "DELAYED", "GATE_CLOSED", "DEPARTED", "CANCELLED", "LANDED", "EXPECTED"]
        c = st.columns(6)
        fn = c[0].selectbox("Flight", flights)
        src = c[1].selectbox("Source", ["FIDS", "AIRLINE"])
        row = db.get_feed(src, fn)
        cur = json.loads(row["record"]) if row else {}
        status = c[2].selectbox("Status", statuses, index=statuses.index(cur.get("status", "ON_TIME")))
        gate = c[3].text_input("Gate", cur.get("gate", ""))
        board_t = c[4].text_input("Boarding", clock.hhmm(cur["boarding_time"]) if cur.get("boarding_time") else "")
        est_t = c[5].text_input("Est. time", clock.hhmm(cur["est_time"]) if cur.get("est_time") else "")
        if st.button("Send feed record", type="primary"):
            day = clock.now().strftime("%Y-%m-%dT")
            rec = {"source": src, "flight_no": fn, "status": status}
            if gate:
                rec["gate"] = gate.strip().upper()
            if board_t:
                rec["boarding_time"] = f"{day}{board_t}:00+04:00"
            if est_t:
                rec["est_time"] = f"{day}{est_t}:00+04:00"
            if cur.get("belt"):
                rec["belt"] = cur["belt"]
            st.toast(f"{fn} {src}: {engine.feed_update(rec)['outcome']}")
            st.rerun()
        st.divider()
        c = st.columns(4)
        hsrc = c[0].selectbox("Simulate outage", ["FIDS", "AIRLINE", "QUEUE"])
        hkey = c[1].selectbox("Flight or sensor", flights + ["SECURITY", "PASSPORT_CONTROL"])
        hstate = c[2].selectbox("State", ["down", "ok"])
        if c[3].button("Apply", width="stretch"):
            engine.set_health(hsrc, hkey, hstate)
            st.rerun()
        st.caption(f"Current outages: {engine.health() or 'none'}")
        c = st.columns(2)
        if c[0].button("Run reminder scan now", width="stretch"):
            st.toast(engine.tick()["outcome"])
            st.rerun()
        if c[1].button("Check approval timeouts", width="stretch"):
            st.toast(f"{len(engine.expire_overdue())} expired")
            st.rerun()

# ================================================================ activity
with tabs[2]:
    st.caption("Every feed read, decision, approval, hand-off and message. Passengers appear only as anonymous ids and "
               "masked contacts.")
    log = pd.DataFrame(db.audit(2000))
    if not log.empty:
        log["Time"] = log["ts"].map(clock.hhmm)
        kinds = sorted(log["kind"].unique())
        c1, c2 = st.columns([2, 1])
        pick = c1.multiselect("Show", kinds, default=[x for x in kinds if x != "TRIGGER"], label_visibility="collapsed")
        text = c2.text_input("Filter", placeholder="Filter by flight, ticket or word", label_visibility="collapsed")
        view = log[log["kind"].isin(pick)]
        if text:
            view = view[view["summary"].str.contains(text, case=False, na=False) |
                        view["event_id"].fillna("").str.contains(text, case=False)]
        view = view.rename(columns={"event_id": "Event", "stage": "Stage", "kind": "Type", "summary": "Details"})
        st.dataframe(view[["Time", "Event", "Stage", "Type", "Details"]], width="stretch", hide_index=True, height=380)
    st.markdown("<div class='section'>Messages sent</div>", unsafe_allow_html=True)
    ob = pd.DataFrame(db.outbox())
    if ob.empty:
        st.caption("No messages yet.")
    else:
        ob["Time"] = ob["ts"].map(clock.hhmm)
        ob = ob.rename(columns={"audience": "To", "flight_no": "Flight", "kind": "Type", "recipient": "Recipient",
                                "lang": "Lang", "approved_by": "Approved by", "text": "Message"})
        st.dataframe(ob[["Time", "To", "Flight", "Type", "Recipient", "Lang", "Approved by", "Message"]], width="stretch",
                     hide_index=True, height=320)

# ================================================================ tests
with tabs[3]:
    csv_path = ROOT / "outputs" / "test_log.csv"
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    c1.caption("26 scripted scenarios on a separate fresh database. Your live demo is not affected.")
    if c2.button("Run all tests", type="primary", width="stretch"):
        env = {**os.environ, "SAHRA_OUT": str(ROOT / "outputs" / "test_run"), "PYTHONIOENCODING": "utf-8"}
        with st.spinner("Running scenarios…"):
            out = subprocess.run([sys.executable, str(ROOT / "scenarios.py")], capture_output=True, text=True, env=env,
                                 cwd=ROOT, encoding="utf-8", errors="replace")
        st.code(out.stdout[-3000:] or out.stderr[-3000:], language=None)
    if csv_path.exists():
        tl = pd.read_csv(csv_path)
        st.metric("Passed", f"{(tl['Result'] == 'PASS').sum()} of {len(tl)}")
        st.dataframe(tl[["ID", "Scenario", "Category", "Outcome", "Human involvement", "Result", "Output (excerpt)"]],
                     width="stretch", hide_index=True, height=560)

# ================================================================ value
with tabs[4]:
    d = value.DEFAULTS
    with st.expander("Assumptions — change any value"):
        c = st.columns(4)
        kw = {
            "pax_per_day": c[0].number_input("Passengers per day", value=d["pax_per_day"], step=1000),
            "desk_contact_rate": c[1].slider("% who ask the desk", 1.0, 10.0, d["desk_contact_rate"] * 100) / 100,
            "handle_min": c[2].slider("Minutes per question", 1.0, 6.0, d["handle_min"]),
            "repetitive_share": c[3].slider("% repetitive questions", 30, 90, round(d["repetitive_share"] * 100)) / 100,
            "self_serve_rate": c[0].slider("% the assistant resolves", 30, 95, round(d["self_serve_rate"] * 100)) / 100,
            "missed_rate": c[1].slider("Missed boardings per 10,000 departing", 2, 40, round(d["missed_rate"] * 10000)) / 10000,
            "opt_in": c[2].slider("% opted in to alerts", 10, 90, round(d["opt_in"] * 100)) / 100,
            "nudge_effect": c[3].slider("% of reached passengers who make it", 20, 90, round(d["nudge_effect"] * 100)) / 100,
        }
    v = value.estimate(**kw)
    k = st.columns(4)
    k[0].metric("Questions handled / day", v["handled_by_assistant_per_day"],
                help=f"{v['desk_load_reduction_pct']}% of desk questions")
    k[1].metric("Staff hours saved / day", v["staff_hours_saved_per_day"],
                help=f"≈ {v['staff_shifts_freed_per_day']} eight-hour shifts")
    k[2].metric("Missed boardings avoided / yr", f"{v['missed_boardings_avoided_per_year']:,}")
    k[3].metric("Peak desk utilisation", f"{v['peak_utilisation_before_pct']}% → {v['peak_utilisation_after_pct']}%")
    st.markdown(f"<div class='muted'>About <b>AED {v['annual_staff_value_aed'] / 1e6:.2f} M</b> a year in staff time and "
                f"<b>AED {v['annual_missed_boarding_value_aed'] / 1e6:.2f} M</b> in avoided missed-boarding costs. "
                f"Peak queue {v['peak_queue_before_people']} → {v['peak_queue_after_people']} people.</div>",
                unsafe_allow_html=True)
    demo = pd.DataFrame(db.outbox())
    if not demo.empty:
        st.caption(f"This session: {sum(demo['audience'] == 'chat')} questions answered without the desk, "
                   f"{sum(demo['audience'] == 'individual')} reminders, {sum(demo['audience'] == 'flight')} approved "
                   "flight messages.")

# ================================================================ how it works
with tabs[5]:
    png = ROOT / "docs" / "flow_diagram.png"
    if png.exists():
        st.image(str(png), width="stretch")
    st.markdown("""
| Rule | How it is enforced — in code, not prompts |
|---|---|
| Never invent a gate, status or time | Answers are templates filled only with reconciled values; the guard rejects any unverified field. |
| Conflicting feeds | Display system and airline must agree. Under 3 min apart = syncing; 3 min or more = conflict, withheld, ops alerted. |
| Missing or stale data | Records older than 15 min are ignored; no fresh value means the assistant refuses to guess. |
| Staff approval | Flight-wide messages pause for a named staff member; 5-min timeout = not sent; data re-checked before sending. |
| Visa, immigration, security | Visa and immigration go to official sources; security rules are quoted verbatim with source and date. |
| Directions | Routes only through places you can actually walk (never back through security); a gate is only used if its data is confirmed. |
| Assistance and medical | Straight to the assistance or medical team, with location. No automated decision. |
| Privacy | No names or booking references stored — salted ids, masked contacts, redacted logs. |
""")
