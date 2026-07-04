"""Local stand-in for a Weather MCP server, used for trip planning."""
_FORECASTS = {
    "Boston": [{"date": "2026-07-08", "high_f": 72, "low_f": 58, "condition": "rain"}],
    "Ho Chi Minh City": [{"date": "2026-07-08", "high_f": 91, "low_f": 79, "condition": "thunderstorms"}],
}


def get_forecast(city: str, date: str = None):
    """read-tier."""
    return {"city": city, "forecast": _FORECASTS.get(city, [{"date": date, "high_f": 75, "low_f": 60, "condition": "unknown"}])}
