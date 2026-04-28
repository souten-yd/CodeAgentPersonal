from __future__ import annotations

import re
import uuid
from collections import Counter

from agent.plan_review_schema import PlanReviewFinding, PlanReviewResult
from agent.plan_schema import Plan
from agent.requirement_schema import RequirementDefinition


class PlanReviewer:
    def review(
        self,
        *,
        requirement: RequirementDefinition,
        plan: Plan,
        nexus_context: dict,
        repository_context: str,
    ) -> PlanReviewResult:
        try:
            findings = self._collect_findings(requirement=requirement, plan=plan, nexus_context=nexus_context, repository_context=repository_context)
            return self._build_result(requirement=requirement, plan=plan, findings=findings)
        except Exception as exc:  # noqa: BLE001
            warning = f"Plan review failed safely with fallback: {exc}"
            return PlanReviewResult(
                review_id=f"review_{uuid.uuid4().hex[:12]}",
                plan_id=plan.plan_id,
                requirement_id=requirement.requirement_id,
                overall_risk="medium",
                approved_for_execution=True,
                requires_user_confirmation=False,
                destructive_change_detected=False,
                findings=[],
                blocking_findings=[],
                summary="Plan review encountered an internal warning. Proceed with manual review.",
                recommended_next_action="proceed",
                warnings=[warning],
            )

    def _collect_findings(self, *, requirement: RequirementDefinition, plan: Plan, nexus_context: dict, repository_context: str) -> list[PlanReviewFinding]:
        findings: list[PlanReviewFinding] = []
        steps = plan.implementation_steps or []
        all_step_text = "\n".join([f"{s.title}\n{s.description}\n{' '.join(s.target_files)}" for s in steps])
        all_plan_text = "\n".join([
            plan.user_goal,
            plan.requirement_summary,
            "\n".join(plan.target_files or []),
            "\n".join(plan.expected_file_changes or []),
            "\n".join(plan.risks or []),
            "\n".join(plan.done_definition or []),
            all_step_text,
            repository_context or "",
        ]).lower()

        all_files = set(plan.target_files or [])
        for s in steps:
            all_files.update(s.target_files or [])

        # A. destructive_change
        destructive_hit_steps = [s.step_id for s in steps if s.action_type == "delete"]
        destructive_patterns = [
            r"rm\s+-rf", r"delete\s+all", r"remove\s+directory", r"\breset\b", r"\bwipe\b",
            r"全削除", r"大量削除",
        ]
        if destructive_hit_steps or _has_pattern(all_plan_text, destructive_patterns):
            findings.append(self._mk_finding(
                severity="critical",
                category="destructive_change",
                title="破壊的変更の可能性が高いPlanです",
                detail="delete操作または広範囲削除パターンが検出されました。",
                related_steps=destructive_hit_steps,
                related_files=sorted(all_files),
                recommendation="削除対象を限定し、バックアップ/ロールバック手順を明確化してください。",
                requires_user_confirmation=True,
            ))

        # B. large_scope_change
        large_scope_tokens = ["全面改修", "大規模リファクタ", "rewrite", "rebuild", "replace all"]
        if len(steps) >= 10 or len(all_files) >= 15 or len(plan.expected_file_changes or []) >= 20 or any(t in all_plan_text for t in large_scope_tokens):
            findings.append(self._mk_finding(
                severity="warning",
                category="large_scope_change",
                title="変更スコープが大きい可能性があります",
                detail=f"steps={len(steps)}, files={len(all_files)}, expected_changes={len(plan.expected_file_changes or [])}",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(all_files),
                recommendation="段階的に分割し、リスクの高い変更を小さな単位に分解してください。",
            ))

        # C. dependency_change
        dep_files = [
            "package.json", "requirements.txt", "pyproject.toml", "dockerfile", "docker-compose.yml", "environment.yml", "poetry.lock", "package-lock.json",
            "pnpm-lock.yaml", "yarn.lock",
        ]
        dep_keywords = ["pip install", "npm install", "apt install", "依存関係追加", "ベースイメージ変更"]
        dep_hits = [f for f in all_files if any(k in f.lower() for k in dep_files)]
        if dep_hits or any(k in all_plan_text for k in dep_keywords):
            findings.append(self._mk_finding(
                severity="high",
                category="dependency_change",
                title="依存関係変更が含まれています",
                detail="依存の追加/更新は副作用が大きいため、互換性確認が必要です。",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(set(dep_hits)),
                recommendation="バージョン固定、互換性確認、再現手順、ロールバック手順を明記してください。",
                requires_user_confirmation=True,
            ))

        # D. security
        sec_keywords = ["auth", "token", "password", "secret", "cors", "external exposure", "public", "認証", "秘密鍵", "apiキー", "外部公開"]
        if any(k in all_plan_text for k in sec_keywords):
            findings.append(self._mk_finding(
                severity="high",
                category="security",
                title="セキュリティ影響のある変更が含まれています",
                detail="認証・鍵・公開設定に関わる変更キーワードを検出しました。",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(all_files),
                recommendation="最小権限・秘密情報マスキング・公開範囲確認・監査ログ確認を行ってください。",
                requires_user_confirmation=True,
            ))

        # E. data_loss
        data_keywords = ["database migration", "db schema", "migration", "drop table", "delete db", "sqlite", "memory.db", "ca_data削除", "データ移行", "db変更"]
        if any(k in all_plan_text for k in data_keywords):
            findings.append(self._mk_finding(
                severity="critical",
                category="data_loss",
                title="データ損失リスクのある変更が含まれています",
                detail="DB/migration関連キーワードが検出されました。",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(all_files),
                recommendation="バックアップとリストア手順、移行検証、ロールバック計画を必須化してください。",
                requires_user_confirmation=True,
            ))

        # F. api_breaking_change
        api_keywords = ["api削除", "endpoint rename", "request/response", "backward incompatible", "fastapi route変更", "route", "endpoint"]
        api_files = [f for f in all_files if f.endswith("main.py") or "/api" in f.lower()]
        if any(k in all_plan_text for k in api_keywords):
            findings.append(self._mk_finding(
                severity="high",
                category="api_breaking_change",
                title="API互換性を壊す可能性があります",
                detail="既存API仕様に影響する変更キーワードを検出しました。",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(api_files),
                recommendation="後方互換方針、移行期間、レスポンス互換テストを追加してください。",
                requires_user_confirmation=True,
            ))

        # G. ui_breaking_change
        ui_keywords = ["ui.html全面変更", "header", "tts", "echo", "agent", "task", "iphone safari", "表示崩れ"]
        ui_files = [f for f in all_files if f.lower().endswith("ui.html")]
        if ui_files and any(k in all_plan_text for k in ui_keywords):
            findings.append(self._mk_finding(
                severity="high",
                category="ui_breaking_change",
                title="UI破壊リスクのある変更が含まれています",
                detail="重要UI領域(ui.html/TTS/Echo関連)への変更が含まれます。",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(ui_files),
                recommendation="iPhone幅確認、TTS表示確認、主要導線の回帰確認を追加してください。",
                requires_user_confirmation=True,
            ))

        # H. config_change
        config_hits = [f for f in all_files if _is_config_like_path(f)]
        config_keywords = [".env", "settings", "ports", "docker", "runpod", "start script", "windows", "bat"]
        if config_hits or any(k in all_plan_text for k in config_keywords):
            findings.append(self._mk_finding(
                severity="warning",
                category="config_change",
                title="設定変更が含まれています",
                detail="環境依存の挙動に影響する可能性があります。",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(set(config_hits)),
                recommendation="既定値の互換性を維持し、設定変更理由を明記してください。",
            ))

        # I. missing_test
        if not (plan.test_plan or []):
            findings.append(self._mk_finding(
                severity="warning",
                category="missing_test",
                title="テスト計画が不足しています",
                detail="test_plan が空です。",
                related_steps=[],
                related_files=[],
                recommendation="最低限、変更対象に対応するAPI/UI/ユニットテストを追加してください。",
            ))
        if _has_high_or_critical(findings) and not (plan.test_plan or []):
            findings.append(self._mk_finding(
                severity="high",
                category="missing_test",
                title="高リスク変更に対してテストが不足しています",
                detail="high/critical finding があるのに test_plan が空です。",
                related_steps=[],
                related_files=[],
                recommendation="高リスク変更に対応する具体的な回帰テストを追加してください。",
                requires_user_confirmation=True,
            ))

        # J. requirement_mismatch
        requirement_done = "\n".join(requirement.done_definition or []).lower()
        plan_done = "\n".join(plan.done_definition or []).lower()
        if requirement_done and plan_done and _low_overlap(requirement_done, plan_done):
            findings.append(self._mk_finding(
                severity="warning",
                category="requirement_mismatch",
                title="要件の完了条件とPlanの完了条件に差異があります",
                detail="Requirement.done_definition と Plan.done_definition の重なりが低いです。",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(all_files),
                recommendation="要件の完了条件をPlanに再反映してください。",
            ))

        out_of_scope_hits = []
        for item in (requirement.out_of_scope or []):
            t = str(item).strip().lower()
            if t and t in all_plan_text:
                out_of_scope_hits.append(item)
        if out_of_scope_hits:
            findings.append(self._mk_finding(
                severity="high",
                category="requirement_mismatch",
                title="out_of_scope 項目がPlanに含まれています",
                detail="; ".join([str(x) for x in out_of_scope_hits]),
                related_steps=[s.step_id for s in steps],
                related_files=sorted(all_files),
                recommendation="out_of_scope項目をPlanから除外し、要件と整合させてください。",
                requires_user_confirmation=True,
            ))

        disallowed_exec = ["implementation_executor", "verification_runner", "project_generator", "自動コード実装", "自動修正ループ"]
        if any(k.lower() in all_plan_text for k in [x.lower() for x in disallowed_exec]):
            findings.append(self._mk_finding(
                severity="critical",
                category="requirement_mismatch",
                title="Phase 4 の範囲外実装がPlanに含まれています",
                detail="Phase 4 で禁止される自動実装系の記述が含まれています。",
                related_steps=[s.step_id for s in steps],
                related_files=sorted(all_files),
                recommendation="Phase 4の範囲（Plan reviewのみ）へ計画を修正してください。",
                requires_user_confirmation=True,
            ))

        # K. nexus_context_mismatch
        nx_warnings = nexus_context.get("warnings") if isinstance(nexus_context, dict) else []
        nx_warning_text = "\n".join([str(x).lower() for x in (nx_warnings or [])])
        if nx_warning_text:
            coverage = 0
            plan_text = (plan.requirement_summary + "\n" + "\n".join(plan.risks or []) + "\n" + "\n".join(plan.constraints or [])).lower()
            for token in ["warning", "注意", "失敗", "fallback", "互換"]:
                if token in nx_warning_text and token in plan_text:
                    coverage += 1
            if coverage == 0:
                findings.append(self._mk_finding(
                    severity="warning",
                    category="nexus_context_mismatch",
                    title="Nexus Context の注意点がPlanに反映されていない可能性があります",
                    detail="nexus_context.warnings が存在しますが、Plan側での明示的考慮が弱いです。",
                    related_steps=[s.step_id for s in steps],
                    related_files=sorted(all_files),
                    recommendation="Nexus warningをリスク・制約・テスト計画へ反映してください。",
                ))

        # ambiguous steps
        ambiguous = [s.step_id for s in steps if len((s.description or "").strip()) < 8 and s.action_type in {"update", "create", "delete", "run_command"}]
        if ambiguous:
            findings.append(self._mk_finding(
                severity="warning",
                category="ambiguous_step",
                title="実装ステップが曖昧です",
                detail="説明が短すぎるステップが検出されました。",
                related_steps=ambiguous,
                related_files=sorted(all_files),
                recommendation="変更対象・目的・検証手順を各ステップに明記してください。",
            ))

        return findings

    def _build_result(self, *, requirement: RequirementDefinition, plan: Plan, findings: list[PlanReviewFinding]) -> PlanReviewResult:
        severity_counter = Counter([f.severity for f in findings])
        categories = {f.category for f in findings}

        destructive_detected = any(f.category == "destructive_change" for f in findings)

        overall_risk = "low"
        high_count = severity_counter.get("high", 0)
        has_critical = severity_counter.get("critical", 0) > 0

        if has_critical or high_count >= 2:
            overall_risk = "critical"
        elif high_count >= 1 or ("dependency_change" in categories and "config_change" in categories):
            overall_risk = "high"
        elif severity_counter.get("warning", 0) >= 2 or categories.intersection({"dependency_change", "config_change", "missing_test"}):
            overall_risk = "medium"

        requires_user_confirmation = False
        if overall_risk in {"high", "critical"}:
            requires_user_confirmation = True
        if destructive_detected or "data_loss" in categories or "api_breaking_change" in categories or "ui_breaking_change" in categories:
            requires_user_confirmation = True

        blocking_findings = [f.finding_id for f in findings if f.severity in {"high", "critical"} or f.requires_user_confirmation]

        if has_critical:
            recommended_next_action = "reject_plan" if destructive_detected else "revise_plan"
        elif requires_user_confirmation:
            recommended_next_action = "ask_user"
        elif findings:
            recommended_next_action = "proceed"
        else:
            recommended_next_action = "proceed"

        approved_for_execution = not requires_user_confirmation

        summary = "No significant issues detected."
        if findings:
            summary = f"{len(findings)} findings detected. Top risk: {overall_risk}."

        warnings = []
        if requires_user_confirmation:
            warnings.append("Plan review flagged this plan for user confirmation before any execution phase.")

        return PlanReviewResult(
            review_id=f"review_{uuid.uuid4().hex[:12]}",
            plan_id=plan.plan_id,
            requirement_id=requirement.requirement_id,
            overall_risk=overall_risk,
            approved_for_execution=approved_for_execution,
            requires_user_confirmation=requires_user_confirmation,
            destructive_change_detected=destructive_detected,
            findings=findings,
            blocking_findings=blocking_findings,
            summary=summary,
            recommended_next_action=recommended_next_action,
            warnings=warnings,
        )

    def _mk_finding(
        self,
        *,
        severity: str,
        category: str,
        title: str,
        detail: str,
        related_steps: list[str],
        related_files: list[str],
        recommendation: str,
        requires_user_confirmation: bool = False,
    ) -> PlanReviewFinding:
        return PlanReviewFinding(
            finding_id=f"finding_{uuid.uuid4().hex[:10]}",
            severity=severity,
            category=category,
            title=title,
            detail=detail,
            related_steps=related_steps,
            related_files=related_files,
            recommendation=recommendation,
            requires_user_confirmation=requires_user_confirmation,
        )


def _has_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def _is_config_like_path(path: str) -> bool:
    p = path.lower()
    needles = [".env", "settings", "docker", "runpod", "start", ".bat", "compose", "port"]
    return any(n in p for n in needles)


def _has_high_or_critical(findings: list[PlanReviewFinding]) -> bool:
    return any(f.severity in {"high", "critical"} for f in findings)


def _low_overlap(a: str, b: str) -> bool:
    ta = set(_tokenize(a))
    tb = set(_tokenize(b))
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    return overlap <= max(1, min(len(ta), len(tb)) // 6)


def _tokenize(text: str) -> list[str]:
    return [x for x in re.split(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", text.lower()) if len(x) >= 2]
