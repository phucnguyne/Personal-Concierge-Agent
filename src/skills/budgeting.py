"""Budgeting skill: summarize logged expenses (read-tier only, never initiates spend).

Manifest:
  triggers: "how much did I spend", "budget", "expenses"
  mcp_servers: [tasks_mcp]
  default_max_tier: read
"""
from ..mcp_servers import tasks_mcp
from ..security.permissions import ToolCall, Tier

NAME = "budgeting"


def handle(request: str, ladder, audit, category: str = "takeout"):
    call = ToolCall(NAME, "summarize_expenses", Tier.READ, {"category": category}, f"Summarize {category} spend")
    ladder.authorize(call)
    result = tasks_mcp.summarize_expenses(**call.arguments)
    audit.record(NAME, call.tool, call.tier.name, "allowed", call.arguments)
    return f"You've spent ${result['total']} on {category} recently, across {len(result['rows'])} purchases."
