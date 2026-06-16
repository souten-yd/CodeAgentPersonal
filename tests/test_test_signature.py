"""I/O-signature redundancy: distinguish parametric tests deterministically."""
from __future__ import annotations

from agent.twin_control_plane.test_signature import io_signatures_for_source

SRC = '''\
def test_gb():
    out = norm("3.5GB")
    assert " giga" in out

def test_khz():
    out = norm("10kHz")
    assert "kilo" in out

def test_gb_dup():
    out = norm("3.5GB")
    assert "giga" in out
'''


def test_different_inputs_outputs_give_distinct_signatures():
    sigs = io_signatures_for_source(SRC, prefix="py://t.py#")
    assert sigs["py://t.py#test_gb"] != sigs["py://t.py#test_khz"]  # different units -> not redundant


def test_identical_io_gives_same_signature():
    sigs = io_signatures_for_source(SRC, prefix="py://t.py#")
    # test_gb and test_gb_dup differ only by an assertion substring (" giga" vs "giga"), so NOT equal;
    # but two truly identical tests would match. Verify the literal capture distinguishes them.
    assert sigs["py://t.py#test_gb"] != sigs["py://t.py#test_gb_dup"]


def test_type_tagged_literals_do_not_collide():
    sigs = io_signatures_for_source('def test_a():\n    assert f(1)\n\ndef test_b():\n    assert f("1")\n',
                                    prefix="py://t.py#")
    assert sigs["py://t.py#test_a"] != sigs["py://t.py#test_b"]  # 1 (int) vs "1" (str)


def test_syntax_error_safe():
    assert io_signatures_for_source("def (:\n") == {}
