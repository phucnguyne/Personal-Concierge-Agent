"""Weather MCP server — backed by the Open-Meteo API (free, no key required).

Replaces the hardcoded forecast data with real weather data.
Preserves the exact same interface: get_forecast(city, date) -> dict.

Features:
  - Geocodes city names to lat/lon via Open-Meteo's geocoding API
  - Fetches real 7-day forecasts from api.open-meteo.com
  - 1-hour TTL cache per city to avoid redundant calls
  - Automatic retry + timeout on transient failures
  - Falls back to mock data if HOMEBASE_MOCK=1 (for notebook demos)
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from .api_utils import get_http_client, api_retry, safe_api_call, TTLCache

logger = logging.getLogger("homebase.mcp.weather")

# ---------------------------------------------------------------------------
# Mock data (kept for backwards compatibility with notebook demos)
# ---------------------------------------------------------------------------
_MOCK_FORECASTS = {
    "Boston": [{"date": "2026-07-08", "high_f": 72, "low_f": 58, "condition": "rain"}],
    "Ho Chi Minh City": [{"date": "2026-07-08", "high_f": 91, "low_f": 79, "condition": "thunderstorms"}],
}

# ---------------------------------------------------------------------------
# Cache: 1-hour TTL per city
# ---------------------------------------------------------------------------
_cache = TTLCache(default_ttl=3600)
_geocode_cache = TTLCache(default_ttl=86400)  # 24h for geocoding results

# ---------------------------------------------------------------------------
# Open-Meteo API endpoints
# ---------------------------------------------------------------------------
_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather interpretation codes → human-readable conditions
_WMO_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    77: "snow grains",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "slight snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with slight hail", 99: "thunderstorms with heavy hail",
}


def _is_mock_mode() -> bool:
    return os.environ.get("HOMEBASE_MOCK", "").strip() in ("1", "true", "yes")


@api_retry
def _geocode_city(city: str) -> Optional[dict]:
    """Convert a city name to lat/lon using Open-Meteo geocoding API."""
    cached = _geocode_cache.get(city.lower())
    if cached is not None:
        return cached

    client = get_http_client()
    resp = client.get(_GEOCODE_URL, params={"name": city, "count": 1, "language": "en"})
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results")
    if not results:
        return None

    location = {
        "lat": results[0]["latitude"],
        "lon": results[0]["longitude"],
        "name": results[0].get("name", city),
        "country": results[0].get("country", ""),
    }
    _geocode_cache.set(city.lower(), location)
    return location


@api_retry
def _fetch_forecast(lat: float, lon: float) -> dict:
    """Fetch a 7-day forecast from Open-Meteo."""
    client = get_http_client()
    resp = client.get(_FORECAST_URL, params={
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,weathercode",
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
        "forecast_days": 7,
    })
    resp.raise_for_status()
    return resp.json()


def _parse_forecast(data: dict, target_date: Optional[str] = None) -> list[dict]:
    """Parse Open-Meteo daily forecast response into our standard format."""
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    highs = daily.get("temperature_2m_max", [])
    lows = daily.get("temperature_2m_min", [])
    codes = daily.get("weathercode", [])

    forecasts = []
    for i, date_str in enumerate(dates):
        entry = {
            "date": date_str,
            "high_f": round(highs[i]) if i < len(highs) else None,
            "low_f": round(lows[i]) if i < len(lows) else None,
            "condition": _WMO_CODES.get(codes[i], "unknown") if i < len(codes) else "unknown",
        }
        forecasts.append(entry)

    # Filter to target date if specified
    if target_date:
        filtered = [f for f in forecasts if f["date"] == target_date]
        if filtered:
            return filtered
        # If exact date not in range, return all (better than nothing)

    return forecasts


@safe_api_call
def get_forecast(city: str, date: str = None) -> dict:
    """read-tier: get weather forecast for a city.

    Args:
        city: City name (e.g. "Boston", "Ho Chi Minh City")
        date: Optional ISO date string (e.g. "2026-07-08"). If omitted, returns 7-day forecast.

    Returns:
        {"city": str, "forecast": [{"date", "high_f", "low_f", "condition"}, ...]}
        or {"error": str} on failure.
    """
    # Mock mode for notebook demos
    if _is_mock_mode():
        return {
            "city": city,
            "forecast": _MOCK_FORECASTS.get(
                city,
                [{"date": date or "unknown", "high_f": 75, "low_f": 60, "condition": "unknown"}]
            ),
        }

    # Check cache
    cache_key = f"forecast:{city.lower()}"
    cached = _cache.get(cache_key)
    if cached is not None:
        logger.debug("Cache hit for %s forecast", city)
        forecasts = _parse_forecast(cached, target_date=date)
        return {"city": city, "forecast": forecasts}

    # Geocode city
    location = _geocode_city(city)
    if location is None:
        return {"city": city, "error": f"Could not find city: {city}"}

    # Fetch forecast
    raw = _fetch_forecast(location["lat"], location["lon"])
    _cache.set(cache_key, raw)

    forecasts = _parse_forecast(raw, target_date=date)
    logger.info("Fetched real forecast for %s (%s)", city, location.get("country", ""))
    return {"city": city, "forecast": forecasts}
