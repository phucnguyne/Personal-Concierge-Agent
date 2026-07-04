"""Travel prep skill: forecast-driven packing advice (read-tier only).

Manifest:
  triggers: "pack", "trip", "traveling to", "weather in"
  mcp_servers: [weather_mcp, calendar_mcp]
  default_max_tier: read
"""
from ..mcp_servers import weather_mcp
from ..security.permissions import ToolCall, Tier

NAME = "travel_prep"


def handle(request: str, ladder, audit, city: str = "Boston"):
    call = ToolCall(NAME, "get_forecast", Tier.READ, {"city": city}, f"Look up forecast for {city}")
    ladder.authorize(call)
    result = weather_mcp.get_forecast(**call.arguments)
    audit.record(NAME, call.tool, call.tier.name, "allowed", call.arguments)
    day = result["forecast"][0]
    advice = "Pack a rain jacket and layers." if "rain" in day["condition"] else "Light layers should be fine."
    return f"{city} on {day['date']}: {day['low_f']}-{day['high_f']}°F, {day['condition']}. {advice}"
