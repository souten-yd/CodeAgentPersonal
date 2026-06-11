from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest, AtlasAutoVerificationResult
from agent.atlas_playwright_smoke_verifier import AtlasPlaywrightSmokeVerifier
from agent.atlas_requirement_tracer import AtlasRequirementTracer
from agent.atlas_task_verification_contracts import evaluate_expected_signals, select_task_verification_contract
from agent.atlas_verification_allowlist import atlas_verification_allowlist
from agent.atlas_visual_artifact_verifier import AtlasVisualArtifactVerifier
from agent.atlas_visual_contract_registry import VisualContract, VisualContractRegistry
from agent.atlas_visual_failure_taxonomy import failures_from_missing_signals
from agent.atlas_visual_requirement_normalizer import VisualRequirementNormalizer
from agent.atlas_visual_task_classifier import VisualTaskClassifier
from agent.test_command_runner_schema import AtlasTestCommandRequest
from agent.project_intelligence.adapters.atlas_verification import AtlasVerificationBridge
from agent.project_intelligence.verification_integration import record_project_intelligence_verification

_normalizer = VisualRequirementNormalizer()
_classifier = VisualTaskClassifier()
_registry = VisualContractRegistry()

# Keywords in goal/done_definition/root_goal that mark a visual artifact task.
_VISUAL_KEYWORDS = (
    "animat", "wave", "oscillat", "canvas", "game", "visual", "render", "draw",
    "hue", "color", "button", "webpage", "web page", "html page", "css style",
    "frontend", "ui ", "layout", "screen",
)

# Browser-smoke failure reasons that are HARD (real defects) vs SOFT (style-sampling /
# environment) which only warn when the static contract already passes.
_HARD_SMOKE_REASONS = ("js_error", "expected_text_missing", "html_file_missing")


class AtlasAutoVerificationService:
    def __init__(
        self,
        *,
        journal,
        storage,
        command_runner,
        visual_verifier=None,
        playwright_verifier=None,
        project_intelligence=None,
        verification_bridge: AtlasVerificationBridge | None = None,
    ):
        self.journal = journal
        self.storage = storage
        self.command_runner = command_runner
        self.visual_verifier = visual_verifier or AtlasVisualArtifactVerifier()
        self.playwright_verifier = playwright_verifier or AtlasPlaywrightSmokeVerifier()
        self.project_intelligence = project_intelligence
        self.verification_bridge = verification_bridge or AtlasVerificationBridge()

    def run_after_auto_safe_apply(self, request: AtlasAutoVerificationRequest) -> AtlasAutoVerificationResult:
        pool = self.storage.load_pool(request.pool_id)
        item = pool.get_item(request.item_id)
        if item is None:
            return AtlasAutoVerificationResult(pool_id=request.pool_id, item_id=request.item_id, run_id=request.run_id, preset_id=request.preset_id, status="blocked", warnings=["item_not_found"], plan_pool=pool.model_dump())
        task_contract = select_task_verification_contract(item, pool)
        self._persist_task_contract(pool, item, task_contract, status="selected")
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        safe_apply_meta = ((item.metadata or {}).get("safe_apply") or {})
        safe = safe_apply_meta.get("status")
        auto_safe = ((item.metadata or {}).get("auto_safe_apply") or {}).get("status")
        if str(safe or "").lower() != "applied" and str(auto_safe or "").lower() != "applied":
            explanation = self._safe_apply_explanation(safe_apply_meta)
            return AtlasAutoVerificationResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, preset_id=request.preset_id, status="skipped", warnings=["safe_apply_not_applied", *list(explanation.get("reasons") or [])], metadata={"safe_apply_not_applied": explanation}, plan_pool=pool.model_dump(), orchestration_summary={"safe_apply_not_applied": explanation})

        workspace_root = str(getattr(pool, "project_path", "") or "").strip()
        if not workspace_root:
            return self._blocked(pool, item.item_id, request, "project_path_missing")

        self._append_event(pool.pool_id, request.run_id, "auto_verification_started", item.item_id, status="started")
        allowlist = atlas_verification_allowlist()
        if request.metadata.get("command"):
            return self._blocked(pool, item.item_id, request, "arbitrary_command_forbidden")
        command_id = request.command_id or str(((item.metadata or {}).get("verification") or {}).get("command_id") or "")
        if not command_id:
            # No allowlisted test command. For visual HTML artifacts, run the static visual
            # contract (and optional Playwright smoke) instead of reporting "nothing to verify"
            # — file existence alone must never pass a visual task.
            html_rel = self._resolve_visual_html(item, pool)
            if html_rel and self._safe_rel(html_rel):
                return self._run_visual_verification(pool, item, request, workspace_root, html_rel)
            return self._blocked(pool, item.item_id, request, "verification_command_missing")
        if command_id not in allowlist or not allowlist[command_id].allowed:
            return self._blocked(pool, item.item_id, request, "verification_command_not_allowlisted")
        spec = allowlist[command_id]

        command = []
        for tok in spec.command:
            if tok == "{test_path}":
                v = str(request.metadata.get("test_path") or ((item.metadata or {}).get("verification") or {}).get("test_path") or "")
                if not self._safe_rel(v):
                    return self._blocked(pool, item.item_id, request, "unsafe_path")
                command.append(v)
            elif tok == "{test_file}":
                v = str(request.metadata.get("test_file") or ((item.metadata or {}).get("verification") or {}).get("test_file") or "")
                if not self._safe_rel(v):
                    return self._blocked(pool, item.item_id, request, "unsafe_path")
                command.append(v)
            elif tok.startswith("{") and tok.endswith("}"):
                return self._blocked(pool, item.item_id, request, "unsupported_template_token")
            else:
                command.append(tok)

        res = self.command_runner.run_command(AtlasTestCommandRequest(command=" ".join(command), cwd=workspace_root, timeout_seconds=spec.timeout_seconds, metadata={"pool_id": pool.pool_id, "item_id": item.item_id, "source": "auto_verification"}))
        status, classify_warnings = self._classify(res, command_id)
        warnings = [*classify_warnings, *res.warnings]
        metadata: dict = {"workspace_root": workspace_root}
        metadata["task_verification_contract"] = task_contract.model_dump()

        # Supplemental visual check (PR-9a): a passing unit test does not prove a visual artifact
        # works, so for visual HTML tasks also run the static contract (+ optional smoke) and let a
        # hard visual failure degrade an otherwise-passing command result.
        html_rel = self._resolve_visual_html(item, pool)
        if html_rel and self._safe_rel(html_rel):
            ev = self._evaluate_visual(Path(workspace_root) / html_rel, self._visual_task_description(item, pool), planned_paths=self._pool_planned_paths(pool))
            metadata["visual_contract"] = ev["static"]
            metadata["browser_smoke"] = ev["smoke"]
            # Keep pool-level pipeline metadata current so the UI never shows a stale repair_profile
            # from a prior _run_visual_verification call (e.g. canvas_game_repair for a non-game task).
            pool.metadata.setdefault("visual_pipeline", {})
            pool.metadata["visual_pipeline"].update({
                "visual_contract_id": ev.get("contract_id", ""),
                "artifact_type": (ev.get("classification") or {}).get("artifact_type", ""),
                "visual_intent": (ev.get("classification") or {}).get("visual_intent", ""),
                "repair_profile": ev.get("contract_repair_profile", ""),
                "structured_failures": ev.get("structured_failures", []),
                "missing_signals": list((ev["static"] or {}).get("missing") or []),
                "verified_at": datetime.now(timezone.utc).isoformat(),
            })
            missing = list((ev["static"] or {}).get("missing") or [])
            # Only attribute the failure to a static miss when it actually hard-failed; a runtime
            # smoke pass overrides static misses (advisory only), so don't label a pass as missing.
            if missing and ev["hard_failed"]:
                metadata["primary_verification_reason"] = f"visual_missing:{missing[0]}"
            warnings = [*warnings, *ev["warnings"]]
            if status == "passed":
                if ev["hard_failed"]:
                    status = "failed"
                elif ev["verify_level"]:
                    metadata["verify_level"] = ev["verify_level"]

        signal_eval = self._evaluate_task_contract_signals(task_contract, res, item, workspace_root)
        metadata["task_verification_contract"].update(signal_eval)
        if status == "passed" and signal_eval.get("status") == "failed":
            status = "failed"
            for signal in signal_eval.get("missing_signals") or []:
                warnings.append(f"task_signal_missing:{signal}")
            warnings.extend([f"repair_instruction:{text}" for text in task_contract.repair_instructions])

        coverage = self._requirement_coverage(pool, item, workspace_root, status=status)
        metadata["requirement_coverage"] = coverage
        pool_coverage = self._pool_requirement_coverage_progress(pool, item, workspace_root, status=status)
        if pool_coverage:
            metadata["pool_requirement_coverage"] = pool_coverage
        if status == "passed" and not coverage.get("success_eligible", True):
            if self._visual_evidence_satisfies(metadata):
                warnings.append("requirement_coverage_advisory")
            else:
                status = "failed"
                warnings.append("requirement_coverage_incomplete")

        event = {"passed": "auto_verification_passed", "blocked": "auto_verification_blocked"}.get(status, "auto_verification_failed")
        self._append_event(pool.pool_id, request.run_id, event, item.item_id, status=status, warnings=warnings)
        out = AtlasAutoVerificationResult(pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, preset_id=request.preset_id, status=status, verification_result=res.model_dump(), command_id=command_id, command=command, exit_code=res.returncode, stdout_tail=(res.stdout or "")[-4000:], stderr_tail=(res.stderr or "")[-4000:], warnings=warnings, errors=list(res.errors), metadata=metadata, plan_pool=pool.model_dump())
        auto_verification = self._ensure_auto_verification_metadata(item)
        auto_verification.update({"status": status, "command_id": command_id, "verified_at": datetime.now(timezone.utc).isoformat()})
        self._persist_task_contract(pool, item, task_contract, status=status, evidence=metadata.get("task_verification_contract"))
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        out.plan_pool = pool.model_dump()
        self._record_project_intelligence_verification(pool, item, request, out)
        return out

    def _classify(self, res, command_id: str) -> tuple[str, list[str]]:
        """Map a raw command result to passed / failed / blocked, distinguishing a real test
        failure from an environment problem (interpreter or pytest missing, no tests collected).
        Environment problems become 'blocked' with an actionable warning so the autopilot does not
        treat a successfully-applied change as a code failure just because the harness can't run."""
        if res.status == "passed":
            return "passed", []
        # Missing interpreter/executable (python/python3/node not on PATH).
        if res.status == "blocked" and str(getattr(res, "blocked_reason", "")) == "executable_not_found":
            return "blocked", ["test_harness_unavailable", "interpreter_or_executable_missing"]
        is_pytest = str(command_id).startswith("pytest")
        stderr = (getattr(res, "stderr", "") or "") + (getattr(res, "stdout", "") or "")
        if is_pytest:
            # pytest itself is not installed in the interpreter we ran. This is an environment gap the
            # caller can fix by provisioning the harness (install pytest) and re-verifying.
            if "No module named pytest" in stderr or "No module named 'pytest'" in stderr:
                return "blocked", ["test_harness_unavailable", "pytest_not_installed"]
            # pytest exit code 5 = no tests were collected: the generated "test" file has no runnable
            # test functions. That is a generation defect, not success — report it as a failure (with
            # a specific warning) so the self-correction loop regenerates a real test instead of
            # silently passing.
            if getattr(res, "returncode", None) == 5:
                return "failed", ["no_tests_collected"]
        # Everything else non-passed (assertion failures, compile errors, timeouts) is a real failure.
        return "failed", []

    def _is_visual_task(self, item, pool) -> bool:
        """Visual if a target/changed file is .html, OR goal/done_definition/root_goal carry
        visual keywords. A bare .css/.js target is NOT sufficient on its own."""
        target_files = [str(f).lower() for f in (getattr(item, "target_files", []) or [])]
        changed = [str(f).lower() for f in (((item.metadata or {}).get("safe_apply") or {}).get("changed_files") or [])]
        all_files = target_files + changed
        if any(f.endswith(".html") for f in all_files):
            return True
        text = " ".join([
            str(getattr(item, "goal", "") or ""),
            " ".join(getattr(item, "done_definition", []) or []),
            str(getattr(pool, "root_goal", "") or ""),
        ]).lower()
        return any(kw in text for kw in _VISUAL_KEYWORDS)

    # Browser assets that an .html page LOADS rather than is — a change to one of these is verified
    # through the page that references it, not on its own.
    _BROWSER_ASSET_SUFFIXES = (".js", ".mjs", ".cjs", ".ts", ".css")

    def _resolve_visual_html(self, item, pool) -> str:
        """Return the relative .html artifact path for a visual task, or '' if none."""
        if not self._is_visual_task(item, pool):
            return ""
        candidates = list(getattr(item, "target_files", []) or [])
        candidates += list(((item.metadata or {}).get("safe_apply") or {}).get("changed_files") or [])
        html_candidates = [str(f).replace("\\", "/") for f in candidates if str(f).lower().endswith(".html")]
        for f in html_candidates:
            if PurePosixPath(f).name.lower() == "index.html":
                return f
        if html_candidates:
            return html_candidates[0]
        # Incremental browser-build fallback: this step changed a browser asset (script.js / *.css)
        # but no .html of its own. In a multi-step plan an earlier step creates index.html and later
        # steps only edit the assets it loads, so the asset step had no .html target and would be
        # reported as "nothing to verify" — degrading the whole run to applied_unverified and
        # suppressing the PR. Verify the asset THROUGH the plan's index.html that already exists on
        # disk and actually references it.
        return self._resolve_plan_html_for_asset_change(pool, candidates)

    def _resolve_plan_html_for_asset_change(self, pool, item_candidates) -> str:
        """Find an .html the PLAN produces that exists on disk and loads one of this step's changed
        browser assets, so an asset-only step is verified through the page that uses it. Returns ''
        when the step changed no browser asset, or no such page exists yet (e.g. a CSS-only task
        whose plan has no entry HTML — that must still block honestly)."""
        asset_names = {
            PurePosixPath(str(f).replace("\\", "/")).name.lower()
            for f in item_candidates
            if str(f).lower().endswith(self._BROWSER_ASSET_SUFFIXES)
        }
        if not asset_names:
            return ""
        workspace_root = str(getattr(pool, "project_path", "") or "").strip()
        if not workspace_root:
            return ""
        plan_html: list[str] = []
        for plan_item in (getattr(pool, "items", []) or []):
            for path in (getattr(plan_item, "target_files", []) or []):
                rel = str(path or "").strip().replace("\\", "/").lstrip("./")
                if rel.lower().endswith(".html") and rel not in plan_html:
                    plan_html.append(rel)
        # index.html first, then any other plan page.
        plan_html.sort(key=lambda r: (PurePosixPath(r).name.lower() != "index.html", r))
        for rel in plan_html:
            if not self._safe_rel(rel):
                continue
            html_file = Path(workspace_root) / rel
            if not html_file.is_file():
                continue
            try:
                text = html_file.read_text(encoding="utf-8", errors="replace").lower()
            except Exception:
                continue
            if any(name in text for name in asset_names):
                return rel
        return ""

    def _visual_task_description(self, item, pool) -> str:
        requirements = self._item_requirement_texts(
            pool,
            item,
            changed_files=self._changed_files_for_requirement_check(item),
        )
        return " ".join(requirements).strip()

    @staticmethod
    def _pool_planned_paths(pool) -> set[str]:
        """Relative paths (and basenames) every plan item will create/update. The browser smoke
        verifier uses this to tolerate a reference to a file that this plan WILL create in a later
        step (incremental build) while still failing on a reference to a file no step produces."""
        planned: set[str] = set()
        for plan_item in (getattr(pool, "items", []) or []):
            for path in (getattr(plan_item, "target_files", []) or []):
                rel = str(path or "").strip().replace("\\", "/").lstrip("./")
                if rel:
                    planned.add(rel)
                    planned.add(rel.rsplit("/", 1)[-1])  # basename
        return planned

    def _evaluate_visual(self, html_path: Path, task_desc: str, planned_paths: set[str] | None = None) -> dict:
        """Run static visual contract + optional Playwright smoke; classify hard/soft outcomes.

        Now contract-aware: normaliser → classifier → contract registry determines which
        signals are required/forbidden before the verifiers are called.  Classification and
        contract are returned for persistence in pool metadata.

        Returns:
            {
              static, smoke, warnings, hard_failed, soft, verify_level,
              classification, contract_id, structured_failures,
            }
        A browser_smoke_failed with a hard reason (js_error / expected_text_missing /
        html_file_missing) is a real defect. A soft reason (style-sampling / playwright_error)
        only warns when the static contract already passes.
        """
        normalized = _normalizer.normalize(task_desc)
        classification = _classifier.classify(normalized, task_desc)
        contract: VisualContract = _registry.select(classification)

        static_res = self.visual_verifier.verify_static(
            html_path, task_description=task_desc, contract=contract,
            extra_required_signals=[],
        )
        smoke = self.playwright_verifier.verify(
            html_path, task_description=task_desc, contract_id=contract.contract_id,
            planned_paths=planned_paths,
        )
        warnings: list[str] = []
        static_failed = str(static_res.get("status")) == "failed"
        smoke_status = str(smoke.get("status"))
        smoke_reason = str(smoke.get("reason") or "")
        smoke_passed = smoke_status == "browser_smoke_passed"
        smoke_hard = smoke_status == "browser_smoke_failed" and any(
            smoke_reason.startswith(r) for r in _HARD_SMOKE_REASONS
        )
        smoke_soft = smoke_status == "browser_smoke_failed" and not smoke_hard
        # Runtime evidence beats the static heuristic: when the browser actually observed the
        # required visual behaviour (style/color/canvas mutation over time), a static-contract
        # false-negative — e.g. color expressed via named keywords instead of hsl()/rgb(), or no
        # "motion" signal for a legitimately motionless color-cycling task — must not hard-fail the
        # item. The static misses are still surfaced, but as advisories rather than failures.
        static_overridden = static_failed and smoke_passed

        if static_failed and not static_overridden:
            warnings.append("visual_contract_failed")
            for miss in (static_res.get("missing") or []):
                warnings.append(f"visual_missing:{miss}")
        elif static_overridden:
            warnings.append("visual_contract_overridden_by_runtime_smoke")
            for miss in (static_res.get("missing") or []):
                warnings.append(f"visual_advisory:{miss}")
        else:
            warnings.append("visual_contract_passed")
        if smoke_hard:
            warnings.append(f"browser_smoke_failed:{smoke_reason}")
        elif smoke_soft:
            # Static passed but the browser style-sampling couldn't confirm motion → warn only.
            warnings.append(f"browser_smoke_warning:{smoke_reason}")

        hard_failed = (static_failed and not smoke_passed) or smoke_hard
        if hard_failed:
            verify_level = None
        elif smoke_passed:
            verify_level = "runtime_smoke_checked"
        else:
            verify_level = "static_checked"

        # Build structured failures from missing signals using the selected contract
        structured_failures = failures_from_missing_signals(
            list((static_res or {}).get("missing") or []),
            contract_id=contract.contract_id,
            repair_profile=contract.repair_profile,
            failure_message_template=contract.failure_message_template,
            artifact_type=classification.artifact_type,
            visual_intent=classification.visual_intent,
            auto_repair_allowed=not hard_failed,
        )

        return {
            "static": static_res, "smoke": smoke, "warnings": warnings,
            "hard_failed": hard_failed, "soft": smoke_soft, "verify_level": verify_level,
            "static_overridden": static_overridden,
            "classification": asdict(classification),
            "contract_id": contract.contract_id,
            "contract_repair_profile": contract.repair_profile,
            "structured_failures": [f.to_dict() for f in structured_failures],
            "normalized_requirement": asdict(normalized),
        }

    def _run_visual_verification(self, pool, item, request, workspace_root: str, html_rel: str):
        """Run the static visual contract (+ optional Playwright smoke) for a visual HTML task
        that has no allowlisted test command."""
        html_path = Path(workspace_root) / html_rel
        ev = self._evaluate_visual(html_path, self._visual_task_description(item, pool), planned_paths=self._pool_planned_paths(pool))
        task_contract = select_task_verification_contract(item, pool)
        warnings = list(ev["warnings"])
        metadata: dict = {
            "workspace_root": workspace_root,
            "visual_contract": ev["static"],
            "browser_smoke": ev["smoke"],
            "task_verification_contract": {
                **task_contract.model_dump(),
                "status": "passed" if not ev["hard_failed"] else "failed",
                "visual_contract_id": ev.get("contract_id", ""),
                "missing_signals": list((ev["static"] or {}).get("missing") or []),
                "repair_instructions": list(task_contract.repair_instructions),
            },
        }
        signal_eval = self._evaluate_task_contract_signals(
            task_contract,
            SimpleNamespace(stdout="", stderr=""),
            item,
            workspace_root,
        )
        metadata["task_verification_contract"].update(signal_eval)
        missing = list((ev["static"] or {}).get("missing") or [])
        # A runtime smoke pass overrides static misses (advisory only); only attribute the failure
        # to a static miss when the item genuinely hard-failed.
        if missing and ev["hard_failed"]:
            metadata["primary_verification_reason"] = f"visual_missing:{missing[0]}"
        if ev["verify_level"]:
            metadata["verify_level"] = ev["verify_level"]

        # Persist classification, contract, and structured failures for debugging/UI
        metadata["visual_contract_id"] = ev.get("contract_id", "")
        metadata["visual_contract_repair_profile"] = ev.get("contract_repair_profile", "")
        metadata["visual_classification"] = ev.get("classification", {})
        metadata["visual_structured_failures"] = ev.get("structured_failures", [])
        metadata["normalized_requirement"] = ev.get("normalized_requirement", {})

        status = "failed" if ev["hard_failed"] else "passed"
        if status == "passed" and signal_eval.get("status") == "failed":
            status = "failed"
            for signal in signal_eval.get("missing_signals") or []:
                warnings.append(f"task_signal_missing:{signal}")
            warnings.extend([f"repair_instruction:{text}" for text in task_contract.repair_instructions])
        coverage = self._requirement_coverage(pool, item, workspace_root, status=status)
        metadata["requirement_coverage"] = coverage
        pool_coverage = self._pool_requirement_coverage_progress(pool, item, workspace_root, status=status)
        if pool_coverage:
            metadata["pool_requirement_coverage"] = pool_coverage
        if status == "passed" and not coverage.get("success_eligible", True):
            if self._visual_evidence_satisfies(metadata):
                warnings.append("requirement_coverage_advisory")
            else:
                status = "failed"
                warnings.append("requirement_coverage_incomplete")

        event = {"passed": "auto_verification_passed"}.get(status, "auto_verification_failed")
        self._append_event(pool.pool_id, request.run_id, event, item.item_id, status=status, warnings=warnings)
        out = AtlasAutoVerificationResult(
            pool_id=pool.pool_id, item_id=item.item_id, run_id=request.run_id, preset_id=request.preset_id,
            status=status, verification_result={"status": status, "source": "visual_artifact"},
            warnings=warnings, errors=[], metadata=metadata, plan_pool=pool.model_dump(),
        )
        auto_verification = self._ensure_auto_verification_metadata(item)
        auto_verification.update({
            "status": status, "source": "visual_artifact",
            "visual_contract_status": ev["static"].get("status"),
            "visual_contract_id": ev.get("contract_id", ""),
            "browser_smoke_status": ev["smoke"].get("status"),
            "verified_at": datetime.now(timezone.utc).isoformat(),
        })
        self._persist_task_contract(pool, item, task_contract, status=status, evidence=metadata.get("task_verification_contract"))

        # Persist classification + contract in pool metadata for UI observability
        pool.metadata.setdefault("visual_pipeline", {})
        pool.metadata["visual_pipeline"].update({
            "visual_contract_id": ev.get("contract_id", ""),
            "artifact_type": (ev.get("classification") or {}).get("artifact_type", ""),
            "visual_intent": (ev.get("classification") or {}).get("visual_intent", ""),
            "repair_profile": ev.get("contract_repair_profile", ""),
            "structured_failures": ev.get("structured_failures", []),
            "missing_signals": missing,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        })

        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        out.plan_pool = pool.model_dump()
        self._record_project_intelligence_verification(pool, item, request, out)
        return out

    def _record_project_intelligence_verification(self, pool, item, request, result) -> None:
        pi_verification = record_project_intelligence_verification(
            project_intelligence=self.project_intelligence,
            checkpoint_bridge=self.verification_bridge,
            pool=pool,
            item=item,
            request=request,
            result=result,
            source="auto",
        )
        if not pi_verification:
            return
        item.metadata.setdefault("verification", {})["project_intelligence_verification"] = pi_verification
        self._ensure_auto_verification_metadata(item)["project_intelligence_verification"] = pi_verification
        result.metadata.setdefault("project_intelligence_verification", pi_verification)
        self.storage.save_pool(pool)
        self.journal.save_plan_pool(pool)
        result.plan_pool = pool.model_dump()

    @staticmethod
    def _ensure_auto_verification_metadata(item) -> dict:
        item.metadata = dict(getattr(item, "metadata", {}) or {})
        current = item.metadata.get("auto_verification")
        if not isinstance(current, dict):
            current = {"enabled": bool(current)}
            item.metadata["auto_verification"] = current
        return current

    def _safe_rel(self, value: str) -> bool:
        if not value:
            return False
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            return False
        return True

    def _persist_task_contract(self, pool, item, contract, *, status: str, evidence: dict | None = None) -> None:
        item.metadata.setdefault("task_verification_contract", {})
        item.metadata["task_verification_contract"].update({
            **contract.model_dump(),
            "status": status,
            **(evidence or {}),
        })
        pool.metadata.setdefault("task_verification_contracts", {})
        pool.metadata["task_verification_contracts"][item.item_id] = dict(item.metadata["task_verification_contract"])

    def _evaluate_task_contract_signals(self, contract, command_result, item, workspace_root: str) -> dict:
        changed_files = self._changed_files_for_requirement_check(item)
        file_contents = {
            rel: text
            for rel in changed_files
            if (text := self._read_single_requirement_evidence(workspace_root, rel)) is not None
        }
        output_text = "\n".join([
            str(getattr(command_result, "stdout", "") or ""),
            str(getattr(command_result, "stderr", "") or ""),
        ])
        result = evaluate_expected_signals(contract, output_text=output_text, file_contents=file_contents)
        result["repair_instructions"] = list(contract.repair_instructions)
        result["evidence_sources"] = {
            "stdout": bool(str(getattr(command_result, "stdout", "") or "")),
            "stderr": bool(str(getattr(command_result, "stderr", "") or "")),
            "changed_files": changed_files,
        }
        return result

    @staticmethod
    def _visual_evidence_satisfies(metadata: dict) -> bool:
        """A visual task that passed its visual contract / runtime smoke has substantive
        evidence the requirement is met. Literal keyword matching of a *visual* requirement
        ("animate a color wave") against HTML/CSS is a false-negative generator, so for these
        passes requirement coverage is advisory, not a hard gate. (Non-visual code tasks have no
        verify_level here and keep the hard requirement-coverage gate.)"""
        return str((metadata or {}).get("verify_level") or "") in {"static_checked", "runtime_smoke_checked"}

    def _requirement_coverage(self, pool, item, workspace_root: str, *, status: str) -> dict:
        changed_files = self._changed_files_for_requirement_check(item)
        requirements = self._item_requirement_texts(pool, item, changed_files=changed_files)
        if not requirements:
            return {
                "scope": "item",
                "total": 0,
                "by_status": {},
                "mapped": [],
                "all_verified": False,
                "success_eligible": True,
            }
        content = self._read_requirement_evidence(workspace_root, changed_files)
        evidence_text = "\n".join([content, *changed_files]).lower()
        mapped: list[dict] = []
        by_status: dict[str, int] = {}
        for idx, requirement in enumerate(requirements, start=1):
            tokens = self._requirement_tokens(requirement)
            if not tokens:
                req_status = "partial"
                missing = []
            else:
                matched = [tok for tok in tokens if tok in evidence_text]
                required_count = max(1, min(len(tokens), (len(tokens) + 1) // 2))
                if len(matched) >= required_count:
                    req_status = "verified" if status == "passed" else "implemented"
                else:
                    req_status = "missing"
                missing = [tok for tok in tokens if tok not in matched]
            by_status[req_status] = by_status.get(req_status, 0) + 1
            mapped.append({
                "requirement_id": f"req_{idx:03d}",
                "description": requirement,
                "status": req_status,
                "implementation_evidence": list(changed_files) if req_status in {"verified", "implemented"} else [],
                "missing_keywords": missing,
            })
        all_verified = by_status.get("verified", 0) == len(requirements)
        success_eligible = all_verified or (
            by_status.get("verified_static", 0) + by_status.get("verified", 0) == len(requirements)
        )
        return {
            "scope": "item",
            "total": len(requirements),
            "by_status": by_status,
            "mapped": mapped,
            "all_verified": all_verified,
            "success_eligible": success_eligible,
        }

    def _item_requirement_texts(self, pool, item, *, changed_files: list[str]) -> list[str]:
        metadata = item.metadata or {}
        original_step = metadata.get("original_step_payload") if isinstance(metadata.get("original_step_payload"), dict) else {}
        step_requirements = [
            *self._coerce_text_list(original_step.get("acceptance_criteria")),
            *self._coerce_text_list(original_step.get("done_definition")),
            *self._coerce_text_list(original_step.get("verification")),
            *self._coerce_text_list(metadata.get("acceptance_criteria")),
        ]
        goal = str(getattr(item, "goal", "") or "").strip()
        requirements = [*step_requirements]
        if goal and (step_requirements or changed_files):
            requirements.insert(0, goal)
        if not step_requirements and not self._has_shared_pool_level_done_definition(pool, item):
            requirements.extend(self._coerce_text_list(getattr(item, "done_definition", []) or []))
        return list(dict.fromkeys(v for v in requirements if v))

    def _has_shared_pool_level_done_definition(self, pool, item) -> bool:
        done = self._coerce_text_list(getattr(item, "done_definition", []) or [])
        if not done or len(getattr(pool, "items", []) or []) < 2:
            return False
        item_original = (getattr(item, "metadata", {}) or {}).get("original_step_payload")
        if isinstance(item_original, dict) and any(
            item_original.get(key) for key in ("acceptance_criteria", "done_definition", "verification")
        ):
            return False
        normalized = tuple(done)
        shared_count = 0
        for candidate in getattr(pool, "items", []) or []:
            if tuple(self._coerce_text_list(getattr(candidate, "done_definition", []) or [])) == normalized:
                shared_count += 1
        return shared_count > 1

    def _pool_requirement_coverage_progress(self, pool, item, workspace_root: str, *, status: str) -> dict:
        pool_meta = getattr(pool, "metadata", {}) or {}
        requirements = list(pool_meta.get("requirement_trace") or [])
        if not requirements:
            return {}
        changed_files: list[str] = []
        verified_files: list[str] = []
        for candidate in getattr(pool, "items", []) or []:
            candidate_changed = self._changed_files_for_requirement_check(candidate)
            if candidate is item:
                candidate_verified = status == "passed"
            else:
                candidate_verified = str(((getattr(candidate, "metadata", {}) or {}).get("auto_verification") or {}).get("status") or "") == "passed"
            changed_files.extend(candidate_changed)
            if candidate_verified:
                verified_files.extend(candidate_changed)
        changed_files = list(dict.fromkeys(changed_files))
        verified_files = list(dict.fromkeys(verified_files))
        file_contents = {
            rel: text
            for rel in changed_files
            if (text := self._read_single_requirement_evidence(workspace_root, rel)) is not None
        }
        mapped = AtlasRequirementTracer().map_requirements_to_evidence(
            requirements,
            changed_files=changed_files,
            verified_files=verified_files,
            done_definitions=[
                text
                for candidate in getattr(pool, "items", []) or []
                for text in self._coerce_text_list(getattr(candidate, "done_definition", []) or [])
            ],
            file_contents=file_contents,
        )
        summary = AtlasRequirementTracer().coverage_summary(mapped)
        return {
            **summary,
            "scope": "pool",
            "progress_only": True,
            "enforceable": False,
            "mapped": mapped,
        }

    def _changed_files_for_requirement_check(self, item) -> list[str]:
        metadata = item.metadata or {}
        safe_apply = metadata.get("safe_apply") if isinstance(metadata.get("safe_apply"), dict) else {}
        auto_safe_apply = metadata.get("auto_safe_apply") if isinstance(metadata.get("auto_safe_apply"), dict) else {}
        candidates = [
            *list(safe_apply.get("changed_files") or []),
            *list(auto_safe_apply.get("changed_files") or []),
            *list(getattr(item, "target_files", []) or []),
        ]
        out: list[str] = []
        for raw in candidates:
            rel = str(raw or "").replace("\\", "/").strip()
            if rel and self._safe_rel(rel) and rel not in out:
                out.append(rel)
        return out

    def _read_requirement_evidence(self, workspace_root: str, rel_paths: list[str]) -> str:
        chunks: list[str] = []
        for rel in rel_paths:
            text = self._read_single_requirement_evidence(workspace_root, rel)
            if text is not None:
                chunks.append(text)
        return "\n".join(chunks).lower()

    def _read_single_requirement_evidence(self, workspace_root: str, rel: str) -> str | None:
        if not self._safe_rel(rel):
            return None
        root = Path(workspace_root)
        try:
            target = (root / rel).resolve()
            target.relative_to(root.resolve())
            if target.is_file():
                return target.read_text(encoding="utf-8", errors="replace")[:100000]
        except Exception:
            return None
        return None

    @staticmethod
    def _requirement_tokens(text: str) -> list[str]:
        stopwords = {
            "the", "and", "for", "with", "that", "this", "should", "must", "shall", "need",
            "needs", "please", "add", "create", "make", "ensure", "show", "display", "update",
            "page", "code", "implement", "implementation", "from", "into", "when", "where",
            "which", "have", "has", "will", "your", "use", "using", "value", "values", "file",
            "files", "text", "appears", "contain", "contains",
        }
        tokens = [
            t.lower()
            for t in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", text or "")
            if t.lower() not in stopwords
        ]
        return list(dict.fromkeys(tokens))[:8]

    @staticmethod
    def _coerce_text_list(value) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(v).strip() for v in value if str(v or "").strip()]
        return [str(value).strip()]

    def _blocked(self, pool, item_id: str, request: AtlasAutoVerificationRequest, reason: str):
        self._append_event(pool.pool_id, request.run_id, "auto_verification_blocked", item_id, status="blocked", warnings=[reason])
        item = pool.get_item(item_id)
        safe_apply_meta = ((item.metadata or {}).get("safe_apply") or {}) if item is not None else {}
        metadata = {"safe_apply": self._safe_apply_explanation(safe_apply_meta)}
        return AtlasAutoVerificationResult(pool_id=pool.pool_id, item_id=item_id, run_id=request.run_id, preset_id=request.preset_id, status="blocked", warnings=[reason], errors=[reason], metadata=metadata, plan_pool=pool.model_dump())

    @staticmethod
    def _safe_apply_explanation(safe_apply_meta: dict) -> dict:
        return {
            "status": str(safe_apply_meta.get("status") or ""),
            "reasons": list(safe_apply_meta.get("reasons") or []),
            "changed_files": list(safe_apply_meta.get("changed_files") or []),
            "file_results": list(safe_apply_meta.get("file_results") or []),
            "actual_file_changed": bool(safe_apply_meta.get("actual_file_changed", False)),
        }

    def _append_event(self, pool_id: str, run_id: str, event_type: str, item_id: str, *, status: str, warnings: list[str] | None = None):
        if not run_id:
            return
        self.journal.append_event(pool_id, run_id, {"event_type": event_type, "pool_id": pool_id, "run_id": run_id, "item_id": item_id, "status": status, "warnings": list(warnings or []), "errors": [], "created_at": datetime.now(timezone.utc).isoformat()})
