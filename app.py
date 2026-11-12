"""Sahra Journey Assistant — Stage 10 dashboard (traveller app + staff console + live log).

    streamlit run app.py
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

st.markdown("""
<style>
:root { --sand:#C8963E; --ink:#0F2A3D; --ok:#1B7F4B; --warn:#B26A00; --bad:#B42318; }
.block-container { padding-top: 3.2rem; }
.brand { font-size: 1.55rem; font-weight: 750; color: var(--ink); letter-spacing: -.01em; }
.brand span { color: var(--sand); }
.sub { color:#5b6b78; margin-top:-4px; }
.badge { display:inline-block; padding:2px 9px; border-radius:999px; font-size:.78rem; font-weight:650; color:#fff; }
.CONFIRMED{background:var(--ok);} .SINGLE_SOURCE{background:#2E6FB7;} .SYNCING{background:var(--warn);}
.CONFLICT{background:var(--bad);} .UNKNOWN{background:#6B7280;}
.card { border:1px solid #e3e6ea; border-radius:14px; padding:14px 16px; margin-bottom:10px; background:#fff; }
.rtl { direction: rtl; text-align: right; }
.step { font-size:.86rem; margin:2px 0; } .step b { color: var(--ink); }
@media (prefers-color-scheme: dark) { .card{background:#111827;border-color:#374151;} .brand{color:#e5e7eb;} }
</style>""", unsafe_allow_html=True)


@st.cache_resource
def boot():
    engine.init()
    return True


boot()
ss = st.session_state
ss.setdefault("sid", "S-" + uuid.uuid4().hex[:8])
ss.setdefault("chat", [])
ss.setdefault("linked", None)
ss.setdefault("autopilot", False)
ss.setdefault("ap_log", [])
ss.setdefault("staff_id", "DO-104")

LANG_OPTS = {"Auto-detect": None, "English": "en", "العربية": "ar", "हिन्दी": "hi"}
ZONES = ["(not shared)", "CHECKIN_HALL", "SECURITY_EXIT", "CENTRAL_PLAZA", "FOOD_COURT", "PRAYER_ROOM", "FAMILY_ZONE"] + \
        [f"A{i}" for i in range(1, 7)] + [f"B{i}" for i in range(1, 13)]
MOBILITY = {"Walking normally": "standard", "With children / family": "family", "Reduced mobility": "reduced_mobility"}


def badge(state):
    return f"<span class='badge {state}'>{state.replace('_', ' ')}</span>"


def show_text(text, lang):
    body = html.escape(text).replace("\n", "<br>")
    st.markdown(f"<div class='{'rtl' if lang == 'ar' else ''}'>{body}</div>", unsafe_allow_html=True)


def show_trace(res):
    q = res.get("quality")
    head = f"Outcome **`{res['outcome']}`**" + (f" · data {badge(q)}" if q else "")
    st.markdown(head, unsafe_allow_html=True)
    for t in res["trace"]:
        st.markdown(f"<div class='step'><b>{html.escape(t['stage'])}</b> — {html.escape(t['summary'])}</div>",
                    unsafe_allow_html=True)


# ============================================================== sidebar
with st.sidebar:
    st.markdown("<div class='brand'>Sahra <span>Journey</span></div><div class='sub'>Passenger journey & terminal assistant</div>",
                unsafe_allow_html=True)

    @st.fragment(run_every="4s")
    def live_panel():
        st.metric("Airport time (simulated)", clock.hhmm(clock.now()), help="Asia/Dubai. Feeds, approvals and nudges run on this clock.")
        if ss.autopilot:
            acts = autopilot.step()
            if acts:
                ss.ap_log = [f"[{clock.hhmm(clock.now())}] {a}" for a in acts] + ss.ap_log
                st.rerun(scope="app")
        nxt = autopilot.pending_replay()
        if nxt:
            st.caption(f"Next live feed event: {clock.hhmm(nxt[0]['at'])} — {nxt[0]['label']}")
        else:
            st.caption("Scripted feed storyline finished — inject your own feeds in the Staff Console.")

    live_panel()
    ss.autopilot = st.toggle("▶ Autopilot (1 airport-minute every 4 s)", value=ss.autopilot,
                             help="Replays live feed events, runs the proactive scan and expires unapproved broadcasts — no prompting.")
    c1, c2 = st.columns(2)
    if c1.button("+1 min", width="stretch"):
        ss.ap_log = [f"[{clock.hhmm(clock.now())}] {a}" for a in autopilot.step()] + ss.ap_log
        st.rerun()
    if c2.button("+5 min", width="stretch"):
        for _ in range(5):
            ss.ap_log = [f"[{clock.hhmm(clock.now())}] {a}" for a in autopilot.step()] + ss.ap_log
        st.rerun()
    if ss.ap_log:
        with st.expander("Autopilot activity", expanded=True):
            for line in ss.ap_log[:12]:
                st.caption(line)
    st.divider()
    with st.expander("Demo bookings (mock data)"):
        st.caption("Link one in the Traveller tab. Real names/refs are never stored — only a salted hash.")
        st.code("K7P2QX  Rahman      SA204 · after Security\nH8N3ZP  Al-Mansouri SA204 · reduced mobility\n"
                "R2D9WE  Sharma      SA204 · family (Hindi)\nP9Q2MS  Iyer        SA118 · family, Check-in\n"
                "E9R2TY  Mostafa     DX330 · (feed conflict)\nB6N1ML  Balushi     OR512 · (feed missing)", language=None)
    if st.button("↺ Reset demo to 14:00", width="stretch"):
        engine.init(reset=True)
        st.cache_resource.clear()
        for k in ("chat", "linked", "ap_log"):
            ss.pop(k, None)
        ss.autopilot = False
        st.rerun()

st.markdown("<div class='brand'>✈️ Sahra International Airport — <span>Journey Assistant</span></div>"
            "<div class='sub'>Right gate, on time, without queueing at the information desk · "
            "never guesses a gate, status or time</div>", unsafe_allow_html=True)
st.write("")
tabs = st.tabs(["🧳 Traveller", "🛂 Staff console", "📜 Live log", "✅ Test scenarios", "📈 Value", "🗺️ How it works"])

# ============================================================== traveller
with tabs[0]:
    left, right = st.columns([3, 2], gap="large")
    with right:
        st.subheader("My trip")
        if ss.linked:
            p = ss.linked
            st.success(f"Booking linked · flight **{p['flight_no']}** · id `{p['pax_id']}`")
            if st.button("Unlink booking"):
                ss.linked = None
                st.rerun()
        else:
            with st.form("link"):
                st.caption("Optional — link your booking for personal walking times and alerts.")
                a, b = st.columns(2)
                ref = a.text_input("Booking reference", max_chars=6, placeholder="K7P2QX")
                last = b.text_input("Last name", placeholder="Rahman")
                if st.form_submit_button("Link booking"):
                    sess, status = engine.verify_booking(ref, last, ss.sid)
                    if status == "ok":
                        ss.linked = sess
                        st.rerun()
                    st.error("Too many attempts — please visit the desk." if status == "locked"
                             else "We couldn't verify that booking. Check the reference and last name.")
        lang_label = st.selectbox("Language", list(LANG_OPTS), index=0)
        default_zone = (ss.linked or {}).get("location") or "(not shared)"
        zone = st.selectbox("I am at", ZONES, index=ZONES.index(default_zone) if default_zone in ZONES else 0,
                            format_func=lambda z: z if z.startswith("(") else wf.label(z))
        default_mob = (ss.linked or {}).get("mobility", "standard")
        mob_label = st.selectbox("Travelling", list(MOBILITY), index=list(MOBILITY.values()).index(default_mob))
        large = st.toggle("Larger text", value=False)

        if ss.linked:
            r = rc.reconcile(ss.linked["flight_no"])
            f = r["fields"]
            st.markdown(
                f"<div class='card'><b>{r['flight_no']} → {r['city']}</b> · {r['airline']}<br>"
                f"Gate: <b>{f['gate']['value'] or '—'}</b> {badge(f['gate']['state'])}<br>"
                f"Boarding: <b>{clock.hhmm(f['boarding_time']['value']) if f['boarding_time']['value'] else '—'}</b> "
                f"{badge(f['boarding_time']['state'])}<br>"
                f"Status: <b>{M.fmt('status', f['status']['value']) if f['status']['value'] else '—'}</b> "
                f"{badge(f['status']['state'])}</div>", unsafe_allow_html=True)
            mine = [m for m in db.outbox() if m["audience"] != "chat" and m["flight_no"] == ss.linked["flight_no"]
                    and m["recipient"] == (db.get_pax(ss.linked["pax_id"]) or {}).get("contact_masked")]
            st.markdown("**Alerts sent to me**")
            if not mine:
                st.caption("None yet. Gate changes and leave-now reminders appear here.")
            for m in mine[:6]:
                with st.container(border=True):
                    st.caption(f"{clock.hhmm(m['ts'])} · {m['kind']} · {m['channel']}")
                    show_text(m["text"], m["lang"])
        else:
            st.markdown("**Departures (public)**")
            board = engine.flight_board()
            for b in [x for x in board if x["dir"] == "DEP"]:
                g = b["_rec"]["fields"]["gate"]
                st.markdown(f"<div class='step'><b>{b['flight']}</b> {b['city']} · gate "
                            f"<b>{g['value'] if g['state'] in ('CONFIRMED', 'SINGLE_SOURCE') else 'being confirmed'}</b> "
                            f"{badge(b['quality'])}</div>", unsafe_allow_html=True)

    with left:
        st.subheader("Ask the assistant")
        quick = {"🛫 Gate SA204": "What gate is SA204?", "🚶 Walk to my gate": "How long to walk to my gate?",
                 "⚠️ Gate DX330": "Which gate is DX330?", "❔ OR512 status": "Is OR512 on time?",
                 "🧑‍🦽 Wheelchair": "My mother needs a wheelchair",
                 "🧴 200 ml perfume": "Can I take a 200 ml perfume in hand luggage?",
                 "🛂 Transit visa": "Do I need a transit visa for London?", "🔒 Someone else": "Is Ahmed Khan on SA204?",
                 "🧳 Belt (हिन्दी)": "SA077 का सामान किस बेल्ट पर आएगा?", "📦 Lost bag": "I left my black backpack at the food court"}
        def _pick():
            v = ss.get("pill")
            if v:
                ss.pending_q = quick[v]
                ss.pill = None

        st.pills("Try a scenario — or type your own question below", list(quick), key="pill", on_change=_pick)
        clicked = ss.pop("pending_q", None)
        if large:
            st.markdown("<style>.stChatMessage p, .stChatMessage div {font-size:1.3rem !important; line-height:1.65;}</style>",
                        unsafe_allow_html=True)
        box = st.container(height=520)
        with box:
            if not ss.chat:
                st.info("Ask about your gate, boarding, walking time, baggage belt, assistance or lost items — "
                        "in English, Arabic or Hindi.")
            for m in ss.chat:
                with st.chat_message(m["role"], avatar="🧳" if m["role"] == "user" else "✈️"):
                    show_text(m["text"], m.get("lang", "en"))
                    if m.get("res"):
                        with st.expander("How I worked this out"):
                            show_trace(m["res"])
        prompt = st.chat_input("Type your question…") or clicked
        if prompt:
            sess = {"session_id": ss.sid, "lang_pref": LANG_OPTS[lang_label], "mobility": MOBILITY[mob_label],
                    "location": None if zone.startswith("(") else zone}
            if ss.linked:
                sess.update({k: ss.linked[k] for k in ("pax_id", "flight_no", "lang")})
            res = engine.ask(prompt, sess)
            ss.chat.append({"role": "user", "text": prompt, "lang": res["lang"]})
            ss.chat.append({"role": "assistant", "text": res["reply"] or "", "lang": res["lang"], "res": res})
            st.rerun()

# ============================================================== staff console
with tabs[1]:
    pend = db.approvals("PENDING")
    open_t = db.tickets("OPEN")
    board = engine.flight_board()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Broadcasts awaiting approval", len(pend))
    hi = sum(t["priority"] in ("URGENT", "HIGH") for t in open_t)
    m2.metric("Open hand-offs / alerts", len(open_t), f"{hi} urgent/high" if hi else None, delta_color="inverse")
    m3.metric("Flights with data issues", sum(b["quality"] not in ("CONFIRMED",) for b in board))
    m4.metric("Messages sent", len(db.outbox()))
    ss.staff_id = st.text_input("Your staff ID (recorded on every decision)", ss.staff_id, max_chars=40)

    st.subheader("① Broadcast approvals")
    st.caption(f"Whole-flight messages never go out without a named staff member. Unapproved after "
               f"{config.APPROVAL_TIMEOUT_MIN} min → not sent, duty manager alerted. Live data is re-checked at send time.")
    if not pend:
        st.success("Nothing waiting.")
    for ap in pend:
        left_min = round((clock.parse(ap["deadline"]) - clock.now()).total_seconds() / 60, 1)
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.markdown(f"**{ap['id']} · {ap['flight_no']} — {ap['summary']}**  \n"
                       f"{ap['recipients']} opted-in passengers · languages: {', '.join(json.loads(ap['langs']))} · "
                       f"expires in **{max(left_min, 0)} min**")
            previews = json.loads(ap["previews"] or "{}")
            with a.expander("Preview every language"):
                for k, v in previews.items():
                    st.caption(k)
                    show_text(v, "ar" if "[ar]" in k else "en")
            note = b.text_input("Note (optional)", key=f"note{ap['id']}")
            if b.button("✅ Approve & send", key=f"ok{ap['id']}", type="primary", width="stretch"):
                r = engine.decide(ap["id"], "approve", ss.staff_id, note)
                st.toast(f"{ap['id']}: {r['outcome']}")
                st.rerun()
            if b.button("✖ Reject", key=f"no{ap['id']}", width="stretch"):
                r = engine.decide(ap["id"], "reject", ss.staff_id, note)
                st.toast(f"{ap['id']}: {r['outcome']}")
                st.rerun()

    st.subheader("② Live flight board — reconciled feeds")
    DOT = {"CONFIRMED": "🟢", "SINGLE_SOURCE": "🔵", "SYNCING": "🟠", "CONFLICT": "🔴", "UNKNOWN": "⚪"}
    df = pd.DataFrame([{**{k: v for k, v in b.items() if k != "_rec"}, "quality": f"{DOT[b['quality']]} {b['quality']}"}
                       for b in board])
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config={"quality": st.column_config.TextColumn("data quality"),
                                "FIDS age": st.column_config.NumberColumn("FIDS age (min)"),
                                "Airline age": st.column_config.NumberColumn("Airline age (min)")})
    issues = [b for b in board if b["quality"] != "CONFIRMED"]
    for b in issues:
        bad = {k: v for k, v in b["_rec"]["fields"].items() if v["state"] not in ("CONFIRMED",)}
        st.markdown(f"{badge(b['quality'])} **{b['flight']}** — " + "; ".join(
            f"{k}: {v['state']} {v.get('values') or ''}" for k, v in bad.items()), unsafe_allow_html=True)

    st.subheader("③ Hand-offs & alerts")
    if open_t:
        tdf = pd.DataFrame(open_t)[["id", "created_at", "priority", "team", "kind", "summary"]]
        tdf["created_at"] = tdf["created_at"].map(clock.hhmm)
        st.dataframe(tdf, width="stretch", hide_index=True)
        c1, c2 = st.columns([3, 1])
        done = c1.selectbox("Mark ticket done", [t["id"] for t in open_t], label_visibility="collapsed")
        if c2.button("Mark done", width="stretch"):
            db.close_ticket(done, ss.staff_id)
            st.rerun()
    else:
        st.success("No open hand-offs.")

    with st.expander("④ Feed simulator & controls (for the demo)"):
        st.caption("Inject a record exactly as the display system (FIDS) or the airline would send it.")
        flights = [f["flight_no"] for f in db.all_flights()]
        c = st.columns(6)
        fn = c[0].selectbox("Flight", flights)
        src = c[1].selectbox("Source", ["FIDS", "AIRLINE"])
        row = db.get_feed(src, fn)
        cur = json.loads(row["record"]) if row else {}
        status = c[2].selectbox("Status", ["ON_TIME", "BOARDING", "DELAYED", "GATE_CLOSED", "DEPARTED", "CANCELLED",
                                           "LANDED", "EXPECTED"],
                                index=["ON_TIME", "BOARDING", "DELAYED", "GATE_CLOSED", "DEPARTED", "CANCELLED", "LANDED",
                                       "EXPECTED"].index(cur.get("status", "ON_TIME")))
        gate = c[3].text_input("Gate", cur.get("gate", ""))
        board_t = c[4].text_input("Boarding (HH:MM)", clock.hhmm(cur["boarding_time"]) if cur.get("boarding_time") else "")
        est_t = c[5].text_input("Est. time (HH:MM)", clock.hhmm(cur["est_time"]) if cur.get("est_time") else "")
        if st.button("📡 Send feed record"):
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
            r = engine.feed_update(rec)
            st.toast(f"{fn} {src}: {r['outcome']}")
            st.rerun()
        st.divider()
        c = st.columns(4)
        hsrc = c[0].selectbox("Simulate outage: source", ["FIDS", "AIRLINE", "QUEUE"])
        hkey = c[1].selectbox("Flight / sensor", flights + ["SECURITY", "PASSPORT_CONTROL"])
        hstate = c[2].selectbox("State", ["down", "ok"])
        if c[3].button("Apply", width="stretch"):
            engine.set_health(hsrc, hkey, hstate)
            st.rerun()
        st.caption(f"Current outages: {engine.health()}")
        c = st.columns(2)
        if c[0].button("⏰ Run proactive scan now", width="stretch"):
            st.toast(engine.tick()["outcome"])
            st.rerun()
        if c[1].button("⌛ Check approval timeouts", width="stretch"):
            st.toast(f"{len(engine.expire_overdue())} expired")
            st.rerun()

# ============================================================== live log
with tabs[2]:
    st.caption("Every feed read, decision, approval, hand-off and message — with the airport time. Names and booking "
               "references never appear: passengers are pseudonymous ids and masked contacts.")
    log = pd.DataFrame(db.audit(2000))
    if not log.empty:
        log["time"] = log["ts"].map(clock.hhmm)
        kinds = sorted(log["kind"].unique())
        default = [k for k in kinds if k not in ("TRIGGER",)]
        pick = st.multiselect("Show", kinds, default=default)
        text = st.text_input("Filter (flight, ticket, word)")
        view = log[log["kind"].isin(pick)]
        if text:
            view = view[view["summary"].str.contains(text, case=False, na=False) |
                        view["event_id"].fillna("").str.contains(text, case=False)]
        st.dataframe(view[["time", "event_id", "stage", "kind", "summary"]], width="stretch", hide_index=True,
                     height=380)
    st.subheader("Messages sent (outbox)")
    ob = pd.DataFrame(db.outbox())
    if ob.empty:
        st.caption("No messages yet.")
    else:
        ob["time"] = ob["ts"].map(clock.hhmm)
        st.dataframe(ob[["time", "audience", "flight_no", "kind", "recipient", "lang", "approved_by", "text"]],
                     width="stretch", hide_index=True, height=320)

# ============================================================== tests
with tabs[3]:
    st.caption("21 scripted scenarios on a separate, fresh database (your live demo is not touched).")
    if st.button("▶ Run all test scenarios", type="primary"):
        env = {**os.environ, "SAHRA_OUT": str(ROOT / "outputs" / "test_run")}
        with st.spinner("Running…"):
            out = subprocess.run([sys.executable, str(ROOT / "scenarios.py")], capture_output=True, text=True, env=env,
                                 cwd=ROOT)
        st.code(out.stdout[-3000:] or out.stderr[-3000:])
    csv_path = ROOT / "outputs" / "test_log.csv"
    if csv_path.exists():
        tl = pd.read_csv(csv_path)
        p = (tl["Result"] == "PASS").sum()
        st.metric("Passed", f"{p} / {len(tl)}")
        st.dataframe(tl, width="stretch", hide_index=True, height=560)

# ============================================================== value
with tabs[4]:
    st.caption("Every number below is an editable assumption — change it and the estimate updates.")
    d = value.DEFAULTS
    c = st.columns(4)
    kw = {
        "pax_per_day": c[0].number_input("Passengers / day", value=d["pax_per_day"], step=1000),
        "desk_contact_rate": c[1].slider("% who ask the desk", 1.0, 10.0, d["desk_contact_rate"] * 100) / 100,
        "handle_min": c[2].slider("Minutes per desk question", 1.0, 6.0, d["handle_min"]),
        "repetitive_share": c[3].slider("% repetitive questions", 30, 90, int(d["repetitive_share"] * 100)) / 100,
        "self_serve_rate": c[0].slider("% of those the assistant resolves", 30, 95, int(d["self_serve_rate"] * 100)) / 100,
        "missed_rate": c[1].slider("Info-related missed boardings (per 10,000 departing)", 2, 40,
                                   int(d["missed_rate"] * 10000)) / 10000,
        "opt_in": c[2].slider("% passengers opted in to alerts", 10, 90, int(d["opt_in"] * 100)) / 100,
        "nudge_effect": c[3].slider("% of reached at-risk passengers who then make it", 20, 90,
                                    int(d["nudge_effect"] * 100)) / 100,
    }
    v = value.estimate(**kw)
    k = st.columns(4)
    k[0].metric("Desk questions handled / day", v["handled_by_assistant_per_day"], f"-{v['desk_load_reduction_pct']}% desk load")
    k[1].metric("Staff time saved / day", f"{v['staff_hours_saved_per_day']} h", f"≈ {v['staff_shifts_freed_per_day']} shifts")
    k[2].metric("Missed boardings avoided / year", f"{v['missed_boardings_avoided_per_year']:,}",
                f"{v['missed_boardings_avoided_per_day']} / day")
    k[3].metric("Peak desk utilisation", f"{v['peak_utilisation_after_pct']}%",
                f"from {v['peak_utilisation_before_pct']}%", delta_color="inverse")
    st.markdown(f"Annual value ≈ **AED {v['annual_staff_value_aed']:,.0f}** staff time + "
                f"**AED {v['annual_missed_boarding_value_aed']:,.0f}** avoided missed-boarding costs. "
                f"Peak queue: {v['peak_queue_before_people']} → {v['peak_queue_after_people']} people waiting "
                f"(M/M/c model, {v['inputs']['agents_at_peak']} agents).")
    demo = pd.DataFrame(db.outbox())
    if not demo.empty:
        st.caption(f"This demo session so far: {sum(demo['audience'] == 'chat')} traveller questions answered without the desk, "
                   f"{sum(demo['audience'] == 'individual')} proactive nudges, {sum(demo['audience'] == 'flight')} approved "
                   "flight-wide messages.")

# ============================================================== how it works
with tabs[5]:
    png = ROOT / "docs" / "flow_diagram.png"
    if png.exists():
        st.image(str(png), width="stretch")
    st.markdown("""
| Safety rule | How it is enforced (code, not prompts) |
|---|---|
| Never invent a gate/status/time | Replies are filled from templates with **reconciled** values only. Stage 6 guard rejects any draft containing an unverified field. |
| Conflicting feeds | Both feeds must agree. Disagreement < 3 min = *syncing*, ≥ 3 min = *conflict* → withheld + ops ticket. |
| Missing / stale data | Records older than 15 min are ignored. No fresh value = *unknown* → refuse to guess + data-gap ticket. |
| Staff approval for broadcasts | Whole-flight drafts pause in a durable LangGraph interrupt. Approve/reject is logged with staff ID; 5-min timeout = **not sent**. Live data is re-checked before sending. |
| Visa / immigration / security rules | Visa & immigration are always referred to official sources. Security answers quote the published guidance verbatim with source and review date. |
| Assistance & medical | Routed straight to PRM / medical + duty manager tickets. No automated decision. |
| Privacy | Names and booking refs are never stored: salted hash ids, masked contacts, redacted logs. The optional LLM only sees redacted text and only classifies intent. |
""")
