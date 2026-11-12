"""All tunable thresholds in one place. Change these, not the code."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
OUT = Path(os.getenv("SAHRA_OUT", BASE / "outputs"))
DB_PATH = OUT / "sahra.db"
CKPT_PATH = OUT / "checkpoints.db"

DEMO_START = "2026-11-12T14:00:00+04:00"   # simulated clock start (Asia/Dubai)

# --- Data trust rules --------------------------------------------------------
FEED_STALE_MIN = 15        # a feed record older than this is ignored
QUEUE_STALE_MIN = 10       # a queue-sensor reading older than this is ignored
CONFLICT_GRACE_MIN = 3     # feeds may disagree this long (sync lag) before it is a CONFLICT
DATA_GAP_ALERT_MIN = 120   # alert staff about missing data for flights departing within this window

# --- Approval gate -------------------------------------------------------------
APPROVAL_TIMEOUT_MIN = 5   # unapproved broadcast expires -> NOT sent, duty manager alerted

# --- Journey planning ------------------------------------------------------------
WALK_BUFFER_MIN = 5        # arrive at gate this many minutes before boarding
NUDGE_LEAD_MIN = 5         # proactive "leave now" nudge this many minutes before leave-by
LOCATION_MAX_AGE_MIN = 30  # last boarding-pass scan older than this is not used
SPEEDS_M_PER_MIN = {"standard": 72, "family": 54, "reduced_mobility": 36}

# --- Safety & privacy ------------------------------------------------------------
MAX_QUESTION_CHARS = 500
VERIFY_MAX_ATTEMPTS = 3
PRIVACY_SALT = os.getenv("SAHRA_SALT", "demo-salt-change-me-in-production")
SUPPORTED_LANGS = ("en", "ar", "hi")
