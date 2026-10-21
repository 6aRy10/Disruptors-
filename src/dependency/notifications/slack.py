from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.request import Request, urlopen


SLACK_API_BASE = "https://slack.com/api"


def internal_risk_alert(
    *,
    risk_score: float,
    object_label: str,
    summary: str,
) -> dict:
    return {
        "text": f"Risk {risk_score:.0f}/100 — {object_label}\n{summary}"
    }


def supplier_capacity_request(
    *,
    sku: str,
    current_capacity: int,
    facility_name: str,
) -> dict:
    return {
        "text": (
            f"Dependency capacity confirmation: {facility_name} is being evaluated "
            f"as an approved recovery source for {sku}. "
            f"Current system capacity: {current_capacity:,} units/week. "
            "Please reply in this thread with current weekly capacity and the "
            "effective-until date in YYYY-MM-DD format."
        )
    }


def send_webhook(
    payload: dict,
    webhook_url: str | None = None,
) -> dict | None:
    url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return None

    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8")
    return {"ok": True, "body": body}


def _slack_api(
    method: str,
    payload: dict,
    *,
    token: str | None = None,
) -> dict:
    bot_token = token or os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        raise RuntimeError("SLACK_BOT_TOKEN is not configured.")

    req = Request(
        f"{SLACK_API_BASE}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {bot_token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urlopen(req, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(
            f"Slack API {method} failed: {result.get('error', 'unknown_error')}"
        )
    return result


def resolve_slack_channel(
    address: str,
    *,
    token: str | None = None,
) -> str:
    """Resolve a stored Slack address into a channel ID.

    Channel IDs are returned as-is. User IDs are converted to a direct-message
    channel with conversations.open.
    """
    value = str(address or "").strip()
    if not value:
        raise ValueError("Slack address is empty.")

    if value.startswith("U"):
        result = _slack_api(
            "conversations.open",
            {"users": value},
            token=token,
        )
        channel = result.get("channel") or {}
        channel_id = channel.get("id")
        if not channel_id:
            raise RuntimeError("Slack conversations.open returned no channel ID.")
        return channel_id

    return value


def post_message(
    *,
    address: str,
    text: str,
    thread_ts: str | None = None,
    token: str | None = None,
) -> dict:
    channel_id = resolve_slack_channel(address, token=token)
    payload = {
        "channel": channel_id,
        "text": text,
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    result = _slack_api(
        "chat.postMessage",
        payload,
        token=token,
    )
    return {
        "channel_id": result.get("channel") or channel_id,
        "ts": result.get("ts"),
        "message": result.get("message"),
    }


def verify_slack_signature(
    *,
    raw_body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str | None = None,
    now_epoch: int | None = None,
    max_age_seconds: int = 300,
) -> bool:
    secret = signing_secret or os.getenv("SLACK_SIGNING_SECRET")
    if not secret:
        raise RuntimeError("SLACK_SIGNING_SECRET is not configured.")

    try:
        timestamp_int = int(timestamp)
    except (TypeError, ValueError):
        return False

    current = int(time.time()) if now_epoch is None else int(now_epoch)
    if abs(current - timestamp_int) > max_age_seconds:
        return False

    base = b"v0:" + timestamp.encode("utf-8") + b":" + raw_body
    digest = hmac.new(
        secret.encode("utf-8"),
        base,
        hashlib.sha256,
    ).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, signature or "")
