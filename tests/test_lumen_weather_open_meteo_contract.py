from pathlib import Path

from app.lumen.budgets import clamp_lumen_weather_budget
from app.lumen.weather import (
    LumenWeatherRequest,
    LumenWeatherResult,
    OpenMeteoForecastClient,
    OpenMeteoGeocodingClient,
    compress_weather_result_for_llm,
    run_lumen_weather_tool,
    weather_code_to_text,
)


class FakeResponse:
    def __init__(self, payload, *, fail=False):
        self.payload = payload
        self.fail = fail

    def raise_for_status(self):
        if self.fail:
            raise RuntimeError("http failed")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(self.payload)


class EmptyGeocoder:
    def search(self, location, *, budget):
        return []


class GoodGeocoder:
    def search(self, location, *, budget):
        return [
            {
                "name": "Tokyo",
                "country": "Japan",
                "admin1": "Tokyo",
                "latitude": 35.6895,
                "longitude": 139.6917,
                "timezone": "Asia/Tokyo",
            }
        ]


class FailingForecaster:
    def forecast(self, **kwargs):
        raise RuntimeError("forecast down")


class GoodForecaster:
    def forecast(self, **kwargs):
        return {
            "timezone": "Asia/Tokyo",
            "current": {
                "temperature_2m": 18.5,
                "apparent_temperature": 17.8,
                "weather_code": 3,
                "precipitation": 0,
                "wind_speed_10m": 4.2,
            },
            "hourly": {"precipitation_probability": [30]},
            "daily": {
                "time": ["2026-05-10", "2026-05-11"],
                "temperature_2m_max": [22, 21],
                "temperature_2m_min": [14, 13],
                "precipitation_probability_max": [30, 60],
                "weather_code": [3, 61],
            },
        }


def test_lumen_weather_module_and_clients_exist():
    assert Path("app/lumen/weather.py").exists()
    assert OpenMeteoGeocodingClient
    assert OpenMeteoForecastClient
    assert callable(run_lumen_weather_tool)
    assert callable(weather_code_to_text)


def test_open_meteo_clients_need_no_api_key_and_apply_budget():
    geo_session = FakeSession({"results": [{"name": "A"}, {"name": "B"}, {"name": "C"}]})
    geocoder = OpenMeteoGeocodingClient(session=geo_session)
    results = geocoder.search("Tokyo", budget=clamp_lumen_weather_budget({"max_geocoding_results": 2, "timeout_sec": 5}))

    assert len(results) == 2
    assert "apikey" not in geo_session.calls[0]["params"]
    assert "api_key" not in geo_session.calls[0]["params"]

    forecast_session = FakeSession({"current": {}, "daily": {}})
    forecaster = OpenMeteoForecastClient(session=forecast_session)
    forecaster.forecast(latitude=1, longitude=2, timezone_name="Asia/Tokyo", budget=clamp_lumen_weather_budget({"forecast_days": 9}))

    assert forecast_session.calls[0]["params"]["forecast_days"] == 7
    assert "apikey" not in forecast_session.calls[0]["params"]
    assert "api_key" not in forecast_session.calls[0]["params"]


def test_lumen_weather_budget_forecast_days_clamps_1_to_7():
    assert clamp_lumen_weather_budget({"forecast_days": 0}).forecast_days == 1
    assert clamp_lumen_weather_budget({"forecast_days": 999}).forecast_days == 7


def test_location_missing_returns_location_required_without_provider_call():
    result = run_lumen_weather_tool(LumenWeatherRequest(message="今日の天気"))
    assert result.ok is False
    assert result.error == "location_required"
    assert "地域を指定" in result.message


def test_geocoding_zero_results_returns_location_not_found():
    result = run_lumen_weather_tool(
        LumenWeatherRequest(message="天気", location="Nowhere"),
        geocoding_client=EmptyGeocoder(),
        forecast_client=GoodForecaster(),
    )
    assert result.ok is False
    assert result.error == "location_not_found"


def test_forecast_failure_is_graceful_error():
    result = run_lumen_weather_tool(
        LumenWeatherRequest(message="東京の天気"),
        geocoding_client=GoodGeocoder(),
        forecast_client=FailingForecaster(),
    )
    assert result.ok is False
    assert result.error == "forecast_failed"
    assert result.location_name == "Tokyo"


def test_success_result_keeps_required_weather_fields_and_code_text():
    result = run_lumen_weather_tool(
        LumenWeatherRequest(message="東京の天気", budget={"forecast_days": 2}),
        geocoding_client=GoodGeocoder(),
        forecast_client=GoodForecaster(),
    )
    assert result.ok is True
    assert result.provider == "open_meteo"
    assert result.location_name == "Tokyo"
    assert result.country == "Japan"
    assert result.admin1 == "Tokyo"
    assert result.current_temperature == 18.5
    assert result.apparent_temperature == 17.8
    assert result.weather_code == 3
    assert result.weather_text == "曇り"
    assert result.precipitation == 0
    assert result.precipitation_probability == 30
    assert result.wind_speed == 4.2
    assert result.daily[0]["temperature_max"] == 22
    assert result.daily[0]["temperature_min"] == 14
    assert result.forecast_dates == ["2026-05-10", "2026-05-11"]
    assert result.fetched_at
    assert weather_code_to_text(61) == "雨"
    assert weather_code_to_text(None) == "不明"


def test_compress_weather_result_for_llm_is_not_raw_json():
    result = LumenWeatherResult(
        ok=True,
        location_name="Tokyo",
        country="Japan",
        latitude=35.6,
        longitude=139.6,
        timezone="Asia/Tokyo",
        current_temperature=18.5,
        weather_code=3,
        weather_text="曇り",
        daily=[{"date": "2026-05-10", "temperature_max": 22, "temperature_min": 14, "precipitation_probability": 30, "weather_text": "曇り"}],
        forecast_dates=["2026-05-10"],
        fetched_at="2026-05-10T00:00:00+00:00",
    )
    context = compress_weather_result_for_llm(result)
    assert context.startswith("[Internal Lumen Weather Context]")
    assert "Provider: Open-Meteo" in context
    assert "Current: 18.5°C" in context
    assert not context.strip().startswith("{")
    assert '"current"' not in context
    assert "Do not invent weather data" in context
