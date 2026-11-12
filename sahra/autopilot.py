"""Autonomous loop: every simulated minute it (1) ingests any new feed records, (2) runs the proactive journey scan,
(3) expires unapproved broadcasts. No human prompting needed — staff only approve broadcasts.

    python -m sahra.autopilot --minutes 20 [--auto-approve DEMO-STAFF]
"""
import argparse
import json

from . import clock, config, db, engine

REPLAY = json.loads((config.DATA / "feed_replay.json").read_text())["events"]


def pending_replay():
    done = set(json.loads(db.get_setting("replay_done", "[]")))
    return [e for e in REPLAY if e["id"] not in done]


def step(minutes=1):
    engine.advance(minutes)
    actions = []
    done = set(json.loads(db.get_setting("replay_done", "[]")))
    for ev in REPLAY:
        if ev["id"] in done or clock.parse(ev["at"]) > clock.now():
            continue
        rec = dict(ev["record"], updated_at=clock.now().isoformat())
        res = engine.feed_update(rec)
        done.add(ev["id"])
        db.set_setting("replay_done", json.dumps(sorted(done)))
        actions.append(f"📡 {ev['label']} → {res['outcome']}")
    res = engine.tick()
    if res["outcome"] != "NO_ACTION_NEEDED":
        actions.append(f"⏰ Proactive scan → {res['outcome']}")
    for r in engine.expire_overdue():
        actions.append(f"⌛ Approval timed out → {r['outcome']}")
    return actions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=20)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--auto-approve", default=None, help="staff id to auto-approve broadcasts (headless demo only)")
    a = ap.parse_args()
    engine.init(reset=a.reset)
    for _ in range(a.minutes):
        acts = step()
        if a.auto_approve:
            for p in db.approvals("PENDING"):
                acts.append(f"✅ {p['id']} approved by {a.auto_approve} → {engine.decide(p['id'], 'approve', a.auto_approve)['outcome']}")
        for x in acts:
            print(f"[{clock.hhmm(clock.now())}] {x}")
    print(f"Outbox: {len(db.outbox())} messages · open tickets: {len(db.tickets('OPEN'))}")


if __name__ == "__main__":
    main()
