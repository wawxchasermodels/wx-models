#!/usr/bin/env python3
"""WA ASK-FIRST switch (Benjamin 10-30-26 6:25 PM). Config: /workspace/wa_alerts/wa_ask_first.json (read on every call).

  needs_ok(page, event, text="") -> (bool, why)   True = Slack #washingtonalerts + wait for Benjamin's OK, no auto-post
  python3 wa_ask_first.py EVENT [TEXT]           CLI check for the WA page (prints JSON, exit 0 auto allowed, 10 ask first)

enabled=false restores the old WA auto-post rules (tornado/SVR/waterspout/dust/winter+wind 10-28-26).
Mountain-pass posts are separate (pass_posts_auto) and not decided here.
"""
import json, sys
import os
CFG = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "wa_ask_first.json"))   # relay snapshot of the box switch (missing file = ask first)
ASK_NOTE = "WA ASK-FIRST (10-30-26 6:25 PM): send to Slack #washingtonalerts and WAIT for Benjamin's OK; do NOT auto-post"

def cfg():
    try: return json.load(open(CFG))
    except Exception: return {"enabled": True, "keep_auto_events": ["tornado warning", "tornado emergency"], "keep_auto_waterspout": True, "pass_posts_auto": True}   # fail safe = ask first

def needs_ok(page, event, text=""):
    if (page or "").lower() != "wa": return False, "not WA page"
    c = cfg()
    if not c.get("enabled", True): return False, "WA ask-first switch is OFF (old WA auto-post rules apply)"
    ev = (event or "").lower().strip()
    if ev in [e.lower() for e in c.get("keep_auto_events", [])]: return False, "kept auto: %s (standing life-safety permission)" % event
    if c.get("keep_auto_waterspout", True) and ev in ("special weather statement", "special marine warning", "marine weather statement") and "waterspout" in (text or "").lower():
        return False, "kept auto: WA waterspout %s" % event
    return True, ASK_NOTE

if __name__ == "__main__":
    if len(sys.argv) < 2: print(__doc__); sys.exit(2)
    n, why = needs_ok("wa", sys.argv[1], " ".join(sys.argv[2:]))
    print(json.dumps({"page": "wa", "event": sys.argv[1], "needs_benjamin_ok": n, "why": why})); sys.exit(10 if n else 0)
