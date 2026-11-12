"""Stage 4b — Journey solver and wayfinding (no LLM).

* shortest(): walking route on the terminal graph. Once airside, a route never goes back through security.
* plan(): walking time + live queue times -> leave-by time for a boarding time.
* parse_places(): finds the places named in a question and decides which is "where I am" and which is "where I'm going".
* route(): nearest matching destination with a short, sign-based description of the way.
"""
import heapq
import json
import math
import re
from datetime import timedelta

from . import clock, config, db

MAP = json.loads((config.DATA / "terminal_map.json").read_text(encoding="utf-8"))
NODES = MAP["nodes"]
DESTS = MAP["destinations"]
GRAPH = {}
for a, b, m in MAP["edges"]:
    GRAPH.setdefault(a, []).append((b, m))
    GRAPH.setdefault(b, []).append((a, m))
ALIASES = sorted(MAP["aliases"].items(), key=lambda kv: -len(kv[0]))
GATE_RE = re.compile(r"(?<![A-Za-z0-9])(?:gate\s*|بوابة\s*|البوابة\s*|गेट\s*)?([ABab](?:1[0-2]|[1-9]))(?![0-9A-Za-z])")
GATE_LOC_RE = re.compile(r"\b(?:at|near|by|next to)\s+gate\s+([AB]\d{1,2})\b", re.I)

# words that mark the following place as "where I am" (English, Arabic) / the preceding place (Hindi postpositions)
ORIGIN_BEFORE = re.compile(r"(?:\b(?:at|near|by|from|outside|next to|in|beside|opposite)\s+(?:the\s+)?(?:gate\s+)?|"
                           r"(?:في|عند|قرب|بجانب|من)\s*(?:ال)?)$", re.I)
DEST_BEFORE = re.compile(r"(?:\b(?:to|for|is|are|find|reach|towards|toward)\s+(?:the\s+|my\s+|a\s+)?(?:gate\s+)?|"
                         r"(?:إلى|الى|أين|اين)\s*(?:ال)?)$", re.I)
ORIGIN_AFTER_HI = re.compile(r"^\s*(?:पर|में|के पास|से)\b")


def label(node):
    return NODES.get(node, {}).get("label", node)


def is_gate(node):
    return bool(NODES.get(node, {}).get("gate"))


def sign_for(node):
    if is_gate(node):
        return "Gates A1–A6" if node.startswith("A") else "Gates B1–B12"
    for d in DESTS.values():
        if node in d["nodes"]:
            return d["sign"]
    return label(node)


def _mentions(text):
    """All place mentions as (start, end, kind, value): kind 'node' or 'dest' (a destination category)."""
    found, low = [], (text or "").lower()
    for m in GATE_RE.finditer(text or ""):
        g = m.group(1).upper()
        if g in NODES:
            found.append((m.start(), m.end(), "node", g))
    for key, d in DESTS.items():
        for kw in sorted(d["keywords"], key=len, reverse=True):
            i = low.find(kw.lower())
            if i >= 0 and (not kw.isascii() or re.search(rf"\b{re.escape(kw.lower())}\b", low)):
                found.append((i, i + len(kw), "dest", key))
                break
    for alias, node in ALIASES:
        i = low.find(alias)
        if i >= 0 and (not alias.isascii() or re.search(rf"\b{re.escape(alias)}\b", low)):
            found.append((i, i + len(alias), "node", node))
    found.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    out, last_end = [], -1
    for f in found:                      # drop overlaps (keep the longest mention at each position)
        if f[0] >= last_end:
            out.append(f)
            last_end = f[1]
    return out


def parse_places(text):
    """Return (origin_node or None, destination or None). destination = ('node', id) | ('dest', category)."""
    origin, dest = None, None
    for start, end, kind, val in _mentions(text):
        before, after = (text or "")[:start][-30:], (text or "")[end:end + 14]
        node = val if kind == "node" else (DESTS[val]["nodes"][0] if len(DESTS[val]["nodes"]) == 1 else None)
        if node and (ORIGIN_BEFORE.search(before) and not DEST_BEFORE.search(before) or ORIGIN_AFTER_HI.search(after)):
            origin = origin or node
        elif dest is None:
            dest = (kind, val)
        elif node and origin is None:
            origin = node
    return origin, dest


def parse_location(text):
    """Where the person says they are (used by hand-offs, lost items and walking time)."""
    m = GATE_LOC_RE.search(text or "")
    if m and m.group(1).upper() in NODES:
        return m.group(1).upper()
    origin, dest = parse_places(text)
    if origin:
        return origin
    if dest and dest[0] == "node":
        return dest[1]
    if dest and dest[0] == "dest" and len(DESTS[dest[1]]["nodes"]) == 1:
        return DESTS[dest[1]]["nodes"][0]
    return None


def shortest(a, b):
    """Dijkstra. Starting airside, landside nodes are not allowed (you can't walk back through security)."""
    airside_start = NODES.get(a, {}).get("airside", False)
    dist, prev, seen = {a: 0}, {}, set()
    pq = [(0, a)]
    while pq:
        d, n = heapq.heappop(pq)
        if n in seen:
            continue
        seen.add(n)
        if n == b:
            break
        for nb, w in GRAPH.get(n, []):
            if airside_start and not NODES[nb].get("airside", False):
                continue
            nd = d + w
            if nd < dist.get(nb, 1e18):
                dist[nb], prev[nb] = nd, n
                heapq.heappush(pq, (nd, nb))
    if b not in dist:
        return None, []
    path, n = [b], b
    while n != a:
        n = prev[n]
        path.append(n)
    return dist[b], path[::-1]


def route(origin, targets, mobility="standard"):
    """Nearest reachable target from origin. Returns dict, or {'unreachable': True} if all targets are landside."""
    best = None
    for t in targets:
        d, path = shortest(origin, t)
        if d is not None and (best is None or d < best[0]):
            best = (d, path, t)
    if best is None:
        return {"unreachable": True}
    d, path, t = best
    speed = config.SPEEDS_M_PER_MIN.get(mobility, config.SPEEDS_M_PER_MIN["standard"])
    waypoints = [n for i, n in enumerate(path) if i in (0, len(path) - 1) or not is_gate(n)]
    return {"origin": origin, "target": t, "distance_m": int(d), "walk_min": max(1, math.ceil(d / speed)),
            "waypoints": [label(n) for n in waypoints], "sign": sign_for(t), "path": path}


def plan(origin: str, gate: str, boarding_iso: str, mobility: str = "standard") -> dict:
    now = clock.now()
    dist, path = shortest(origin, gate)
    if dist is None:
        return {"error": "no route"}
    speed = config.SPEEDS_M_PER_MIN.get(mobility, config.SPEEDS_M_PER_MIN["standard"])
    walk = max(1, math.ceil(dist / speed))
    queue_min, known, unknown = 0, [], []
    for node in path:
        if NODES[node].get("checkpoint"):
            qrow = db.get_queue(node)
            if qrow and clock.minutes_since(qrow["updated_at"]) <= config.QUEUE_STALE_MIN:
                queue_min += qrow["wait_min"]
                known.append({"checkpoint": label(node), "wait_min": qrow["wait_min"]})
            else:
                unknown.append(label(node))
    boarding = clock.parse(boarding_iso)
    leave_by = boarding - timedelta(minutes=walk + queue_min + config.WALK_BUFFER_MIN)
    if now + timedelta(minutes=walk + queue_min) > boarding:
        status = "AT_RISK"
    elif now >= leave_by - timedelta(minutes=config.NUDGE_LEAD_MIN):
        status = "LEAVE_NOW"
    else:
        status = "ON_TRACK"
    return {"origin": origin, "origin_label": label(origin), "gate": gate, "distance_m": int(dist), "walk_min": walk,
            "mobility": mobility, "queues_known": known, "queues_unknown": unknown, "queue_min": queue_min,
            "boarding": boarding.isoformat(), "leave_by": leave_by.isoformat(), "status": status,
            "minutes_to_leave": round((leave_by - now).total_seconds() / 60), "path": path}
