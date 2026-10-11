"""Product-local paths."""

from __future__ import annotations

from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PRODUCT_ROOT / "data"
SCHEMA_DIR = PRODUCT_ROOT / "schema"
REGISTRY_PATH = DATA_DIR / "registry.json"
REPORTS_DIR = DATA_DIR / "reports"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
