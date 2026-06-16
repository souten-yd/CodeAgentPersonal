"""Shared time helpers.

Consolidates ``_utc_now_iso`` — an identical one-line UTC-timestamp helper that the full-suite triage
found reimplemented in ~32 modules (see docs/full_suite_triage_report_2026-06-17.md). A single source
removes the copies; callers import it under the same private name so call sites are unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
