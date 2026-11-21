"""Configuration for the Monday business review."""
from pathlib import Path
REPORT_DATE = "2026-11-16"
DATA_CUTOFF = "2026-11-15"
DATA_START = "2026-09-07"
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ALERT_LIMIT = 15
LOW_FILL_RATE = 90.0
LOW_AVAILABILITY = 50.0
SALES_DECLINE_PCT = -30.0
RANK_DETERIORATION = 5
SUSTAINED_WEEKS = 3
MIN_ORDER_GAP_WEEKS = 2
MIN_PO_COVERAGE_PCT = 95.0
RANK_BASELINE_WEEKS = 4
ALERT_SCORE_WEIGHTS = {"severity": 0.30, "revenue": 0.25, "duration": 0.20, "store_footprint": 0.15, "product_importance": 0.10}
CRITICAL_SCORE = 75
HIGH_SCORE = 50
