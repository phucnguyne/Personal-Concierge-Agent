"""Tests for the Weather MCP server (Open-Meteo integration).

Tests use respx to mock httpx calls, so no real network access is needed.
The autouse mock_mode fixture from conftest.py runs these in mock mode by default.
We also test the real API path with mocked HTTP to verify the parsing logic.
"""
import pytest
import httpx
import respx

from src.mcp_servers import weather_mcp


class TestWeatherMCPMockMode:
    """Tests that run with HOMEBASE_MOCK=1 (mock data, no HTTP calls)."""

    def test_known_city_returns_forecast(self):
        result = weather_mcp.get_forecast("Boston")
        assert "forecast" in result
        assert result["city"] == "Boston"
        assert len(result["forecast"]) >= 1
        assert result["forecast"][0]["condition"] == "rain"

    def test_unknown_city_returns_default(self):
        result = weather_mcp.get_forecast("Narnia", date="2026-07-08")
        assert "forecast" in result
        assert result["forecast"][0]["condition"] == "unknown"

    def test_ho_chi_minh_city(self):
        result = weather_mcp.get_forecast("Ho Chi Minh City")
        assert result["forecast"][0]["condition"] == "thunderstorms"
        assert result["forecast"][0]["high_f"] == 91


class TestWeatherMCPRealPath:
    """Tests that exercise the real API code path with mocked HTTP responses."""

    @respx.mock
    def test_geocode_and_forecast(self, monkeypatch):
        """Test the full geocode → forecast pipeline with mocked HTTP."""
        monkeypatch.delenv("HOMEBASE_MOCK", raising=False)

        # Clear caches
        weather_mcp._cache.clear()
        weather_mcp._geocode_cache.clear()

        # Mock geocoding response
        respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
            return_value=httpx.Response(200, json={
                "results": [{
                    "latitude": 42.36,
                    "longitude": -71.06,
                    "name": "Boston",
                    "country": "United States",
                }]
            })
        )

        # Mock forecast response
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json={
                "daily": {
                    "time": ["2026-07-08", "2026-07-09"],
                    "temperature_2m_max": [72.5, 78.1],
                    "temperature_2m_min": [58.2, 62.0],
                    "weathercode": [61, 0],
                }
            })
        )

        result = weather_mcp.get_forecast("Boston")
        assert result["city"] == "Boston"
        assert len(result["forecast"]) == 2
        assert result["forecast"][0]["high_f"] == 72  # rounded
        assert result["forecast"][0]["condition"] == "slight rain"
        assert result["forecast"][1]["condition"] == "clear sky"

    @respx.mock
    def test_unknown_city_real_path(self, monkeypatch):
        """Test graceful handling when geocoding returns no results."""
        monkeypatch.delenv("HOMEBASE_MOCK", raising=False)
        weather_mcp._geocode_cache.clear()

        respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
            return_value=httpx.Response(200, json={})
        )

        result = weather_mcp.get_forecast("Nonexistentville")
        assert "error" in result
        assert "Could not find city" in result["error"]

    @respx.mock
    def test_network_error_returns_error_dict(self, monkeypatch):
        """Test that network errors return an error dict, never raise."""
        monkeypatch.delenv("HOMEBASE_MOCK", raising=False)
        weather_mcp._geocode_cache.clear()

        respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        result = weather_mcp.get_forecast("Boston")
        assert "error" in result

    @respx.mock
    def test_date_filter(self, monkeypatch):
        """Test filtering forecast to a specific date."""
        monkeypatch.delenv("HOMEBASE_MOCK", raising=False)
        weather_mcp._cache.clear()
        weather_mcp._geocode_cache.clear()

        respx.get("https://geocoding-api.open-meteo.com/v1/search").mock(
            return_value=httpx.Response(200, json={
                "results": [{"latitude": 42.36, "longitude": -71.06, "name": "Boston"}]
            })
        )
        respx.get("https://api.open-meteo.com/v1/forecast").mock(
            return_value=httpx.Response(200, json={
                "daily": {
                    "time": ["2026-07-08", "2026-07-09", "2026-07-10"],
                    "temperature_2m_max": [72, 78, 80],
                    "temperature_2m_min": [58, 62, 64],
                    "weathercode": [61, 0, 3],
                }
            })
        )

        result = weather_mcp.get_forecast("Boston", date="2026-07-09")
        assert len(result["forecast"]) == 1
        assert result["forecast"][0]["date"] == "2026-07-09"
