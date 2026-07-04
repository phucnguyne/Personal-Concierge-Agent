"""Scheduling skill: read/reschedule calendar events.

Manifest (what the orchestrator checks before loading this skill in full):
  triggers: "calendar", "schedule", "reschedule", "move my", "what's on"
  mcp_servers: [calendar_mcp]
  default_max_tier: draft   (committing a reschedule is act-tier and needs approval)
"""
from ..mcp_servers import calendar_mcp
from ..security.permissions import ToolCall, Tier

NAME = "scheduling"


def handle(request: str, ladder, audit):
    request_l = request.lower()

    if "move" in request_l or "reschedule" in request_l:
        # Step 1: propose the change (draft-tier, always allowed)
        call = ToolCall(NAME, "propose_reschedule", Tier.DRAFT,
                         {"event_id": "evt1", "new_start": "2026-07-09T10:00:00", "new_end": "2026-07-09T10:30:00"},
                         "Draft: move 'Team sync' to Thu Jul 9, 10:00am")
        ladder.authorize(call)
        result = calendar_mcp.propose_reschedule(**call.arguments)
        audit.record(NAME, call.tool, call.tier.name, "allowed", call.arguments)

        # Step 2: committing the change is act-tier -> needs approval
        commit_call = ToolCall(NAME, "commit_reschedule", Tier.ACT, call.arguments,
                                "Move 'Team sync' from Mon 3:00pm to Thu 10:00am — confirm?")
        approved = ladder.authorize(commit_call)
        if approved:
            commit_result = calendar_mcp.commit_reschedule(**commit_call.arguments)
            audit.record(NAME, commit_call.tool, commit_call.tier.name, "approved", commit_call.arguments)
            return f"Done — moved to {commit_call.arguments['new_start']}. (draft: {result['draft']})"
        else:
            audit.record(NAME, commit_call.tool, commit_call.tier.name, "blocked", commit_call.arguments)
            return f"I've drafted the change but need your OK before moving it: {result['draft']}"

    # default: read-only lookup
    call = ToolCall(NAME, "list_events", Tier.READ, {}, "List upcoming events")
    ladder.authorize(call)
    result = calendar_mcp.list_events()
    audit.record(NAME, call.tool, call.tier.name, "allowed", call.arguments)
    return f"Upcoming: {result['events']}"
