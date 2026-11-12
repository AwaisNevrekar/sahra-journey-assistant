"""Generates the one-page flow diagram (SVG -> PNG + PDF). Requires rsvg-convert or cairosvg.

    python docs/make_diagram.py
"""
import shutil
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent
W, H = 1600, 1130
INK, SAND, MUTED, LINE = "#0F2A3D", "#C8963E", "#5B6B78", "#9AA7B2"
parts = []


def box(x, y, w, h, title, lines=(), fill="#FFFFFF", stroke=INK, tcol=INK, r=10, tsize=17, lsize=13.5, bold=True):
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
    ty = y + 24 if lines else y + h / 2 + 6
    parts.append(f'<text x="{x + 12}" y="{ty}" font-size="{tsize}" font-weight="{700 if bold else 400}" fill="{tcol}">'
                 f'{escape(title)}</text>')
    for i, ln in enumerate(lines):
        parts.append(f'<text x="{x + 12}" y="{ty + 20 + i * 18}" font-size="{lsize}" fill="{MUTED}">{escape(ln)}</text>')


def arrow(x1, y1, x2, y2, color=INK, label=None, dash=False, lx=None, ly=None):
    d = ' stroke-dasharray="6 5"' if dash else ""
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2"{d} marker-end="url(#a)"/>')
    if label:
        parts.append(f'<text x="{lx if lx is not None else (x1 + x2) / 2 + 6}" y="{ly if ly is not None else (y1 + y2) / 2 - 4}" '
                     f'font-size="12.5" font-weight="700" fill="{color}">{escape(label)}</text>')


def path(d, color=INK, dash=False, label=None, lx=0, ly=0):
    da = ' stroke-dasharray="6 5"' if dash else ""
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{da} marker-end="url(#a)"/>')
    if label:
        parts.append(f'<text x="{lx}" y="{ly}" font-size="12.5" font-weight="700" fill="{color}">{escape(label)}</text>')


def heading(x, y, t, col=SAND):
    parts.append(f'<text x="{x}" y="{y}" font-size="14" font-weight="800" letter-spacing="1.5" fill="{col}">{escape(t)}</text>')


# ---------------------------------------------------------------- title
parts.append(f'<rect width="{W}" height="{H}" fill="#FBFAF7"/>')
parts.append(f'<rect width="{W}" height="64" fill="{INK}"/>')
parts.append('<text x="30" y="41" font-size="25" font-weight="800" fill="#FFFFFF">Sahra Journey Assistant</text>'
             f'<text x="400" y="41" font-size="18" fill="{SAND}">System flow · data feeds · decision rules</text>'
             '<text x="1570" y="41" font-size="14" fill="#C9D3DB" text-anchor="end">LangGraph · Pydantic · SQLite · Streamlit</text>')

# ---------------------------------------------------------------- inputs
heading(30, 95, "DATA FEEDS & TRIGGERS")
inputs = [("Display system (FIDS)", ["gate · status · boarding · ETD"]),
          ("Airline operations feed", ["same fields, independent source"]),
          ("Queue sensors", ["Passport & Security wait (min)"]),
          ("Traveller question", ["app / WhatsApp chat · EN · AR · HI"]),
          ("Every-minute scheduler", ["proactive journey scan"]),
          ("Staff console", ["approve / reject · close tickets"])]
iy = 110
for t, l in inputs:
    box(30, iy, 270, 62, t, l, fill="#FFFFFF", stroke=LINE)
    arrow(300, iy + 31, 355, 137 if iy < 470 else 137, color=LINE)
    iy += 74
box(30, iy + 6, 270, 92, "Mock reference data", ["terminal walking graph (m)", "published security & facility info",
                                                 "found-items register"], fill="#F3EEE4", stroke=SAND)

# ---------------------------------------------------------------- pipeline (centre)
X, CW = 360, 860
heading(X, 95, "AUTONOMOUS PIPELINE — one LangGraph run per event")
box(X, 110, CW, 52, "1  Trigger", ["feed update · traveller question · scheduled scan"], fill="#FFFFFF")
arrow(X + CW / 2, 162, X + CW / 2, 178)
box(X, 180, CW, 62, "2  Validate & sanitise",
    ["Pydantic schema (gate format, statuses, timezone) · timestamp not in future · prompt-injection / fake-broadcast filter"])
arrow(X + CW / 2, 242, X + CW / 2, 258)
box(X, 260, CW, 62, "3  Coordinator",
    ["Deterministic router (EN/AR/HI keywords) → worker · optional LLM only for 'unknown' intent, on redacted text"])
arrow(X + CW / 2, 322, X + CW / 2, 338)

# workers
parts.append(f'<rect x="{X}" y="340" width="{CW}" height="232" rx="10" fill="#EEF3F7" stroke="{INK}" stroke-width="1.6"/>')
parts.append(f'<text x="{X + 12}" y="364" font-size="17" font-weight="700" fill="{INK}">4  Specialised workers</text>'
             f'<text x="{X + 230}" y="364" font-size="13.5" fill="{MUTED}">(pure code unless stated)</text>')
wk = [("4a Feed reconciler", ["FIDS vs airline per field", "→ data state + staff alerts"]),
      ("4b Journey solver", ["Dijkstra walking route", "+ live queues → leave-by"]),
      ("4c Responder", ["EN / AR / HI templates", "filled with verified facts"]),
      ("4d Human hand-off", ["medical · wheelchair ·", "unanswerable → ticket now"]),
      ("4e Lost & found", ["match found register", "→ staff verify in person"]),
      ("4f Official info", ["quote published text only", "visa → official sources"]),
      ("4g Proactive scan", ["who must leave now?", "nudge + PRM buggy alert"])]
for i, (t, l) in enumerate(wk):
    cx = X + 14 + (i % 4) * 211
    cy = 378 + (i // 4) * 94
    box(cx, cy, 200, 84, t, l, fill="#FFFFFF", stroke=LINE, tsize=15, lsize=12.5)
parts.append(f'<text x="{X + 14 + 3 * 211 + 4}" y="{378 + 94 + 30}" font-size="12.5" fill="{MUTED}">feed events → 4a → 5</text>'
             f'<text x="{X + 14 + 3 * 211 + 4}" y="{378 + 94 + 48}" font-size="12.5" fill="{MUTED}">questions → 4a/4b/4c</text>'
             f'<text x="{X + 14 + 3 * 211 + 4}" y="{378 + 94 + 66}" font-size="12.5" fill="{MUTED}">or 4d / 4e / 4f</text>')
arrow(X + CW / 2, 572, X + CW / 2, 588)
box(X, 590, CW, 56, "5  Remember state",
    ["Detects gate change · delay ≥ 10 min · cancellation vs last CONFIRMED values · remembers what passengers were told"])
arrow(X + CW / 2, 646, X + CW / 2, 662)
box(X, 664, CW, 62, "6  Guard — code only, never an LLM",
    ["Broadcasts & nudges: CONFIRMED facts only · replies: CONFIRMED or named single source · no booking ref / phone in text"],
    fill="#FFF7E8", stroke=SAND)
arrow(X + 300, 726, X + 300, 750, label="whole flight", lx=X + 308, ly=744)
path(f"M {X + CW - 60} 726 L {X + CW - 60} 830", label="single reply / nudge → auto-send", lx=X + CW - 290, ly=744)
box(X, 752, 600, 60, "7  Staff approval (durable LangGraph interrupt)",
    ["approve / reject with staff ID · 5-min timeout = NOT sent + duty manager"], fill="#FCE9E7", stroke="#B42318")
arrow(X + 300, 812, X + 300, 830)
box(X, 832, CW, 54, "8  Write gateway",
    ["Re-reconciles live feeds: if anything changed since the draft → abort · otherwise one atomic outbox write"])
arrow(X + CW / 2, 886, X + CW / 2, 900)
box(X, 902, CW, 40, "9  Log & report  →  10  Streamlit dashboard (traveller app · staff console · live log)", [], tsize=15)

# blocked path
path(f"M {X} 226 L {X - 14} 226 L {X - 14} 700 L {X - 3} 700", color="#B42318", dash=True,
     label="blocked → refusal only", lx=X + CW - 175, ly=205)

# ---------------------------------------------------------------- outputs (right)
RX = 1262
heading(RX, 95, "OUTCOMES")
outs = [("Traveller reply", ["verified facts, or 'being confirmed'"], "#FFFFFF", LINE),
        ("Personal nudge", ["leave-now / at-risk, one passenger"], "#FFFFFF", LINE),
        ("Flight-wide broadcast", ["only after staff approval", "multilingual per passenger"], "#FFFFFF", LINE)]
oy = 110
for t, l, f, s in outs:
    box(RX, oy, 310, 54 + 18 * (len(l) - 1), t, l, fill=f, stroke=s)
    oy += 70 + 18 * (len(l) - 1)
heading(RX, oy + 22, "HUMAN HAND-OFFS (tickets)")
tk = [("Medical + duty manager", "URGENT"), ("PRM assistance team", "HIGH"), ("Ops control", "conflict · data gap"),
      ("Gate team", "at-risk passenger"), ("Lost & Found", "verify ownership"), ("Info desk", "unanswered question"),
      ("Duty manager", "approval timeout")]
ty = oy + 34
for t, s in tk:
    parts.append(f'<rect x="{RX}" y="{ty}" width="310" height="34" rx="8" fill="#FFFFFF" stroke="{LINE}"/>'
                 f'<text x="{RX + 12}" y="{ty + 22}" font-size="14" font-weight="700" fill="{INK}">{escape(t)}</text>'
                 f'<text x="{RX + 298}" y="{ty + 22}" font-size="12.5" fill="#B42318" text-anchor="end">{escape(s)}</text>')
    ty += 40
box(RX, ty + 6, 310, 72, "Audit log & outbox", ["every feed read, decision, approval,", "message — pseudonymous ids only"],
    fill="#F3EEE4", stroke=SAND)
path(f"M {X + CW} 859 L {RX - 22} 859 L {RX - 22} 137 L {RX - 4} 137", color=INK)
parts.append(f'<line x1="{RX - 22}" y1="225" x2="{RX - 4}" y2="225" stroke="{INK}" stroke-width="2" marker-end="url(#a)"/>'
             f'<line x1="{RX - 22}" y1="320" x2="{RX - 4}" y2="320" stroke="{INK}" stroke-width="2" marker-end="url(#a)"/>')
path(f"M {X + CW} 425 L {RX - 40} 425 L {RX - 40} {oy + 50} L {RX - 4} {oy + 50}", color="#B42318", dash=True)

# ---------------------------------------------------------------- decision rules band
BY = 962
parts.append(f'<rect x="30" y="{BY}" width="{W - 60}" height="150" rx="12" fill="#FFFFFF" stroke="{INK}" stroke-width="1.6"/>')
heading(48, BY + 26, "DECISION RULES — per field, per flight (4a)", col=INK)
states = [("CONFIRMED", "#1B7F4B", "both fresh feeds agree", "broadcasts · nudges · replies"),
          ("SINGLE SOURCE", "#2E6FB7", "only one fresh feed has it", "replies only, source named"),
          ("SYNCING", "#B26A00", "feeds disagree < 3 min", "withheld: 'being confirmed'"),
          ("CONFLICT", "#B42318", "feeds disagree ≥ 3 min", "withheld + ops ticket"),
          ("UNKNOWN", "#6B7280", "no fresh value (> 15 min old)", "refuse to guess + data-gap ticket")]
for i, (n, c, rule, use) in enumerate(states):
    x = 48 + i * 305
    parts.append(f'<rect x="{x}" y="{BY + 42}" width="132" height="26" rx="13" fill="{c}"/>'
                 f'<text x="{x + 66}" y="{BY + 60}" font-size="13" font-weight="800" fill="#FFFFFF" text-anchor="middle">{n}</text>'
                 f'<text x="{x}" y="{BY + 90}" font-size="13.5" fill="{INK}">{escape(rule)}</text>'
                 f'<text x="{x}" y="{BY + 110}" font-size="13.5" font-weight="700" fill="{c}">→ {escape(use)}</text>')
parts.append(f'<text x="48" y="{BY + 138}" font-size="13" fill="{MUTED}">Thresholds (sahra/config.py): feed stale 15 min · '
             'conflict grace 3 min · approval timeout 5 min · arrive 5 min before boarding · nudge 5 min before leave-by · '
             'walking 72 / 54 / 36 m·min⁻¹ (standard / family / reduced mobility)</text>')

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       'font-family="DejaVu Sans, Inter, Segoe UI, Arial, sans-serif">'
       f'<defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto">'
       f'<path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker></defs>' + "".join(parts) + "</svg>")
(OUT / "flow_diagram.svg").write_text(svg, encoding="utf-8")
if shutil.which("rsvg-convert"):
    subprocess.run(["rsvg-convert", "-w", "2400", "-o", str(OUT / "flow_diagram.png"), str(OUT / "flow_diagram.svg")], check=True)
    subprocess.run(["rsvg-convert", "-f", "pdf", "-o", str(OUT / "flow_diagram.pdf"), str(OUT / "flow_diagram.svg")], check=True)
else:
    import cairosvg
    cairosvg.svg2png(url=str(OUT / "flow_diagram.svg"), write_to=str(OUT / "flow_diagram.png"), output_width=2400)
    cairosvg.svg2pdf(url=str(OUT / "flow_diagram.svg"), write_to=str(OUT / "flow_diagram.pdf"))
print("written", OUT / "flow_diagram.png")
