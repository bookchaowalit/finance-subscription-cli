"""
Thin bridge into Solo Empire infra helpers.

Product code must import Google env + HTTP only through this module.
No business logic belongs in infra.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .paths import INFRA_UTILS

if str(INFRA_UTILS) not in sys.path:
    sys.path.insert(0, str(INFRA_UTILS))

from _env import get_google_creds  # type: ignore  # noqa: E402
from _http import api_request, get_access_token  # type: ignore  # noqa: E402


def google_access_token() -> str:
    client_id, client_secret, refresh_token = get_google_creds()
    return get_access_token(client_id, client_secret, refresh_token)


__all__ = ["api_request", "get_google_creds", "google_access_token", "get_access_token"]
