"""_get_read_file_inject_max_chars used to be a user-tunable setting (default 16000 chars,
manually adjustable in the settings modal). That static default silently over-truncated large
read_file results on big-context models even when plenty of context room was free -- the settings
modal item was removed (it wasn't generically usable: right for a small local model, wrong for a
large-context one). It now scales with the model's actual active context window instead.
"""
import main


def test_scales_up_for_large_context_models(monkeypatch):
    monkeypatch.setattr(main, "_current_n_ctx", 131072)
    assert main._get_read_file_inject_max_chars() == 65536


def test_floor_matches_prior_default_for_small_context_models(monkeypatch):
    monkeypatch.setattr(main, "_current_n_ctx", 8192)
    assert main._get_read_file_inject_max_chars() == 16000


def test_ceiling_is_never_exceeded(monkeypatch):
    monkeypatch.setattr(main, "_current_n_ctx", 1_000_000)
    assert main._get_read_file_inject_max_chars() == 120000


def test_read_file_inject_max_chars_is_no_longer_a_settable_field():
    assert "read_file_inject_max_chars" not in main.SETTINGS_DEFAULTS
