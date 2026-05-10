"""No-key Open-Meteo weather tool for Lumen.

The module keeps provider access bounded and compresses results before they are
passed to the LLM. It never requires API keys and never asks the LLM to infer a
missing location.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
from pydantic import BaseModel, Field

from app.lumen.budgets import LumenWeatherBudget, clamp_lumen_weather_budget
from app.lumen.intent import extract_weather_location_hint

OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PROVIDER = "open_meteo"
LOCATION_REQUIRED_MESSAGE = "天気を確認する地域を指定してください。例: 東京、横浜、札幌"


class LumenWeatherError(BaseModel):
    """Structured weather tool error passed through job events."""

    error: str
    message: str
    provider: str = PROVIDER


class LumenWeatherRequest(BaseModel):
    """Weather lookup request resolved from the submit payload and message."""

    message: str = ""
    location: str | None = None
    lang: str = "ja"
    budget: LumenWeatherBudget = Field(default_factory=LumenWeatherBudget)


class LumenWeatherResult(BaseModel):
    """Compressed provider-neutral weather result for Lumen."""

    ok: bool
    provider: str = PROVIDER
    location_name: str | None = None
    country: str | None = None
    admin1: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    current_temperature: float | None = None
    apparent_temperature: float | None = None
    weather_code: int | None = None
    weather_text: str | None = None
    precipitation: float | None = None
    precipitation_probability: float | None = None
    wind_speed: float | None = None
    daily: list[dict[str, Any]] = Field(default_factory=list)
    forecast_dates: list[str] = Field(default_factory=list)
    fetched_at: str | None = None
    error: str | None = None
    message: str = ""


def _dump_model(value: BaseModel) -> dict[str, Any]:
    return value.model_dump() if hasattr(value, "model_dump") else value.dict()


def weather_code_to_text(code: int | None, lang: str = "ja") -> str:
    """Convert representative Open-Meteo WMO weather codes to readable text."""

    if code is None:
        return "不明" if lang == "ja" else "unknown"
    mapping_ja = {
        0: "快晴",
        1: "晴れ",
        2: "一部曇り",
        3: "曇り",
        45: "霧",
        48: "霧",
        51: "霧雨",
        53: "霧雨",
        55: "霧雨",
        61: "雨",
        63: "雨",
        65: "雨",
        71: "雪",
        73: "雪",
        75: "雪",
        80: "にわか雨",
        81: "にわか雨",
        82: "にわか雨",
        95: "雷雨",
        96: "雷雨",
        99: "雷雨",
    }
    mapping_en = {
        0: "clear sky",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "fog",
        51: "drizzle",
        53: "drizzle",
        55: "drizzle",
        61: "rain",
        63: "rain",
        65: "rain",
        71: "snow",
        73: "snow",
        75: "snow",
        80: "rain showers",
        81: "rain showers",
        82: "rain showers",
        95: "thunderstorm",
        96: "thunderstorm",
        99: "thunderstorm",
    }
    return (mapping_ja if lang == "ja" else mapping_en).get(int(code), "不明" if lang == "ja" else "unknown")


class OpenMeteoGeocodingClient:
    """Small Open-Meteo geocoding client. No API key is required."""

    def __init__(self, *, base_url: str = OPEN_METEO_GEOCODING_URL, session: Any | None = None) -> None:
        self.base_url = base_url
        self.session = session or requests

    def search(self, location: str, *, budget: LumenWeatherBudget) -> list[dict[str, Any]]:
        safe_budget = clamp_lumen_weather_budget(budget)
        response = self.session.get(
            self.base_url,
            params={
                "name": location,
                "count": safe_budget.max_geocoding_results,
                "language": "ja",
                "format": "json",
            },
            timeout=safe_budget.timeout_sec,
        )
        response.raise_for_status()
        data = response.json() or {}
        results = data.get("results") or []
        return list(results)[: safe_budget.max_geocoding_results]


class OpenMeteoForecastClient:
    """Small Open-Meteo forecast client. No API key is required."""

    def __init__(self, *, base_url: str = OPEN_METEO_FORECAST_URL, session: Any | None = None) -> None:
        self.base_url = base_url
        self.session = session or requests

    def forecast(self, *, latitude: float, longitude: float, timezone_name: str, budget: LumenWeatherBudget) -> dict[str, Any]:
        safe_budget = clamp_lumen_weather_budget(budget)
        response = self.session.get(
            self.base_url,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone_name or "auto",
                "forecast_days": safe_budget.forecast_days,
                "current": ",".join(
                    [
                        "temperature_2m",
                        "apparent_temperature",
                        "weather_code",
                        "precipitation",
                        "wind_speed_10m",
                    ]
                ),
                "hourly": "precipitation_probability",
                "daily": ",".join(
                    [
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_probability_max",
                        "weather_code",
                    ]
                ),
            },
            timeout=safe_budget.timeout_sec,
        )
        response.raise_for_status()
        return response.json() or {}


def _first_hourly_probability(forecast: dict[str, Any]) -> float | None:
    values = (forecast.get("hourly") or {}).get("precipitation_probability") or []
    if not values:
        return None
    return values[0]


def _build_daily(forecast: dict[str, Any], *, lang: str, budget: LumenWeatherBudget) -> tuple[list[dict[str, Any]], list[str]]:
    daily_payload = forecast.get("daily") or {}
    dates = list(daily_payload.get("time") or [])[: budget.forecast_days]
    max_values = list(daily_payload.get("temperature_2m_max") or [])
    min_values = list(daily_payload.get("temperature_2m_min") or [])
    precip_values = list(daily_payload.get("precipitation_probability_max") or [])
    weather_codes = list(daily_payload.get("weather_code") or [])
    daily: list[dict[str, Any]] = []
    for idx, date in enumerate(dates):
        code = weather_codes[idx] if idx < len(weather_codes) else None
        daily.append(
            {
                "date": date,
                "temperature_max": max_values[idx] if idx < len(max_values) else None,
                "temperature_min": min_values[idx] if idx < len(min_values) else None,
                "precipitation_probability": precip_values[idx] if idx < len(precip_values) else None,
                "weather_code": code,
                "weather_text": weather_code_to_text(code, lang=lang),
            }
        )
    return daily, dates


def run_lumen_weather_tool(
    request: LumenWeatherRequest | dict[str, Any],
    *,
    geocoding_client: OpenMeteoGeocodingClient | None = None,
    forecast_client: OpenMeteoForecastClient | None = None,
) -> LumenWeatherResult:
    """Run the bounded Open-Meteo lookup and return a graceful result."""

    req = request if isinstance(request, LumenWeatherRequest) else LumenWeatherRequest(**request)
    budget = clamp_lumen_weather_budget(req.budget)
    location = (req.location or "").strip() or (extract_weather_location_hint(req.message) or "").strip()
    fetched_at = datetime.now(timezone.utc).isoformat()
    if not location:
        return LumenWeatherResult(
            ok=False,
            error="location_required",
            message=LOCATION_REQUIRED_MESSAGE,
            fetched_at=fetched_at,
        )

    geocoder = geocoding_client or OpenMeteoGeocodingClient()
    forecaster = forecast_client or OpenMeteoForecastClient()
    try:
        candidates = geocoder.search(location, budget=budget)
    except Exception as exc:  # network/provider errors must be graceful
        return LumenWeatherResult(ok=False, error="geocoding_failed", message=f"天気の地域検索に失敗しました: {exc}", fetched_at=fetched_at)
    if not candidates:
        return LumenWeatherResult(ok=False, error="location_not_found", message=f"地域が見つかりませんでした: {location}", fetched_at=fetched_at)

    selected = candidates[0]
    latitude = selected.get("latitude")
    longitude = selected.get("longitude")
    timezone_name = selected.get("timezone") or "auto"
    try:
        forecast = forecaster.forecast(
            latitude=float(latitude),
            longitude=float(longitude),
            timezone_name=timezone_name,
            budget=budget,
        )
    except Exception as exc:
        return LumenWeatherResult(
            ok=False,
            provider=PROVIDER,
            location_name=selected.get("name") or location,
            country=selected.get("country"),
            admin1=selected.get("admin1"),
            latitude=latitude,
            longitude=longitude,
            timezone=timezone_name,
            error="forecast_failed",
            message=f"天気予報の取得に失敗しました: {exc}",
            fetched_at=fetched_at,
        )

    current = forecast.get("current") or {}
    code = current.get("weather_code")
    daily, forecast_dates = _build_daily(forecast, lang=req.lang, budget=budget)
    return LumenWeatherResult(
        ok=True,
        provider=PROVIDER,
        location_name=selected.get("name") or location,
        country=selected.get("country"),
        admin1=selected.get("admin1"),
        latitude=latitude,
        longitude=longitude,
        timezone=forecast.get("timezone") or timezone_name,
        current_temperature=current.get("temperature_2m"),
        apparent_temperature=current.get("apparent_temperature"),
        weather_code=code,
        weather_text=weather_code_to_text(code, lang=req.lang),
        precipitation=current.get("precipitation"),
        precipitation_probability=_first_hourly_probability(forecast),
        wind_speed=current.get("wind_speed_10m"),
        daily=daily,
        forecast_dates=forecast_dates,
        fetched_at=fetched_at,
        message="天気を取得しました。",
    )


def _location_line(result: LumenWeatherResult) -> str:
    parts = [part for part in [result.location_name, result.admin1, result.country] if part]
    return ", ".join(parts) or "unknown"


def compress_weather_result_for_llm(result: LumenWeatherResult | dict[str, Any]) -> str:
    """Return a compact non-JSON context block for the LLM."""

    weather = result if isinstance(result, LumenWeatherResult) else LumenWeatherResult(**result)
    lines = ["[Internal Lumen Weather Context]", "Provider: Open-Meteo"]
    if not weather.ok:
        lines.extend(
            [
                f"Status: error ({weather.error or 'unknown'})",
                f"Message: {weather.message}",
                "Instruction: Answer the user naturally in Japanese. Explain that weather data could not be obtained or ask for a region when required. Do not invent weather data beyond this context.",
            ]
        )
        return "\n".join(lines)

    lines.append(f"Location: {_location_line(weather)}")
    if weather.latitude is not None and weather.longitude is not None:
        lines.append(f"Coordinates: {weather.latitude}, {weather.longitude}")
    if weather.timezone:
        lines.append(f"Timezone: {weather.timezone}")
    current = f"Current: {weather.current_temperature}°C, {weather.weather_text or '不明'}"
    if weather.apparent_temperature is not None:
        current += f" (feels like {weather.apparent_temperature}°C)"
    if weather.precipitation is not None:
        current += f", precipitation {weather.precipitation}mm"
    if weather.precipitation_probability is not None:
        current += f", precipitation probability {weather.precipitation_probability}%"
    if weather.wind_speed is not None:
        current += f", wind {weather.wind_speed}km/h"
    lines.append(current)
    if weather.daily:
        first = weather.daily[0]
        lines.append(
            "Today: max {max}°C / min {min}°C, precipitation probability {pop}%, {text}".format(
                max=first.get("temperature_max"),
                min=first.get("temperature_min"),
                pop=first.get("precipitation_probability"),
                text=first.get("weather_text") or "不明",
            )
        )
        for item in weather.daily[1:]:
            lines.append(
                "Forecast {date}: max {max}°C / min {min}°C, precipitation probability {pop}%, {text}".format(
                    date=item.get("date"),
                    max=item.get("temperature_max"),
                    min=item.get("temperature_min"),
                    pop=item.get("precipitation_probability"),
                    text=item.get("weather_text") or "不明",
                )
            )
    if weather.forecast_dates:
        lines.append(f"Forecast dates: {', '.join(weather.forecast_dates)}")
    lines.append(f"Fetched at: {weather.fetched_at}")
    lines.append("Instruction: Answer the user naturally in Japanese. Do not invent weather data beyond this context.")
    return "\n".join(lines)


__all__ = [
    "OpenMeteoGeocodingClient",
    "OpenMeteoForecastClient",
    "LumenWeatherRequest",
    "LumenWeatherResult",
    "LumenWeatherError",
    "run_lumen_weather_tool",
    "compress_weather_result_for_llm",
    "weather_code_to_text",
]
