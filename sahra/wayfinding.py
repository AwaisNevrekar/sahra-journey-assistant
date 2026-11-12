"""Stage 4b — Journey solver (no LLM): shortest walking route + live queue times -> leave-by time."""
import heapq
import json
import math
import re
from datetime import timedelta

from . import clock, config, db

MAP = json.loads((config.DATA / "terminal_map.json").read_text(encoding="utf-8"))
NODES = MAP["nodes"]
GRAPH = {}
for a, b, m in MAP["edges"]:
    GRAPH.setdefault(a, []).append((b, m))
    GRAPH.setdefault(b, []).append((a, m))
ALIASES = sorted(MAP["aliases"].items(), key=lambda kv: -len(kv[0]))
GATE_LOC_RE = re.compile(r"\b(?:at|near|by|next to)\s+gate\s+([AB]\d{1,2})\b", re.I)


def label(node):
    return NODES.get(node, {}).get("label", node)


def parse_location(text: str):
    m = GATE_LOC_RE.search(text or "")
    if m and m.group(1).upper() in NODES:
        return m.group(1).upper()
    low = (text or "").lower()
    for alias, node in ALIASES:
        if alias in low:
            return node
    return None


def shortest(a, b):
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
