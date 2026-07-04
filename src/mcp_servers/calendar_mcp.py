"""Calendar MCP server — backed by the real Google Calendar API.

Replaces hardcoded event data with real Google Calendar API calls via OAuth 2.0.
Preserves the exact same interface: list_events, propose_reschedule, commit_reschedule.

Features:
  - OAuth 2.0 with calendar.events scope
  - list_events reads real calendar events from the user's primary calendar
  - propose_reschedule is pure computation (no API call) — builds a draft diff
  - commit_reschedule issues a real PATCH to the Google Calendar API
  - All calls wrapped in retry + timeout + error handling
  - Falls back to mock data if HOMEBASE_MOCK=1 or OAuth isn't configured
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .api_utils import safe_api_call

logger = logging.getLogger("homebase.mcp.calendar")

# ---------------------------------------------------------------------------
# Mock data (kept for backwards compatibility)
# ---------------------------------------------------------------------------
_MOCK_EVENTS = [
    {"id": "evt1", "title": "Team sync", "start": "2026-07-06T15:00:00", "end": "2026-07-06T15:30:00"},
    {"id": "evt2", "title": "Dentist", "start": "2026-07-08T09:00:00", "end": "2026-07-08T10:00:00"},
]


def _is_mock_mode() -> bool:
    return os.environ.get("HOMEBASE_MOCK", "").strip() in ("1", "true", "yes")


def _google_auth_available() -> bool:
    """Check if Google OAuth is configured."""
    try:
        from ..auth.google_oauth import is_google_auth_configured
        return is_google_auth_configured()
    except Exception:
        return False


def _get_calendar_service():
    """Get an authenticated Google Calendar API service."""
    from ..auth.google_oauth import get_google_service
    return get_google_service("calendar", "v3")


def _parse_gcal_event(event: dict) -> dict:
    """Convert a Google Calendar API event to our standard format."""
    start = event.get("start", {})
    end = event.get("end", {})
    return {
        "id": event.get("id", ""),
        "title": event.get("summary", "(No title)"),
        "start": start.get("dateTime", start.get("date", "")),
        "end": end.get("dateTime", end.get("date", "")),
        "location": event.get("location", ""),
        "description": event.get("description", ""),
    }


@safe_api_call
def list_events(start: str = None, end: str = None) -> dict:
    """read-tier: list events in a date range from the user's primary Google Calendar.

    Args:
        start: ISO datetime string for the start of the range (default: now)
        end: ISO datetime string for the end of the range (default: 7 days from now)

    Returns:
        {"events": [{"id", "title", "start", "end", "location", "description"}, ...]}
    """
    if _is_mock_mode() or not _google_auth_available():
        logger.info("Calendar MCP running in mock mode")
        return {"events": _MOCK_EVENTS}

    service = _get_calendar_service()

    # Default range: now to 7 days from now
    now = datetime.now(timezone.utc)
    time_min = start or now.isoformat()
    time_max = end or (now + timedelta(days=7)).isoformat()

    # Ensure timezone info is present
    if not time_min.endswith("Z") and "+" not in time_min and "-" not in time_min[-6:]:
        time_min += "Z"
    if not time_max.endswith("Z") and "+" not in time_max and "-" not in time_max[-6:]:
        time_max += "Z"

    results = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=50,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = [_parse_gcal_event(e) for e in results.get("items", [])]
    logger.info("Listed %d events from Google Calendar", len(events))
    return {"events": events}


@safe_api_call
def propose_reschedule(event_id: str, new_start: str, new_end: str) -> dict:
    """draft-tier: build a proposed reschedule change — no API call, pure computation.

    Args:
        event_id: Google Calendar event ID
        new_start: Proposed new start time (ISO datetime)
        new_end: Proposed new end time (ISO datetime)

    Returns:
        {"draft": {"event_id", "title", "old_start", "new_start", "new_end"}}
    """
    if _is_mock_mode() or not _google_auth_available():
        event = next((e for e in _MOCK_EVENTS if e["id"] == event_id), None)
        if not event:
            return {"error": f"event {event_id} not found"}
        return {
            "draft": {
                "event_id": event_id,
                "title": event["title"],
                "old_start": event["start"],
                "new_start": new_start,
                "new_end": new_end,
            }
        }

    # In real mode, fetch the current event to show what's changing
    service = _get_calendar_service()
    event = service.events().get(calendarId="primary", eventId=event_id).execute()

    old_start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))

    return {
        "draft": {
            "event_id": event_id,
            "title": event.get("summary", "(No title)"),
            "old_start": old_start,
            "new_start": new_start,
            "new_end": new_end,
        }
    }


@safe_api_call
def commit_reschedule(event_id: str, new_start: str, new_end: str) -> dict:
    """act-tier: actually move the event via the Google Calendar API.

    Must go through the permission ladder first (this is enforced by the skill layer).

    Args:
        event_id: Google Calendar event ID
        new_start: New start time (ISO datetime)
        new_end: New end time (ISO datetime)

    Returns:
        {"status": "committed", "event": {...}}
    """
    if _is_mock_mode() or not _google_auth_available():
        event = next((e for e in _MOCK_EVENTS if e["id"] == event_id), None)
        if not event:
            return {"error": f"event {event_id} not found"}
        event["start"], event["end"] = new_start, new_end
        return {"status": "committed", "event": event}

    service = _get_calendar_service()

    # PATCH the event with new times
    body = {
        "start": {"dateTime": new_start},
        "end": {"dateTime": new_end},
    }
    updated = service.events().patch(
        calendarId="primary",
        eventId=event_id,
        body=body,
    ).execute()

    result_event = _parse_gcal_event(updated)
    logger.info("Committed reschedule for event %s", event_id)
    return {"status": "committed", "event": result_event}
