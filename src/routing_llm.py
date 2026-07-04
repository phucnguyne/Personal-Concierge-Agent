"""LLM-based intent router (optional upgrade over keyword routing).

Uses the Google Gen AI SDK (`google-genai`, the current unified SDK for the
Gemini API) to have a real model decide which skill should handle a
request — the "ADK-style" routing implied in the architecture diagram,
where a real orchestrator agent would use an LLM call rather than
keyword matching.

Falls back to keyword routing automatically if no API key is configured,
the `google-genai` package isn't installed, or the call fails for any
reason — so a notebook using this router still runs end-to-end on a
fresh kernel with no key set (it just logs that it fell back).

For local/dev use, this module will auto-load a `.env` file from the
project root if `python-dotenv` is installed (optional dependency) —
put `GEMINI_API_KEY=your-key-here` in a `.env` file next to `README.md`
and it will be picked up automatically. On Kaggle, use Add-ons -> Secrets
instead (a `.env` file won't be present on a fresh kernel).
"""
import os

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass  # python-dotenv not installed — fine, just relies on real env vars / Kaggle secrets

SKILL_NAMES = ["scheduling", "meal_planning", "travel_prep", "budgeting", "correspondence", "none"]

_SYSTEM_INSTRUCTION = (
    "You are the routing layer of a personal concierge agent called HomeBase. "
    "Given a user's request, decide which single skill should handle it.\n"
    "Valid skills:\n"
    "- scheduling: calendar lookups, moving/rescheduling meetings\n"
    "- meal_planning: dinner plans, grocery/shopping lists\n"
    "- travel_prep: weather/packing advice for a trip\n"
    "- budgeting: spending summaries, expense questions\n"
    "- correspondence: drafting an email or reply\n"
    "If none clearly apply, answer 'none'.\n"
    "Respond with ONLY the skill name, lowercase, nothing else — no punctuation, no explanation."
)


class LLMRouterUnavailable(Exception):
    """Raised when the LLM router can't be used; caller should fall back to keyword routing."""


def llm_route(request: str, api_key: str = None, model: str = "gemini-2.5-flash") -> str:
    """Return a skill name (or 'none') using a real Gemini call.

    Raises LLMRouterUnavailable (never a raw SDK exception) so callers can
    catch one exception type and fall back cleanly.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise LLMRouterUnavailable("no GEMINI_API_KEY / GOOGLE_API_KEY configured")

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise LLMRouterUnavailable(f"google-genai is not installed ({e}); run: pip install google-genai")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=request,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                temperature=0,
            ),
        )
        answer = (response.text or "").strip().lower()
    except Exception as e:
        raise LLMRouterUnavailable(f"Gemini call failed: {e}")

    for name in SKILL_NAMES:
        if name in answer:
            return name
    return "none"
