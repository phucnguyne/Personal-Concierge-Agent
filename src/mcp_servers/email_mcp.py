"""Local stand-in for an Email MCP server.

Deliberately supports draft creation but NOT sending — HomeBase never
sends email autonomously in this project; sending is treated as
out-of-scope act-tier and always requires a real client / human hand-off.
"""
_DRAFTS = []


def create_draft(to: str, subject: str, body: str):
    """draft-tier: create an email draft, do not send."""
    draft = {"id": f"draft{len(_DRAFTS)+1}", "to": to, "subject": subject, "body": body}
    _DRAFTS.append(draft)
    return {"draft": draft}


def list_drafts():
    """read-tier."""
    return {"drafts": _DRAFTS}
