"""
Google OAuth + HTTP helpers for the product (self-contained).

Product code must import Google credentials + HTTP only through this module.
Credentials come from the process environment (GOOGLE_CLIENT_ID,
GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN); inject them from your secret
manager. Nothing is read from any other repository.
"""

from __future__ import annotations

import os

from .http_util import api_request, get_access_token


def get_google_creds() -> tuple[str, str, str]:
    values = []
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(f"{name} is not set (provide Google OAuth via the environment)")
        values.append(value)
    return values[0], values[1], values[2]


def google_access_token() -> str:
    client_id, client_secret, refresh_token = get_google_creds()
    return get_access_token(client_id, client_secret, refresh_token)


__all__ = ["api_request", "get_access_token", "get_google_creds", "google_access_token"]
