"""Tasks MCP server — backed by the real Google Tasks API + local SQLite for expenses.

Replaces hardcoded task/expense data with:
  - Google Tasks API for to-dos and shopping lists
  - Local SQLite database for expense tracking (lightweight, no cloud dependency)

Preserves the exact same interface: list_tasks, propose_task_list, commit_task_list, summarize_expenses.

Features:
  - OAuth 2.0 with tasks scope for Google Tasks
  - SQLite for expense data (survives restarts, will migrate to Postgres in Phase 5)
  - All calls wrapped in retry + timeout + error handling
  - Falls back to mock data if HOMEBASE_MOCK=1 or OAuth isn't configured
"""
import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from .api_utils import safe_api_call

logger = logging.getLogger("homebase.mcp.tasks")

# ---------------------------------------------------------------------------
# Mock data (kept for backwards compatibility)
# ---------------------------------------------------------------------------
_MOCK_TASKS = [
    {"id": "t1", "title": "Buy birthday gift", "done": False, "list": "errands"},
]
_MOCK_EXPENSES = [
    {"category": "takeout", "amount": 42.50, "date": "2026-07-01"},
    {"category": "takeout", "amount": 18.00, "date": "2026-06-27"},
    {"category": "groceries", "amount": 96.30, "date": "2026-06-29"},
]

# ---------------------------------------------------------------------------
# SQLite for expense tracking
# ---------------------------------------------------------------------------
_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "expenses.db"


def _init_expenses_db() -> sqlite3.Connection:
    """Initialize the expenses SQLite database (create table if needed)."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _seed_expenses_if_empty(conn: sqlite3.Connection) -> None:
    """Seed the database with sample data if it's empty (first run)."""
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    if count == 0:
        logger.info("Seeding expenses database with sample data")
        for exp in _MOCK_EXPENSES:
            conn.execute(
                "INSERT INTO expenses (category, amount, date) VALUES (?, ?, ?)",
                (exp["category"], exp["amount"], exp["date"]),
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Google Tasks helpers
# ---------------------------------------------------------------------------
def _is_mock_mode() -> bool:
    return os.environ.get("HOMEBASE_MOCK", "").strip() in ("1", "true", "yes")


def _google_auth_available() -> bool:
    """Check if Google OAuth is configured."""
    try:
        from ..auth.google_oauth import is_google_auth_configured
        return is_google_auth_configured()
    except Exception:
        return False


def _get_tasks_service():
    """Get an authenticated Google Tasks API service."""
    from ..auth.google_oauth import get_google_service
    return get_google_service("tasks", "v1")


def _find_or_create_tasklist(service, list_name: str) -> str:
    """Find a task list by name, or create it. Returns the tasklist ID."""
    results = service.tasklists().list(maxResults=100).execute()
    for tl in results.get("items", []):
        if tl.get("title", "").lower() == list_name.lower():
            return tl["id"]

    # Create new list
    new_list = service.tasklists().insert(body={"title": list_name}).execute()
    logger.info("Created new Google Tasks list: %s", list_name)
    return new_list["id"]


def _parse_google_task(task: dict, list_name: str = "") -> dict:
    """Convert a Google Tasks API task to our standard format."""
    return {
        "id": task.get("id", ""),
        "title": task.get("title", ""),
        "done": task.get("status") == "completed",
        "list": list_name,
    }


# ---------------------------------------------------------------------------
# Public API (same interface as the original mock)
# ---------------------------------------------------------------------------
@safe_api_call
def list_tasks(list_name: str = None) -> dict:
    """read-tier: list tasks from Google Tasks.

    Args:
        list_name: Optional task list name to filter by. If None, returns tasks from all lists.

    Returns:
        {"tasks": [{"id", "title", "done", "list"}, ...]}
    """
    if _is_mock_mode() or not _google_auth_available():
        logger.info("Tasks MCP in mock mode")
        if list_name:
            return {"tasks": [t for t in _MOCK_TASKS if t["list"] == list_name]}
        return {"tasks": _MOCK_TASKS}

    service = _get_tasks_service()
    all_tasks = []

    if list_name:
        # Find specific list
        results = service.tasklists().list(maxResults=100).execute()
        for tl in results.get("items", []):
            if tl.get("title", "").lower() == list_name.lower():
                tasks_resp = service.tasks().list(tasklist=tl["id"], maxResults=100).execute()
                for t in tasks_resp.get("items", []):
                    all_tasks.append(_parse_google_task(t, list_name=tl.get("title", "")))
                break
    else:
        # All lists
        results = service.tasklists().list(maxResults=100).execute()
        for tl in results.get("items", []):
            tl_name = tl.get("title", "")
            tasks_resp = service.tasks().list(tasklist=tl["id"], maxResults=100).execute()
            for t in tasks_resp.get("items", []):
                all_tasks.append(_parse_google_task(t, list_name=tl_name))

    logger.info("Listed %d tasks from Google Tasks", len(all_tasks))
    return {"tasks": all_tasks}


@safe_api_call
def propose_task_list(items: list, list_name: str) -> dict:
    """draft-tier: propose a new set of tasks — pure computation, no API call.

    Args:
        items: List of task title strings
        list_name: Name for the task list

    Returns:
        {"draft": {"list", "items"}}
    """
    return {"draft": {"list": list_name, "items": items}}


@safe_api_call
def commit_task_list(items: list, list_name: str) -> dict:
    """act-tier: actually save the tasks to Google Tasks.

    Args:
        items: List of task title strings
        list_name: Name for the task list

    Returns:
        {"status": "committed", "count": int}
    """
    if _is_mock_mode() or not _google_auth_available():
        for item in items:
            _MOCK_TASKS.append({"id": f"t{len(_MOCK_TASKS)+1}", "title": item, "done": False, "list": list_name})
        return {"status": "committed", "count": len(items)}

    service = _get_tasks_service()
    tasklist_id = _find_or_create_tasklist(service, list_name)

    created = 0
    for item in items:
        service.tasks().insert(
            tasklist=tasklist_id,
            body={"title": item},
        ).execute()
        created += 1

    logger.info("Committed %d tasks to Google Tasks list '%s'", created, list_name)
    return {"status": "committed", "count": created}


@safe_api_call
def summarize_expenses(category: str = None, month: str = None) -> dict:
    """read-tier: summarize expenses from the local SQLite database.

    Args:
        category: Optional category to filter by (e.g. "takeout", "groceries")
        month: Optional month filter in "YYYY-MM" format

    Returns:
        {"total": float, "rows": [{"category", "amount", "date"}, ...]}
    """
    if _is_mock_mode():
        rows = _MOCK_EXPENSES
        if category:
            rows = [r for r in rows if r["category"] == category]
        total = sum(r["amount"] for r in rows)
        return {"total": round(total, 2), "rows": rows}

    conn = _init_expenses_db()
    _seed_expenses_if_empty(conn)

    query = "SELECT category, amount, date, description FROM expenses WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)
    if month:
        query += " AND date LIKE ?"
        params.append(f"{month}%")

    query += " ORDER BY date DESC"
    cursor = conn.execute(query, params)
    rows = [
        {"category": r[0], "amount": r[1], "date": r[2], "description": r[3]}
        for r in cursor.fetchall()
    ]
    total = sum(r["amount"] for r in rows)
    conn.close()

    logger.info("Summarized %d expense records (total: $%.2f)", len(rows), total)
    return {"total": round(total, 2), "rows": rows}


@safe_api_call
def add_expense(category: str, amount: float, date: str = None, description: str = "") -> dict:
    """draft-tier: log a new expense to the local database.

    Args:
        category: Expense category (e.g. "takeout", "groceries")
        amount: Amount in dollars
        date: Date of expense (ISO format, defaults to today)
        description: Optional description

    Returns:
        {"status": "logged", "expense": {...}}
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    if _is_mock_mode():
        _MOCK_EXPENSES.append({"category": category, "amount": amount, "date": date})
        return {"status": "logged", "expense": {"category": category, "amount": amount, "date": date}}

    conn = _init_expenses_db()
    conn.execute(
        "INSERT INTO expenses (category, amount, date, description) VALUES (?, ?, ?, ?)",
        (category, amount, date, description),
    )
    conn.commit()
    conn.close()

    logger.info("Logged expense: $%.2f in %s on %s", amount, category, date)
    return {
        "status": "logged",
        "expense": {"category": category, "amount": amount, "date": date, "description": description},
    }
