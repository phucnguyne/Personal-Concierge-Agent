"""Email MCP server — backed by the real Gmail API (drafts only).

Replaces the in-memory draft list with real Gmail API calls.
Preserves the exact same interface: create_draft, list_drafts.

HARD CONSTRAINT: This module only requests the gmail.compose scope.
It NEVER requests gmail.send — HomeBase never sends email autonomously.

Features:
  - OAuth 2.0 with gmail.compose scope only
  - create_draft creates a real Gmail draft
  - list_drafts lists real drafts from the user's Gmail
  - All calls wrapped in retry + timeout + error handling
  - Falls back to mock data if HOMEBASE_MOCK=1 or OAuth isn't configured
"""
import os
import base64
import logging
from email.mime.text import MIMEText
from typing import Optional

from .api_utils import safe_api_call

logger = logging.getLogger("homebase.mcp.email")

# ---------------------------------------------------------------------------
# Mock data (kept for backwards compatibility)
# ---------------------------------------------------------------------------
_MOCK_DRAFTS = []


def _is_mock_mode() -> bool:
    return os.environ.get("HOMEBASE_MOCK", "").strip() in ("1", "true", "yes")


def _google_auth_available() -> bool:
    """Check if Google OAuth is configured."""
    try:
        from ..auth.google_oauth import is_google_auth_configured
        return is_google_auth_configured()
    except Exception:
        return False


def _get_gmail_service():
    """Get an authenticated Gmail API service."""
    from ..auth.google_oauth import get_google_service
    return get_google_service("gmail", "v1")


def _build_mime_message(to: str, subject: str, body: str) -> str:
    """Build a base64url-encoded MIME message for the Gmail API."""
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return raw


def _parse_gmail_draft(draft: dict) -> dict:
    """Convert a Gmail API draft to our standard format."""
    msg = draft.get("message", {})
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    return {
        "id": draft.get("id", ""),
        "to": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "snippet": msg.get("snippet", ""),
    }


@safe_api_call
def create_draft(to: str, subject: str, body: str) -> dict:
    """draft-tier: create an email draft in Gmail — does NOT send.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Plain-text email body

    Returns:
        {"draft": {"id", "to", "subject", "body"}}
    """
    if _is_mock_mode() or not _google_auth_available():
        draft = {"id": f"draft{len(_MOCK_DRAFTS)+1}", "to": to, "subject": subject, "body": body}
        _MOCK_DRAFTS.append(draft)
        logger.info("Email MCP in mock mode — draft stored in memory")
        return {"draft": draft}

    service = _get_gmail_service()

    raw_message = _build_mime_message(to, subject, body)
    draft_body = {"message": {"raw": raw_message}}

    result = service.users().drafts().create(
        userId="me",
        body=draft_body,
    ).execute()

    logger.info("Created real Gmail draft: %s", result.get("id"))
    return {
        "draft": {
            "id": result.get("id", ""),
            "to": to,
            "subject": subject,
            "body": body,
        }
    }


@safe_api_call
def list_drafts(max_results: int = 10) -> dict:
    """read-tier: list email drafts from Gmail.

    Args:
        max_results: Maximum number of drafts to return (default 10)

    Returns:
        {"drafts": [{"id", "to", "subject", "snippet"}, ...]}
    """
    if _is_mock_mode() or not _google_auth_available():
        logger.info("Email MCP in mock mode — returning in-memory drafts")
        return {"drafts": _MOCK_DRAFTS}

    service = _get_gmail_service()

    results = service.users().drafts().list(
        userId="me",
        maxResults=max_results,
    ).execute()

    drafts_raw = results.get("drafts", [])

    # Fetch details for each draft (the list endpoint only returns IDs)
    drafts = []
    for d in drafts_raw:
        try:
            detail = service.users().drafts().get(
                userId="me",
                id=d["id"],
                format="metadata",
                metadataHeaders=["To", "Subject"],
            ).execute()
            drafts.append(_parse_gmail_draft(detail))
        except Exception as e:
            logger.warning("Failed to fetch draft %s: %s", d.get("id"), e)

    logger.info("Listed %d Gmail drafts", len(drafts))
    return {"drafts": drafts}
