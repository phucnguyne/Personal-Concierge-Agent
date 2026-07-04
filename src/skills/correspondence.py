"""Correspondence skill: draft emails. Sending is out of scope by design —
HomeBase is never permitted to send email autonomously in this project.

Manifest:
  triggers: "email", "reply to", "draft a note to"
  mcp_servers: [email_mcp]
  default_max_tier: draft
"""
from ..mcp_servers import email_mcp
from ..security.permissions import ToolCall, Tier

NAME = "correspondence"


def handle(request: str, ladder, audit, to: str = "sam@example.com"):
    subject = "Re: Saturday"
    body = "Hi Sam — Saturday no longer works for me, could we push to Sunday afternoon instead?"
    call = ToolCall(NAME, "create_draft", Tier.DRAFT, {"to": to, "subject": subject, "body": body},
                     f"Draft email to {to}")
    ladder.authorize(call)
    result = email_mcp.create_draft(**call.arguments)
    audit.record(NAME, call.tool, call.tier.name, "allowed", call.arguments)
    return f"Drafted (not sent): {result['draft']}"
