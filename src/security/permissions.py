"""Permission ladder: read / draft / act.

Every tool call must be tagged with a tier before it reaches an MCP server.
- read  : always allowed, no side effects
- draft : always allowed, produces an artifact but commits nothing
- act   : requires explicit human approval before execution
"""
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Callable, Optional


class Tier(IntEnum):
    READ = 0
    DRAFT = 1
    ACT = 2


@dataclass
class ToolCall:
    skill: str
    tool: str
    tier: Tier
    arguments: dict
    description: str  # human-readable summary shown for approval


class PermissionDenied(Exception):
    pass


class PermissionLadder:
    """Gates tool calls by tier. ACT calls require an approval callback."""

    def __init__(self, approve_fn: Optional[Callable[[ToolCall], bool]] = None, auto_approve: bool = False):
        # approve_fn(call) -> bool ; in a real deployment this would surface a UI prompt.
        self.approve_fn = approve_fn
        self.auto_approve = auto_approve  # only for scripted demo scenarios

    def authorize(self, call: ToolCall) -> bool:
        if call.tier in (Tier.READ, Tier.DRAFT):
            return True
        if call.tier == Tier.ACT:
            if self.auto_approve:
                return True
            if self.approve_fn is None:
                return False
            return bool(self.approve_fn(call))
        raise ValueError(f"Unknown tier: {call.tier}")
