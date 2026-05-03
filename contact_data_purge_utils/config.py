"""
contact_data_purge/config.py
─────────────────────────────────────────────────────────────────────────────
All configuration constants loaded from environment variables.
Edit values in .env (local) or Lambda environment variables (production).
─────────────────────────────────────────────────────────────────────────────
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Processing ────────────────────────────────────────────────────────────────
MODE                   = os.getenv("MODE",                    "PREVIEW")
BATCH_SIZE             = int(os.getenv("BATCH_SIZE",          50))
PAGE_SIZE              = int(os.getenv("PAGE_SIZE",           100))
TEST_BATCH_SIZE        = int(os.getenv("TEST_BATCH_SIZE",     5))
DELAY_BETWEEN_REQUESTS = float(os.getenv("DELAY_BETWEEN_REQUESTS", 0.5))

# ── Output ────────────────────────────────────────────────────────────────────
EXPORT_TO_CSV = os.getenv("EXPORT_TO_CSV", "true").lower() == "true"
OUTPUT_DIR    = os.getenv("OUTPUT_DIR", "output")

# ── Multi-batch filtering ─────────────────────────────────────────────────────
FILTER_METHOD        = os.getenv("FILTER_METHOD",         "DATE_RANGE")
CURRENT_BATCH_INDEX  = int(os.getenv("CURRENT_BATCH_INDEX", 0))
FILTER_START_DATE    = os.getenv("FILTER_START_DATE",     "2024-01-01")
FILTER_END_DATE      = os.getenv("FILTER_END_DATE",       "2024-12-31")

# ── AWS ───────────────────────────────────────────────────────────────────────
AWS_REGION      = os.getenv("AWS_REGION",      "ap-southeast-2")
AWS_SECRET_NAME = os.getenv("AWS_SECRET_NAME")

# ── Batch range definitions ───────────────────────────────────────────────────
# Used in MULTI_BATCH mode to paginate beyond the API's 1,000-record limit.
# Each entry represents one run — increment CURRENT_BATCH_INDEX between runs.

DATE_RANGES = [
    {"start": "2024-01-01", "end": "2024-03-31"},
    {"start": "2024-04-01", "end": "2024-06-30"},
    {"start": "2024-07-01", "end": "2024-09-30"},
    {"start": "2024-10-01", "end": "2024-12-31"},
    {"start": "2023-01-01", "end": "2023-12-31"},
]

NAME_RANGES = [
    {"start": "A", "end": "E"},
    {"start": "F", "end": "J"},
    {"start": "K", "end": "O"},
    {"start": "P", "end": "T"},
    {"start": "U", "end": "Z"},
]
