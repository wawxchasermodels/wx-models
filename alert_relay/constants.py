"""Shared relay settings. Heartbeat ages are the failover line."""

# While a timestamp is younger than this, that channel's watcher is treated as alive
# and the relay does not POST. Urgent polls every 30s on the box; quiet's master
# tick is 5 minutes. These windows survive a couple of missed heartbeat writes.
URGENT_HEARTBEAT_MAX_AGE_SEC = 10 * 60
QUIET_HEARTBEAT_MAX_AGE_SEC = 12 * 60

HB_VAR_URGENT = "ALERT_RELAY_HB_URGENT"
HB_VAR_QUIET = "ALERT_RELAY_HB_QUIET"

# box_heartbeat.py will not PATCH a channel more often than this, even if the
# watcher calls beat() every poll. A VM pause freezes wall time, so the next
# call after resume sees an old stamp and writes immediately.
HB_MIN_INTERVAL_SEC = {"urgent": 120, "quiet": 180}

DEFAULT_REPO = "wawxchasermodels/wx-models"
STATE_BRANCH = "relay-state"
STATE_PATH = "sent.json"

SECRET_NAMES = (
    "URGENT_WEBHOOK_URL",
    "URGENT_WEBHOOK_AUTH",
    "QUIET_WEBHOOK_URL",
    "QUIET_WEBHOOK_AUTH",
)

# Alerts issued during the overnight hold were not sent by a live box.
# Matches watch_quiet.HOLD_* and the urgent WA SVR hold.
HOLD_START_HOUR = 21
HOLD_END_USA = 2
HOLD_END_WA = 5
SEED_RECENT_MINUTES = 15
