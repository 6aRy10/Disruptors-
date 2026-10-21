"""Access gate for state-changing Dependency API requests.

In local demo mode a loopback client may write without a token. Every
non-loopback writer must provide the configured secret; absent configuration
always fails closed. This does not implement multi-user role authorization.
"""
from __future__ import annotations

import hmac
import ipaddress

from fastapi import HTTPException


def require_write_authorization(
    *,
    client_host: str,
    authorization: str | None,
    configured_token: str | None,
) -> None:
    try:
        loopback = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        loopback = False

    token = (configured_token or "").strip()
    if not token:
        if loopback:
            return
        raise HTTPException(
            status_code=503,
            detail="Remote writes disabled: DEPENDENCY_WRITE_TOKEN is not configured.",
        )

    supplied = ""
    if authorization:
        scheme, _, credential = authorization.partition(" ")
        if scheme.lower() == "bearer":
            supplied = credential.strip()

    if not supplied or not hmac.compare_digest(token, supplied):
        raise HTTPException(status_code=401, detail="Write authorization required.")
