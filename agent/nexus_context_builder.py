from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from agent.nexus_context_schema import NexusContextItem, NexusContextPack


class NexusContextBuilder:
    """Phase 3 nexus context builder.

    - Never raises to caller.
    - Builds compact context from Memory / Skills / past artifacts / project files.
    - Returns dict-compatible payload for backward compatibility.
    """

    def __init__(
        self,
        memory_search_fn: Callable[[str, int], list] | None = None,
        active_skills_fn: Callable[[], list] | None = None,
        warning_logger: Callable[[str], None] | None = None,
        ca_data_dir: str | None = None,
    ) -> None:
        self.memory_search_fn = memory_search_fn
        self.active_skills_fn = active_skills_fn
        self.warning_logger = warning_logger
        self.ca_data_dir = str(ca_data_dir or "").strip()

    def build(
        self,
        user_input: str,
        use_nexus: bool = True,
        project_path: str = "",
        project_name: str = "",
        resolved_project_path: str = "",
        max_items: int = 12,
        context_budget_chars: int = 12000,
    ) -> dict:
        if not use_nexus:
            return self._to_dict(
                NexusContextPack(
                    available=False,
                    summary="Nexus context is disabled. Continue with empty context.",
                    items=[],
                    warnings=["Nexus usage disabled by request."],
                    context_budget_chars=max(500, int(context_budget_chars or 12000)),
                )
            )

        warnings: list[str] = []
        query_terms = _extract_query_terms(user_input, project_name)
        items: list[NexusContextItem] = []
        budget = max(500, int(context_budget_chars or 12000))
        selected_project_path = (resolved_project_path or project_path or "").strip()

        try:
            items.extend(self._collect_memory(user_input=user_input, query_terms=query_terms, warnings=warnings))
            items.extend(self._collect_skills(query_terms=query_terms, warnings=warnings))
            items.extend(
                self._collect_skill_files(
                    project_path=selected_project_path,
                    query_terms=query_terms,
                    warnings=warnings,
                )
            )
            items.extend(self._collect_past_requirements(query_terms=query_terms, warnings=warnings))
            items.extend(self._collect_past_plans(query_terms=query_terms, warnings=warnings))
            items.extend(self._collect_run_logs(query_terms=query_terms, warnings=warnings))
            items.extend(
                self._collect_project_context(
                    project_path=selected_project_path,
                    query_terms=query_terms,
                    warnings=warnings,
                )
            )
        except Exception as exc:  # noqa: BLE001
            self._warn(warnings, f"Nexus context build warning: {exc}")

        total_before = len(items)
        scored = [self._score_item(item, query_terms=query_terms, project_name=project_name) for item in items]
        deduped = self._dedupe_items(scored)
        ranked = sorted(deduped, key=lambda x: x.score, reverse=True)
        limited = ranked[: max(1, int(max_items or 12))]

        source_counts = dict(Counter(i.source_type for i in limited))
        compact_text, truncated = _build_compact_text(limited, warnings, budget)
        has_non_project_sources = any(i.source_type != "project_file" for i in limited)
        available = len(limited) > 0 and has_non_project_sources

        if not available and not warnings:
            warnings.append("Nexus is not configured or no related context was found.")

        if available:
            summary = f"Collected {len(limited)} relevant item(s) from {len(source_counts)} source type(s)."
        elif limited:
            summary = "Collected local project context only. Nexus signals were limited."
        else:
            summary = "Nexus context is not available. Continue with empty context."

        pack = NexusContextPack(
            available=available,
            summary=summary,
            items=limited,
            warnings=_dedup_warnings(warnings),
            query_terms=query_terms,
            source_counts=source_counts,
            total_items_before_filter=total_before,
            total_items_after_filter=len(limited),
            context_budget_chars=budget,
            truncated=truncated,
            compact_text=compact_text,
        )
        return self._to_dict(pack)

    def _collect_memory(self, *, user_input: str, query_terms: list[str], warnings: list[str]) -> list[NexusContextItem]:
        out: list[NexusContextItem] = []
        if not callable(self.memory_search_fn):
            self._warn(warnings, "memory_search_fn is unavailable.")
            return out
        try:
            hits = self.memory_search_fn(user_input, limit=5) or []
            for i, hit in enumerate(hits[:5], start=1):
                h = hit if isinstance(hit, dict) else {"content": str(hit)}
                title = str(h.get("title") or h.get("category") or f"Memory hit {i}")
                content = _limit_text(str(h.get("content") or h), 1600)
                out.append(
                    NexusContextItem(
                        item_id=f"memory_{i}_{_short_hash(title + content)}",
                        source_type="memory",
                        title=title,
                        content=content,
                        summary=_summarize_text(content, 220),
                        source_path="memory.db",
                        source_id=str(h.get("id") or h.get("memory_id") or ""),
                        score=float(h.get("score") or 0.0),
                        reason="Memory hit relevant to current request.",
                        freshness="unknown",
                        risk_level="low",
                        tags=[str(h.get("category") or "memory")] + query_terms[:2],
                        metadata={"raw_score": h.get("score")},
                    )
                )
        except Exception as exc:  # noqa: BLE001
            self._warn(warnings, f"Memory collection warning: {exc}")
        return out

    def _collect_skills(self, *, query_terms: list[str], warnings: list[str]) -> list[NexusContextItem]:
        out: list[NexusContextItem] = []
        if not callable(self.active_skills_fn):
            self._warn(warnings, "active_skills_fn is unavailable.")
            return out
        try:
            skills = self.active_skills_fn() or []
            for i, skill in enumerate(skills[:5], start=1):
                s = skill if isinstance(skill, dict) else {"name": str(skill)}
                name = str(s.get("name") or f"skill_{i}")
                desc = _limit_text(str(s.get("description") or ""), 1200)
                path = str(s.get("path") or "")
                out.append(
                    NexusContextItem(
                        item_id=f"skill_{i}_{_short_hash(name + path)}",
                        source_type="skill",
                        title=name,
                        content=desc,
                        summary=_summarize_text(desc or name, 200),
                        source_path=path,
                        source_id=name,
                        reason="Active skill may constrain planning steps.",
                        freshness="active",
                        risk_level="low",
                        tags=["skill", *query_terms[:2]],
                        metadata={"path": path},
                    )
                )
        except Exception as exc:  # noqa: BLE001
            self._warn(warnings, f"Skills collection warning: {exc}")
        return out

    def _collect_skill_files(self, *, project_path: str, query_terms: list[str], warnings: list[str]) -> list[NexusContextItem]:
        out: list[NexusContextItem] = []
        candidates: list[Path] = []

        roots: list[Path] = []
        if project_path:
            roots.append(Path(project_path))
        if self.ca_data_dir:
            roots.append(Path(self.ca_data_dir) / "skills")
            roots.append(Path("./ca_data/skills"))

        for root in roots:
            if not root.exists() or not root.is_dir():
                continue
            try:
                for p in _find_skill_files(root)[:5]:
                    candidates.append(p)
            except Exception as exc:  # noqa: BLE001
                self._warn(warnings, f"SKILL.md scan warning at {root}: {exc}")

        seen: set[str] = set()
        for p in candidates:
            sp = str(p.resolve()) if p.exists() else str(p)
            if sp in seen:
                continue
            seen.add(sp)
            content = _safe_read_text(p, max_chars=2400)
            if not content:
                continue
            out.append(
                NexusContextItem(
                    item_id=f"skill_file_{_short_hash(sp)}",
                    source_type="skill_file",
                    title=f"SKILL.md: {p.parent.name}",
                    content=content,
                    summary=_summarize_text(content, 220),
                    source_path=str(p),
                    source_id=p.name,
                    reason="Skill instructions can affect planning constraints.",
                    freshness=_freshness_label(p),
                    risk_level="medium",
                    tags=["skill_file", *query_terms[:2]],
                    metadata={"size": p.stat().st_size if p.exists() else 0},
                )
            )
            if len(out) >= 5:
                break
        return out

    def _collect_past_requirements(self, *, query_terms: list[str], warnings: list[str]) -> list[NexusContextItem]:
        out: list[NexusContextItem] = []
        req_dir = self._ca_data_path("requirements")
        if req_dir is None or not req_dir.exists():
            return out
        files = sorted(req_dir.glob("*.json"), key=_mtime_key, reverse=True)[:10]
        for p in files:
            try:
                data = json.loads(_safe_read_text(p, max_chars=12000) or "{}")
                text = "\n".join(
                    [
                        str(data.get("user_input") or ""),
                        str(data.get("interpreted_goal") or ""),
                        " ".join(str(x) for x in (data.get("functional_requirements") or [])[:5]),
                        " ".join(str(x) for x in (data.get("constraints") or [])[:5]),
                        " ".join(str(x) for x in (data.get("risks") or [])[:5]),
                        " ".join(str(x) for x in (data.get("answered_questions") or [])[:3]),
                    ]
                ).strip()
                if not text:
                    continue
                out.append(
                    NexusContextItem(
                        item_id=f"past_req_{_short_hash(str(p))}",
                        source_type="past_requirement",
                        title=f"Past Requirement: {p.stem}",
                        content=_limit_text(text, 1800),
                        summary=_summarize_text(text, 220),
                        source_path=str(p),
                        source_id=p.stem,
                        reason="Past requirements can provide reusable assumptions and constraints.",
                        freshness=_freshness_label(p),
                        risk_level="low",
                        tags=["past_requirement", *query_terms[:2]],
                        metadata={"mtime": _mtime_iso(p)},
                    )
                )
                if len(out) >= 5:
                    break
            except Exception as exc:  # noqa: BLE001
                self._warn(warnings, f"Past requirement read warning ({p.name}): {exc}")
        return out

    def _collect_past_plans(self, *, query_terms: list[str], warnings: list[str]) -> list[NexusContextItem]:
        out: list[NexusContextItem] = []
        plans_dir = self._ca_data_path("plans")
        if plans_dir is None or not plans_dir.exists():
            return out
        files = sorted(plans_dir.glob("*.plan.json"), key=_mtime_key, reverse=True)[:10]
        for p in files:
            try:
                data = json.loads(_safe_read_text(p, max_chars=14000) or "{}")
                text = "\n".join(
                    [
                        str(data.get("user_goal") or ""),
                        str(data.get("selected_architecture") or ""),
                        " ".join(str(x) for x in (data.get("implementation_steps") or [])[:3]),
                        " ".join(str(x) for x in (data.get("risks") or [])[:5]),
                        " ".join(str(x) for x in (data.get("test_plan") or [])[:5]),
                    ]
                ).strip()
                if not text:
                    continue
                out.append(
                    NexusContextItem(
                        item_id=f"past_plan_{_short_hash(str(p))}",
                        source_type="past_plan",
                        title=f"Past Plan: {p.stem}",
                        content=_limit_text(text, 1800),
                        summary=_summarize_text(text, 220),
                        source_path=str(p),
                        source_id=p.stem,
                        reason="Past plans can provide architecture and risk patterns.",
                        freshness=_freshness_label(p),
                        risk_level="medium",
                        tags=["past_plan", *query_terms[:2]],
                        metadata={"mtime": _mtime_iso(p)},
                    )
                )
                if len(out) >= 5:
                    break
            except Exception as exc:  # noqa: BLE001
                self._warn(warnings, f"Past plan read warning ({p.name}): {exc}")
        return out

    def _collect_run_logs(self, *, query_terms: list[str], warnings: list[str]) -> list[NexusContextItem]:
        out: list[NexusContextItem] = []
        runs_dir = self._ca_data_path("runs")
        if runs_dir is None or not runs_dir.exists() or not runs_dir.is_dir():
            return out
        files: list[Path] = []
        try:
            for pat in ("*/final_report.md", "*/errors.json", "*/steps.json"):
                files.extend(runs_dir.glob(pat))
        except Exception as exc:  # noqa: BLE001
            self._warn(warnings, f"Run logs scan warning: {exc}")
            return out

        for p in sorted(files, key=_mtime_key, reverse=True)[:15]:
            try:
                text = _safe_read_text(p, max_chars=2200)
                if not text:
                    continue
                out.append(
                    NexusContextItem(
                        item_id=f"run_log_{_short_hash(str(p))}",
                        source_type="run_log",
                        title=f"Run Log: {p.name}",
                        content=text,
                        summary=_summarize_text(text, 220),
                        source_path=str(p),
                        source_id=p.parent.name,
                        reason="Past run outcomes include failure/success evidence.",
                        freshness=_freshness_label(p),
                        risk_level="high" if _contains_failure_terms(text) else "medium",
                        tags=["run_log", *query_terms[:2]],
                        metadata={"mtime": _mtime_iso(p)},
                    )
                )
                if len(out) >= 5:
                    break
            except Exception as exc:  # noqa: BLE001
                self._warn(warnings, f"Run log read warning ({p.name}): {exc}")
        return out

    def _collect_project_context(self, *, project_path: str, query_terms: list[str], warnings: list[str]) -> list[NexusContextItem]:
        out: list[NexusContextItem] = []
        root = Path(project_path) if project_path else None
        if root is None or not root.exists() or not root.is_dir():
            return out

        patterns = [
            "README.md",
            "pyproject.toml",
            "requirements.txt",
            "package.json",
            "Dockerfile",
            "docker-compose.yml",
            "main.py",
            "app.py",
            "ui.html",
            ".env.example",
            "docs/*.md",
        ]

        files: list[Path] = []
        for pat in patterns:
            try:
                files.extend(root.glob(pat))
            except Exception as exc:  # noqa: BLE001
                self._warn(warnings, f"Project context scan warning ({pat}): {exc}")
        ordered = sorted({str(p.resolve()): p for p in files if p.exists()}.values(), key=_project_file_priority)

        for p in ordered[:12]:
            if _should_skip_path(p):
                continue
            text = _safe_read_text(p, max_chars=4000)
            if not text:
                continue
            rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
            out.append(
                NexusContextItem(
                    item_id=f"project_file_{_short_hash(str(p))}",
                    source_type="project_file",
                    title=f"Project File: {rel}",
                    content=text,
                    summary=_summarize_text(text, 220),
                    source_path=str(p),
                    source_id=rel,
                    reason="Project files provide local implementation constraints.",
                    freshness=_freshness_label(p),
                    risk_level="low",
                    tags=["project_file", p.name.lower(), *query_terms[:2]],
                    metadata={"mtime": _mtime_iso(p)},
                )
            )
            if len(out) >= 5:
                break
        return out

    def _score_item(self, item: NexusContextItem, *, query_terms: list[str], project_name: str) -> NexusContextItem:
        text = f"{item.title}\n{item.summary}\n{item.content}".lower()
        score = float(item.score or 0.0)
        reasons: list[str] = []

        if any(t and t in text for t in query_terms[:8]):
            score += 0.3
            reasons.append("keyword_match")
        if project_name and project_name.lower() in text:
            score += 0.2
            reasons.append("project_match")
        if item.source_type in {"skill", "memory", "past_plan"}:
            score += 0.15
            reasons.append("source_priority")
        if item.freshness in {"recent_7d", "recent_30d"}:
            score += 0.1
            reasons.append("recent")
        if _contains_failure_terms(text):
            score += 0.15
            reasons.append("failure_or_solution_signal")
        if item.source_type == "skill_file" and any(t in text for t in query_terms[:5]):
            score += 0.1
            reasons.append("skill_relevance")
        if _important_filename_bonus(item.source_path):
            score += 0.08
            reasons.append("important_filename")

        item.score = round(min(score, 1.8), 4)
        item.reason = ", ".join(reasons) if reasons else (item.reason or "context_candidate")
        return item

    def _dedupe_items(self, items: list[NexusContextItem]) -> list[NexusContextItem]:
        deduped: list[NexusContextItem] = []
        seen: set[str] = set()
        for item in items:
            key = _short_hash(f"{item.source_type}|{item.title}|{item.summary}")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _ca_data_path(self, name: str) -> Path | None:
        if not self.ca_data_dir:
            return None
        return Path(self.ca_data_dir) / name

    def _warn(self, warnings: list[str], msg: str) -> None:
        warnings.append(msg)
        if callable(self.warning_logger):
            self.warning_logger(msg)

    def _to_dict(self, pack: NexusContextPack) -> dict:
        payload = pack.model_dump()
        for it in payload.get("items", []):
            if "type" not in it:
                it["type"] = it.get("source_type", "other")
        return payload


def _extract_query_terms(user_input: str, project_name: str) -> list[str]:
    text = f"{user_input} {project_name}".strip().lower()
    tokens = re.findall(r"[\w\-\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]{2,}", text)
    stop = {"with", "from", "that", "this", "plan", "only", "phase", "task", "する", "して", "です", "ます"}
    uniq: list[str] = []
    for t in tokens:
        if t in stop:
            continue
        if t not in uniq:
            uniq.append(t)
    return uniq[:12]


def _find_skill_files(root: Path) -> list[Path]:
    results: list[Path] = []
    if _should_skip_path(root):
        return results
    max_depth = 4
    for p in root.rglob("SKILL.md"):
        try:
            rel_depth = len(p.relative_to(root).parts)
        except Exception:  # noqa: BLE001
            rel_depth = max_depth + 1
        if rel_depth > max_depth:
            continue
        if _should_skip_path(p):
            continue
        results.append(p)
    return sorted(results, key=_mtime_key, reverse=True)


def _safe_read_text(path: Path, *, max_chars: int) -> str:
    if not path.exists() or not path.is_file():
        return ""
    if _should_skip_path(path):
        return ""
    try:
        if path.stat().st_size > max(1024, max_chars * 6):
            return ""
        raw = path.read_bytes()
        if b"\x00" in raw[:2048]:
            return ""
        text = raw.decode("utf-8", errors="ignore")
        return _limit_text(text, max_chars)
    except Exception:  # noqa: BLE001
        return ""


def _limit_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)] + "..."


def _summarize_text(text: str, max_chars: int) -> str:
    normalized = " ".join(text.replace("\n", " ").split())
    return _limit_text(normalized, max_chars)


def _contains_failure_terms(text: str) -> bool:
    lowered = text.lower()
    terms = ["error", "failed", "failure", "warning", "fix", "solution", "例外", "失敗", "修正", "警告"]
    return any(t in lowered for t in terms)


def _important_filename_bonus(path_str: str) -> bool:
    lowered = path_str.lower()
    return any(k in lowered for k in ["readme", "pyproject", "requirements", "package.json", "docker", "skill.md", "final_report", "errors.json"])


def _project_file_priority(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    order = {
        "readme.md": 0,
        "pyproject.toml": 1,
        "requirements.txt": 2,
        "package.json": 3,
        "dockerfile": 4,
        "docker-compose.yml": 5,
        "main.py": 6,
        "app.py": 7,
        "ui.html": 8,
        ".env.example": 9,
    }
    return order.get(name, 50), name


def _should_skip_path(path: Path) -> bool:
    skip_parts = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build"}
    return any(part in skip_parts for part in path.parts)


def _short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:10]


def _mtime_key(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except Exception:  # noqa: BLE001
        return 0.0


def _mtime_iso(path: Path) -> str:
    ts = _mtime_key(path)
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _freshness_label(path: Path) -> str:
    try:
        ts = path.stat().st_mtime
        age_days = (datetime.now(timezone.utc).timestamp() - ts) / 86400
    except Exception:  # noqa: BLE001
        return "unknown"
    if age_days <= 7:
        return "recent_7d"
    if age_days <= 30:
        return "recent_30d"
    if age_days <= 180:
        return "recent_180d"
    return "old"


def _build_compact_text(items: list[NexusContextItem], warnings: list[str], budget: int) -> tuple[str, bool]:
    lines = ["# Nexus Context Summary", f"Collected {len(items)} relevant items.", ""]
    grouped: dict[str, list[NexusContextItem]] = {}
    for item in items:
        grouped.setdefault(item.source_type, []).append(item)

    source_titles = {
        "memory": "Memory",
        "skill": "Skills",
        "skill_file": "Skill Files",
        "past_requirement": "Past Requirements",
        "past_plan": "Past Plans",
        "run_log": "Run Logs",
        "project_file": "Project Context",
        "project_note": "Project Notes",
        "nexus_evidence": "Nexus Evidence",
        "other": "Other",
    }
    for source, source_items in grouped.items():
        lines.append(f"## {source_titles.get(source, source)}")
        for item in source_items[:4]:
            lines.extend([
                f"- title: {item.title}",
                f"  score: {item.score} reason: {item.reason}",
                f"  summary: {item.summary}",
            ])
        lines.append("")

    if warnings:
        lines.append("## Warnings")
        for w in _dedup_warnings(warnings)[:10]:
            lines.append(f"- {w}")

    text = "\n".join(lines).strip()
    if len(text) <= budget:
        return text, False
    return text[: max(0, budget - 3)] + "...", True


def _dedup_warnings(warnings: list[str]) -> list[str]:
    return list(dict.fromkeys([str(w).strip() for w in warnings if str(w).strip()]))
