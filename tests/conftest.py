"""Shared pytest configuration for the test suite.

Registers custom markers so they don't warn. ``real_model`` marks tests that exercise a
real local/self-hosted model server (PFG-30+); they self-skip when no server is reachable.
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_model: exercises a real local/self-hosted model server; skips when unavailable",
    )
