from app.lumen.intent import extract_weather_location_hint, extract_weather_time_hint


def test_temporal_prefix_weather_questions_extract_location():
    assert extract_weather_location_hint("明日の横浜の天気予報を教えて") == "横浜"
    assert extract_weather_location_hint("今日の横浜の天気予報を教えて") == "横浜"


def test_location_first_temporal_weather_questions_extract_location():
    assert extract_weather_location_hint("横浜の明日の天気") == "横浜"
    assert extract_weather_location_hint("横浜で明日雨降る？") == "横浜"
    assert extract_weather_location_hint("横浜は今日寒い？") == "横浜"


def test_temporal_only_weather_question_keeps_location_required():
    assert extract_weather_location_hint("明日の天気") is None


def test_temporal_weather_time_hint_is_preserved():
    assert extract_weather_time_hint("今日の横浜の天気予報を教えて") == "today"
    assert extract_weather_time_hint("明日の横浜の天気予報を教えて") == "tomorrow"
    assert extract_weather_time_hint("明後日の横浜の天気予報を教えて") == "day_after_tomorrow"
    assert extract_weather_time_hint("週末の横浜の天気") == "weekend"
    assert extract_weather_time_hint("今週の横浜の天気") == "this_week"
    assert extract_weather_time_hint("来週の横浜の天気") == "next_week"
