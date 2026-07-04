"""Lightweight PII redaction for logging and cross-skill payloads.

This is intentionally simple (regex-based) — good enough for a capstone demo.
A production system would use a proper PII-detection model/service.
"""
import re

EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
PHONE_RE = re.compile(r"\b(\+?\d{1,2}[\s.-]?)?(\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b")
ADDRESS_RE = re.compile(r"\d{1,5}\s+\w+(\s\w+){0,3}\s(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b", re.IGNORECASE)


def redact(text: str) -> str:
    if not text:
        return text
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = ADDRESS_RE.sub("[REDACTED_ADDRESS]", text)
    return text


def redact_payload(payload: dict) -> dict:
    """Recursively redact string values in a dict, for safe audit logging."""
    out = {}
    for k, v in payload.items():
        if isinstance(v, str):
            out[k] = redact(v)
        elif isinstance(v, dict):
            out[k] = redact_payload(v)
        else:
            out[k] = v
    return out
