# Lumen Design

## Responsibility

Lumen is the lightweight conversation surface for CodeAgent. Its job is normal chat plus optional one-shot lightweight web assist. It is not an autonomous executor and it is not the Deep Research system.

## Lumen owns

- Normal chat.
- Conversation continuation with `chat_history`.
- Optional lightweight Web search.
- Explicit limits for Web query count, results per query, fetched pages, total fetched characters, timeout, and LLM chat/web-assist steps.
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

## Web search policy

Lumen Web policy is explicit:

- `off`: do not perform Web search.
- `auto`: perform lightweight search only when the prompt appears to need current external information.
- `on`: perform lightweight search within the Lumen budget.

The legacy `search_enabled` compatibility field is interpreted before `search_policy`:

- `search_enabled == false` maps to `search_policy = "off"`.
- `search_enabled == true` maps to `search_policy = "on"`.
- `search_enabled is None` leaves `search_policy` in control; the default is `"auto"`.

## Web search budget

`LumenSearchBudget` is clamped at submit/execution boundaries:

| Field | Default | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| `max_queries` | 3 | 0 | 5 |
| `max_results_per_query` | 5 | 1 | 10 |
| `max_fetch_pages` | 3 | 0 | 5 |
| `max_total_chars` | 12000 | 2000 | 30000 |
| `timeout_sec` | 20 | 5 | 60 |

Lumen `max_steps` defaults to 8 and clamps to 1-20. In Lumen this is a chat/web-assist event budget, not an agent task-step budget.

## Nexus Deep Research separation

Lumen uses one-shot lightweight web assist only; recursive depth = 0. Lumen does not own recursive research. Nexus owns Deep Research, Recursive Research, report generation, knowledge inspection, and document accumulation. If a Lumen prompt looks like a long-running investigation, Lumen may say: “This question may require long-running research. Nexus Deep Research can perform multiple searches and report generation.” Lumen must not automatically start a Nexus job.

## Atlas / Agent separation

Atlas / Agent owns autonomous execution, file edits, code execution, and multi-step agent pipelines. Lumen must not run shell commands, edit files, execute code, approve task plans, or operate the old task runner.

## Legacy task mode removed

`/jobs/submit` is now a Lumen chat-only submit path. `mode` aliases `chat`, `lumen`, and `conversation` normalize to `chat`; `task`, `agent_task`, and `legacy_task` are rejected with `legacy_task_mode_removed` before a job is created or a background thread starts.

## Preventing JSON options leakage

The removed task-mode branch previously mixed planning, retries, and options fallback into `/jobs/submit`, which allowed task-planning text such as 「JSON形式で出力」 to leak into Lumen chats. Lumen background execution now calls only `execute_chat_with_optional_web_search`; the service must not contain `options_prompt`, task retry stages, or `approved_tasks` execution paths.
