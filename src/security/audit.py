"""Append-only audit log for every tool call — allowed, drafted, or blocked."""
import time
import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, List

from .pii_redaction import redact_payload


@dataclass
class AuditEntry:
    timestamp: float
    skill: str
    tool: str
    tier: str
    decision: str  # "allowed" | "blocked" | "approved" | "rejected"
    payload_redacted: dict
    payload_hash: str


class AuditLog:
    def __init__(self):
        self._entries: List[AuditEntry] = []

    def record(self, skill: str, tool: str, tier: str, decision: str, payload: dict):
        redacted = redact_payload(payload)
        payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
        entry = AuditEntry(
            timestamp=time.time(),
            skill=skill,
            tool=tool,
            tier=tier,
            decision=decision,
            payload_redacted=redacted,
            payload_hash=payload_hash,
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> List[dict]:
        return [asdict(e) for e in self._entries]

    def print_log(self):
        for e in self._entries:
            t = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
            print(f"[{t}] {e.decision:9s} | {e.skill:15s} | {e.tool:20s} | tier={e.tier:5s} | hash={e.payload_hash}")
