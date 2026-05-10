from app.lumen.intent import extract_weather_location_hint, extract_weather_time_hint


def test_temporal_weather_location_patterns_are_extracted():
    assert extract_weather_location_hint("明日の横浜の天気") == "横浜"
    assert extract_weather_location_hint("今日の横浜の天気") == "横浜"
    assert extract_weather_location_hint("横浜の明日の天気") == "横浜"
    assert extract_weather_location_hint("明日の天気") is None


def test_weather_time_hint_extracts_tomorrow():
    assert extract_weather_time_hint("明日の横浜の天気") == "tomorrow"
