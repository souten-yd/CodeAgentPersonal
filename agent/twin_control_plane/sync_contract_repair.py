"""Generic sync-contract repair — parameterized over endpoints, not hardcoded to one.

`plan_pool_contract_repair` proved a single drift can be fixed by a templated test-input rewrite, but its
template is ONE-OFF: the URL and payload are baked in. The drift KIND, though, is generic — an endpoint
that went async (returns ``status: queued/running``) is restored to its synchronous behaviour by adding
``?sync=1`` to the POST. Several endpoints share exactly this (each has ``sync: int = Query(0)``):
``/api/atlas/plan-pools``, ``/verification/run``, ``/debug-review/run``, ``/safe-apply/execute`` … So the
repair is the SAME transform parameterized by an endpoint map; only plan-pools additionally needs a
``plan_payload`` so the pool has an item.

This rewrites ONLY the URL/body of ``.post(<url>, json={...})`` CALLS — never a URL inside an assertion
or a route-set literal (the failure mode a naive global regex hits: turning a "route X is registered"
assertion into "X?sync=1"). The caller still gates with ``assertion_preserving_edit`` and verifies by
running the test, so this is the deterministic, frontier-free path; the weak LLM is reserved for drifts
that are NOT this shape (where this transform changes nothing or fails verification).
"""
from __future__ import annotations

import re
from typing import Mapping, Optional

# Endpoints known to have gone async with a ``?sync=1`` escape hatch. Value = a plan_payload literal to
# inject into the request body (only plan-pools needs one), or None for "add ?sync=1 only".
PLAN_PAYLOAD_LITERAL = ("'plan_payload': {'implementation_steps': [{'step_id': 'step_001', "
                        "'title': 'Step', 'action_type': 'update', 'target_files': ['README.md']}]}")

DEFAULT_ASYNC_ENDPOINTS: dict[str, Optional[str]] = {
    "/api/atlas/plan-pools": PLAN_PAYLOAD_LITERAL,
    "/api/atlas/verification/run": None,
    "/api/atlas/debug-review/run": None,
    "/api/atlas/safe-apply/execute": None,
}

_POST_RE = re.compile(r"""\.post\(\s*(['"])(?P<url>[^'"]*?)\1""")


def _add_sync(url: str) -> str:
    if "sync=1" in url:
        return url
    return f"{url}{'&' if '?' in url else '?'}sync=1"


def _matching_brace(src: str, open_idx: int) -> int:
    depth, in_str, esc = 0, "", False
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


def repair_sync_contracts(src: str, endpoints: Optional[Mapping[str, Optional[str]]] = None) -> tuple[str, int]:
    """Add ``?sync=1`` (and an optional ``plan_payload``) to ``.post()`` calls whose URL matches one of
    ``endpoints``. Returns ``(new_src, n_changes)``. URLs that are NOT the first arg of a ``.post(`` call
    (assertions, route lists) are left untouched."""
    eps = dict(endpoints if endpoints is not None else DEFAULT_ASYNC_ENDPOINTS)
    changes = 0
    for m in reversed(list(_POST_RE.finditer(src))):
        url = m.group("url")
        payload = None
        matched = False
        for ep, pl in eps.items():
            if ep in url:
                matched, payload = True, pl
                break
        if not matched or "sync=1" in url:
            continue
        # optional payload injection into the json={...} body of this call
        if payload:
            jm = re.compile(r"json\s*=\s*\{").search(src, m.end())
            if jm:
                bopen = jm.end() - 1
                bclose = _matching_brace(src, bopen)
                if bclose != -1 and "plan_payload" not in src[bopen:bclose]:
                    body = src[bopen:bclose]
                    insert = payload + (", " if body[1:].strip() not in ("", "}") else "")
                    src = src[:bopen + 1] + insert + src[bopen + 1:]
        src = src[:m.start("url")] + _add_sync(url) + src[m.end("url"):]
        changes += 1
    return src, changes
