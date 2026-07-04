"""ADK-style orchestrator agent.

In a real deployment this would be an `Agent` from google-adk with an LLM
doing the routing. Here routing is keyword-based so the notebook runs
deterministically without an API key — the *shape* (route -> load skill on
demand -> pass shared ladder/audit) is what maps onto the real ADK pattern.
"""
from .skills import scheduling, meal_planning, travel_prep, budgeting, correspondence
from .security.permissions import PermissionLadder
from .security.audit import AuditLog
from .routing_llm import llm_route, LLMRouterUnavailable

SKILL_MANIFEST = [
    (scheduling, ["calendar", "schedule", "reschedule", "move my", "what's on"]),
    (meal_planning, ["dinner", "meal plan", "grocery", "cook"]),
    (travel_prep, ["pack", "trip", "traveling", "weather"]),
    (budgeting, ["spend", "budget", "expense"]),
    (correspondence, ["email", "reply to", "draft a note"]),
]

SKILL_BY_NAME = {skill_module.NAME: skill_module for skill_module, _ in SKILL_MANIFEST}


class HomeBaseOrchestrator:
    def __init__(self, approve_fn=None, auto_approve=False,
                 router: str = "keyword", gemini_api_key: str = None, gemini_model: str = "gemini-2.5-flash"):
        """
        router: "keyword" (default, deterministic, no API key needed) or
                "llm" (real Gemini call decides the skill; falls back to
                keyword routing automatically if no key/package/call fails).
        """
        self.ladder = PermissionLadder(approve_fn=approve_fn, auto_approve=auto_approve)
        self.audit = AuditLog()
        self.router = router
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model

    def _route_by_keyword(self, request: str):
        r = request.lower()
        for skill_module, keywords in SKILL_MANIFEST:
            if any(k in r for k in keywords):
                return skill_module
        return None

    def route(self, request: str):
        """Progressive disclosure: only decide which skill module to load."""
        if self.router == "llm":
            try:
                name = llm_route(request, api_key=self.gemini_api_key, model=self.gemini_model)
                return SKILL_BY_NAME.get(name)  # None for "none" or an unrecognized name
            except LLMRouterUnavailable as e:
                print(f"[router] LLM routing unavailable ({e}) — falling back to keyword routing for this request")
        return self._route_by_keyword(request)

    def handle(self, request: str, **kwargs):
        skill_module = self.route(request)
        if skill_module is None:
            return "I'm not sure which skill handles that yet — try asking about scheduling, meals, travel, budget, or email."
        return skill_module.handle(request, self.ladder, self.audit, **kwargs)
