"""Tests for the causal verification gate — reject spurious passes (the #1933 class)."""
from __future__ import annotations

from agent.twin_control_plane.causal_verification import cause_symbols, verify_causal


def test_cause_symbols_extraction():
    assert "threading" in cause_symbols("NameError: name 'threading' is not defined")
    assert "echo_list" in cause_symbols("AttributeError: module 'main' has no attribute 'echo_list'")
    assert "plan_pool" in cause_symbols("KeyError: 'plan_pool'")
    assert cause_symbols("AssertionError: assert 8 == 9") == set()      # value mismatch -> no symbol


def test_regression_1933_spurious_fix_is_rejected():
    # the exact #1933 case: NameError about `threading`, but the patch edits an unrelated function.
    old = "def normalize_action_type(value):\n    if value in {'write', 'add'}:\n        return 'create'\n    return ''\n"
    new = ("def normalize_action_type(value):\n    if value in {'write', 'add'}:\n        return 'create'\n"
           "    if value in {'apply'}:\n        return 'update'\n    return ''\n")
    v = verify_causal(old, new, "NameError: name 'threading' is not defined",
                      target_func="normalize_action_type", localized_func="normalize_action_type")
    assert v.causal is False
    assert "threading" in v.cause_symbols and not v.matched


def test_rejects_symbol_mentioned_only_as_string_or_comment():
    # the weak LLM tried to game the gate by writing the symbol as a STRING, not real code.
    old = "def normalize(value):\n    return ''\n"
    gamed = ("def normalize(value):\n    # handle the threading NameError\n"
             "    if value == 'threading':\n        return 'run_command'\n    return ''\n")
    v = verify_causal(old, gamed, "NameError: name 'threading' is not defined", target_func="normalize")
    assert v.causal is False                       # "threading" only appears as a string/comment


def test_genuine_fix_referencing_the_symbol_is_causal():
    old = "def run():\n    threading.Thread(target=f).start()\n"
    new = "import threading\n\ndef run():\n    threading.Thread(target=f).start()\n"
    v = verify_causal(old, new, "NameError: name 'threading' is not defined", target_func="run")
    assert v.causal is True and "threading" in v.matched


def test_keyerror_fix_must_touch_the_key():
    old = "def pick(d):\n    return d['planpool']\n"
    good = "def pick(d):\n    return d['plan_pool']\n"
    bad = "def pick(d):\n    return d.get('x')\n"
    assert verify_causal(old, good, "KeyError: 'plan_pool'", target_func="pick").causal is True
    assert verify_causal(old, bad, "KeyError: 'plan_pool'", target_func="pick").causal is False


def test_abstains_on_value_mismatch():
    # no named symbol -> the gate cannot key on anything; it abstains (defers to the test/related bundle)
    old = "def add(a, b):\n    return a - b\n"
    new = "def add(a, b):\n    return a + b\n"
    assert verify_causal(old, new, "AssertionError: assert 5 == 5", target_func="add").causal is True


def test_rejects_when_target_differs_from_localized():
    v = verify_causal("x", "y", "KeyError: 'k'", target_func="foo", localized_func="bar")
    assert v.causal is False and "differs" in v.reason
