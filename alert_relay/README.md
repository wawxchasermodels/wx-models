# Alert relay

GitHub Actions backup for the two weather-alert watchers that run on the Linux box. The box sometimes stays paused for hours. While it is paused, this scheduled job runs the same filters and POSTs the same webhook bodies. While the box watchers are alive, the job sends nothing.

The filter and payload code under `logic/` is copied from the box watchers (`watch.py`, `watch_quiet.py`, and the SPC, hurricane, mountain-pass, and gov-imagery modules). It was not rewritten. Paths, HTTP, and the one-shot Actions entrypoint are the only adaptations.

## What runs

`.github/workflows/alert-relay.yml`

- cron `*/5 * * * *` plus `workflow_dispatch`
- concurrency group `alert-relay` so runs do not overlap
- Python standard library only (no pip install on the runner)
- one urgent poll and one quiet tick per run, which is as fast as Actions cron allows (the box urgent loop is still every 30 seconds)
- api.weather.gov and the other feeds are allowed to time out; a failed fetch is logged and retried on the next run

`workflow_dispatch` has a `dry_run` input. Dry-run fetches live data, prints the webhook bodies it would POST, and does not POST or update the cache or `sent.json`.

## Heartbeat

The box publishes two repository Actions variables. Updating a variable does not create a commit.

| Variable | Writer | Fresh if younger than |
| --- | --- | --- |
| `ALERT_RELAY_HB_URGENT` | urgent watcher | 10 minutes |
| `ALERT_RELAY_HB_QUIET` | quiet watcher | 12 minutes |

The value is an ISO-8601 UTC timestamp. Two variables avoid a read-modify-write race between the 30-second loop and the 5-minute loop. `box_heartbeat.py` throttles writes (urgent: at most every 2 minutes, quiet: every 3 minutes) and never raises.

Missing, unparseable, or stale means that channel is down and the relay acts as the watcher. A timestamp more than 10 minutes in the future is also treated as stale, so a bad clock cannot silence the relay.

While the quiet heartbeat is fresh the relay still refreshes the WSDOT mountain-pass snapshot (at most every 15 minutes) and does not POST. Pass-change ids are a hash of the whole change list. Keeping the snapshot current means a takeover does not bundle a week of already-sent pass changes into a new id. That refresh can miss a change that landed in the last poll before the box died.

On takeover, alerts the box issued while its heartbeat was still fresh are marked seen and not POSTed, except alerts issued inside an overnight hold (USA 9 PM–2 AM PT, WA 9 PM–5 AM PT, plus the urgent watcher's WA severe-thunderstorm hold until 5 AM). Those were deliberately not sent. Life-safety urgent alerts are not held. Alerts issued after the last heartbeat are eligible, including ones older than 15 minutes, because that is the outage window. With no heartbeat at all, the first run uses the box's own 15-minute cold start so enabling the workflow does not dump every active alert in the country.

## State and dedupe

Watcher memory (seen ids, SPC posted keys, hurricane woken counts, the pass snapshot, gov-imagery keys, inflight payload ids) is stored in the Actions cache (`alert_relay/.cache`). Cache updates do not commit. The cache is restored with a prefix key so the latest run wins. If the cache is evicted, `sent.json` is rehydrated and a cold start seeds alerts older than 15 minutes when there is no heartbeat timestamp.

Alerts the relay actually POSTed (not seeded, not adopted) are folded into `sent.json` on the branch `relay-state`. That branch is updated only when the sent index changes, so a healthy box produces no commits there. The file is public weather ids, never webhook URLs or auth headers.

Payload ids match the box formula: `u-` or `q-` plus the first 16 hex chars of SHA1(sorted item ids + the tick of the first attempt). A retry of the same undelivered batch keeps that id (`inflight_payload`), which is what the receiver's `payload_seen.py` checks.

Payload ids are not enough when the box comes back. The tick is part of the hash, so a box send and a relay send of the same alert get different payload ids. The receiver's alert-id / item-id dedupe is a second net, but the box watchers would still POST. `box_sync_seen.py` closes that gap: at startup it reads `sent.json` and merges those ids into the local seen files (urgent keys, quiet `id|page`, quakes, SPC posted ranks, hurricane woken counts, a newer pass snapshot, gov-imagery feed keys). It does not create a missing seen file, so a brand-new install can still cold-start seed. It never raises.

## 60-day inactivity

GitHub disables scheduled workflows on a public repository after 60 days without a commit on the default branch. Variable updates do not count. The workflow's monthly cron (`17 9 1 * *`, 09:17 UTC on the 1st) commits `alert_relay/keepalive.txt` on `main`. That is the keepalive. The 5-minute job does not commit to `main`.

## Secrets

The workflow reads these Actions secrets and masks them. They are never printed; the log shows only whether they are set, plus `::add-mask::` so a traceback cannot echo them.

- `URGENT_WEBHOOK_URL`
- `URGENT_WEBHOOK_AUTH`
- `QUIET_WEBHOOK_URL`
- `QUIET_WEBHOOK_AUTH`

`setup_secrets.py` uploads them once from the box environment. It prints the name, the length, and `OK` or `FAIL`. It does not print values.

## Fine-grained PAT

Create one fine-grained personal access token, resource owner of this account, repository access **only** `wawxchasermodels/wx-models`.

| Repository permission | Access | Used by |
| --- | --- | --- |
| Variables | Read and write | `box_heartbeat.py` |
| Secrets | Read and write | `setup_secrets.py` (public key + sealed-box PUT) |

Contents and Actions are not required on the PAT. The workflow's `GITHUB_TOKEN` pushes `relay-state` and the monthly keepalive (`contents: write`) and saves the cache (`actions: write`). `sent.json` is read back through the public contents API, so the box does not need Contents permission.

Put the token in the box environment as `GITHUB_RELAY_TOKEN`. Do not commit it.

## Commands on the box

Copy these files from this repo into `/workspace/urgent_watch/` (the directory that is already on the watchers' import path):

- `box_heartbeat.py`
- `box_sync_seen.py`
- `constants.py`
- `github_api.py`
- `setup_secrets.py` (only for the one-time upload)

One-time secret upload. The four webhook variables must already be in that shell's environment. The script needs PyNaCl and nothing else is written to disk.

```bash
python3 -m pip install --user pynacl
export GITHUB_REPOSITORY=wawxchasermodels/wx-models
python3 /workspace/urgent_watch/setup_secrets.py
```

Wire the watchers. Both calls are failure-tolerant: a GitHub error cannot crash the loop.

In `watch.py`, once before the poll loop (inside `run`, before `while`, or in `__main__` before `run()`):

```python
try: import box_sync_seen; box_sync_seen.sync()
except Exception: pass
```

Inside the urgent poll loop, once per iteration (writes are throttled):

```python
try: import box_heartbeat; box_heartbeat.beat("urgent")
except Exception: pass
```

In `watch_quiet.py`, the same sync line once before its loop, and inside the 5-minute master loop:

```python
try: import box_heartbeat; box_heartbeat.beat("quiet")
except Exception: pass
```

Optional manual poke:

```bash
python3 /workspace/urgent_watch/box_heartbeat.py both
python3 /workspace/urgent_watch/box_sync_seen.py
```

Enable the workflow on `main` after the first heartbeat write, or do one dry-run dispatch first. Until a heartbeat exists the relay treats that channel as down.

## Testing

Offline (no network):

```bash
python3 alert_relay/selftest.py
```

Live dry-run from a checkout, against api.weather.gov and the other feeds. This does not POST.

```bash
ALERT_RELAY_DRY_RUN=1 ALERT_RELAY_CACHE_DIR=/tmp/alert-relay-dry python3 alert_relay/relay.py
```

On GitHub: Actions → alert-relay → Run workflow → dry_run checked. The log's final JSON is what would have been POSTed (`body` is the webhook document, including `payload_id`).

Dry-run does not write the cache, so running it again shows the same cold-start preview. The live job is what remembers sent ids. `selftest.py` checks that a later sync into the box seen files does not create a missing seen file and does not drop ids the box already had.

## Limits

- Urgent cadence while the box is down is 5 minutes, not 30 seconds.
- USA Severe Thunderstorm Warnings that qualify only because 300,000 or more people are inside the polygon do not fire here. That check needs the box's Census block tables, which are not in this repo. The relay fails closed (it does not guess). WA severe thunderstorm warnings do not need that check and still fire, including the 9 PM–5 AM PT hold.
- The SPC state grid is regenerated at the box's stated resolution (0.25°, 0.1° for Washington) because `spc_state_grid.json` was not in the watcher source. A border county can disagree by about one cell. The payload shape and the upgrade rules are unchanged, and the woken routine still checks the SPC map.
- Claim locks on the box are local files. They are not visible to Actions. While the box is down there is no live claim to honor; while it is up the relay does not send.
