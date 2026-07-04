"""Shared test fixtures for MCP server integration tests."""
import os
import pytest


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    """Ensure all tests run in mock mode by default (no real API calls)."""
    monkeypatch.setenv("HOMEBASE_MOCK", "1")


@pytest.fixture
def real_mode(monkeypatch):
    """Override mock_mode to test real API paths (use with care — requires credentials)."""
    monkeypatch.delenv("HOMEBASE_MOCK", raising=False)
