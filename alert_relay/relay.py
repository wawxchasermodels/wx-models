#!/usr/bin/env python3
"""One-shot GitHub Actions backup for the urgent and quiet weather watchers.

Reads repository-variable heartbeats. A fresh heartbeat means that channel's
box watcher is alive: the relay POSTs nothing. A stale or missing heartbeat
means the relay runs one tick of the same filters and POSTs the same webhook
bodies. State stays in the Actions cache. Alerts the relay actually POSTs are
also published to sent.json on branch relay-state so the box can skip them
when it wakes up.

  ALERT_RELAY_DRY_RUN=1 python3 alert_relay/relay.py

Dry-run fetches live data, writes nothing to the real cache, and prints the
webhook bodies it would POST.
"""
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import constants
import github_api
import heartbeat
import sent_index
from adopt import parse_time

log = logging.getLogger("alert_relay")


def _dry():
    return os.environ.get("ALERT_RELAY_DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def _repo():
    return os.environ.get("GITHUB_REPOSITORY") or os.environ.get("ALERT_RELAY_REPO") or constants.DEFAULT_REPO


def _load(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def _save(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def mask_secrets():
    for name in constants.SECRET_NAMES:
        value = os.environ.get(name) or ""
        if value:
            sys.stdout.write("::add-mask::%s\n" % value)
    sys.stdout.flush()


def scrub(text):
    for name in constants.SECRET_NAMES:
        value = os.environ.get(name) or ""
        if value and value in text:
            text = text.replace(value, "***")
    return text


def _secrets_ok(prefix):
    url = os.environ.get(prefix + "_WEBHOOK_URL") or ""
    auth = os.environ.get(prefix + "_WEBHOOK_AUTH") or ""
    return bool(url and auth)


def prepare_base(cache_dir, dry):
    os.makedirs(cache_dir, exist_ok=True)
    if not dry:
        return cache_dir
    tmp = tempfile.mkdtemp(prefix="alert-relay-dry-")
    for name in os.listdir(cache_dir):
        src = os.path.join(cache_dir, name)
        dst = os.path.join(tmp, name)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
    return tmp


def load_remote_sent():
    token = os.environ.get("GITHUB_TOKEN") or ""
    try:
        code, body = github_api.get_raw_file(_repo(), constants.STATE_PATH, constants.STATE_BRANCH, token)
    except Exception as exc:
        log.warning("sent index fetch failed (%s)", type(exc).__name__)
        return None
    if code != 200 or not isinstance(body, str) or not body.strip():
        return None
    try:
        doc = json.loads(body)
    except Exception:
        return None
    if isinstance(doc, dict) and doc.get("version") == 1:
        return doc
    return None


def publish_sent(doc):
    if os.environ.get("ALERT_RELAY_PUBLISH") != "1":
        return False
    token = os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        log.warning("sent index not published (GITHUB_TOKEN unset)")
        return False
    repo = _repo()
    if not github_api.ensure_branch(repo, constants.STATE_BRANCH, "main", token):
        log.warning("sent index not published (could not open %s)", constants.STATE_BRANCH)
        return False
    sha = github_api.get_contents_sha(repo, constants.STATE_PATH, constants.STATE_BRANCH, token)
    payload = json.dumps(doc, indent=1, sort_keys=True).encode("utf-8") + b"\n"
    code, _body = github_api.put_contents(
        repo, constants.STATE_PATH, constants.STATE_BRANCH,
        "relay: record alerts the backup posted", payload, sha, token,
    )
    if code in (200, 201):
        log.info("published %s on %s", constants.STATE_PATH, constants.STATE_BRANCH)
        return True
    log.warning("sent index publish failed (http %s)", code)
    return False


def rehydrate(sent, base):
    """Copy relay-sent ids into the watcher files. Returns which seen files already existed."""
    urgent_path = os.path.join(base, "seen.json")
    quiet_path = os.path.join(base, "seen_quiet.json")
    existed = {"urgent": os.path.exists(urgent_path), "quiet": os.path.exists(quiet_path)}
    if not isinstance(sent, dict):
        return existed
    urgent = sent.get("urgent") or {}
    quiet = sent.get("quiet") or {}
    if urgent.get("keys"):
        cur = _load(urgent_path, {})
        for key, value in urgent["keys"].items():
            cur.setdefault(key, value)
        _save(urgent_path, cur)
    if quiet.get("seen"):
        cur = _load(quiet_path, {})
        for key, value in quiet["seen"].items():
            cur.setdefault(key, value)
        _save(quiet_path, cur)
    if quiet.get("quakes"):
        path = os.path.join(base, "seen_quakes_quiet.json")
        cur = _load(path, {})
        for key, value in quiet["quakes"].items():
            cur.setdefault(key, value)
        _save(path, cur)
    if quiet.get("gov_feeds"):
        path = os.path.join(base, "gov_imagery_seen.json")
        doc = _load(path, {})
        if not isinstance(doc, dict):
            doc = {}
        feeds = doc.setdefault("feeds", {})
        for key, value in quiet["gov_feeds"].items():
            feeds.setdefault(key, value)
        _save(path, doc)
    if quiet.get("spc_posted") and not os.path.exists(os.path.join(base, "spc_quiet_state.json")):
        fired = []
        for rec in quiet["spc_posted"].values():
            fired.extend(rec.get("ids") or [])
        _save(os.path.join(base, "spc_quiet_state.json"), {
            "schema": 2, "days": {}, "posted": quiet["spc_posted"], "fired": fired[-40:],
            "seeded_at": sent.get("updated"), "last_poll": sent.get("updated"),
        })
    if quiet.get("hurricanes") and not os.path.exists(os.path.join(base, "hurricanes_quiet_state.json")):
        _save(os.path.join(base, "hurricanes_quiet_state.json"), {
            "storms": quiet["hurricanes"], "seeded_at": sent.get("updated"), "last_poll": sent.get("updated"),
        })
    snap = quiet.get("pass_snapshot")
    if isinstance(snap, dict) and snap.get("passes") and not os.path.exists(os.path.join(base, "passes_quiet_state.json")):
        _save(os.path.join(base, "passes_quiet_state.json"), {
            "passes": snap["passes"], "seeded_at": snap.get("at"), "last_poll": snap.get("at"), "last_changes": [],
        })
    return existed


def _brief(item, fields):
    return {key: item.get(key) for key in fields if item.get(key) not in (None, "", [])}


def _old(item, now, minutes, field):
    sent = parse_time(item.get(field) or "")
    if sent is None:
        return True
    return sent < now - timedelta(minutes=minutes)


def _split_seed(items, now, field="sent"):
    seeded, keep = [], []
    for item in items:
        if _old(item, now, constants.SEED_RECENT_MINUTES, field):
            seeded.append(item)
        else:
            keep.append(item)
    return seeded, keep


def _hourly_posts(state):
    now = time.time()
    return [t for t in (state or {}).get("posts") or [] if isinstance(t, (int, float)) and t > now - 3600]


def _preview_pid(prefix, state, keys, now_iso):
    import payload_seen
    key = sorted({str(k) for k in keys})
    inflight = (state or {}).get("inflight_payload") or {}
    if inflight.get("ids") == key and inflight.get("payload_id"):
        return inflight["payload_id"]
    return payload_seen.compute_id(prefix, key, now_iso)


def refresh_passes(base):
    """While the quiet watcher is alive, keep the pass snapshot current.

    Mountain-pass ids hash the whole change list. A week-old snapshot would
    POST one combined diff the receiver has never seen. Refreshing while the
    heartbeat is fresh means a takeover only diffs what changed after the box
    stopped. The refresh itself never POSTs.
    """
    import net
    import passes_quiet
    import watch
    path = os.path.join(base, "passes_quiet_state.json")
    doc = _load(path, {})
    if not isinstance(doc, dict):
        doc = {}
    last = float(doc.get("refreshed_ts") or 0)
    if time.time() - last < passes_quiet.PASS_POLL_SECONDS:
        return "not_due"
    try:
        snap = passes_quiet.fetch_passes(net.Session(), watch.USER_AGENT)
    except Exception as exc:
        log.warning("pass snapshot refresh failed (%s)", type(exc).__name__)
        return "error"
    now = datetime.now(timezone.utc).isoformat()
    _save(path, {
        "passes": snap,
        "seeded_at": doc.get("seeded_at") or now,
        "last_poll": now,
        "last_changes": [],
        "refreshed_ts": time.time(),
        "refreshed_while": "box_heartbeat_fresh",
    })
    log.info("refreshed %d mountain-pass rows while the quiet heartbeat was fresh", len(snap))
    return "refreshed"


def _urgent_report(res, now, adopt_before, do_seed):
    import watch
    if res is None:
        return {"action": "fetch_failed", "would_send": [], "body": None}
    send = list(res.get("send") or [])
    held = list(res.get("held") or [])
    adopted = []
    if adopt_before is not None:
        import adopt
        adopted, send = adopt.partition(send, adopt_before, watch._urgent_held_at_issue, lambda item: parse_time(item.get("sent") or ""))
    seeded = []
    if do_seed:
        seeded, send = _split_seed(send + held, now)
        held = [item for item in held if item not in seeded]
        send = [item for item in send if item not in seeded and item not in held]
    state = _load(watch.STATE_FILE, {"posts": []})
    posts = _hourly_posts(state)
    capped = []
    if len(posts) >= watch.MAX_POSTS_PER_HOUR:
        capped = [item for item in send if not watch.cap_exempt(item)]
        send = [item for item in send if watch.cap_exempt(item)]
    body = None
    if send:
        pid = _preview_pid("u", state, [item.get("id") for item in send], now.isoformat())
        body = {"source": "urgent_watch", "alerts": send, "payload_id": pid}
    return {
        "action": "would_send" if body else "nothing_to_send",
        "active": res.get("active"),
        "overnight": res.get("overnight"),
        "would_send_count": len(send),
        "would_hold_count": len(held),
        "would_seed_count": len(seeded),
        "would_adopt_count": len(adopted),
        "would_cap_count": len(capped),
        "would_seed": [_brief(item, ("id", "event", "scope", "reason", "areaDesc", "sent")) for item in seeded],
        "would_send": send,
        "would_hold": held,
        "body": body,
    }


def _quiet_report(res, now, adopt_before, do_seed):
    import watch_quiet
    if res is None:
        return {"action": "fetch_failed", "would_send": [], "body": None}
    items = list(res.get("qualifying") or [])
    # Same order as the live loop: cold-start seed, then adopt, then the overnight hold.
    seeded = []
    if do_seed:
        seeded, items = _split_seed(items, now)
    adopted = []
    if adopt_before is not None:
        import adopt
        def _held(item, sent_at):
            return watch_quiet.overnight_held(item.get("page"), sent_at) if not item.get("kind") else False
        adopted, items = adopt.partition(items, adopt_before, _held, lambda item: parse_time(item.get("sent") or ""))
    held = [item for item in items if watch_quiet.overnight_held(item.get("page"), now)]
    send = [item for item in items if item not in held]
    quakes = list(res.get("quakes_qualifying") or [])
    quake_adopted = []
    if adopt_before is not None:
        import adopt
        quake_adopted, quakes = adopt.partition(quakes, adopt_before, lambda item, sent_at: False, lambda item: parse_time(item.get("time") or ""))
    spc_hold, spc_send = [], []
    for item in res.get("spc_qualifying") or []:
        if watch_quiet.overnight_held(item.get("page"), now):
            spc_hold.append(item)
        else:
            spc_send.append(item)
    hurricanes = [] if res.get("hurricanes_would_seed") else list(res.get("hurricanes_qualifying") or [])
    passes = []
    if res.get("passes_state_seeded") and res.get("passes_changes"):
        passes = [watch_quiet.passes_quiet.pass_item(res["passes_changes"], now.isoformat())]
    gov = None
    if res.get("gov_imagery_in_window") and res.get("gov_imagery_would_send"):
        gov = res["gov_imagery_would_send"]
    batch = send + quakes + spc_send + hurricanes + passes + ([gov] if gov else [])
    state = _load(watch_quiet.STATE_FILE, {"posts": []})
    posts = _hourly_posts(state)
    capped = False
    if len(posts) >= watch_quiet.MAX_POSTS_PER_HOUR and batch:
        capped = True
        batch = []
    body = None
    if batch:
        keys = [watch_quiet._batch_key(item) for item in batch]
        pid = _preview_pid("q", state, keys, now.isoformat())
        body = watch_quiet.batch_body(batch, pid, now)
    return {
        "action": "would_send" if body else "nothing_to_send",
        "active_alerts": res.get("active"),
        "quakes_active": res.get("quakes_active"),
        "would_send_count": len(batch),
        "would_hold_alerts": len(held),
        "would_seed_alerts": [_brief(item, ("id", "page", "event", "area", "reason", "sent")) for item in seeded],
        "would_adopt_alerts": len(adopted),
        "would_adopt_quakes": len(quake_adopted),
        "quakes_stale_would_seed": res.get("quakes_stale_would_seed"),
        "spc_would_send": len(spc_send),
        "spc_would_hold": len(spc_hold),
        "spc_would_seed_days": res.get("spc_would_seed_days"),
        "hurricanes_would_seed": bool(res.get("hurricanes_would_seed")),
        "hurricanes_would_send": len(hurricanes),
        "passes_would_send": len(passes),
        "passes_would_seed": not res.get("passes_state_seeded"),
        "gov_in_window": res.get("gov_imagery_in_window"),
        "gov_would_send": bool(gov),
        "capped": capped,
        "errors": {k: res.get(k) for k in ("passes_error", "spc_error", "hurricanes_error", "gov_imagery_error") if res.get(k)},
        "body": body,
    }


def _set_adopt(stamp):
    if stamp is None:
        os.environ.pop("ALERT_RELAY_ADOPT_BEFORE", None)
    else:
        os.environ["ALERT_RELAY_ADOPT_BEFORE"] = stamp.isoformat()


def _set_force(flag):
    if flag:
        os.environ["ALERT_RELAY_FORCE_SEED"] = "1"
    else:
        os.environ.pop("ALERT_RELAY_FORCE_SEED", None)


def fold_new_deliveries(base, sent):
    path = os.path.join(base, "relay_delivered.jsonl")
    rows = sent_index.read_jsonl(path)
    if not rows:
        return sent, False
    sent = sent_index.fold(sent, rows)
    if any(item.get("kind") == "mountain-pass" for row in rows for item in (row.get("items") or [])):
        passes = _load(os.path.join(base, "passes_quiet_state.json"), {})
        if isinstance(passes, dict) and passes.get("passes"):
            sent_index.set_pass_snapshot(sent, passes["passes"], rows[-1].get("at"))
    sent = sent_index.prune(sent)
    try:
        os.remove(path)
    except OSError:
        pass
    return sent, True


def channel_plan(raw, max_age, now):
    state, age, stamp = heartbeat.status(raw, max_age, now)
    adopt = stamp if state == "stale" and stamp is not None else None
    return {"state": state, "age_sec": None if age is None else round(age, 1), "adopt_before": adopt}


def main():
    started = time.time()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    mask_secrets()
    dry = _dry()
    cache_dir = os.environ.get("ALERT_RELAY_CACHE_DIR") or os.path.join(ROOT, ".cache")
    base = prepare_base(cache_dir, dry)
    os.environ["ALERT_RELAY"] = "1"
    os.environ["ALERT_RELAY_BASE"] = base
    logic_dir = os.path.join(ROOT, "logic")
    if logic_dir not in sys.path:
        sys.path.insert(0, logic_dir)
    # Imported after BASE is set; the copied modules read it at import time.
    import watch
    import watch_quiet

    now = datetime.now(timezone.utc)
    urgent_plan = channel_plan(os.environ.get("ALERT_RELAY_HB_URGENT"), constants.URGENT_HEARTBEAT_MAX_AGE_SEC, now)
    quiet_plan = channel_plan(os.environ.get("ALERT_RELAY_HB_QUIET"), constants.QUIET_HEARTBEAT_MAX_AGE_SEC, now)
    log.info("urgent heartbeat %s age=%s; quiet heartbeat %s age=%s; dry_run=%s",
             urgent_plan["state"], urgent_plan["age_sec"], quiet_plan["state"], quiet_plan["age_sec"], dry)

    local_sent = sent_index.load(os.path.join(base, "sent.json"))
    remote_sent = load_remote_sent()
    sent = sent_index.union_sent(local_sent, remote_sent) if remote_sent else local_sent
    existed = rehydrate(sent, base)
    sent_index.save(os.path.join(base, "sent.json"), sent)

    report = {
        "dry_run": dry,
        "urgent_heartbeat": urgent_plan["state"],
        "urgent_heartbeat_age_sec": urgent_plan["age_sec"],
        "quiet_heartbeat": quiet_plan["state"],
        "quiet_heartbeat_age_sec": quiet_plan["age_sec"],
    }
    exit_code = 0

    # --- urgent ---
    if urgent_plan["state"] == "fresh" and not dry:
        report["urgent"] = {"action": "skip", "reason": "heartbeat fresh"}
        log.info("urgent watcher heartbeat is fresh; not sending")
    elif urgent_plan["state"] == "fresh" and dry:
        report["urgent"] = {"action": "skip", "reason": "heartbeat fresh", "would_send": [], "body": None}
        log.info("dry-run: urgent heartbeat fresh, would send nothing")
    else:
        if not dry and not _secrets_ok("URGENT"):
            log.error("urgent heartbeat is %s and URGENT_WEBHOOK_URL / URGENT_WEBHOOK_AUTH are missing", urgent_plan["state"])
            report["urgent"] = {"action": "missing_secrets"}
            exit_code = 1
        else:
            _set_adopt(None if dry else urgent_plan["adopt_before"])
            _set_force((not existed["urgent"]) and urgent_plan["adopt_before"] is None and not dry)
            try:
                res = watch.run(once=True, dry_run=dry)
            except SystemExit as exc:
                log.error("urgent watcher exited %s", exc.code)
                res = None
                exit_code = 1
            if dry:
                # do_seed for the report mirrors the live first-run rule, including schema.
                state = _load(watch.STATE_FILE, {})
                do_seed = ((not existed["urgent"] or state.get("schema", 1) < watch.SCHEMA)
                           and urgent_plan["adopt_before"] is None)
                report["urgent"] = _urgent_report(res, now, urgent_plan["adopt_before"], do_seed)
            else:
                report["urgent"] = {"action": "fetch_failed" if res is None else "ran"}
                if res is None and exit_code == 0:
                    log.warning("urgent fetch failed; will retry next run")

    # --- quiet ---
    if quiet_plan["state"] == "fresh" and not dry:
        report["quiet"] = {"action": "skip", "reason": "heartbeat fresh", "passes": refresh_passes(base)}
        log.info("quiet watcher heartbeat is fresh; not sending")
    elif quiet_plan["state"] == "fresh" and dry:
        report["quiet"] = {"action": "skip", "reason": "heartbeat fresh", "would_send": [], "body": None}
        log.info("dry-run: quiet heartbeat fresh, would send nothing")
    else:
        if not dry and not _secrets_ok("QUIET"):
            log.error("quiet heartbeat is %s and QUIET_WEBHOOK_URL / QUIET_WEBHOOK_AUTH are missing", quiet_plan["state"])
            report["quiet"] = {"action": "missing_secrets"}
            exit_code = 1
        else:
            _set_adopt(None if dry else quiet_plan["adopt_before"])
            _set_force((not existed["quiet"]) and quiet_plan["adopt_before"] is None and not dry)
            try:
                res = watch_quiet.run(once=True, dry_run=dry)
            except SystemExit as exc:
                log.error("quiet watcher exited %s", exc.code)
                res = None
                exit_code = 1
            if dry:
                do_seed = (not existed["quiet"]) and quiet_plan["adopt_before"] is None
                report["quiet"] = _quiet_report(res, now, quiet_plan["adopt_before"], do_seed)
            else:
                report["quiet"] = {"action": "fetch_failed" if res is None else "ran"}
                if res is None and exit_code == 0:
                    log.warning("quiet fetch failed; will retry next run")

    if not dry:
        sent, changed = fold_new_deliveries(base, sent)
        sent_index.save(os.path.join(base, "sent.json"), sent)
        if changed:
            publish_sent(sent)
        elif remote_sent and sent_index.canonical(sent) != sent_index.canonical(remote_sent):
            publish_sent(sent)

    report["elapsed_sec"] = round(time.time() - started, 1)
    print(json.dumps(report, indent=1, default=str))
    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.stderr.write(scrub(traceback.format_exc()))
        sys.exit(1)
