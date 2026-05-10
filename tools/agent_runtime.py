from __future__ import annotations

import inspect
from collections import Counter
from collections.abc import Callable
from typing import Any


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _call(func: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> Any:
    if not callable(func):
        return None
    return await _maybe_await(func(*args, **kwargs))


def _action_type(action: Any) -> str:
    if isinstance(action, dict):
        action_type = action.get("type")
        return str(action_type) if action_type is not None else "unknown"
    action_type = getattr(action, "type", None)
    return str(action_type) if action_type is not None else "unknown"


def is_dangerous(action: Any) -> bool:
    """Default danger check. Treat explicit dangerous flags as unsafe."""
    if isinstance(action, dict):
        return bool(action.get("dangerous") or action.get("is_dangerous"))
    return bool(getattr(action, "dangerous", False) or getattr(action, "is_dangerous", False))


async def agent_loop(state: Any) -> None:
    """Run async agent loop with fixed pipeline and safety stops.

    Required order:
    buildContext -> planner -> selectAction -> tool/llm execute -> evaluator -> memoryUpdate
    """
    setattr(state, "running", True)
    if not hasattr(state, "loopCount"):
        setattr(state, "loopCount", 0)
    if not hasattr(state, "lastActions") or getattr(state, "lastActions") is None:
        setattr(state, "lastActions", [])

    try:
        while bool(getattr(state, "running", False)):
            # Safety 1: loop upper bound.
            state.loopCount += 1
            if state.loopCount > 50:
                break

            # 1) buildContext
            context = await _call(getattr(state, "buildContext", None), state)

            # 2) planner
            plan = await _call(getattr(state, "planner", None), context, state)

            # 3) selectAction
            action = await _call(getattr(state, "selectAction", None), plan, context, state)
            if action is None:
                break

            action_type = _action_type(action)
            state.lastActions.append(action_type)
            if len(state.lastActions) > 5:
                state.lastActions = state.lastActions[-5:]

            # Safety 2: repeated same action type.
            if Counter(state.lastActions)[action_type] >= 3:
                break

            # Safety 3: pre-execution danger check.
            danger_checker = getattr(state, "is_dangerous", None)
            dangerous = await _call(danger_checker, action)
            if dangerous is None:
                dangerous = is_dangerous(action)
            if dangerous:
                break

            # 4) tool/llm execute
            execute_fn: Callable[..., Any] | None = getattr(state, "execute", None)
            if execute_fn is None:
                if action_type == "tool":
                    execute_fn = getattr(state, "tool_execute", None)
                else:
                    execute_fn = getattr(state, "llm_execute", None)
            execution_result = await _call(execute_fn, action, context, state)

            # 5) evaluator
            evaluation = await _call(getattr(state, "evaluator", None), execution_result, action, plan, context, state)

            # 6) memoryUpdate
            await _call(getattr(state, "memoryUpdate", None), evaluation, execution_result, action, plan, context, state)

            if isinstance(evaluation, dict) and evaluation.get("done"):
                break
            if getattr(evaluation, "done", False):
                break
    finally:
        # Keep state consistent even on exceptions.
        setattr(state, "running", False)
