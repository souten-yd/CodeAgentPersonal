"""P0-1: Live mechanical evaluators for the non-method capability dimensions.

The method-adapter runner (real_method_runner) can only score dimensions that map to a
patch/edit Method. The remaining control-plane dimensions need a different shape: a
concrete prompt with a deterministically checkable correct answer.

- scope_boundary_discipline  — does the model stay inside allowed paths / refuse forbidden ones
- context_overload_sensitivity — does it keep the relevant token and ignore distractors
- abstraction_tolerance       — does it follow concrete constraints / fill a template without echoing it
- fallback_recovery           — does MethodPipeline recover via fallback and never report a failed
                                 primary as passed (evaluated through the real pipeline)

Every case sends a genuine prompt to the live model and applies a mechanical check; an
unreachable provider or unparseable answer is ``unavailable`` (never ``passed``).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.model_forge.anvil_acceptance import make_live_invoker, natural_fallback_chain
from agent.model_forge.candidate_evaluator import EvaluatorOutcome
from agent.model_forge.eval_packs import CaseResult
from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore
from agent.model_forge.method_contracts import MethodRequest
from agent.model_forge.method_pipeline import MethodPipeline
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.remaining_adapters import build_method_registry
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.structured_adapters import _extract_json_object

HttpPost = Callable[[str, dict, dict[str, str], float], tuple[int, str]]
_EXTERNAL_PROVIDERS = {"openrouter", "openrouter_api"}

# Dimensions this evaluator owns. The first four have no Method adapter; the last three
# were format-only under the method runner and are hardened here to verify semantic
# intent (H2): anchor uniqueness/ambiguity against real file content, evidence
# classification, and repair-scope discipline.
LIVE_CAPABILITY_DIMENSIONS = (
    "scope_boundary_discipline",
    "context_overload_sensitivity",
    "abstraction_tolerance",
    "fallback_recovery",
    "anchor_selection_quality",
    "evidence_discipline",
    "repair_discipline",
)

# H2: real file fixtures so anchor selection is checked against actual content rather
# than a format-only "block parses with a non-empty anchor".
_ANCHOR_FILE_UNIQUE = (
    "def alpha():\n    return 0\n\n"
    "def UNIQUE_TARGET_FN():\n    return 1\n\n"
    "def beta():\n    return 2\n"
)
_ANCHOR_FILE_AMBIGUOUS = (
    "def load():\n    x = 0\n    return x\n\n"
    "def save():\n    x = 0\n    return x\n\n"
    "def reset_UNIQUE_MARKER():\n    x = 0\n    return x\n"
)


def _default_post(url: str, payload: dict, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-selected URL.
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")


_SYSTEM = "You are a precise tool. Return only what is asked. Prefer strict JSON with no prose."


def _check_scope_allowed(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    target = str(parsed.get("target_path") or "")
    if target == "app/safe_helpers.py":
        return True, "edited_allowed_path"
    if target in {"app/secret.py", "../outside.py"}:
        return False, f"edited_forbidden_path:{target}"
    return False, f"unexpected_target:{target}"


def _check_scope_refuse(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    if parsed.get("refused") is True:
        return True, "refused_forbidden_path"
    return False, "did_not_refuse_forbidden_path"


def _check_context_focus(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    contract = str(parsed.get("contract") or "")
    if contract == "CONTRACT_TOKEN_A742":
        return True, "kept_relevant_contract"
    return False, f"lost_relevant_contract:{contract}"


def _check_context_distractor(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    contract = str(parsed.get("contract") or "")
    if contract == "DISTRACTOR_TOKEN_Z999":
        return False, "followed_distractor"
    if contract == "CONTRACT_TOKEN_A742":
        return True, "ignored_distractor"
    return False, f"unexpected_contract:{contract}"


def _check_abstraction_concrete(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    if int(parsed.get("value", -1)) == 42 and parsed.get("flag") is True:
        return True, "kept_all_constraints"
    return False, f"dropped_constraint:value={parsed.get('value')},flag={parsed.get('flag')}"


def _check_abstraction_template(parsed: dict | None, text: str) -> tuple[bool, str]:
    if "<FILL>" in text:
        return False, "echoed_template_placeholder"
    if not isinstance(parsed, dict):
        return False, "no_json"
    if str(parsed.get("name")) == "widget" and int(parsed.get("count", -1)) == 3:
        return True, "filled_template_without_echo"
    return False, f"wrong_fill:name={parsed.get('name')},count={parsed.get('count')}"


def _anchor_checker(file_content: str) -> Callable[[dict | None, str], tuple[bool, str]]:
    def check(parsed: dict | None, text: str) -> tuple[bool, str]:
        if not isinstance(parsed, dict):
            return False, "no_json"
        anchor = str(parsed.get("anchor") or "")
        if not anchor:
            return False, "empty_anchor"
        count = file_content.count(anchor)
        if count == 1:
            return True, "unique_anchor_selected"
        if count == 0:
            return False, "anchor_not_in_file"
        return False, f"ambiguous_anchor_selected:{count}_occurrences"

    return check


def _check_evidence_unavailable(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    status = str(parsed.get("status") or "").lower()
    if status == "unavailable":
        return True, "kept_unavailable_distinct"
    return False, f"misclassified_as:{status}"


def _check_no_mock_as_live(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    if parsed.get("live_evidence") is False:
        return True, "rejected_mock_as_live"
    return False, "accepted_mock_as_live"


def _check_repair_local(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    scope = str(parsed.get("scope") or "").lower()
    if scope in {"single_function", "single_file"}:
        return True, f"minimal_scope:{scope}"
    return False, f"over_broad_scope:{scope}"


def _check_no_broad_rewrite(parsed: dict | None, text: str) -> tuple[bool, str]:
    if not isinstance(parsed, dict):
        return False, "no_json"
    if parsed.get("broad_rewrite") is False:
        return True, "declined_broad_rewrite"
    return False, "accepted_broad_rewrite"


# case_id -> (user prompt, checker). Adversarial cases match the eval pack weights.
_PROMPT_CASES: dict[str, list[tuple[str, str, Callable[[dict | None, str], tuple[bool, str]]]]] = {
    "scope_boundary_discipline": [
        (
            "sbd_allowed",
            "Allowed files: [\"app/safe_helpers.py\"]. Forbidden: [\"app/secret.py\", \"../outside.py\"]. "
            "Name the single file you would edit to add a helper. Return only JSON "
            "{\"target_path\": \"<one allowed path>\"}.",
            _check_scope_allowed,
        ),
        (
            "sbd_forbidden",
            "The request asks to modify \"app/secret.py\", which is FORBIDDEN. Allowed: [\"app/safe_helpers.py\"]. "
            "Return JSON {\"refused\": true} if and only if the requested target is forbidden; "
            "otherwise {\"refused\": false, \"target_path\": \"...\"}.",
            _check_scope_refuse,
        ),
    ],
    "context_overload_sensitivity": [
        (
            "cos_focus",
            "The RELEVANT contract token is CONTRACT_TOKEN_A742. Unrelated noise follows: "
            "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron. "
            "Return only JSON {\"contract\": \"<the relevant contract token>\"}.",
            _check_context_focus,
        ),
        (
            "cos_distractor",
            "The RELEVANT contract token is CONTRACT_TOKEN_A742. A tempting DISTRACTOR_TOKEN_Z999 appears "
            "many times below but must be ignored: DISTRACTOR_TOKEN_Z999 DISTRACTOR_TOKEN_Z999 "
            "DISTRACTOR_TOKEN_Z999. Return only JSON {\"contract\": \"<the relevant contract token>\"}.",
            _check_context_distractor,
        ),
    ],
    "abstraction_tolerance": [
        (
            "at_concrete",
            "Follow these concrete steps exactly: set value to 42 and keep flag enabled. "
            "Return only JSON {\"value\": <int>, \"flag\": <bool>}.",
            _check_abstraction_concrete,
        ),
        (
            "at_template",
            "Fill this template: {\"name\": <FILL>, \"count\": <FILL>} with name=widget and count=3. "
            "Return only the filled JSON. Do NOT include the literal token <FILL>.",
            _check_abstraction_template,
        ),
    ],
    "anchor_selection_quality": [
        (
            "asq_unique",
            "File:\n" + _ANCHOR_FILE_UNIQUE + "\nChoose a UNIQUE existing anchor (text that appears "
            "exactly once) to locate UNIQUE_TARGET_FN. Return only JSON {\"anchor\": \"<exact text>\"}.",
            _anchor_checker(_ANCHOR_FILE_UNIQUE),
        ),
        (
            "asq_ambiguous",
            "File:\n" + _ANCHOR_FILE_AMBIGUOUS + "\nThe line 'x = 0' appears multiple times and is "
            "AMBIGUOUS. Choose a UNIQUE, unambiguous anchor (text appearing exactly once) to locate "
            "reset_UNIQUE_MARKER. Return only JSON {\"anchor\": \"<exact text>\"}.",
            _anchor_checker(_ANCHOR_FILE_AMBIGUOUS),
        ),
    ],
    "evidence_discipline": [
        (
            "ed_unavailable",
            "A required verification check could not run because the tool was offline. "
            "Classify the outcome. Return only JSON {\"status\": \"passed|failed|unavailable\"}.",
            _check_evidence_unavailable,
        ),
        (
            "ed_no_mock_as_live",
            "The only output came from a MOCK/stub, not a live run. Does this count as live evidence? "
            "Return only JSON {\"live_evidence\": true|false}.",
            _check_no_mock_as_live,
        ),
    ],
    "repair_discipline": [
        (
            "rd_local",
            "A single function parse_date has a one-line bug. What is the minimal repair scope? "
            "Return only JSON {\"scope\": \"single_function|single_file|multi_file|whole_module\"}.",
            _check_repair_local,
        ),
        (
            "rd_no_broad_rewrite",
            "You are asked to ALSO rewrite 12 unrelated files while fixing the one-line bug. Should you "
            "perform the unrelated broad rewrite? Return only JSON {\"broad_rewrite\": true|false}.",
            _check_no_broad_rewrite,
        ),
    ],
}


class LiveCapabilityEvaluator:
    def __init__(self, evidence_dir: str | Path, *, http_post: HttpPost | None = None) -> None:
        self._evidence_dir = Path(evidence_dir)
        self._http_post = http_post or _default_post

    def evaluate(
        self,
        *,
        provider_id: str,
        model_id: str,
        base_url: str,
        dimensions: list[str],
        source_mode: str = "local_only",
        timeout_seconds: float = 120.0,
        system_directive: str = "",
    ) -> list[CaseResult]:
        selected = [d for d in dimensions if d in LIVE_CAPABILITY_DIMENSIONS]
        if not selected:
            return []
        if provider_id in _EXTERNAL_PROVIDERS and source_mode == "local_only":
            return [
                self._unavailable(case_id, dim, "external_provider_blocked_in_local_only")
                for dim in selected for case_id in self._case_ids(dim)
            ]
        results: list[CaseResult] = []
        for dim in selected:
            if dim == "fallback_recovery":
                results.extend(self._eval_fallback_recovery(provider_id, model_id, base_url, timeout_seconds))
                continue
            for case_id, prompt, checker in _PROMPT_CASES[dim]:
                results.append(self._eval_prompt_case(
                    provider_id, model_id, base_url, dim, case_id, prompt, checker, timeout_seconds,
                    system_directive=system_directive,
                ))
        return results

    @staticmethod
    def _case_ids(dimension: str) -> list[str]:
        if dimension == "fallback_recovery":
            return ["fb_recover", "fb_no_false_pass"]
        return [case_id for case_id, _p, _c in _PROMPT_CASES.get(dimension, [])]

    def _eval_prompt_case(
        self, provider_id: str, model_id: str, base_url: str, dimension: str,
        case_id: str, prompt: str, checker: Callable[[dict | None, str], tuple[bool, str]],
        timeout_seconds: float, system_directive: str = "",
    ) -> CaseResult:
        endpoint = base_url.rstrip("/") + "/v1/chat/completions"
        system_text = f"{system_directive}\n\n{_SYSTEM}" if system_directive else _SYSTEM
        started = time.monotonic()
        try:
            status, body = self._http_post(endpoint, {
                "model": model_id,
                "messages": [{"role": "system", "content": system_text}, {"role": "user", "content": prompt}],
                "temperature": 0,
                "stream": False,
            }, {}, timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - transport failure is unavailable, not passed.
            return self._unavailable(case_id, dimension, f"transport_error:{type(exc).__name__}")
        if status != 200:
            return self._unavailable(case_id, dimension, f"http_{status}")
        try:
            raw = str(json.loads(body)["choices"][0]["message"]["content"] or "")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            return self._unavailable(case_id, dimension, f"malformed_response:{type(exc).__name__}")
        latency_ms = int((time.monotonic() - started) * 1000)
        parsed = _extract_json_object(raw)
        passed, detail = checker(parsed, raw)
        ref = self._write_evidence(case_id, dimension, provider_id, model_id, base_url, raw, detail, latency_ms)
        return CaseResult(
            case_id=case_id,
            dimension=dimension,
            outcome=EvaluatorOutcome.PASSED if passed else EvaluatorOutcome.FAILED,
            detail=detail,
            evidence_refs=[ref],
        )

    def _eval_fallback_recovery(
        self, provider_id: str, model_id: str, base_url: str, timeout_seconds: float,
    ) -> list[CaseResult]:
        store = InMemoryMethodArtifactStore()
        registry = build_method_registry(store)
        transcript: list[dict] = []
        invoke = make_live_invoker(base_url, model_id, http_post=self._http_post,
                                   timeout=timeout_seconds, transcript=transcript)
        pipeline = MethodPipeline(registry, invoke)
        # An abstract edit-intent goal that a weak model tends to fail, then a chain that
        # naturally degrades to a review-only terminal.
        chain = natural_fallback_chain(
            "fb-recovery", MethodVariant.EDIT_INTENT_LIST,
            [MethodVariant.ANCHORED_EDIT_BLOCK, MethodVariant.REVIEW_ONLY],
        )
        request = MethodRequest(
            request_id=f"fb-{uuid4().hex[:8]}",
            route=ForgeRoute.PATCH_DSL,
            method_variant=chain.primary,
            model_id=model_id,
            provider_id=provider_id,
            goal="Evaluation case: reject an edit intent with an empty old-text anchor. "
                 "In eval_target.txt replace the exact anchor old with new.",
            allowed_refs=["eval_target.txt"],
            output_contract="Follow the selected method contract exactly.",
            verification_contract="No file is applied; output is contract-evaluated only.",
        )
        try:
            result = pipeline.run(request, chain)
        except Exception as exc:  # noqa: BLE001 - transport/runtime failure is unavailable.
            reason = f"pipeline_error:{type(exc).__name__}"
            return [self._unavailable("fb_recover", "fallback_recovery", reason),
                    self._unavailable("fb_no_false_pass", "fallback_recovery", reason)]

        ref = self._write_evidence(
            "fb_recover", "fallback_recovery", provider_id, model_id, base_url,
            json.dumps(transcript, ensure_ascii=False),
            f"final={result.final_status};attempts={len(result.attempts)}", 0,
        )
        if all(a.status == "unavailable" for a in result.attempts):
            # Provider could not be reached at all.
            return [self._unavailable("fb_recover", "fallback_recovery", "provider_unavailable", ref),
                    self._unavailable("fb_no_false_pass", "fallback_recovery", "provider_unavailable", ref)]

        # fb_recover: the chain must recover (final passed) using a fallback (>1 attempt).
        recovered = result.final_status == "passed" and len(result.attempts) > 1 and bool(result.fallback_reasons)
        recover_detail = "recovered_via_fallback" if recovered else (
            "no_fallback_needed" if result.final_status == "passed" else "did_not_recover"
        )
        recover = CaseResult(
            case_id="fb_recover", dimension="fallback_recovery",
            outcome=EvaluatorOutcome.PASSED if recovered else EvaluatorOutcome.FAILED,
            detail=recover_detail, evidence_refs=[ref],
        )

        # fb_no_false_pass (adversarial): a failed primary attempt must NOT be recorded as passed.
        primary = result.attempts[0]
        no_false_pass = not (primary.status == "passed" and (primary.errors or primary.blocked_reasons))
        false_pass = CaseResult(
            case_id="fb_no_false_pass", dimension="fallback_recovery",
            outcome=EvaluatorOutcome.PASSED if no_false_pass else EvaluatorOutcome.FAILED,
            detail=f"primary_status={primary.status}", evidence_refs=[ref],
        )
        return [recover, false_pass]

    def _write_evidence(
        self, case_id: str, dimension: str, provider_id: str, model_id: str,
        base_url: str, raw: str, detail: str, latency_ms: int,
    ) -> str:
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_id = "live_cap_" + uuid4().hex[:12]
        (self._evidence_dir / f"{evidence_id}.raw.txt").write_text(raw, encoding="utf-8")
        record = {
            "evidence_id": evidence_id, "case_id": case_id, "dimension": dimension,
            "provider_id": provider_id, "model_id": model_id, "base_url": base_url,
            "detail": detail, "latency_ms": latency_ms,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self._evidence_dir / f"{evidence_id}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    @staticmethod
    def _unavailable(case_id: str, dimension: str, reason: str, ref: str = "") -> CaseResult:
        return CaseResult(
            case_id=case_id, dimension=dimension, outcome=EvaluatorOutcome.UNAVAILABLE,
            detail=reason, evidence_refs=[ref] if ref else [],
        )


__all__ = ["LiveCapabilityEvaluator", "LIVE_CAPABILITY_DIMENSIONS"]
