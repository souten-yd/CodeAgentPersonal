from __future__ import annotations

from collections.abc import Callable
import inspect

from agent.types import Action, ToolResult
from agent.tools import builtin, nexus_tools

ToolCallable = Callable[[dict], ToolResult]


class ToolRegistry:
    """Action.tool 名と実行関数を結びつけるレジストリ。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolCallable] = {}

    def register(self, name: str, handler: ToolCallable) -> None:
        self._tools[name] = handler

    def get(self, name: str) -> ToolCallable | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def invoke(self, action: Action) -> ToolResult:
        handler = self.get(action.tool)
        if handler is None:
            return ToolResult(
                action_id=action.id,
                success=False,
                error=f"tool not found: {action.tool}",
            )
        return handler(action.input)


def _validate_tool_input(fn: Callable[..., dict], tool_input: dict) -> str | None:
    if not isinstance(tool_input, dict):
        return "tool input must be a dict"

    signature = inspect.signature(fn)
    try:
        signature.bind(**tool_input)
    except TypeError as exc:
        return str(exc)
    return None


def _wrap_dict_tool(name: str, fn: Callable[..., dict]) -> ToolCallable:
    def _handler(tool_input: dict) -> ToolResult:
        validation_error = _validate_tool_input(fn, tool_input)
        if validation_error:
            return ToolResult(action_id=name, success=False, error=f"invalid arguments for {name}: {validation_error}")
        try:
            result = fn(**tool_input)
            ok = bool(result.get("ok", True))
            return ToolResult(action_id=name, success=ok, output=result, error=None if ok else str(result))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(action_id=name, success=False, error=str(exc))

    return _handler


def create_default_registry() -> ToolRegistry:
    """Register built-in and Nexus tools for Agent mode."""
    registry = ToolRegistry()

    registry.register("read_file", _wrap_dict_tool("read_file", builtin.read_file))
    registry.register("write_file", _wrap_dict_tool("write_file", builtin.write_file))
    registry.register("apply_patch", _wrap_dict_tool("apply_patch", builtin.apply_patch))
    registry.register("search_code", _wrap_dict_tool("search_code", builtin.search_code))
    registry.register("run_command", _wrap_dict_tool("run_command", builtin.run_command))
    registry.register("run_tests", _wrap_dict_tool("run_tests", builtin.run_tests))
    registry.register("get_error_trace", _wrap_dict_tool("get_error_trace", builtin.get_error_trace))

    registry.register("nexus_search_library", _wrap_dict_tool("nexus_search_library", nexus_tools.nexus_search_library))
    registry.register("nexus_web_search", _wrap_dict_tool("nexus_web_search", nexus_tools.nexus_web_search))
    registry.register("nexus_build_report", _wrap_dict_tool("nexus_build_report", nexus_tools.nexus_build_report))
    registry.register(
        "nexus_build_report_legacy",
        _wrap_dict_tool("nexus_build_report_legacy", nexus_tools.nexus_build_report_legacy),
    )
    registry.register("nexus_upload_document", _wrap_dict_tool("nexus_upload_document", nexus_tools.nexus_upload_document))
    registry.register("nexus_news_scan", _wrap_dict_tool("nexus_news_scan", nexus_tools.nexus_news_scan))
    registry.register("nexus_market_research", _wrap_dict_tool("nexus_market_research", nexus_tools.nexus_market_research))
    registry.register("nexus_export_bundle", _wrap_dict_tool("nexus_export_bundle", nexus_tools.nexus_export_bundle))

    return registry
