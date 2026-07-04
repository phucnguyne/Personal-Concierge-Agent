"""Local stand-in for a Tasks/Notes MCP server (to-dos, shopping lists, expense notes)."""
_TASKS = [
    {"id": "t1", "title": "Buy birthday gift", "done": False, "list": "errands"},
]
_EXPENSES = [
    {"category": "takeout", "amount": 42.50, "date": "2026-07-01"},
    {"category": "takeout", "amount": 18.00, "date": "2026-06-27"},
    {"category": "groceries", "amount": 96.30, "date": "2026-06-29"},
]


def list_tasks(list_name: str = None):
    """read-tier."""
    if list_name:
        return {"tasks": [t for t in _TASKS if t["list"] == list_name]}
    return {"tasks": _TASKS}


def propose_task_list(items: list, list_name: str):
    """draft-tier: propose a new set of tasks (e.g. a shopping list), do not save."""
    return {"draft": {"list": list_name, "items": items}}


def commit_task_list(items: list, list_name: str):
    """act-tier: actually save the tasks."""
    for item in items:
        _TASKS.append({"id": f"t{len(_TASKS)+1}", "title": item, "done": False, "list": list_name})
    return {"status": "committed", "count": len(items)}


def summarize_expenses(category: str = None, month: str = None):
    """read-tier."""
    rows = _EXPENSES
    if category:
        rows = [r for r in rows if r["category"] == category]
    total = sum(r["amount"] for r in rows)
    return {"total": round(total, 2), "rows": rows}
