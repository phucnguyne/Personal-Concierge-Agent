"""Local stand-in for a Calendar MCP server.

Mirrors the shape of a real MCP tool call: name in, structured result out.
Swap this for a real Google Calendar MCP server without touching the
orchestrator, skills, or security layer.
"""
from datetime import datetime, timedelta

_EVENTS = [
    {"id": "evt1", "title": "Team sync", "start": "2026-07-06T15:00:00", "end": "2026-07-06T15:30:00"},
    {"id": "evt2", "title": "Dentist", "start": "2026-07-08T09:00:00", "end": "2026-07-08T10:00:00"},
]


def list_events(start: str = None, end: str = None):
    """read-tier: list events in range."""
    return {"events": _EVENTS}


def propose_reschedule(event_id: str, new_start: str, new_end: str):
    """draft-tier: build a proposed change, do not apply it."""
    event = next((e for e in _EVENTS if e["id"] == event_id), None)
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


def commit_reschedule(event_id: str, new_start: str, new_end: str):
    """act-tier: actually move the event. Must go through the permission ladder first."""
    event = next((e for e in _EVENTS if e["id"] == event_id), None)
    if not event:
        return {"error": f"event {event_id} not found"}
    event["start"], event["end"] = new_start, new_end
    return {"status": "committed", "event": event}
