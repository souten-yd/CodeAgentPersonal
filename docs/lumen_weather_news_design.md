# Lumen Weather / News Design

## PR4.68b scope

PR4.68b is weather-only. It adds a no-key Open-Meteo weather tool for Lumen and does not implement news, RSS, GDELT, SearXNG news connectors, `app/api/lumen.py` route splitting, or UI splitting. Lumen remains chat-only: the weather tool provides context for a natural-language chat answer, not task execution.

## Weather provider

- Provider: Open-Meteo.
- Geocoding: Open-Meteo geocoding endpoint resolves explicit location text.
- Forecast: Open-Meteo forecast endpoint fetches bounded current, hourly precipitation probability, and daily forecast fields.
- API keys: none required and no API-key setting is introduced.

## Location handling

Lumen must not ask the LLM to guess a missing weather location. `request.location` has priority. If it is absent, Lumen may use a lightweight location hint from the message such as `東京の天気`, `大阪 明日の天気`, or `札幌は雨？`. If no location is available, the tool returns `location_required` with a user-facing request to specify a region.

## Budgets and timeouts

`LumenWeatherBudget` limits provider work. `max_geocoding_results` limits geocoding candidates, `forecast_days` is clamped to 1..7, and `timeout_sec` is clamped to 5..30 seconds. These limits are applied at submit and execution boundaries.

## LLM context policy

The LLM receives compressed weather context, not raw provider JSON. The context includes provider, location, current weather, daily forecast summaries, fetched time, and an explicit instruction to avoid inventing weather data beyond the provided context. Job events keep a structured `tool_result` for observability.

## Failure policy

Provider failures are graceful. Geocoding misses return `location_not_found`; forecast/network failures return an error result. Failure contexts tell the LLM to answer that the weather could not be obtained, or to ask for a region when required, rather than fabricating weather.

## Later PRs

News is deferred to PR4.68c or later. That later work may add no-key multi-source news connectors shared by Lumen and Nexus, but PR4.68b intentionally avoids RSS fetching, GDELT, SearXNG news providers, and automatic Nexus Deep Research handoff. `app/api/lumen.py` remains PR4.68d and UI splitting remains PR4.68e.
