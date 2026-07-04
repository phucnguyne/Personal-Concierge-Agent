"""Mechanical evaluation harness (no human judgment needed):
1. Skill-routing accuracy
2. Permission-tier accuracy for the first tool call issued per request
3. Approval-gate integrity: no ACT call ever executes without a recorded approval
"""
from .orchestrator import HomeBaseOrchestrator

ROUTING_CASES = [
    ("what's on my calendar this week", "scheduling"),
    ("move my 3pm to tomorrow", "scheduling"),
    ("plan dinner for the week", "meal_planning"),
    ("grocery list please", "meal_planning"),
    ("what's the weather like on my trip to Boston", "travel_prep"),
    ("how much did I spend on takeout", "budgeting"),
    ("draft a reply to Sam", "correspondence"),
]

TIER_CASES = [
    ("what's on my calendar this week", "READ"),
    ("plan dinner for the week", "DRAFT"),
    ("how much did I spend on takeout", "READ"),
    ("draft a reply to Sam", "DRAFT"),
]


def run_routing_eval():
    orch = HomeBaseOrchestrator(auto_approve=True)
    correct = 0
    for request, expected in ROUTING_CASES:
        skill = orch.route(request)
        got = skill.NAME if skill else None
        ok = got == expected
        correct += ok
        print(f"{'PASS' if ok else 'FAIL'}  '{request}' -> expected={expected} got={got}")
    print(f"\nRouting accuracy: {correct}/{len(ROUTING_CASES)}")
    return correct / len(ROUTING_CASES)


def run_tier_eval():
    correct = 0
    for request, expected_tier in TIER_CASES:
        orch = HomeBaseOrchestrator(auto_approve=True)
        orch.handle(request)
        first_entry = orch.audit.entries()[0]
        ok = first_entry["tier"] == expected_tier
        correct += ok
        print(f"{'PASS' if ok else 'FAIL'}  '{request}' -> expected={expected_tier} got={first_entry['tier']}")
    print(f"\nTier accuracy: {correct}/{len(TIER_CASES)}")
    return correct / len(TIER_CASES)


def run_approval_gate_eval():
    """Confirm that when approval is withheld, no ACT-tier call is ever marked 'approved'."""
    orch = HomeBaseOrchestrator(approve_fn=lambda call: False)  # always reject
    orch.handle("move my 3pm to tomorrow")
    entries = orch.audit.entries()
    act_entries = [e for e in entries if e["tier"] == "ACT"]
    leaked = [e for e in act_entries if e["decision"] == "approved"]
    ok = len(leaked) == 0
    print(f"{'PASS' if ok else 'FAIL'}  ACT calls executed without approval: {len(leaked)} (should be 0)")
    return ok
