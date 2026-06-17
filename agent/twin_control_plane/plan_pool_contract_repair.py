"""Templated test-input repair for the plan-pool async-contract drift.

`POST /api/atlas/plan-pools` intentionally went async (returns ``{pool_id, status: queued}``); tests that
still read ``response['plan_pool']['items'][0]`` raise ``KeyError: 'plan_pool'`` — the largest failure
cluster, and TEST DEBT (the API is correct). The deterministic fix is the same per call site: request the
synchronous path (``?sync=1``) and supply a ``plan_payload`` so the pool has a real item, instead of the
removed blocking-planner default.

This rewrites the test's INPUT only — the request URL and body — never an assertion. It is a pure source
transform (no model): it finds ``.post(<plan-pools url>, json={...})`` calls that lack ``sync=1`` and adds
``?sync=1`` to the URL plus a ``plan_payload`` key to the body. The caller gates each rewrite with
``assertion_preserving_edit`` and verifies by running the test (keep on pass, Git-rollback on fail), so a
call site the template does not fit is reverted, never left broken.
"""
from __future__ import annotations

import re

# One item is enough for the tests that use the pool as an opaque handle (they mutate the item via
# storage and assert on the service, not on item content); the fields cover the common item reads
# (title / action_type / target_files / step_id).
_PLAN_PAYLOAD = ("'plan_payload': {'implementation_steps': [{'step_id': 'step_001', 'title': 'Step', "
                 "'action_type': 'update', 'target_files': ['README.md']}]}")

_POST_URL_RE = re.compile(r"""\.post\(\s*(['"])(?P<url>[^'"]*plan-pools[^'"]*)\1""")


def _add_sync(url: str) -> str:
    if "sync=1" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sync=1"


def _matching_brace(src: str, open_idx: int) -> int:
    """Index just past the ``}`` matching the ``{`` at ``open_idx`` (string-aware). -1 if unbalanced."""
    depth = 0
    in_str = ""
    esc = False
    for i in range(open_idx, len(src)):
        ch = src[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = ""
            continue
        if ch in "'\"":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def repair_plan_pool_source(src: str) -> tuple[str, int]:
    """Rewrite plan-pool POST call sites to the synchronous-with-payload contract. Returns
    ``(new_src, n_changes)``; ``n_changes == 0`` means nothing matched (left unchanged)."""
    changes = 0
    # Work right-to-left so earlier insert offsets stay valid.
    for m in reversed(list(_POST_URL_RE.finditer(src))):
        url = m.group("url")
        if "sync=1" in url:
            continue
        # locate the json={...} dict that belongs to this .post( call
        json_kw = re.compile(r"json\s*=\s*\{")
        jm = json_kw.search(src, m.end())
        if not jm:
            continue
        brace_open = jm.end() - 1
        brace_close = _matching_brace(src, brace_open)
        if brace_close == -1:
            continue
        body = src[brace_open:brace_close]
        if "plan_payload" in body:
            new_url = _add_sync(url)
            src = src[:m.start("url")] + new_url + src[m.end("url"):]
            changes += 1
            continue
        # insert the plan_payload key right after the opening brace
        insert = _PLAN_PAYLOAD + (", " if body[1:].strip() not in ("", "}") else "")
        src = src[:brace_open + 1] + insert + src[brace_open + 1:]
        # then add ?sync=1 to the url (offsets before brace_open are unaffected)
        new_url = _add_sync(url)
        src = src[:m.start("url")] + new_url + src[m.end("url"):]
        changes += 1
    return src, changes
