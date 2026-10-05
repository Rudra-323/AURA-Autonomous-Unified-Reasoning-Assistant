"""Weather tool — async httpx, OpenWeatherMap primary with search fallback."""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from config.settings import get_settings
from tools.web_search import run_google_search
from utils.errors import ExternalServiceError
from utils.logging import get_logger
from utils.security import describe_http_error

log = get_logger("tools.weather")

_TIMEOUT = 8.0
_GEOCODE_URL = "https://api.openweathermap.org/geo/1.0/direct"
_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


async def _fetch_openweather(location: str) -> str:
    settings = get_settings()
    if not settings.openweather_api_key:
        raise ExternalServiceError("OpenWeatherMap is not configured")

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            geo_resp = await client.get(
                _GEOCODE_URL,
                params={"q": location, "limit": 1, "appid": settings.openweather_api_key},
            )
            geo_resp.raise_for_status()
            geo_data = geo_resp.json()
            if not geo_data:
                raise ExternalServiceError(f"Could not find a location matching '{location}'")

            lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
            resolved_name = geo_data[0].get("name", location)

            weather_resp = await client.get(
                _WEATHER_URL,
                params={"lat": lat, "lon": lon, "appid": settings.openweather_api_key, "units": "metric"},
            )
            weather_resp.raise_for_status()
            data = weather_resp.json()
        except httpx.TimeoutException as exc:
            raise ExternalServiceError(f"OpenWeatherMap timed out ({describe_http_error(exc)})") from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"OpenWeatherMap request failed ({describe_http_error(exc)})") from exc

    d = data["weather"][0]["description"]
    temp, feels, hum = data["main"]["temp"], data["main"]["feels_like"], data["main"]["humidity"]
    wind = data["wind"]["speed"]
    return f"Weather in {resolved_name}: {d}, {temp}°C (feels like {feels}°C), humidity {hum}%, wind {wind} m/s."


@tool
async def weather(location: str) -> str:
    """Get current weather for a location, e.g. "Bengaluru" or "Paris, FR"."""
    try:
        return await _fetch_openweather(location)
    except ExternalServiceError as exc:
        log.warning("weather.primary_failed", extra={"location": location, "error": str(exc)})

    try:
        results = await run_google_search(f"current weather in {location}", max_results=3)
        if not results:
            return f"I couldn't retrieve weather data for {location} right now."
        summary = " ".join(r["snippet"] for r in results[:2])
        return f"(OpenWeatherMap was unavailable; web search fallback) {summary}"
    except ExternalServiceError:
        return f"I couldn't retrieve weather data for {location} right now."
