"""Tests for the Calendar MCP server (Google Calendar API integration).

All tests run in mock mode (HOMEBASE_MOCK=1) by default via conftest.py.
Tests verify the mock fallback path and the interface contract.
"""
import pytest

from src.mcp_servers import calendar_mcp


class TestCalendarMCPMockMode:
    """Tests that run with HOMEBASE_MOCK=1 (mock data, no API calls)."""

    def test_list_events_returns_events(self):
        result = calendar_mcp.list_events()
        assert "events" in result
        assert len(result["events"]) == 2
        assert result["events"][0]["title"] == "Team sync"
        assert result["events"][1]["title"] == "Dentist"

    def test_list_events_has_required_fields(self):
        result = calendar_mcp.list_events()
        for event in result["events"]:
            assert "id" in event
            assert "title" in event
            assert "start" in event
            assert "end" in event

    def test_propose_reschedule_valid_event(self):
        result = calendar_mcp.propose_reschedule(
            event_id="evt1",
            new_start="2026-07-09T10:00:00",
            new_end="2026-07-09T10:30:00",
        )
        assert "draft" in result
        draft = result["draft"]
        assert draft["event_id"] == "evt1"
        assert draft["title"] == "Team sync"
        assert draft["new_start"] == "2026-07-09T10:00:00"

    def test_propose_reschedule_unknown_event(self):
        result = calendar_mcp.propose_reschedule(
            event_id="nonexistent",
            new_start="2026-07-09T10:00:00",
            new_end="2026-07-09T10:30:00",
        )
        assert "error" in result

    def test_commit_reschedule_valid_event(self):
        result = calendar_mcp.commit_reschedule(
            event_id="evt1",
            new_start="2026-07-09T10:00:00",
            new_end="2026-07-09T10:30:00",
        )
        assert result["status"] == "committed"
        assert result["event"]["start"] == "2026-07-09T10:00:00"

    def test_commit_reschedule_unknown_event(self):
        result = calendar_mcp.commit_reschedule(
            event_id="nonexistent",
            new_start="2026-07-09T10:00:00",
            new_end="2026-07-09T10:30:00",
        )
        assert "error" in result

    def test_never_raises_exception(self):
        """The safe_api_call decorator should catch all exceptions."""
        # All these should return dicts, never raise
        result1 = calendar_mcp.list_events()
        assert isinstance(result1, dict)

        result2 = calendar_mcp.propose_reschedule("x", "y", "z")
        assert isinstance(result2, dict)
