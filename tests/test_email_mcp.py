"""Tests for the Email MCP server (Gmail API integration).

All tests run in mock mode (HOMEBASE_MOCK=1) by default via conftest.py.
Tests verify the mock fallback path and the interface contract.
"""
import pytest

from src.mcp_servers import email_mcp


class TestEmailMCPMockMode:
    """Tests that run with HOMEBASE_MOCK=1 (mock data, no API calls)."""

    def test_create_draft_returns_draft(self):
        result = email_mcp.create_draft(
            to="test@example.com",
            subject="Test Subject",
            body="Hello, this is a test.",
        )
        assert "draft" in result
        draft = result["draft"]
        assert draft["to"] == "test@example.com"
        assert draft["subject"] == "Test Subject"
        assert draft["body"] == "Hello, this is a test."
        assert "id" in draft

    def test_list_drafts_returns_list(self):
        # Clear mock drafts first
        email_mcp._MOCK_DRAFTS.clear()

        # Create a draft
        email_mcp.create_draft("a@b.com", "Sub", "Body")

        # List should include it
        result = email_mcp.list_drafts()
        assert "drafts" in result
        assert len(result["drafts"]) >= 1

    def test_create_draft_has_unique_ids(self):
        email_mcp._MOCK_DRAFTS.clear()
        r1 = email_mcp.create_draft("a@b.com", "Sub1", "Body1")
        r2 = email_mcp.create_draft("c@d.com", "Sub2", "Body2")
        assert r1["draft"]["id"] != r2["draft"]["id"]

    def test_never_raises_exception(self):
        """The safe_api_call decorator should catch all exceptions."""
        result = email_mcp.create_draft("x", "y", "z")
        assert isinstance(result, dict)

        result = email_mcp.list_drafts()
        assert isinstance(result, dict)


class TestEmailMCPSecurityConstraints:
    """Verify that the Email MCP never exposes a send capability."""

    def test_no_send_function(self):
        """There should be no send_email or send function in the module."""
        public_funcs = [name for name in dir(email_mcp) if not name.startswith("_")]
        assert "send_email" not in public_funcs
        assert "send" not in public_funcs

    def test_create_draft_never_sends(self):
        """create_draft should only create a draft — verify by function name and return shape."""
        result = email_mcp.create_draft("test@test.com", "Test", "Test body")
        # The return should say "draft", never "sent"
        assert "draft" in result
        assert "sent" not in str(result).lower()
