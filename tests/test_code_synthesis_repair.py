"""Tests for weak-LLM code synthesis repair (stubbed LLM — no real model)."""
from __future__ import annotations

from agent.twin_control_plane.code_synthesis_repair import (
    extract_function, repair_file_with_synthesis, replace_function, synthesize_function_fix,
)

_SRC = (
    "import os\n"
    "\n"
    "def add(a, b):\n"
    "    return a - b\n"          # the bug
    "\n"
    "def other():\n"
    "    return 1\n"
)


def test_extract_function_span():
    span = extract_function(_SRC, "add")
    assert span is not None and span.name == "add"
    assert "return a - b" in span.text and "def add" in span.text


def test_replace_function_keeps_rest_and_parses():
    new = replace_function(_SRC, "add", "def add(a, b):\n    return a + b\n")
    assert new is not None
    assert "return a + b" in new
    assert "def other():" in new and "import os" in new      # rest untouched
    assert extract_function(new, "other") is not None


def test_replace_rejects_unparseable():
    assert replace_function(_SRC, "add", "def add(a, b):\n    return a +") is None


def test_replace_rejects_wrong_function_name():
    assert replace_function(_SRC, "add", "def renamed(a, b):\n    return a + b\n") is None


def test_synthesize_accepts_valid_single_function():
    def llm(system, user):
        return {"function": "def add(a, b):\n    return a + b\n"}

    out = synthesize_function_fix(llm, func_text="def add(a, b):\n    return a - b\n",
                                  func_name="add", failure_reason="assert 5 == 5")
    assert out is not None and "a + b" in out


def test_synthesize_rejects_extra_functions_or_rename():
    def llm_two(system, user):
        return {"function": "def add(a, b):\n    return a + b\ndef sneaky():\n    pass\n"}

    assert synthesize_function_fix(llm_two, func_text="x", func_name="add", failure_reason="") is None

    def llm_rename(system, user):
        return {"function": "def nope(a, b):\n    return a + b\n"}

    assert synthesize_function_fix(llm_rename, func_text="x", func_name="add", failure_reason="") is None


def test_synthesize_handles_bad_model_output():
    assert synthesize_function_fix(lambda s, u: {"function": "not python ::"},
                                   func_text="x", func_name="add", failure_reason="") is None
    assert synthesize_function_fix(lambda s, u: None, func_text="x", func_name="add",
                                   failure_reason="") is None


def test_repair_file_end_to_end_with_stub():
    def llm(system, user):
        return {"function": "def add(a, b):\n    return a + b\n"}

    new = repair_file_with_synthesis(file_source=_SRC, func_name="add",
                                     failure_reason="assert add(2,3) == 5", test_text="assert add(2,3)==5",
                                     llm_json_fn=llm)
    assert new is not None and "return a + b" in new


def test_repair_file_noop_when_model_returns_same():
    def llm(system, user):
        return {"function": "def add(a, b):\n    return a - b\n"}      # unchanged

    new = repair_file_with_synthesis(file_source=_SRC, func_name="add", failure_reason="x",
                                     test_text="x", llm_json_fn=llm)
    assert new is None                                                  # no change proposed
