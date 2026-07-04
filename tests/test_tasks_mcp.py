"""Tests for the Tasks MCP server (Google Tasks API + SQLite expenses).

All tests run in mock mode (HOMEBASE_MOCK=1) by default via conftest.py.
Tests verify the mock fallback path and the interface contract.
Expense tests also verify the SQLite path (non-mock).
"""
import os
import sqlite3
import tempfile
import pytest

from src.mcp_servers import tasks_mcp


class TestTasksMCPMockMode:
    """Tests that run with HOMEBASE_MOCK=1 (mock data, no API calls)."""

    def test_list_tasks_returns_all(self):
        result = tasks_mcp.list_tasks()
        assert "tasks" in result
        assert len(result["tasks"]) >= 1

    def test_list_tasks_filter_by_list(self):
        result = tasks_mcp.list_tasks(list_name="errands")
        assert "tasks" in result
        for task in result["tasks"]:
            assert task["list"] == "errands"

    def test_list_tasks_empty_list(self):
        result = tasks_mcp.list_tasks(list_name="nonexistent")
        assert "tasks" in result
        assert len(result["tasks"]) == 0

    def test_propose_task_list_returns_draft(self):
        items = ["milk", "eggs", "bread"]
        result = tasks_mcp.propose_task_list(items, "groceries")
        assert "draft" in result
        assert result["draft"]["list"] == "groceries"
        assert result["draft"]["items"] == items

    def test_commit_task_list_adds_tasks(self):
        # Reset mock tasks
        tasks_mcp._MOCK_TASKS.clear()
        tasks_mcp._MOCK_TASKS.append(
            {"id": "t1", "title": "Buy birthday gift", "done": False, "list": "errands"}
        )

        items = ["bananas", "yogurt"]
        result = tasks_mcp.commit_task_list(items, "groceries")
        assert result["status"] == "committed"
        assert result["count"] == 2

        # Verify tasks were added
        all_tasks = tasks_mcp.list_tasks()
        titles = [t["title"] for t in all_tasks["tasks"]]
        assert "bananas" in titles
        assert "yogurt" in titles

    def test_never_raises_exception(self):
        """The safe_api_call decorator should catch all exceptions."""
        result = tasks_mcp.list_tasks()
        assert isinstance(result, dict)

        result = tasks_mcp.propose_task_list([], "test")
        assert isinstance(result, dict)


class TestExpensesMockMode:
    """Test expense functions in mock mode."""

    def test_summarize_all_expenses(self):
        result = tasks_mcp.summarize_expenses()
        assert "total" in result
        assert "rows" in result
        assert result["total"] > 0

    def test_summarize_by_category(self):
        result = tasks_mcp.summarize_expenses(category="takeout")
        assert "total" in result
        assert all(r["category"] == "takeout" for r in result["rows"])

    def test_summarize_empty_category(self):
        result = tasks_mcp.summarize_expenses(category="nonexistent")
        assert result["total"] == 0
        assert len(result["rows"]) == 0


class TestExpensesSQLite:
    """Test expense functions with the SQLite backend (non-mock mode)."""

    def test_sqlite_add_and_summarize(self, monkeypatch, tmp_path):
        """Test adding an expense and summarizing from SQLite."""
        monkeypatch.delenv("HOMEBASE_MOCK", raising=False)

        # Point DB to a temp file
        db_path = tmp_path / "test_expenses.db"
        monkeypatch.setattr(tasks_mcp, "_DB_PATH", db_path)

        # Add expense
        result = tasks_mcp.add_expense("coffee", 5.50, "2026-07-01", "Starbucks")
        assert result["status"] == "logged"
        assert result["expense"]["amount"] == 5.50

        # Summarize
        summary = tasks_mcp.summarize_expenses(category="coffee")
        assert summary["total"] == 5.50
        assert len(summary["rows"]) == 1
        assert summary["rows"][0]["description"] == "Starbucks"

    def test_sqlite_seed_on_first_run(self, monkeypatch, tmp_path):
        """Test that the database is seeded with sample data on first run."""
        monkeypatch.delenv("HOMEBASE_MOCK", raising=False)

        db_path = tmp_path / "test_seed.db"
        monkeypatch.setattr(tasks_mcp, "_DB_PATH", db_path)

        # First summarize should trigger seeding
        result = tasks_mcp.summarize_expenses()
        assert result["total"] > 0
        assert len(result["rows"]) >= 3  # 3 seed records

    def test_sqlite_month_filter(self, monkeypatch, tmp_path):
        """Test filtering expenses by month."""
        monkeypatch.delenv("HOMEBASE_MOCK", raising=False)

        db_path = tmp_path / "test_month.db"
        monkeypatch.setattr(tasks_mcp, "_DB_PATH", db_path)

        tasks_mcp.add_expense("food", 10.00, "2026-07-01")
        tasks_mcp.add_expense("food", 20.00, "2026-06-15")

        july = tasks_mcp.summarize_expenses(month="2026-07")
        assert july["total"] == 10.00

        june = tasks_mcp.summarize_expenses(month="2026-06")
        assert june["total"] == 20.00
