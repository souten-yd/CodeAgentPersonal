# Lumen Design

## Responsibility

Lumen is CodeAgent's lightweight conversation surface. Its stable core is normal chat plus a future path for small, bounded, no-key tools such as weather, news, and one-shot Web assistance. In PR4.68b, Lumen remains chat-only for user-facing behavior while adding a bounded no-key weather tool: it may call Open-Meteo for weather context, but it still does not run legacy tasks, news connectors, recursive research, or autonomous execution.

## Lumen owns

- Normal chat through `/jobs/submit` while the route remains the Lumen-compatible submit endpoint.
- Conversation continuation with `chat_history`.
- Request parsing and clamping for lightweight search, weather, and news budgets.
- `tool_policy` and `search_policy` normalization to `off` / `auto` / `on`.
- Lightweight intent detection for `chat`, `weather`, `news`, `web`, and `nexus_deep_research_suggestion`.
- A tool plan that can execute only the bounded Open-Meteo weather tool; news/Web entries remain planned-only.
- Clear user-facing errors when the LLM is not ready or Web search is unavailable.
- A text-only handoff suggestion when a question is better suited to Nexus Deep Research.

## Lumen does not own

- Legacy task mode.
- `approved_tasks` execution.
- Plan-to-task execution.
- Retry stage 1/2/3 orchestration.
- Options JSON fallback.
- `auto_select_option`.
- File editing, shell execution, code-agent execution, or Playwright repair loops.
- Model-switching orchestration.
- Deep Research itself.
- Recursive Research itself.
- News connectors, GDELT, RSS fetches, SearXNG news fetches, API route splitting to `app/api/lumen.py`, and UI splitting in PR4.68b.

## Legacy task mode removed

`/jobs/submit` is now a Lumen chat-only submit path. `mode` aliases `chat`, `lumen`, and `conversation` normalize to `chat`; missing and empty modes also normalize to `chat`. Removed modes `task`, `agent_task`, and `legacy_task` are rejected with `legacy_task_mode_removed` before a job is created or a background thread starts. Unknown modes are rejected as invalid Lumen modes rather than being silently converted to chat.

## Tool and search policy

Lumen tool policy is explicit:

- `off`: do not plan or run lightweight tools.
- `auto`: allow Lumen to plan a future lightweight tool when intent detection indicates it.
- `on`: force-enable future lightweight tool planning within the Lumen budget.

Lumen search policy uses the same values:

- `off`: do not perform Web search.
- `auto`: perform lightweight search only when the prompt appears to need current external information.
- `on`: perform lightweight search within the Lumen budget.

Invalid policy values are normalized to `auto`. The legacy `search_enabled` compatibility field is interpreted before `search_policy`:

- `search_enabled == false` maps to `search_policy = "off"`.
- `search_enabled == true` maps to `search_policy = "on"`.
- `search_enabled is None` leaves `search_policy` in control; the default is `"auto"`.

## Lightweight budgets

`LumenSearchBudget` is clamped at submit/execution boundaries:

| Field | Default | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| `max_queries` | 3 | 0 | 5 |
| `max_results_per_query` | 5 | 1 | 10 |
| `max_fetch_pages` | 3 | 0 | 5 |
| `max_total_chars` | 12000 | 2000 | 30000 |
| `timeout_sec` | 20 | 5 | 60 |

`LumenWeatherBudget` bounds the no-key Open-Meteo weather tool and is clamped as follows:

| Field | Default | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| `max_geocoding_results` | 3 | 1 | 5 |
| `forecast_days` | 3 | 1 | 7 |
| `timeout_sec` | 10 | 5 | 30 |

`LumenNewsBudget` is reserved for future no-key news providers and is clamped as follows:

| Field | Default | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| `max_providers` | 3 | 1 | 5 |
| `max_queries` | 2 | 1 | 5 |
| `max_results_per_provider` | 5 | 1 | 10 |
| `max_total_items` | 15 | 3 | 30 |
| `max_fetch_pages` | 0 | 0 | 3 |
| `timeout_sec` | 20 | 5 | 60 |
| `save_to_nexus` | false | n/a | n/a |

Lumen `max_steps` defaults to 8 and clamps to 1-20. In Lumen this is a chat/web-assist event budget, not an agent task-step budget. Lumen has recursive depth = 0.

## Weather/news/web tools

PR4.68b adds the weather-only Open-Meteo tool. The tool uses Open-Meteo geocoding and forecast endpoints without API keys, stores a `tool_result` event, compresses the weather result before LLM injection, and instructs the model not to invent weather data. If neither `request.location` nor a lightweight message location hint is available, the tool returns `location_required` and asks the user to specify a region instead of guessing. News connectors, RSS, GDELT, SearXNG news providers, and route/UI splits are intentionally not implemented in this PR.

## Nexus Deep Research separation

Lumen uses one-shot lightweight web assist only; recursive depth = 0. Lumen does not own recursive research. Nexus owns Deep Research, Recursive Research, report generation, knowledge inspection, and document accumulation. If a Lumen prompt looks like a long-running investigation, Lumen may say: “This question may require long-running research. Nexus Deep Research can perform multiple searches and report generation.” Lumen must not automatically start a Nexus job and must not mix Nexus Deep Research controls into Lumen budgets.

## Atlas / Agent separation

Atlas / Agent owns autonomous execution, file edits, code execution, and multi-step agent pipelines. Lumen must not run shell commands, edit files, execute code, approve task plans, or operate the old task runner. Removing legacy task mode from `/jobs/submit` does not remove Atlas/Agent routes or Nexus routes.

## API / service / domain / UI split plan

- PR4.68a: keep `/jobs/submit` in `app/api/jobs.py` as the temporary Lumen chat-compatible endpoint, with Lumen domain primitives in `app/lumen/`.
- PR4.68b: add the no-key Open-Meteo weather tool while keeping Lumen chat-only, legacy task mode rejected, and news/API/UI splits unimplemented.
- PR4.68d: move Lumen route ownership to `app/api/lumen.py` after the chat-only contract is stable.
- PR4.68e: split the UI after route/service/domain boundaries are stable.
- Service code must continue to call only `execute_chat_with_optional_web_search` for Lumen response generation.

## Preventing JSON options leakage

The removed task-mode branch previously mixed planning, retries, and options fallback into `/jobs/submit`, which allowed task-planning text such as 「JSON形式で出力」 to leak into Lumen chats. Lumen background execution now calls only `execute_chat_with_optional_web_search`; the service must not contain `options_prompt`, task retry stages, or `approved_tasks` execution paths. Contract tests scan `app/services/jobs.py` for these forbidden strings to prevent recurrence of “指定のJSON形式で出力します” and options JSON leakage.
