"""Google OAuth 2.0 helper for Calendar, Gmail (compose-only), and Tasks APIs.

This module handles:
  - Initial OAuth consent flow (opens browser for user sign-in)
  - Token persistence to a local file (encrypted in Phase 4)
  - Automatic token refresh when expired
  - Building authenticated Google API service objects

Usage:
    from src.auth.google_oauth import get_google_service

    calendar = get_google_service("calendar", "v3")
    gmail    = get_google_service("gmail", "v1")
    tasks    = get_google_service("tasks", "v1")

Environment variables (or .env file):
    GOOGLE_CLIENT_ID       — OAuth Client ID from Google Cloud Console
    GOOGLE_CLIENT_SECRET   — OAuth Client Secret
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("homebase.auth")

# ---------------------------------------------------------------------------
# OAuth scopes — intentionally minimal
# ---------------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",     # Calendar: read + write events
    "https://www.googleapis.com/auth/gmail.compose",        # Gmail: create drafts only (NOT send)
    "https://www.googleapis.com/auth/tasks",                # Tasks: read + write
]

# Default token file location (project root)
_TOKEN_PATH = Path(__file__).resolve().parent.parent.parent / ".google_token.json"
_CREDENTIALS_PATH = Path(__file__).resolve().parent.parent.parent / "credentials.json"


class GoogleAuthError(Exception):
    """Raised when Google OAuth fails and cannot be recovered."""


def _load_dotenv():
    """Try to load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv, find_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass


def _get_credentials_config() -> dict:
    """Build OAuth client config from environment variables or credentials.json file."""
    _load_dotenv()

    # First check for credentials.json file (downloaded from Google Cloud Console)
    if _CREDENTIALS_PATH.exists():
        with open(_CREDENTIALS_PATH) as f:
            creds_data = json.load(f)
        # Google Console exports as {"installed": {...}} or {"web": {...}}
        if "installed" in creds_data:
            return creds_data["installed"]
        elif "web" in creds_data:
            return creds_data["web"]
        return creds_data

    # Fall back to environment variables
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise GoogleAuthError(
            "Google OAuth not configured. Either:\n"
            "  1. Place a credentials.json file in the project root (download from Google Cloud Console), or\n"
            "  2. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file"
        )

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }


def get_credentials():
    """Get valid Google OAuth credentials, refreshing or re-authenticating as needed.

    Returns a google.oauth2.credentials.Credentials object.
    Raises GoogleAuthError if authentication cannot be completed.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
    except ImportError as e:
        raise GoogleAuthError(
            f"Required packages not installed: {e}\n"
            "Run: pip install google-auth-oauthlib google-api-python-client"
        )

    creds = None

    # Load saved token if it exists
    if _TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)
        except Exception as e:
            logger.warning("Failed to load saved token: %s", e)
            creds = None

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            logger.info("Google OAuth token refreshed successfully")
            return creds
        except Exception as e:
            logger.warning("Token refresh failed: %s — will re-authenticate", e)
            creds = None

    # Valid token exists
    if creds and creds.valid:
        return creds

    # Need to authenticate from scratch
    try:
        config = _get_credentials_config()
        flow = InstalledAppFlow.from_client_config(
            {"installed": config},
            SCOPES,
        )
        creds = flow.run_local_server(port=0, open_browser=True)
        _save_token(creds)
        logger.info("Google OAuth authentication completed successfully")
        return creds
    except Exception as e:
        raise GoogleAuthError(f"Google OAuth authentication failed: {e}")


def _save_token(creds) -> None:
    """Save credentials to the token file for future use."""
    try:
        with open(_TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        logger.debug("Token saved to %s", _TOKEN_PATH)
    except Exception as e:
        logger.warning("Failed to save token: %s", e)


def get_google_service(api_name: str, api_version: str, credentials=None):
    """Build an authenticated Google API service object.

    Args:
        api_name: Google API name (e.g. "calendar", "gmail", "tasks")
        api_version: API version (e.g. "v3", "v1")
        credentials: Optional pre-built credentials; if None, will authenticate.

    Returns:
        A googleapiclient.discovery.Resource object.

    Raises:
        GoogleAuthError if authentication fails.
    """
    try:
        from googleapiclient.discovery import build
    except ImportError:
        raise GoogleAuthError(
            "google-api-python-client is not installed. Run: pip install google-api-python-client"
        )

    if credentials is None:
        credentials = get_credentials()

    return build(api_name, api_version, credentials=credentials)


# ---------------------------------------------------------------------------
# Utility: check if OAuth is configured (for mock fallback logic)
# ---------------------------------------------------------------------------
def is_google_auth_configured() -> bool:
    """Return True if Google OAuth credentials are available (token or config)."""
    if _TOKEN_PATH.exists():
        return True

    _load_dotenv()
    if os.environ.get("GOOGLE_CLIENT_ID") and os.environ.get("GOOGLE_CLIENT_SECRET"):
        return True
    if _CREDENTIALS_PATH.exists():
        return True

    return False
