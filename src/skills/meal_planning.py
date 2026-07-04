"""Meal planning skill: generate a weekly plan + shopping list (draft-tier).

Manifest:
  triggers: "dinner", "meal plan", "grocery list", "what should I cook"
  mcp_servers: [tasks_mcp]
  default_max_tier: draft
"""
from ..mcp_servers import tasks_mcp
from ..security.permissions import ToolCall, Tier

NAME = "meal_planning"

_SAMPLE_PLAN = ["Mon: stir-fry veggies + tofu", "Tue: sheet-pan chicken", "Wed: lentil soup",
                "Thu: leftovers", "Fri: pizza night"]
_SHOPPING_LIST = ["tofu", "mixed veggies", "chicken thighs", "lentils", "pizza dough"]


def handle(request: str, ladder, audit):
    call = ToolCall(NAME, "propose_task_list", Tier.DRAFT,
                     {"items": _SHOPPING_LIST, "list_name": "groceries"},
                     "Draft shopping list for this week's meal plan")
    ladder.authorize(call)
    result = tasks_mcp.propose_task_list(**call.arguments)
    audit.record(NAME, call.tool, call.tier.name, "allowed", call.arguments)
    plan_str = "\n".join(_SAMPLE_PLAN)
    return f"Here's a plan for the week:\n{plan_str}\n\nDraft shopping list (not saved yet): {result['draft']['items']}"
