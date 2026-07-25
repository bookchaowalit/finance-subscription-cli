"""Product-local paths. Never writes into Solo Empire core DB."""

from __future__ import annotations

import os
from pathlib import Path

PRODUCT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PRODUCT_ROOT / "data"
SCHEMA_DIR = PRODUCT_ROOT / "schema"
REGISTRY_PATH = DATA_DIR / "registry.json"
REPORTS_DIR = DATA_DIR / "reports"


def find_monorepo_root() -> Path:
    """Locate Solo Empire monorepo for infra OAuth/HTTP helpers only.

    Resolution order:
    1. SOLO_EMPIRE_ROOT env
    2. Walk parents for infra/scripts/utils/_env.py
    3. ~/solo-empire
    """
    env = os.environ.get("SOLO_EMPIRE_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if (p / "infra" / "scripts" / "utils" / "_env.py").exists():
            return p
        raise RuntimeError(f"SOLO_EMPIRE_ROOT={env} missing infra/scripts/utils/_env.py")

    for p in [PRODUCT_ROOT, *PRODUCT_ROOT.parents]:
        if (p / "infra" / "scripts" / "utils" / "_env.py").exists():
            return p

    home_candidate = Path.home() / "solo-empire"
    if (home_candidate / "infra" / "scripts" / "utils" / "_env.py").exists():
        return home_candidate.resolve()

    raise RuntimeError(
        "Solo Empire monorepo not found. Set SOLO_EMPIRE_ROOT to the solo-empire path "
        "(needs infra/scripts/utils for Google OAuth)."
    )


MONOREPO_ROOT = find_monorepo_root()
INFRA_UTILS = MONOREPO_ROOT / "infra" / "scripts" / "utils"


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
