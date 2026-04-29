from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, UploadFile, Form
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import subprocess
import shutil
import json
import os
import re
import base64
import tempfile
import zipfile
import threading
import platform
import ast
import textwrap
import sqlite3
import uuid
import logging
import asyncio
import sys
import difflib
import time
import inspect
import io
import hashlib
import traceback
import unicodedata
from datetime import datetime
from collections import OrderedDict
from dataclasses import dataclass, field
from agent.context_builder import ContextBuilder, FileSummaryCache, TaskV2ContextBuilder
from agent.evaluator import Evaluator
from agent.executor import Executor
from agent.io import ConversationTurn, TextIOAdapter, VoiceIOAdapter
from agent.loop import AgentLoop
from agent.memory import HybridMemoryStore, MemoryStore
from agent.planner import Planner
from agent.session import AgentSession
from agent.tools.registry import ToolRegistry, create_default_registry
from agent.types import Action, Evaluation, Plan, ToolResult
from agent.task_planning_runner import TaskPlanningRunner
from app.tts.engine_registry import EngineRegistry, TTSEngineRuntime
from app.tts.style_bert_vits2_runtime import StyleBertVITS2Runtime
from app.tts.style_bert_vits2_manager import (
    StyleBertVITS2Error,
    ensure_model_exists,
    import_model_zip,
)
from app.tts.style_bert_vits2_paths import (
    resolve_style_bert_vits2_base_dir,
    resolve_style_bert_vits2_models_dir,
)

_STYLE_BERT_VITS2_BASE_DIR = resolve_style_bert_vits2_base_dir()
_STYLE_BERT_VITS2_MODELS_DIR = resolve_style_bert_vits2_models_dir()
os.makedirs(_STYLE_BERT_VITS2_MODELS_DIR, exist_ok=True)
from app.nexus.router import router as nexus_router
from app.nexus.web_scout import plan_web_queries, run_web_search
from app.nexus.web_service import execute_nexus_web_search

# Windows Proactor: SSE切断時のConnectionResetError警告を抑制
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

from contextlib import asynccontextmanager

try:
    import jsonschema as _jsonschema  # type: ignore
except Exception:
    _jsonschema = None

@asynccontextmanager
async def lifespan(app):
    # 起動時: 前回の残骸コンテナをクリーンアップ（後方定義のためglobals経由）
    cleanup = globals().get("_cleanup_server_containers")
    if cleanup: cleanup()
    # 起動時: DBから設定を復元
    _load_opencode_settings = globals().get("_load_ensemble_settings_from_opencode_json")
    if _load_opencode_settings: _load_opencode_settings()
    _load_settings_on_startup = globals().get("_restore_settings_from_db")
    if _load_settings_on_startup: _load_settings_on_startup()
    _cleanup_legacy_settings = globals().get("_cleanup_legacy_llm_settings")
    if _cleanup_legacy_settings: _cleanup_legacy_settings()
    _cleanup_catalog_rows = globals().get("_cleanup_legacy_catalog_rows")
    if _cleanup_catalog_rows: _cleanup_catalog_rows()
    _seed_model_catalog = globals().get("seed_default_model_catalog")
    if _seed_model_catalog: _seed_model_catalog()
    _schedule_model_load = globals().get("schedule_default_model_load")
    if _schedule_model_load: _schedule_model_load(reason="startup")
    _log_tts_startup_health = globals().get("_log_tts_startup_health")
    if _log_tts_startup_health: _log_tts_startup_health()
    _load_echo_voice_ref = globals().get("_load_persisted_echo_voice_ref")
    if _load_echo_voice_ref: _load_echo_voice_ref()
    yield
    # 終了時: サーバーコンテナを全て停止
    cleanup = globals().get("_cleanup_server_containers")
    if cleanup: cleanup()

app = FastAPI(lifespan=lifespan)
app.include_router(nexus_router, prefix="/nexus", tags=["nexus"])


def build_agent_loop(
    planner: Planner,
    executor: Executor,
    evaluator: Evaluator,
    context_builder: ContextBuilder,
    memory_store: MemoryStore,
) -> AgentLoop:
    """
    main.py が直接ツール実行/評価ロジックを持たないための境界。
    実装詳細は agent/ 配下へ寄せ、ここでは依存注入のみを行う。
    """
    return AgentLoop(
        planner=planner,
        executor=executor,
        evaluator=evaluator,
        context_builder=context_builder,
        memory=memory_store,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LLM_URL = os.environ.get("LLM_URL", "http://localhost:8080/v1/chat/completions")

# 機能別LLMエンドポイント（start.batの環境変数から読む）
LLM_URL_PLANNER  = os.environ.get("CODEAGENT_LLM_PLANNER",  LLM_URL)
LLM_URL_EXECUTOR = os.environ.get("CODEAGENT_LLM_EXECUTOR", LLM_URL)
LLM_URL_CHAT     = os.environ.get("CODEAGENT_LLM_CHAT",     LLM_URL)
LLM_URL_LIGHT    = os.environ.get("CODEAGENT_LLM_LIGHT",    LLM_URL)
LLM_MODE         = os.environ.get("CODEAGENT_LLM_MODE",     "single")

print(f"[LLM] mode={LLM_MODE}")
print(f"  Planner/Verifier: {LLM_URL_PLANNER}")
print(f"  Executor:         {LLM_URL_EXECUTOR}")
print(f"  Chat/Clarify:     {LLM_URL_CHAT}")

# =========================
# ディレクトリ構造
#   ca_data/        - Gitで管理するデータフォルダ（DB・スキル・ワークスペース）
#   .codeagent/     - 機密情報専用（Gitに絶対コミットしない）
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _is_runpod_runtime() -> bool:
    has_workspace = os.path.isdir("/workspace")
    has_runpod_env = bool(os.environ.get("RUNPOD_POD_ID") or os.environ.get("RUNPOD_API_KEY"))
    forced = os.environ.get("CODEAGENT_RUNTIME", "").strip().lower()
    if forced in {"runpod", "rp"}:
        return has_workspace
    if forced in {"local", "default", "docker"}:
        return False
    return has_runpod_env and has_workspace

IS_RUNPOD_RUNTIME = _is_runpod_runtime()
DEFAULT_CA_DATA_DIR = "/workspace/ca_data" if IS_RUNPOD_RUNTIME else os.path.join(BASE_DIR, "ca_data")
CA_DATA_DIR          = os.path.abspath(os.environ.get("CODEAGENT_CA_DATA_DIR", DEFAULT_CA_DATA_DIR))
CODEAGENT_HIDDEN_DIR = os.path.join(BASE_DIR, ".codeagent")
OPENCODE_CONFIG_PATH = os.path.join(BASE_DIR, "opencode.json")
LOG_DIR = os.path.join(CA_DATA_DIR, "Logs")
OPENCODE_ENSEMBLE_LOG_DIR = os.path.join(LOG_DIR, "ensemble")
ECHOVAULT_DIR = os.path.join(CA_DATA_DIR, "EchoVault")
ECHO_UPLOAD_MAX_BYTES = max(1, int(os.environ.get("ECHO_UPLOAD_MAX_BYTES", str(100 * 1024 * 1024)) or (100 * 1024 * 1024)))
ECHO_UPLOAD_ALLOWED_FORMATS = {"wav", "mp3", "m4a", "webm", "ogg", "flac"}
LLAMA_STARTUP_LOG_PATH = os.path.join(LOG_DIR, "llama_startup.log")

os.makedirs(CA_DATA_DIR, exist_ok=True)
os.makedirs(CODEAGENT_HIDDEN_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(OPENCODE_ENSEMBLE_LOG_DIR, exist_ok=True)
os.makedirs(ECHOVAULT_DIR, exist_ok=True)

DEFAULT_WORK_DIR = os.path.join(CA_DATA_DIR, "workspace")
WORK_DIR = os.path.abspath(os.environ.get("CODEAGENT_WORK_DIR", DEFAULT_WORK_DIR))
SANDBOX_CONTAINER = "claude_sandbox"

os.makedirs(WORK_DIR, exist_ok=True)


def get_default_llama_server_path() -> str:
    env_path = os.environ.get("LLAMA_SERVER_PATH", "").strip()
    if env_path:
        return env_path

    candidates = [
        os.path.join(BASE_DIR, "llama", "llama-server.exe"),   # Windows
        os.path.join(BASE_DIR, "llama", "llama-server"),       # Linux prebuilt
        os.path.join(BASE_DIR, "llama", "bin", "llama-server") # Linux source build/prebuilt
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0] if os.name == "nt" else candidates[1]

# =========================
# Dockerタイムアウトガードレール
# =========================
# (デフォルト秒数, 最大許容秒数) — LLMが timeout= を指定したとき上限でクランプする
_DOCKER_TIMEOUT_LIMITS: dict[str, tuple[int, int]] = {
    "run_python":  (30,  300),   # 通常スクリプト: デフォ30s, 最大5分
    "run_file":    (30,  300),   # 同上
    "run_browser": (90,  300),   # Playwright: デフォ90s, 最大5分
    "run_npm":     (120, 600),   # npm install等: デフォ120s, 最大10分
    "run_node":    (30,  300),   # Node.js: デフォ30s, 最大5分
    "run_shell":   (45,  300),   # 開発用シェル実行: デフォ45s, 最大5分
}

def _clamp_docker_timeout(tool: str, requested: int | None) -> int:
    """LLM指定のタイムアウトを妥当な範囲にクランプして返す。"""
    default, max_val = _DOCKER_TIMEOUT_LIMITS.get(tool, (30, 300))
    if requested is None:
        return default
    clamped = max(5, min(int(requested), max_val))
    if clamped != int(requested):
        print(f"[timeout_guard] {tool}: {requested}s → {clamped}s (max={max_val}s)")
    return clamped

UI_DIR = "./ui"
os.makedirs(UI_DIR, exist_ok=True)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

# =========================
# Web検索 有効/無効フラグ（デフォルトOFF）
# =========================
_search_enabled = False
_search_num_results: int = 5  # デフォルト5件

# =========================
# LLMストリーミング 有効/無効フラグ（デフォルトON）
# =========================
_llm_streaming: bool = True

# =========================
# パーマネントメモリ（全プロジェクト共有）
# =========================
MEMORY_DB = os.path.join(CA_DATA_DIR, "memory.db")
MODEL_DB_PATH = os.environ.get("CODEAGENT_MODEL_DB_PATH", os.path.join(CA_DATA_DIR, "model_db.db"))
DEFAULT_SKILLS_DIR_LOCAL = os.path.join(CA_DATA_DIR, "skills")
DEFAULT_SKILLS_DIR_RUNPOD = "/workspace/ca_data/skills"
DEFAULT_SKILLS_DIR = DEFAULT_SKILLS_DIR_RUNPOD if IS_RUNPOD_RUNTIME else DEFAULT_SKILLS_DIR_LOCAL
SKILLS_DIR = os.path.abspath(os.environ.get("CODEAGENT_SKILLS_DIR", DEFAULT_SKILLS_DIR))

# =========================
# 起動時データ移行（既存ファイルを ca_data/ へ移動）
# =========================
import shutil as _shutil

def _migrate_existing_data():
    """既存のDBファイル・フォルダを ca_data/ へ移行する（初回のみ）"""
    migrations = [
        (os.path.join(BASE_DIR, "memory.db"),   MEMORY_DB),
        (os.path.join(BASE_DIR, "model_db.db"), MODEL_DB_PATH),
        (os.path.join(BASE_DIR, "workspace"),   WORK_DIR),
        (os.path.join(BASE_DIR, "skills"),      SKILLS_DIR),
    ]
    for src, dst in migrations:
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                _shutil.move(src, dst)
                print(f"[migrate] {os.path.basename(src)} → ca_data/")
            except Exception as e:
                print(f"[migrate] WARN: {src} → {dst}: {e}")

_migrate_existing_data()

def _repair_nested_project_dirs():
    """旧パス処理で project/project/... になった構成を安全に平坦化する。"""
    if not os.path.isdir(WORK_DIR):
        return
    for project in os.listdir(WORK_DIR):
        project_root = os.path.join(WORK_DIR, project)
        nested_root = os.path.join(project_root, project)
        if not os.path.isdir(project_root) or not os.path.isdir(nested_root):
            continue
        entries = [name for name in os.listdir(project_root) if not name.startswith(".")]
        if entries != [project]:
            continue
        try:
            for name in os.listdir(nested_root):
                src = os.path.join(nested_root, name)
                dst = os.path.join(project_root, name)
                if os.path.exists(dst):
                    print(f"[repair] skip nested move because destination exists: {dst}")
                    break
                _shutil.move(src, dst)
            else:
                _shutil.rmtree(nested_root, ignore_errors=True)
                print(f"[repair] flattened nested project dir: {project}/{project}")
        except Exception as e:
            print(f"[repair] WARN: {nested_root}: {e}")

_repair_nested_project_dirs()

# =========================
# 機密情報管理（.codeagent/ — Gitに絶対コミットしない）
# =========================
CREDS_FILE = os.path.join(CODEAGENT_HIDDEN_DIR, ".credentials")

def creds_load() -> dict:
    """GitHubトークン等の機密情報をロード"""
    if not os.path.exists(CREDS_FILE):
        return {"github_token": "", "github_username": ""}
    try:
        with open(CREDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"github_token": "", "github_username": ""}

def creds_save(data: dict):
    """機密情報を .codeagent/.credentials に保存（owner読み取り専用）"""
    os.makedirs(CODEAGENT_HIDDEN_DIR, exist_ok=True)
    with open(CREDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(CREDS_FILE, 0o600)
    except Exception:
        pass

# =========================
# ModelManager（動的モデル切り替え）
# =========================

import subprocess as _sp
import threading as _mm_thread
import time as _mm_time

_usage_diag_lock = _mm_thread.Lock()
_last_usage_diag: dict = {}
_windows_dxdiag_cache: dict = {"mb": -1, "checked_at": 0.0}


def _set_last_usage_diag(diag: dict):
    with _usage_diag_lock:
        global _last_usage_diag
        _last_usage_diag = diag


def _get_last_usage_diag() -> dict:
    with _usage_diag_lock:
        return dict(_last_usage_diag)

DEFAULT_MODEL_CATALOG = {}
DEFAULT_TASK_MODEL_MAP = {}
MODEL_ROLE_OPTIONS = ("plan", "chat", "search", "verify", "code", "complex", "reason", "multi", "translate")


def _parse_extra_args(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _infer_parser_name(*parts) -> str:
    joined = " ".join(str(p or "") for p in parts).lower()
    if "gpt-oss" in joined or "gpt_oss" in joined:
        return "gpt_oss"
    if "qwen" in joined:
        return "qwen_think"
    return "json"


def _runtime_spec_from_row(row: dict) -> dict:
    vram_mb = row.get("vram_mb", -1)
    try:
        vram_gb = round(float(vram_mb) / 1024, 1) if float(vram_mb) > 0 else -1
    except Exception:
        vram_gb = -1
    auto_roles = [x.strip() for x in str(row.get("auto_roles", "")).split(",") if x.strip()]
    if int(row.get("vlm_enabled", 1) or 1) == 0 and "multi" in auto_roles:
        auto_roles = [r for r in auto_roles if r != "multi"]
    ctx = _resolve_ctx_size(row.get("ctx_size"))
    if ctx < _resolve_default_ctx_size() and any(role in auto_roles for role in ("plan", "search")):
        ctx = _resolve_default_ctx_size()
    inferred_parser = _infer_parser_name(
        row.get("name", ""),
        row.get("model_key", ""),
        row.get("path", "")
    )
    parser = (row.get("parser") or "").strip() or inferred_parser
    if parser == "json" and inferred_parser != "json":
        parser = inferred_parser
    return {
        "name": row.get("name", "") or row.get("model_key", ""),
        "path": row.get("path", ""),
        "is_vlm": bool(int(row.get("is_vlm", 0) or 0)),
        "vlm_enabled": bool(int(row.get("vlm_enabled", 1) or 1)),
        "has_mmproj": bool(int(row.get("has_mmproj", 0) or 0)),
        "mmproj_path": row.get("mmproj_path", "") or "",
        "ctx": ctx,
        "gpu_layers": int(row.get("gpu_layers", 999) or 999),
        "threads": int(row.get("threads", 8) or 8),
        "vram_gb": vram_gb,
        "load_sec": max(1, int(float(row.get("load_sec", 1) or 1))),
        "parser": parser,
        "description": row.get("description", "") or row.get("notes", ""),
        "parallel": int(row.get("parallel", -1) or -1),
        "batch_size": int(row.get("batch_size", -1) or -1),
        "ubatch_size": int(row.get("ubatch_size", -1) or -1),
        "cache_type_k": row.get("cache_type_k", "") or "",
        "cache_type_v": row.get("cache_type_v", "") or "",
        "extra_args": _parse_extra_args(row.get("extra_args", "")),
        "auto_roles": auto_roles,
        "file_size_mb": int(row.get("file_size_mb", 0) or 0),
        "quantization": row.get("quantization", "") or "",
        "proven_ngl": int(row.get("proven_ngl", -1) or -1),
    }


def _parse_benchmark_profiles(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _model_text_tps(model: dict) -> float:
    profiles = _parse_benchmark_profiles(model.get("benchmark_profiles", ""))
    text_profile = profiles.get("text", {}) if isinstance(profiles, dict) else {}
    for value in (text_profile.get("tok_per_sec"), model.get("tok_per_sec", -1)):
        try:
            v = float(value)
            if v > 0:
                return v
        except Exception:
            pass
    return -1.0


def get_runtime_model_catalog(include_disabled: bool = False) -> dict:
    catalog = {}
    rows = model_db_list() if "model_db_list" in globals() else []
    for row in rows:
        model_key = (row.get("model_key") or "").strip()
        if not model_key:
            continue
        if row.get("enabled", 1) == 0:
            if not include_disabled:
                catalog.pop(model_key, None)
                continue
            spec = _runtime_spec_from_row(row)
            spec["disabled"] = True
            catalog[model_key] = spec
            continue
        catalog[model_key] = _runtime_spec_from_row(row)
    return catalog


def _role_setting_key(role: str) -> str:
    return f"role_model_{role}"


def _safe_settings_get(key: str, default: str = "") -> str:
    getter = globals().get("settings_get")
    if callable(getter):
        try:
            return getter(key)
        except Exception:
            return default
    return default


def _get_summary_token_limit() -> int:
    raw = _safe_settings_get("summary_max_tokens", "200")
    try:
        val = int(raw)
    except Exception:
        val = 200
    if val not in (200, 400, 800):
        if val < 300:
            return 200
        if val < 600:
            return 400
        return 800
    return val


def _get_read_file_inject_max_chars() -> int:
    raw = _safe_settings_get("read_file_inject_max_chars", "16000")
    try:
        val = int(raw)
    except Exception:
        val = 16000
    return max(4000, min(val, 120000))


def _is_quality_output_ok(output: str) -> bool:
    text = (output or "").strip()
    if len(text) < 24:
        return False
    lowered = text.lower()
    bad_markers = (
        "todo", "notimplemented", "未実装", "placeholder", "dummy",
        "can't", "cannot", "できません", "対応できません", "省略",
    )
    return not any(marker in lowered for marker in bad_markers)


def get_coder_ladder_keys(catalog: dict | None = None) -> list[str]:
    catalog = catalog or get_runtime_model_catalog()
    if not catalog:
        return []
    picked: list[str] = []
    for setting_key in ("coder_primary", "coder_secondary", "coder_tertiary"):
        key = _safe_settings_get(setting_key, "").strip()
        if key and key in catalog and key not in picked:
            picked.append(key)
    if len(picked) >= 3:
        return picked[:3]

    candidates = [m for m in model_db_list() if int(m.get("enabled", 1) or 1) != 0 and (m.get("model_key") in catalog)]
    ranked = sorted(
        candidates,
        key=lambda m: (
            1 if any(tag in ((m.get("name", "") + " " + m.get("model_key", "")).lower()) for tag in ("coder", "code", "qwen")) else 0,
            _model_text_tps(m),
        )
    )
    for m in ranked:
        mk = m.get("model_key", "")
        if mk and mk not in picked:
            picked.append(mk)
        if len(picked) >= 3:
            break
    return picked[:3]


def _get_auto_role_model_map(catalog: dict | None = None) -> dict:
    catalog = catalog or get_runtime_model_catalog()
    task_map = {}
    for key, spec in catalog.items():
        for role in spec.get("auto_roles", []):
            task_map.setdefault(role, key)
    return task_map


def get_runtime_task_model_map(catalog: dict | None = None, include_disabled: bool = False) -> dict:
    catalog = catalog or get_runtime_model_catalog(include_disabled=include_disabled)
    auto_map = _get_auto_role_model_map(catalog)
    planner_key = auto_map.get("plan") or (next(iter(catalog.keys())) if catalog else "")
    task_map = {}
    for role in MODEL_ROLE_OPTIONS:
        override = _safe_settings_get(_role_setting_key(role), "").strip()
        if override and override in catalog:
            task_map[role] = override
            continue
        if role in auto_map:
            task_map[role] = auto_map[role]
            continue
        if planner_key:
            task_map[role] = planner_key
    return task_map


def get_model_spec(model_key: str) -> dict:
    return get_runtime_model_catalog(include_disabled=True).get(model_key, {})


def _slugify_model_key(text: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return safe[:64] or f"model_{uuid.uuid4().hex[:8]}"


def choose_model_for_role(role: str, include_disabled: bool = False) -> str:
    catalog = get_runtime_model_catalog(include_disabled=include_disabled)
    task_map = get_runtime_task_model_map(catalog, include_disabled=include_disabled)
    if role in task_map:
        return task_map[role]
    if catalog:
        return next(iter(catalog.keys()))
    return ""


def _model_health_ok(port: int) -> bool:
    try:
        import requests as _r
        return _r.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200
    except Exception:
        return False


def _choose_default_startup_model() -> str:
    return (
        choose_model_for_role("plan", include_disabled=True)
        or choose_model_for_role("chat", include_disabled=True)
        or choose_model_for_role("code", include_disabled=True)
    )


def schedule_default_model_load(reason: str = "", force: bool = False) -> tuple[bool, str]:
    if not _model_manager.has_llama_server():
        return False, "llama_server_not_found"
    if not model_db_exists():
        return False, "no_model_db"
    models = [m for m in model_db_list() if int(m.get("enabled", 1) or 1) != 0 and m.get("path")]
    if not models:
        return False, "no_models"
    if not force and _model_health_ok(_model_manager.llm_port):
        _model_manager._sync_current_model()
        return False, "already_running"

    key = _choose_default_startup_model()
    if not key:
        return False, "no_startup_model"

    import threading as _t

    def _worker():
        try:
            print(f"[ModelManager] auto-load requested ({reason or 'unspecified'}) -> {key}")
            _model_manager.ensure_model(key)
        except Exception as e:
            print(f"[ModelManager] auto-load error ({reason or 'unspecified'}): {e}")

    _t.Thread(target=_worker, daemon=True).start()
    return True, key


def _fallback_role_recommendations(models: list[dict]) -> dict[str, list[str]]:
    recommendations: dict[str, list[str]] = {}
    if not models:
        return recommendations

    def parser_rank(model: dict) -> int:
        parser = (model.get("parser") or "").strip()
        if parser == "json":
            return 3
        if parser in ("gpt_oss", "qwen_think"):
            return 2
        return 1

    by_speed = sorted(models, key=lambda m: _model_text_tps(m), reverse=True)
    planner = by_speed[0]
    verifier = sorted(models, key=lambda m: (parser_rank(m), _model_text_tps(m)), reverse=True)[0]
    coder = sorted(
        models,
        key=lambda m: (
            1 if any(tag in ((m.get("name", "") + " " + m.get("model_key", "")).lower()) for tag in ("coder", "code", "qwen")) else 0,
            _model_text_tps(m),
        ),
        reverse=True,
    )[0]
    chat = planner

    for model in models:
        roles: list[str] = []
        if model["id"] == planner["id"]:
            roles.extend(["plan", "search"])
        if model["id"] == verifier["id"]:
            roles.append("verify")
        if model["id"] == coder["id"]:
            roles.extend(["code", "complex"])
        if model["id"] == chat["id"]:
            roles.extend(["chat", "reason"])
        if model.get("is_vlm") and int(model.get("vlm_enabled", 1) or 1) != 0:
            roles.append("multi")
        recommendations[model["id"]] = list(dict.fromkeys(roles))
    return recommendations


def recommend_roles_with_planner(models: list[dict]) -> tuple[str, dict[str, list[str]]]:
    candidates = [m for m in models if int(m.get("enabled", 1) or 1) != 0]
    if not candidates:
        return "", {}
    planner_model = max(candidates, key=lambda m: _model_text_tps(m))
    planner_key = (planner_model.get("model_key") or "").strip()
    fallback = _fallback_role_recommendations(candidates)
    if not _model_manager.has_llama_server():
        return planner_key, fallback
    if not planner_key:
        return "", fallback

    previous_key = _model_manager.current_key
    try:
        _model_manager.ensure_model(planner_key)
        planner_url = _model_manager.llm_url
        planner_parser = get_model_spec(planner_key).get("parser", "json")
        summary = []
        for model in candidates:
            profiles = _parse_benchmark_profiles(model.get("benchmark_profiles", ""))
            summary.append({
                "id": model.get("id"),
                "model_key": model.get("model_key"),
                "name": model.get("name"),
                "is_vlm": bool(model.get("is_vlm")),
                "has_mmproj": bool(model.get("has_mmproj")),
                "parser": model.get("parser"),
                "ctx_size": model.get("ctx_size"),
                "gpu_layers": model.get("gpu_layers"),
                "tok_per_sec": _model_text_tps(model),
                "profiles": profiles,
                "quantization": model.get("quantization", ""),
                "file_size_mb": model.get("file_size_mb", -1),
            })
        prompt = (
            "You are choosing default roles for a local multi-model coding assistant.\n"
            "Use each model at most for the roles it fits best.\n"
            "Available roles: plan, chat, search, verify, code, complex, reason, multi.\n"
            "Return strict JSON only in the form:\n"
            "{\"recommendations\":[{\"id\":\"...\",\"roles\":[\"plan\",\"chat\"]}]}\n"
            "Rules:\n"
            "- The fastest reliable text model should usually get plan.\n"
            "- Prefer strong JSON/reliable models for verify.\n"
            "- Prefer strongest coding models for code/complex.\n"
            "- VLM-capable models may get multi.\n"
            "- Leave roles empty for weak or redundant models.\n\n"
            f"Models:\n{json.dumps(summary, ensure_ascii=False)}"
        )
        reply, _usage = call_llm_chat([{"role": "user", "content": prompt}], llm_url=planner_url)
        parsed = extract_json(reply, parser=planner_parser)
        items = parsed.get("recommendations", []) if isinstance(parsed, dict) else []
        recs: dict[str, list[str]] = {}
        for item in items:
            mid = str(item.get("id", "")).strip()
            roles = [str(x).strip() for x in item.get("roles", []) if str(x).strip()]
            if mid:
                recs[mid] = list(dict.fromkeys(roles))
        if recs:
            for mid, roles in fallback.items():
                recs.setdefault(mid, roles)
            return planner_key, recs
    except Exception as e:
        print(f"[ModelDB] role recommendation fallback: {e}")
    finally:
        if previous_key and previous_key != _model_manager.current_key:
            try:
                _model_manager.ensure_model(previous_key)
            except Exception:
                pass
    return planner_key, fallback


ROUTER_PROMPT = """Classify the user request into ONE word.
Options: code, complex, plan, chat, search, verify
- code: writing/fixing code, implementing features
- complex: hard debugging, system architecture, algorithms
- plan: requirements, task breakdown, design discussion
- chat: general questions, explanations
- search: finding docs, researching libraries
- verify: testing, validation
Reply with ONLY the single word."""

class ModelManager:
    def __init__(self):
        self.llama_path      = get_default_llama_server_path()
        self.llm_port        = int(os.environ.get("LLM_PORT", "8080"))
        self.router_url      = os.environ.get("ROUTER_URL", "")
        self.current_key     = os.environ.get("INITIAL_MODEL", "") or choose_model_for_role("chat", include_disabled=True)
        self._process        = None
        self._lock           = _mm_thread.Lock()
        self._status         = "ready"
        self._switch_eta     = 0.0
        self._switch_callbacks = []
        self._last_start_cmd = ""
        self._last_startup_hints: list[str] = []
        self._startup_log_fd = None
        if not self.has_llama_server():
            print(f"[ModelManager] WARNING: llama-server not found: {self.llama_path}")
        # 起動時に実際に動いているモデルを検出してcurrent_keyを同期
        self._sync_current_model()

    def has_llama_server(self) -> bool:
        return bool(self.llama_path and os.path.exists(self.llama_path))

    def _sync_current_model(self):
        """llama-serverの/propsからモデルパスを取得してcurrent_keyを同期"""
        try:
            import requests as _r
            res = _r.get(f"http://127.0.0.1:{self.llm_port}/props", timeout=3)
            if res.status_code == 200:
                data = res.json()
                model_path = (
                    data.get("model_path") or
                    data.get("default_generation_settings", {}).get("model") or ""
                ).replace("\\", "/").lower()
                if model_path:
                    for key, spec in get_runtime_model_catalog(include_disabled=True).items():
                        p = spec.get("path", "").replace("\\", "/").lower()
                        if p and p in model_path:
                            if key != self.current_key:
                                print(f"[ModelManager] sync: detected {key} ({spec['name']}) on port {self.llm_port}")
                                self.current_key = key
                            return
        except Exception:
            pass  # llama-serverが未起動の場合はINITIAL_MODELのまま

    @property
    def llm_url(self):
        return f"http://127.0.0.1:{self.llm_port}/v1/chat/completions"

    @property
    def current_parser(self) -> str:
        """現在ロード中のモデルのパーサー種別を返す"""
        return get_model_spec(self.current_key).get("parser", "json")

    def _catalog(self, include_disabled: bool = False) -> dict:
        return get_runtime_model_catalog(include_disabled=include_disabled)

    def _task_model_map(self) -> dict:
        return get_runtime_task_model_map(self._catalog())

    def classify(self, message: str, plan_result: dict = None) -> str:
        """
        LFMでタスクを分類。plan_resultがあればより精度の高い判断をする。
        plan_resultなし → メッセージのみで判断（粗い）
        plan_resultあり → タスク数・要件・内容で判断（精密）
        """
        if not self.router_url:
            return self._heuristic_classify(message, plan_result)

        # プランデータがある場合はより詳細な情報をLFMに渡す
        if plan_result:
            tasks = plan_result.get("tasks", [])
            task_count = len(tasks)
            task_titles = ", ".join(t.get("title", "") for t in tasks[:5])
            requirements = "; ".join(plan_result.get("requirements", [])[:3])
            approach = plan_result.get("approach", "")[:200]
            prompt_content = (
                f"Request: {message[:200]}\n"
                f"Tasks ({task_count}): {task_titles}\n"
                f"Requirements: {requirements}\n"
                f"Approach: {approach}"
            )
        else:
            prompt_content = message[:400]

        try:
            import requests as _req
            r = _req.post(self.router_url, json={
                "messages": [
                    {"role": "system", "content": ROUTER_PROMPT},
                    {"role": "user",   "content": prompt_content},
                ],
                "temperature": 0.0, "max_tokens": 8,
            }, timeout=6)
            word = r.json()["choices"][0]["message"]["content"].strip().lower().split()[0].rstrip(".,!")
            key = self._task_model_map().get(word) or choose_model_for_role(word)
            print(f"[Router] LFM: '{word}' -> {key}")
            return key
        except Exception as e:
            print(f"[Router] LFM error: {e}, using heuristic")
            return self._heuristic_classify(message, plan_result)

    def _heuristic_classify(self, message: str, plan_result: dict = None) -> str:
        """LFM不使用時のルールベース分類"""
        if plan_result:
            tasks = plan_result.get("tasks", [])
            n = len(tasks)
            titles_text = " ".join(t.get("title","") + " " + t.get("detail","") for t in tasks)
        else:
            n = 1
            titles_text = message

        txt = (message + " " + titles_text).lower()
        complex_keywords = ["algorithm", "distributed", "concurrent", "architecture",
                            "design pattern", "optimization", "アルゴリズム", "設計", "最適化"]
        code_keywords = ["implement", "create", "build", "fix", "debug", "write",
                         "実装", "作成", "修正", "デバッグ", "コード"]

        if n >= 7 or any(k in txt for k in complex_keywords):
            return self._task_model_map().get("complex") or choose_model_for_role("complex")
        elif n >= 3 or any(k in txt for k in code_keywords):
            return self._task_model_map().get("code") or choose_model_for_role("code")
        else:
            return self._task_model_map().get("chat") or choose_model_for_role("chat")

    def ensure_model(self, key: str, on_event=None) -> bool:
        """必要なら切り替え、不要なら即return True"""
        catalog = self._catalog()
        if not catalog.get(key, {}).get("path"):
            key = self._task_model_map().get("chat") or choose_model_for_role("chat")
        if not key or key not in catalog:
            return False
        if key == self.current_key and self._status == "ready":
            return True
        # 同一モデルパス＆URL のモデルへの切り替えはアンロード不要（keyのエイリアス更新のみ）
        if self._status == "ready" and self.current_key and self.current_key in catalog:
            target_path = catalog[key].get("path", "")
            current_path = catalog[self.current_key].get("path", "")
            target_url = catalog[key].get("llm_url", "") or ""
            current_url = catalog[self.current_key].get("llm_url", "") or ""
            if target_path and target_path == current_path and target_url == current_url:
                self.current_key = key
                return True
        return self._switch(key, on_event)

    def _switch(self, key: str, on_event=None) -> bool:
        def emit(t, msg, pct=0, eta=0):
            if on_event:
                on_event({"type": t, "message": msg, "pct": pct, "eta_sec": eta})

        with self._lock:
            self._status = "switching"
            catalog = self._catalog()
            spec = catalog[key]
            self._switch_eta = _mm_time.time() + spec["load_sec"]
            prev_name = catalog.get(self.current_key, {}).get("name", "current")

            emit("model_switching", f"Unloading {prev_name}...", 10, spec["load_sec"])
            self._kill()
            _mm_time.sleep(0.5)

            emit("model_switching", f"Loading {spec['name']}...", 30,
                 max(0, int(self._switch_eta - _mm_time.time())))

            ok = self._start(spec, on_event, emit)
            if ok:
                self.current_key = key
                self._status = "ready"
                self._last_startup_hints = []  # 起動成功時はヒントをクリア
                # _current_n_ctxをモデルのctxに合わせて更新
                global _current_n_ctx
                _current_n_ctx = spec.get("ctx", _current_n_ctx)
                print(f"[ModelManager] _current_n_ctx updated to {_current_n_ctx}")
                emit("model_ready", f"{spec['name']} is ready", 100, 0)
                return True
            else:
                self._status = "error"
                emit("model_error", f"Failed to load {spec['name']}", -1, 0)
                return False

    def _kill(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try: self._process.wait(timeout=8)
            except: self._process.kill()
        self._process = None
        if self._startup_log_fd:
            try:
                self._startup_log_fd.close()
            except Exception:
                pass
            self._startup_log_fd = None
        # Windowsでポートを解放
        try:
            _sp.run(
                ["powershell", "-Command",
                 f"Get-NetTCPConnection -LocalPort {self.llm_port} "
                 f"-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | "
                 f"ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}"],
                capture_output=True, timeout=10
            )
        except: pass

    def _start(self, spec: dict, on_event, emit) -> bool:
        if not self.has_llama_server():
            print(f"[ModelManager] llama-server not found: {self.llama_path}")
            return False

        # ─── GPU設定を決定 ────────────────────────────────────────
        user_ck = (spec.get("cache_type_k") or "").strip()
        user_cv = (spec.get("cache_type_v") or "").strip()

        gpu_cfg = _calc_safe_gpu_layers(spec)
        eff_ck = user_ck or gpu_cfg["cache_type_k"]
        eff_cv = user_cv or gpu_cfg["cache_type_v"]
        calc_gpu_layers = gpu_cfg["gpu_layers"]

        proven_ngl = int(spec.get("proven_ngl", -1) or -1)
        gpu_vendor = _detect_gpu_vendor()

        # ─── プラットフォーム別の起動フロー ────────────────────
        if os.name == "nt":
            return self._start_windows(spec, eff_ck, eff_cv, gpu_vendor, emit)
        else:
            return self._start_linux(spec, eff_ck, eff_cv, gpu_vendor, emit,
                                     calc_gpu_layers, proven_ngl)

    def _start_windows(self, spec, eff_ck, eff_cv, gpu_vendor, emit) -> bool:
        """Windows: auto-fit のみ（-ngl 省略、llama.cppに任せる）。"""
        print(f"[ModelManager] Windows: auto-fit で起動")
        emit("model_switching", f"Loading {spec['name']}... (auto-fit)", 10, 0)
        result = self._try_start_once(
            spec, gpu_layers=None, eff_ck=eff_ck, eff_cv=eff_cv,
            gpu_vendor=gpu_vendor, emit=emit,
        )
        if result == "ok":
            actual_ngl = self._parse_ngl_from_log()
            if actual_ngl is not None:
                self._save_proven_ngl(spec, actual_ngl)
            return True
        return False

    def _start_linux(self, spec, eff_ck, eff_cv, gpu_vendor, emit,
                     calc_gpu_layers, proven_ngl) -> bool:
        """
        Linux (Runpod/CUDA) 3フェーズ起動:
          Phase 0: ngl_ctx_profiles キャッシュヒット → 直接起動（Phase 1-3 スキップ）
          Phase 1: auto-fit（-ngl省略）
          Phase 2: KVキャッシュ込みVRAM予測値 or プロファイル補間値から開始し指数的半減
          Phase 3: [ok_ngl, first_fail_ngl] で二分探索して最適値を確定
                   Phase 2 が一発成功の場合は [ok_ngl, total_layers_gguf] で探索

        first_fail_ngl は「Phase 2 での最初の失敗値」を保存する。
        旧コードの min(fail_ngl, ...) は「最低失敗値」を追跡するため
        Phase 3 探索範囲が崩壊する（例: [1,2]）バグがあった。
        """
        ctx = int(spec.get("ctx", _default_llm_ctx_size()) or _default_llm_ctx_size())
        predicted_ngl = self._predict_ngl_with_kv(spec, eff_ck, eff_cv)

        # GGUF から総レイヤー数を取得（Phase 3 上限として使用）
        _meta = _read_gguf_metadata(spec.get("path", ""))
        total_layers_gguf = next(
            (int(v) for k, v in _meta.items() if k.endswith(".block_count")), None
        )

        # ─── Phase 0: ngl_ctx_profiles キャッシュヒット ─────────
        profiles = self._load_ngl_ctx_profiles(spec)
        cached_ngl = self._ngl_from_profiles(profiles, spec, ctx, eff_ck, eff_cv)
        if cached_ngl > 0 and str(ctx) in profiles:
            # 完全一致キャッシュ → 直接試行（探索フェーズをすべてスキップ）
            self._kill_process()
            print(f"[ModelManager] Phase 0: ctx={ctx} キャッシュヒット ngl={cached_ngl} で直接起動")
            emit("model_switching", f"Loading {spec['name']}... (cache ngl={cached_ngl})", 10, 0)
            result = self._try_start_once(
                spec, gpu_layers=cached_ngl, eff_ck=eff_ck, eff_cv=eff_cv,
                gpu_vendor=gpu_vendor, emit=emit,
            )
            if result == "ok":
                self._save_proven_ngl(spec, cached_ngl)
                return True
            # キャッシュ値が失敗（VRAM 減少等）→ エントリ削除して通常探索へ
            print(f"[ModelManager] Phase 0: キャッシュ値 ngl={cached_ngl} 失敗 → 通常探索へ")
            self._clear_ngl_ctx_profile(spec, ctx)
            self._kill_process()

        # ─── Phase 1: auto-fit を試行 ────────────────────────
        autofit_oom = False
        print("[ModelManager] Linux Phase 1: auto-fit で起動を試行")
        emit("model_switching", f"Loading {spec['name']}... (auto-fit)", 10, 0)
        result = self._try_start_once(
            spec, gpu_layers=None, eff_ck=eff_ck, eff_cv=eff_cv,
            gpu_vendor=gpu_vendor, emit=emit,
        )
        if result == "ok":
            actual_ngl = self._parse_ngl_from_log()
            if actual_ngl is not None:
                self._save_proven_ngl(spec, actual_ngl)
                self._save_ngl_ctx_profile(spec, ctx, actual_ngl)
            return True
        autofit_oom = (result == "oom")
        if not autofit_oom:
            print("[ModelManager] auto-fit失敗(非OOM) → Phase 2へ")
        self._kill_process()

        # ─── Phase 2: 指数的半減で最初の成功値を発見 ──────────
        # 初期値の優先順位:
        #   1. ngl_ctx_profiles 補間値 (近傍 ctx からKV式で補間)
        #   2. proven_ngl (DB キャッシュ)
        #   3. predicted_ngl (KV込みVRAM予測)
        #   4. calc_gpu_layers // 2 (フォールバック)
        if cached_ngl > 0 and str(ctx) not in profiles:
            # 近傍 ctx からの補間値（完全一致でない場合）
            gpu_layers = cached_ngl
            print(f"[ModelManager] Phase 2: 近傍ctx補間値 ngl={gpu_layers} を初期値に使用")
        elif proven_ngl >= 0:
            gpu_layers = min(calc_gpu_layers, proven_ngl)
            print(f"[ModelManager] Phase 2: proven_ngl={proven_ngl} を初期値に使用 (計算値={calc_gpu_layers})")
        elif predicted_ngl > 0:
            gpu_layers = predicted_ngl
            print(f"[ModelManager] Phase 2: KV込み予測値 predicted_ngl={predicted_ngl} を初期値に使用")
        else:
            gpu_layers = max(1, calc_gpu_layers // 2)
            print(f"[ModelManager] Phase 2: 初期値を半減 {calc_gpu_layers} → {gpu_layers}")

        first_fail_ngl = -1  # Phase 2 での最初の失敗値（Phase 3 の upper bound）
        ok_ngl = -1

        _OOM_MAX_RETRIES = 6
        for _oom_attempt in range(_OOM_MAX_RETRIES + 1):
            self._kill_process()
            print(f"[ModelManager] Linux Phase 2: -ngl={gpu_layers} ({_oom_attempt + 1}/{_OOM_MAX_RETRIES + 1})")
            emit("model_switching", f"Loading {spec['name']}... -ngl={gpu_layers}", 15, 0)
            result = self._try_start_once(
                spec, gpu_layers=gpu_layers, eff_ck=eff_ck, eff_cv=eff_cv,
                gpu_vendor=gpu_vendor, emit=emit,
            )
            if result == "ok":
                ok_ngl = gpu_layers
                break
            if result != "oom":
                self._kill_process()
                return False
            if first_fail_ngl < 0:
                first_fail_ngl = gpu_layers  # 最初のOOM値を記録（Phase 3 上限）
            if gpu_layers <= 0:
                print("[ModelManager] gpu_layers=0でもOOM → リトライ不可")
                return False
            prev = gpu_layers
            gpu_layers = max(0, gpu_layers // 2)
            print(f"[ModelManager] OOM検出 → gpu_layers {prev} → {gpu_layers}")
            emit("model_switching", f"VRAM不足: GPU層 {prev}→{gpu_layers} でリトライ中...", 20, 0)
            self._kill_process()

        if ok_ngl < 0:
            print("[ModelManager] Phase 2: OOMリトライ回数を超過")
            self._kill_process()
            return False

        # ─── Phase 3: 二分探索で最適値を確定 ─────────────────
        # hi の決定ロジック:
        #   first_fail_ngl > ok_ngl → Phase 2 での最初失敗値をそのまま上限に使う
        #   first_fail_ngl == -1   → Phase 2 が一発成功（OOM なし）
        #                            auto-fit が OOM していた場合は total_layers_gguf を上限に
        #                            → predicted_ngl より高い層が収まる可能性を探索する
        self._kill_process()
        lo = ok_ngl
        if first_fail_ngl > ok_ngl:
            hi = first_fail_ngl
        elif autofit_oom and total_layers_gguf and total_layers_gguf > ok_ngl:
            # Phase 2 一発成功、auto-fit OOM → total_layers で上限を設定
            hi = total_layers_gguf
            print(f"[ModelManager] Phase 3: Phase 2 一発成功のため上限を total_layers={hi} に拡張")
        else:
            hi = ok_ngl  # 探索範囲なし → Phase 3 スキップ

        best = ok_ngl
        _BISECT_MAX = 5

        if hi - lo > 1:
            print(f"[ModelManager] Linux Phase 3: 二分探索 [{lo}..{hi}] で最適値を探索")

        for _bisect_attempt in range(_BISECT_MAX):
            if hi - lo <= 1:
                break
            mid = (lo + hi) // 2
            print(f"[ModelManager] Phase 3: 二分探索 -ngl={mid} (範囲 [{lo}..{hi}])")
            emit("model_switching", f"GPU最適化中... -ngl={mid} ({lo}-{hi})", 25, 0)
            result = self._try_start_once(
                spec, gpu_layers=mid, eff_ck=eff_ck, eff_cv=eff_cv,
                gpu_vendor=gpu_vendor, emit=emit,
            )
            if result == "ok":
                best = mid
                lo = mid
                self._kill_process()
            else:
                hi = mid
                self._kill_process()

        # best で最終起動
        if best != ok_ngl or self._process is None or self._process.poll() is not None:
            self._kill_process()
            print(f"[ModelManager] Phase 3: 最適値 -ngl={best} で最終起動")
            emit("model_switching", f"Loading {spec['name']}... -ngl={best} (最適値)", 30, 0)
            result = self._try_start_once(
                spec, gpu_layers=best, eff_ck=eff_ck, eff_cv=eff_cv,
                gpu_vendor=gpu_vendor, emit=emit,
            )
            if result != "ok":
                return False

        self._save_proven_ngl(spec, best)
        self._save_ngl_ctx_profile(spec, ctx, best)  # ctx→ngl をプロファイルに記録
        return True

    def _try_start_once(self, spec, gpu_layers, eff_ck, eff_cv, gpu_vendor, emit) -> str:
        """
        llama-serverを1回起動してヘルスチェックまで行う。
        gpu_layers=None の場合は -ngl を省略し、auto-fit に委ねる。
        Returns: "ok" | "oom" | "fail"
        """
        # ─── コマンド構築 ─────────────────────────────────────
        cmd = [
            self.llama_path,
            "--model",    spec["path"],
            "--port",     str(self.llm_port),
            "--host",     "0.0.0.0",
            "--ctx-size", str(spec["ctx"]),
            "--threads",  str(spec["threads"]),
            "--no-mmap",
        ]
        if gpu_layers is not None:
            cmd += ["-ngl", str(gpu_layers)]
        ngl_display = str(gpu_layers) if gpu_layers is not None else "auto(fit)"
        if spec.get("is_vlm") and spec.get("vlm_enabled", True):
            mmproj = str(spec.get("mmproj_path", "") or "").strip()
            if mmproj:
                if not os.path.exists(mmproj):
                    msg = f"VLM mmprojファイルが見つかりません: {mmproj}"
                    print(f"[ModelManager] {msg}")
                    self._last_startup_hints = [msg]
                    return "fail"
                cmd += ["--mmproj", mmproj]
            else:
                print(f"[ModelManager] is_vlm=True but mmproj_path not set, starting without --mmproj")
        if gpu_vendor == "nvidia":
            cmd += ["--flash-attn", "on"]
        elif gpu_vendor == "amd":
            print(f"[ModelManager] flash-attn skipped (AMD GPU)")
        if spec.get("parallel", -1) and spec.get("parallel", -1) > 0:
            cmd += ["--parallel", str(spec["parallel"])]
        if spec.get("batch_size", -1) and spec.get("batch_size", -1) > 0:
            cmd += ["--batch-size", str(spec["batch_size"])]
        if spec.get("ubatch_size", -1) and spec.get("ubatch_size", -1) > 0:
            cmd += ["--ubatch-size", str(spec["ubatch_size"])]
        if eff_ck:
            cmd += ["--cache-type-k", eff_ck]
        if eff_cv:
            cmd += ["--cache-type-v", eff_cv]
        for arg in spec.get("extra_args", []):
            cmd.append(arg)
        cmd_text = (
            f"[ModelManager] starting:"
            f" model={spec.get('path','')}"
            f" -ngl={ngl_display}"
            f" --ctx-size={spec.get('ctx')}"
            f" --threads={spec.get('threads')}"
            f" cache_k={eff_ck or 'f16(default)'}"
            f" cache_v={eff_cv or 'f16(default)'}"
            f" full_cmd={' '.join(cmd)}"
        )
        print(cmd_text)
        self._last_start_cmd = " ".join(cmd)

        # ─── プロセス起動 ─────────────────────────────────────
        try:
            flags = _sp.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            if self._startup_log_fd:
                try:
                    self._startup_log_fd.close()
                except Exception:
                    pass
                self._startup_log_fd = None
            log_fd = open(LLAMA_STARTUP_LOG_PATH, "ab")
            header = (
                f"\n\n=== {datetime.utcnow().isoformat()}Z model-start ===\n"
                f"{cmd_text}\n"
            ).encode("utf-8", errors="replace")
            log_fd.write(header)
            log_fd.flush()
            self._process = _sp.Popen(
                cmd, stdout=log_fd, stderr=log_fd, creationflags=flags
            )
            self._startup_log_fd = log_fd
        except Exception as e:
            if 'log_fd' in locals():
                try:
                    log_fd.close()
                except Exception:
                    pass
            self._startup_log_fd = None
            print(f"[ModelManager] Popen error: {e}")
            return "fail"

        # ─── ヘルスチェックループ ─────────────────────────────
        import requests as _req
        health = f"http://127.0.0.1:{self.llm_port}/health"
        for i in range(180):
            _mm_time.sleep(1)
            elapsed = i
            remaining = max(0, int(self._switch_eta - _mm_time.time()))
            pct = min(90, 30 + elapsed * 60 // spec["load_sec"])
            emit("model_switching", f"Loading {spec['name']}... {elapsed}s", pct, remaining)
            try:
                if _req.get(health, timeout=2).status_code == 200:
                    return "ok"
            except Exception:
                pass
            if self._process.poll() is not None:
                print("[ModelManager] process exited during load")
                break

        # ─── 失敗判定: OOMか否か ──────────────────────────────
        self._last_startup_hints = _infer_startup_failure_hints(LLAMA_STARTUP_LOG_PATH)
        if self._last_startup_hints:
            print(f"[ModelManager] startup hints: {self._last_startup_hints}")
        hints_text = " ".join(self._last_startup_hints).lower()
        _oom_keywords = ("vram", "out of memory", "cudamalloc", "oom", "failed to allocate",
                         "ggml_cuda_device_malloc", "メモリ")
        if any(kw in hints_text for kw in _oom_keywords):
            return "oom"
        return "fail"

    def _parse_ngl_from_log(self) -> int | None:
        """起動ログから実際に使われた n_gpu_layers の値をパースする。"""
        import re
        try:
            if not os.path.exists(LLAMA_STARTUP_LOG_PATH):
                return None
            with open(LLAMA_STARTUP_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[-200:]
            for line in reversed(lines):
                # llama.cppのログ形式: "n_gpu_layers = 12" など
                m = re.search(r"n_gpu_layers\s*=\s*(\d+)", line)
                if m:
                    val = int(m.group(1))
                    print(f"[ModelManager] ログからn_gpu_layers={val}を検出")
                    return val
        except Exception:
            pass
        return None

    def _predict_ngl_with_kv(self, spec: dict, eff_ck: str, eff_cv: str) -> int:
        """
        KVキャッシュ込みのVRAM消費をレイヤー単位で計算し、
        収まる最大 ngl を予測して返す。失敗時は -1 を返す。

        formula:
            vram_per_layer = (file_size_mb + kv_total_mb) / total_layers
            predicted_ngl  = floor((free_vram - overhead) / vram_per_layer) × safety
        """
        file_size_mb = int(spec.get("file_size_mb", 0) or 0)
        ctx = int(spec.get("ctx", _default_llm_ctx_size()) or _default_llm_ctx_size())
        model_path = spec.get("path", "")
        if not model_path or file_size_mb <= 0:
            return -1
        free_vram_mb = _get_total_free_vram_mb()
        if free_vram_mb <= 0:
            return -1

        # GGUFメタデータから総レイヤー数を取得
        meta = _read_gguf_metadata(model_path)
        total_layers = None
        for key, val in meta.items():
            if key.endswith(".block_count"):
                total_layers = int(val)
                break
        if not total_layers:
            return -1

        # KVキャッシュサイズ（全レイヤー分）。
        # q8_0 は f16 比で品質劣化がほぼなく（コード生成含め1%未満）、
        # q4_0 よりも正確な予測が必要なため q8_0 をデフォルトとする。
        ck = eff_ck or "q8_0"
        cv = eff_cv or "q8_0"
        kv_total_mb = _calc_kv_cache_mb_from_gguf(model_path, ctx, ck, cv)
        if kv_total_mb <= 0:
            return -1

        overhead_mb = 320 + 750  # llama-server固定 + CUDAコンテキスト
        available = max(0, free_vram_mb - overhead_mb)
        vram_per_layer = (file_size_mb + kv_total_mb) / total_layers
        if vram_per_layer <= 0:
            return -1

        # 10%の安全マージンを適用
        predicted = int(available / vram_per_layer * 0.90)
        predicted = max(0, min(total_layers, predicted))
        print(
            f"[ModelManager] KV込みNGL予測: free={free_vram_mb}MB, "
            f"file={file_size_mb}MB, kv={kv_total_mb}MB, layers={total_layers}, "
            f"vram/layer={vram_per_layer:.1f}MB → predicted_ngl={predicted}"
        )
        return predicted

    def _save_proven_ngl(self, spec: dict, gpu_layers: int):
        """成功した gpu_layers を proven_ngl としてDBに保存する。"""
        model_path = spec.get("path", "")
        if not model_path:
            return
        try:
            row = model_db_find_by_path(model_path)
            if row and row.get("id"):
                old_val = int(row.get("proven_ngl", -1) or -1)
                if old_val != gpu_layers:
                    model_db_update(row["id"], {"proven_ngl": gpu_layers})
                    print(f"[ModelManager] proven_ngl={gpu_layers} をDBに保存 (旧値={old_val})")
        except Exception as e:
            print(f"[ModelManager] proven_ngl保存エラー: {e}")

    # ── ngl_ctx_profiles: (ctx → ngl) キャッシュ ─────────────────────────

    def _load_ngl_ctx_profiles(self, spec: dict) -> dict:
        """DBから {ctx_str: ngl_int} のプロファイル辞書を返す。"""
        try:
            row = model_db_find_by_path(spec.get("path", ""))
            if row:
                raw = row.get("ngl_ctx_profiles", "") or ""
                if raw:
                    return json.loads(raw)
        except Exception:
            pass
        return {}

    def _save_ngl_ctx_profile(self, spec: dict, ctx: int, ngl: int) -> None:
        """(ctx, ngl) を ngl_ctx_profiles に追記してDBに保存する。"""
        try:
            row = model_db_find_by_path(spec.get("path", ""))
            if row and row.get("id"):
                profiles: dict = {}
                raw = row.get("ngl_ctx_profiles", "") or ""
                if raw:
                    profiles = json.loads(raw)
                profiles[str(ctx)] = ngl
                model_db_update(row["id"], {"ngl_ctx_profiles": json.dumps(profiles)})
                print(f"[ModelManager] ngl_ctx_profiles 更新: ctx={ctx} ngl={ngl} (計{len(profiles)}件)")
        except Exception as e:
            print(f"[ModelManager] ngl_ctx_profiles保存エラー: {e}")

    def _clear_ngl_ctx_profile(self, spec: dict, ctx: int) -> None:
        """特定 ctx のキャッシュエントリを削除する（キャッシュ値がOOMした場合に呼ぶ）。"""
        try:
            row = model_db_find_by_path(spec.get("path", ""))
            if row and row.get("id"):
                profiles: dict = {}
                raw = row.get("ngl_ctx_profiles", "") or ""
                if raw:
                    profiles = json.loads(raw)
                if str(ctx) in profiles:
                    del profiles[str(ctx)]
                    model_db_update(row["id"], {"ngl_ctx_profiles": json.dumps(profiles)})
                    print(f"[ModelManager] ngl_ctx_profiles からctx={ctx}を削除（キャッシュ値失敗）")
        except Exception:
            pass

    def _ngl_from_profiles(self, profiles: dict, spec: dict,
                            target_ctx: int, eff_ck: str, eff_cv: str) -> int:
        """
        ngl_ctx_profiles から target_ctx に適した ngl を返す。
        - 完全一致: そのまま返す
        - 近傍一致: KVキャッシュ込みのVRAM式で補間する
          ngl_new = ngl_ref × (w/layer + kv/layer@ctx_ref)
                                / (w/layer + kv/layer@ctx_new)
        失敗時は -1 を返す。
        """
        if not profiles:
            return -1
        # 完全一致
        if str(target_ctx) in profiles:
            return int(profiles[str(target_ctx)])
        # 近傍一致 → KV込み補間
        try:
            available_ctxs = {int(k): int(v) for k, v in profiles.items() if str(k).isdigit()}
            if not available_ctxs:
                return -1
            nearest_ctx = min(available_ctxs, key=lambda c: abs(c - target_ctx))
            ngl_ref = available_ctxs[nearest_ctx]
            model_path = spec.get("path", "")
            file_size_mb = int(spec.get("file_size_mb", 0) or 0)
            if not model_path or file_size_mb <= 0:
                return -1
            meta = _read_gguf_metadata(model_path)
            total_layers = next(
                (int(v) for k, v in meta.items() if k.endswith(".block_count")), None
            )
            if not total_layers:
                return -1
            ck = eff_ck or "q8_0"
            cv = eff_cv or "q8_0"
            kv_ref = _calc_kv_cache_mb_from_gguf(model_path, nearest_ctx, ck, cv)
            kv_new = _calc_kv_cache_mb_from_gguf(model_path, target_ctx, ck, cv)
            if kv_ref > 0 and kv_new > 0:
                w_per = file_size_mb / total_layers
                numer = ngl_ref * (w_per + kv_ref / total_layers)
                denom = w_per + kv_new / total_layers
                ngl_new = int(numer / denom * 0.95)  # 5% 安全マージン
            else:
                # KV計算不可 → コンテキスト比で比例縮小
                ngl_new = int(ngl_ref * nearest_ctx / target_ctx)
            ngl_new = max(1, min(total_layers, ngl_new))
            print(f"[ModelManager] ngl補間: ctx {nearest_ctx}→{target_ctx}, ngl {ngl_ref}→{ngl_new}")
            return ngl_new
        except Exception:
            return -1

    def _kill_process(self):
        """llama-serverプロセスを停止する。"""
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
        if self._startup_log_fd:
            try:
                self._startup_log_fd.close()
            except Exception:
                pass
            self._startup_log_fd = None

    def status_dict(self) -> dict:
        # switching中でない場合は実際のモデルと同期
        if self._status != "switching":
            self._sync_current_model()
        catalog = self._catalog()
        spec = catalog.get(self.current_key, {})
        return {
            "status": self._status,
            "current_key": self.current_key,
            "current_name": spec.get("name", ""),
            "vram_gb": spec.get("vram_gb", 0),
            "eta_sec": max(0, int(self._switch_eta - _mm_time.time())) if self._status == "switching" else 0,
            "catalog": {
                k: {"name": v["name"], "description": v["description"],
                    "vram_gb": v["vram_gb"], "load_sec": v["load_sec"],
                    "available": bool(v["path"])}
                for k, v in catalog.items()
            },
        }


_model_manager = ModelManager()


# =========================
# 履歴DB（プロジェクトごとSQLite）
# =========================
import threading as _threading
_db_lock = _threading.Lock()

def _get_db_path(project: str) -> str:
    path = os.path.join(WORK_DIR, project, ".history.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

def _init_db(conn: sqlite3.Connection):
    """テーブルとインデックスを初期化（初回のみ実行）"""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, mode TEXT NOT NULL,
        message TEXT NOT NULL, status TEXT NOT NULL, result TEXT
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, project TEXT NOT NULL, message TEXT NOT NULL,
        mode TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS job_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
        seq INTEGER NOT NULL, event_type TEXT NOT NULL,
        data TEXT NOT NULL, created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS snapshot_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL,
        task_id TEXT,
        commit_hash TEXT NOT NULL,
        stage TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS snapshot_archive_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL,
        task_id TEXT,
        commit_hash TEXT NOT NULL,
        stage TEXT NOT NULL,
        archived_tag TEXT NOT NULL,
        archived_at TEXT NOT NULL
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_steps_job_id ON job_steps(job_id, seq)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_job ON snapshot_history(job_id, id DESC)")
    conn.commit()

def get_db(project: str) -> sqlite3.Connection:
    """毎回新しいコネクションを開く。WALモードで読み書き並行OK。"""
    conn = sqlite3.connect(_get_db_path(project), check_same_thread=False)
    _init_db(conn)
    return conn


# ──────────────────────────────────────────────────
# パーマネントメモリ（全プロジェクト共有 SQLite）
# ──────────────────────────────────────────────────

_memory_lock = _db_lock  # 既存のDBロックを共用

def _get_memory_conn() -> sqlite3.Connection:
    """メモリDBへのコネクションを返す（テーブル初期化込み）"""
    conn = sqlite3.connect(MEMORY_DB, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS memory (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL DEFAULT 'general',
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        keywords TEXT NOT NULL DEFAULT '[]',
        source_project TEXT DEFAULT 'global',
        source_job TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        usage_count INTEGER DEFAULT 0
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mem_cat ON memory(category)")
    conn.commit()
    return conn

def memory_save(entry: dict) -> str:
    """メモリエントリを保存（idなければ新規作成）"""
    import uuid, json
    now = __import__('datetime').datetime.utcnow().isoformat()
    mid = entry.get("id") or str(uuid.uuid4())
    kw = entry.get("keywords", [])
    if isinstance(kw, list):
        kw = json.dumps(kw, ensure_ascii=False)
    with _memory_lock:
        conn = _get_memory_conn()
        try:
            existing = conn.execute("SELECT id FROM memory WHERE id=?", (mid,)).fetchone()
            if existing:
                conn.execute("""UPDATE memory SET category=?,title=?,content=?,keywords=?,
                    source_project=?,source_job=?,updated_at=? WHERE id=?""",
                    (entry.get("category","general"), entry["title"], entry["content"],
                     kw, entry.get("source_project","global"), entry.get("source_job",""),
                     now, mid))
            else:
                conn.execute("""INSERT INTO memory
                    (id,category,title,content,keywords,source_project,source_job,created_at,updated_at,usage_count)
                    VALUES (?,?,?,?,?,?,?,?,?,0)""",
                    (mid, entry.get("category","general"), entry["title"], entry["content"],
                     kw, entry.get("source_project","global"), entry.get("source_job",""), now, now))
            conn.commit()
        finally:
            conn.close()
    return mid

def memory_get_all() -> list:
    """全メモリエントリを取得（更新日時降順）"""
    import json
    conn = _get_memory_conn()
    try:
        rows = conn.execute(
            "SELECT id,category,title,content,keywords,source_project,source_job,created_at,updated_at,usage_count"
            " FROM memory ORDER BY updated_at DESC"
        ).fetchall()
        result = []
        for r in rows:
            kw = r[4]
            try: kw = json.loads(kw) if kw else []
            except: kw = []
            result.append({"id":r[0],"category":r[1],"title":r[2],"content":r[3],
                           "keywords":kw,"source_project":r[5],"source_job":r[6],
                           "created_at":r[7],"updated_at":r[8],"usage_count":r[9]})
        return result
    finally:
        conn.close()

def memory_delete(mid: str) -> bool:
    with _memory_lock:
        conn = _get_memory_conn()
        try:
            conn.execute("DELETE FROM memory WHERE id=?", (mid,))
            conn.commit()
            return True
        finally:
            conn.close()

def memory_search(query: str, limit: int = 4) -> list:
    """キーワードベースでメモリを検索してスコア順に返す"""
    import json, re
    all_entries = memory_get_all()
    if not query or not all_entries:
        return []
    # トークン化（日本語・英語混在対応）
    tokens = set(re.sub(r'[^\w\s]', ' ', query.lower()).split())
    tokens = {t for t in tokens if len(t) >= 2}
    if not tokens:
        return all_entries[:limit]
    scored = []
    import math as _math
    for e in all_entries:
        score = 0
        title_l = e["title"].lower()
        content_l = e["content"].lower()
        kw_l = " ".join(e.get("keywords", [])).lower()
        for t in tokens:
            if t in title_l:   score += 3
            if t in kw_l:      score += 2
            if t in content_l: score += 1
        if score > 0:
            # usage_count を対数スケールでブースト（頻繁に参照された知識を優先）
            score += _math.log(e.get("usage_count", 0) + 1) * 0.8
            scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    hits = [e for _, e in scored[:limit]]
    # usage_count をインクリメント（非同期で）
    if hits:
        try:
            conn = _get_memory_conn()
            conn.execute(
                f"UPDATE memory SET usage_count=usage_count+1 WHERE id IN ({','.join('?'*len(hits))})",
                [h["id"] for h in hits]
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
    return hits

def _analyze_job_for_memory(job_id: str, project: str, llm_url: str = ""):
    """ジョブログを解析して構造化メモリに知識を保存する"""
    try:
        logs = job_log_get(job_id)
        if not logs:
            return {"ok": True, "saved": 0, "reason": "no_logs"}
        # ログサマリーを構築
        task_summaries = []
        errors = []
        solutions = []
        for entry in logs:
            t = entry.get("type","")
            if t == "task_start":
                task_summaries.append(f"タスク開始: {entry.get('title','')}")
            elif t == "task_done":
                task_summaries.append(f"タスク完了: {entry.get('output','')[:100]}")
            elif t == "task_error":
                errors.append(entry.get("error","")[:150])
            elif t == "skill_generated":
                solutions.append(f"SKILL自動生成: {entry.get('skill_name','')} — {entry.get('rationale','')[:100]}")
            elif t == "tool_result":
                r = entry.get("result_preview","")
                if "ERROR" in r or "error" in r:
                    errors.append(r[:100])

        # タスク完了がなければスキップ（空ジョブ）
        if not task_summaries:
            return {"ok": True, "saved": 0, "reason": "no_task_summaries"}

        log_summary = "\n".join(task_summaries[-20:])
        error_summary = "\n".join(set(errors[:8]))
        solution_summary = "\n".join(solutions[:5])

        prompt = f"""コードエージェントの実行ログを分析し、将来の作業に役立つ知識をメモリとして抽出してください。

【実行タスク概要】
{log_summary}

【発生したエラー】
{error_summary or "(なし)"}

【実施した解決策】
{solution_summary or "(なし)"}

以下のカテゴリで、実際に役立つ知識のみ抽出してください（自明・一般的すぎる内容は不要）:
- error_solution: 再発しやすいエラーパターンとその解決策
- env_knowledge: 環境・ツール・ライブラリに関する具体的な知識（バージョン依存・OS依存等）
- workflow: 複数タスクで共通して有効だった効率的な手順・コツ

スキルとして実装すべきものは含めず、知識・経験として記録すべきものだけを抽出してください。
抽出価値がなければ {{"memories":[]}} を返してください。

【JSONのみ出力】
{{"memories":[{{"category":"error_solution","title":"タイトル（40字以内）","content":"詳細（200字以内）","keywords":["kw1","kw2"]}}]}}"""

        reply, _ = call_llm_chat(
            [{"role": "user", "content": prompt}],
            llm_url=llm_url or LLM_URL
        )
        parsed = extract_json(reply, parser=_model_manager.current_parser)
        memories = (parsed or {}).get("memories", [])
        saved = 0
        for m in memories[:5]:
            if m.get("title") and m.get("content"):
                m["source_project"] = project
                m["source_job"] = job_id
                memory_save(m)
                saved += 1
        if saved:
            print(f"[MEMORY] {saved} entries saved from job {job_id}")
        return {"ok": True, "saved": saved, "reason": "completed"}
    except Exception as e:
        print(f"[MEMORY] analyze error: {e}")
        return {"ok": False, "saved": 0, "reason": str(e)}


def save_session(session_id: str, project: str, message: str, mode: str, result: dict):
    try:
        status = "done" if (result.get("success") or result.get("status") == "done") else "error"
        with _db_lock:
            conn = get_db(project)
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?)",
                    (session_id, datetime.now().isoformat(), mode, message, status,
                     json.dumps(result, ensure_ascii=False))
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:
        print(f"[DB] save error: {e}")

# =========================
# ジョブ管理（DB永続化）
# =========================

_job_wait_events: dict = {}
_job_option_choices: dict = {}  # "{job_id}_{task_id}" -> chosen option dict
_job_wait_answers: dict = {}
import threading as _wait_threading
import threading as _job_threading

def job_create(project: str, message: str, mode: str) -> str:
    job_id = str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()
    with _db_lock:
        conn = get_db(project)
        try:
            conn.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?)",
                (job_id, project, message, mode, "queued", now, now)
            )
            conn.commit()
        finally:
            conn.close()
    return job_id

def job_update_status(project: str, job_id: str, status: str):
    now = datetime.now().isoformat()
    with _db_lock:
        conn = get_db(project)
        try:
            conn.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", (status, now, job_id))
            conn.commit()
        finally:
            conn.close()

def job_append_step(project: str, job_id: str, seq: int, event_type: str, data: dict):
    now = datetime.now().isoformat()
    with _db_lock:
        conn = get_db(project)
        try:
            conn.execute(
                "INSERT INTO job_steps (job_id, seq, event_type, data, created_at) VALUES (?,?,?,?,?)",
                (job_id, seq, event_type, json.dumps(data, ensure_ascii=False), now)
            )
            conn.commit()
        finally:
            conn.close()

def job_get_steps(project: str, job_id: str, after_seq: int = -1) -> list:
    conn = get_db(project)
    try:
        rows = conn.execute(
            "SELECT seq, event_type, data, created_at FROM job_steps WHERE job_id=? AND seq>? ORDER BY seq",
            (job_id, after_seq)
        ).fetchall()
    finally:
        conn.close()
    return [{"seq": r[0], "type": r[1], "data": json.loads(r[2]), "ts": r[3]} for r in rows]

def job_get(project: str, job_id: str) -> dict | None:
    conn = get_db(project)
    try:
        row = conn.execute(
            "SELECT id,project,message,mode,status,created_at,updated_at FROM jobs WHERE id=?",
            (job_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return {"id": row[0], "project": row[1], "message": row[2], "mode": row[3],
            "status": row[4], "created_at": row[5], "updated_at": row[6]}

def job_list(project: str, limit: int = 30) -> list:
    conn = get_db(project)
    try:
        rows = conn.execute(
            "SELECT id,message,mode,status,created_at,updated_at FROM jobs WHERE project=? ORDER BY created_at DESC LIMIT ?",
            (project, limit)
        ).fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "message": r[1], "mode": r[2], "status": r[3],
             "created_at": r[4], "updated_at": r[5]} for r in rows]


def snapshot_history_add(project: str, job_id: str, task_id, commit_hash: str, stage: str):
    now = datetime.now().isoformat()
    with _db_lock:
        conn = get_db(project)
        try:
            conn.execute(
                "INSERT INTO snapshot_history (job_id, task_id, commit_hash, stage, created_at) VALUES (?,?,?,?,?)",
                (job_id, str(task_id) if task_id is not None else "", commit_hash, stage, now)
            )
            conn.commit()
        finally:
            conn.close()


# =========================
# コンテキスト管理
# =========================

def _estimate_tokens(messages: list) -> int:
    """メッセージリストのトークン数を概算。
    日本語等のマルチバイト文字を考慮してUTF-8バイト数÷3を使用する。
    （ASCII: 1byte/char → 約4文字/token、日本語: 3byte/char → 約1-2文字/token）
    """
    total = sum(len(str(m.get("content", "")).encode("utf-8")) for m in messages)
    return total // 3

def _trim_messages(messages: list, max_ctx: int, reserve_output: int = 4096) -> list:
    """
    コンテキスト上限を超えないようにmessagesを古い順にtrimする。
    system（index=0）は常に保持。最新メッセージを優先。
    """
    budget = max_ctx - reserve_output
    if _estimate_tokens(messages) <= budget:
        return messages

    system = messages[:1]           # system promptは必ず残す
    rest = messages[1:]             # 残りのやり取り

    # 後ろから貪欲に詰める
    kept = []
    tokens_used = _estimate_tokens(system)
    for msg in reversed(rest):
        t = len(str(msg.get("content", "")).encode("utf-8")) // 3
        if tokens_used + t <= budget:
            kept.insert(0, msg)
            tokens_used += t
        else:
            # 入り切らない場合はさらにcontentを切り詰めて1件だけ入れる
            if not kept:  # 最低1件は必要
                truncated = dict(msg)
                truncated["content"] = str(msg.get("content", ""))[:800] + "\n[...truncated]"
                kept.insert(0, truncated)
            break

    return system + kept


def _calc_reserve_output(max_ctx: int, *, ratio: float = 0.25) -> int:
    """
    出力予約トークンを n_ctx 比率で動的計算する。
    ratio は 20%〜35% にクランプする。
    """
    safe_ctx = max(512, int(max_ctx or 0))
    safe_ratio = max(0.20, min(0.35, float(ratio)))
    reserve = int(safe_ctx * safe_ratio)
    return max(512, min(safe_ctx - 256, reserve))


def get_project_context(project: str, limit: int = 5) -> str:
    """LLMに渡す過去作業サマリーを生成する"""
    try:
        conn = get_db(project)
        rows = conn.execute(
            "SELECT timestamp, message, status FROM sessions WHERE status='done' ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        if not rows:
            return ""
        lines = ["【このプロジェクトのこれまでの作業履歴】"]
        for row in reversed(rows):
            ts = row[0][:10]
            lines.append(f"- [{ts}] {row[1][:100]}")
        return "\n".join(lines)
    except:
        return ""

def _normalize_project_name(name: str) -> str:
    raw = str(name or "").strip()
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", raw)
    return cleaned or "default"

def _project_root(project: str = "default") -> str:
    safe_project = _normalize_project_name(project)
    root = os.path.abspath(os.path.join(WORK_DIR, safe_project))
    work_abs = os.path.abspath(WORK_DIR)
    if root != work_abs and not root.startswith(work_abs + os.sep):
        raise ValueError(f"invalid project: {project}")
    return root

def _assert_within_project_root(project: str, target_path: str, allow_missing: bool = False) -> str:
    """target_path が project root 配下にあることを厳格に検証する（symlink考慮）。"""
    root = _project_root(project)
    root_real = os.path.realpath(root)
    target_abs = os.path.abspath(target_path)

    if allow_missing and not os.path.exists(target_abs):
        parent = os.path.dirname(target_abs) or root
        parent_real = os.path.realpath(parent)
        if parent_real != root_real and not parent_real.startswith(root_real + os.sep):
            raise ValueError(f"path escapes project root: {target_path}")
        return target_abs

    target_real = os.path.realpath(target_abs)
    if target_real != root_real and not target_real.startswith(root_real + os.sep):
        raise ValueError(f"path escapes project root: {target_path}")
    return target_abs

def _normalize_project_relpath(path: str, project: str = "default") -> str:
    raw = str(path or "").replace("\\", "/").strip()
    while raw.startswith("./"):
        raw = raw[2:]
    for prefix in (f"workspace/{project}/", f"{project}/", "workspace/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    normalized = os.path.normpath(raw).replace("\\", "/").lstrip("/")
    if normalized in ("", "."):
        raise ValueError("empty path")
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError(f"path escapes project: {path}")
    return normalized

def _project_path(project: str, path: str) -> tuple[str, str]:
    rel = _normalize_project_relpath(path, project)
    root = _project_root(project)
    full = os.path.abspath(os.path.join(root, rel))
    _assert_within_project_root(project, full, allow_missing=True)
    return full, rel

def _reset_project_dir(project: str) -> str:
    root = _project_root(project)
    os.makedirs(root, exist_ok=True)
    for name in os.listdir(root):
        target = os.path.join(root, name)
        try:
            if os.path.isdir(target) and not os.path.islink(target):
                _shutil.rmtree(target, ignore_errors=True)
            else:
                os.remove(target)
        except FileNotFoundError:
            pass
    return root

def _split_js_top_level_csv(raw: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_single = False
    in_double = False
    in_template = False
    esc = False
    for ch in raw:
        if esc:
            buf.append(ch)
            esc = False
            continue
        if ch == "\\":
            buf.append(ch)
            esc = True
            continue
        if in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
            continue
        if in_double:
            buf.append(ch)
            if ch == '"':
                in_double = False
            continue
        if in_template:
            buf.append(ch)
            if ch == "`":
                in_template = False
            continue
        if ch == "'":
            buf.append(ch)
            in_single = True
            continue
        if ch == '"':
            buf.append(ch)
            in_double = True
            continue
        if ch == "`":
            buf.append(ch)
            in_template = True
            continue
        if ch in "([{":
            depth += 1
            buf.append(ch)
            continue
        if ch in ")]}":
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts

def _extract_new_call_arg_count(src: str, open_paren_idx: int) -> int | None:
    depth = 1
    i = open_paren_idx + 1
    in_single = False
    in_double = False
    in_template = False
    esc = False
    args_buf: list[str] = []
    while i < len(src):
        ch = src[i]
        if esc:
            args_buf.append(ch)
            esc = False
            i += 1
            continue
        if ch == "\\":
            args_buf.append(ch)
            esc = True
            i += 1
            continue
        if in_single:
            args_buf.append(ch)
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            args_buf.append(ch)
            if ch == '"':
                in_double = False
            i += 1
            continue
        if in_template:
            args_buf.append(ch)
            if ch == "`":
                in_template = False
            i += 1
            continue
        if ch == "'":
            args_buf.append(ch)
            in_single = True
            i += 1
            continue
        if ch == '"':
            args_buf.append(ch)
            in_double = True
            i += 1
            continue
        if ch == "`":
            args_buf.append(ch)
            in_template = True
            i += 1
            continue
        if ch == "(":
            depth += 1
            args_buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                raw_args = "".join(args_buf).strip()
                if not raw_args:
                    return 0
                return len(_split_js_top_level_csv(raw_args))
            args_buf.append(ch)
            i += 1
            continue
        args_buf.append(ch)
        i += 1
    return None

def _script_js_static_integrity_check(project: str) -> dict:
    project_root = _project_root(project)
    script_path = os.path.join(project_root, "script.js")
    if not os.path.exists(script_path):
        return {"ok": True, "summary": "skip: script.js not found", "impact_lines": []}

    node_check = _sp.run(["node", "--check", script_path], cwd=project_root, capture_output=True, text=True)
    if node_check.returncode != 0:
        detail = (node_check.stderr or node_check.stdout or "").strip()
        return {"ok": False, "summary": "script.js syntax parse failed", "error": detail}

    with open(script_path, "r", encoding="utf-8") as f:
        script_content = f.read()
    ctor_match = re.search(r"class\s+Ball\b[\s\S]*?\bconstructor\s*\(([\s\S]*?)\)", script_content)
    if not ctor_match:
        return {"ok": True, "summary": "skip: class Ball constructor not found", "impact_lines": []}

    ctor_params = _split_js_top_level_csv(ctor_match.group(1))
    min_arity = len([p for p in ctor_params if p and "=" not in p and not p.strip().startswith("...")])
    has_rest = any(p.strip().startswith("...") for p in ctor_params if p)
    max_arity = None if has_rest else len([p for p in ctor_params if p])

    rg = _sp.run(
        ["rg", "-n", r"new Ball\(", project_root],
        cwd=project_root,
        capture_output=True,
        text=True
    )
    impact_lines = []
    if rg.returncode == 0 and rg.stdout.strip():
        impact_lines = [line.strip() for line in rg.stdout.strip().splitlines() if line.strip()]
    elif rg.returncode not in (0, 1):
        return {"ok": False, "summary": "rg failed while collecting new Ball callsites", "error": rg.stderr.strip()}

    violations = []
    for rel in impact_lines:
        path_and_line = rel.split(":", 2)
        if len(path_and_line) < 2:
            continue
        rel_path = path_and_line[0]
        call_file = rel_path if os.path.isabs(rel_path) else os.path.join(project_root, rel_path)
        try:
            with open(call_file, "r", encoding="utf-8") as cf:
                call_src = cf.read()
        except Exception:
            continue
        for m in re.finditer(r"new\s+Ball\s*\(", call_src):
            arg_count = _extract_new_call_arg_count(call_src, m.end() - 1)
            if arg_count is None:
                violations.append(f"{rel_path}:?: could not parse arguments")
                continue
            if arg_count < min_arity or (max_arity is not None and arg_count > max_arity):
                call_line = call_src.count("\n", 0, m.start()) + 1
                expect = f"{min_arity}..∞" if max_arity is None else (str(min_arity) if min_arity == max_arity else f"{min_arity}..{max_arity}")
                violations.append(f"{rel_path}:{call_line}: args={arg_count}, expected={expect}")

    if violations:
        return {
            "ok": False,
            "summary": "new Ball callsites do not match Ball constructor signature",
            "impact_lines": impact_lines,
            "violations": violations,
            "constructor_params": ctor_params,
        }
    return {
        "ok": True,
        "summary": "script.js static integrity check passed",
        "impact_lines": impact_lines,
        "constructor_params": ctor_params,
    }

# =========================
# ツール定義
# =========================

def edit_file(path: str, old_str: str, new_str: str, project: str = "default") -> str:
    """
    Claude Code方式の差分置換。
    old_strがファイル内に一意に存在する場合のみ置換する。
    存在しない・複数ある場合はエラーを返し再試行を促す。
    """
    try:
        full, path = _project_path(project, path)
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
        count = content.count(old_str)
        if count == 0:
            # 前後の空白を無視して近似マッチを探してヒントを返す
            old_stripped = old_str.strip()
            lines = content.splitlines()
            hints = [f"  line {i+1}: {l.strip()[:80]}"
                     for i, l in enumerate(lines)
                     if old_stripped[:20] in l][:3]
            hint_str = ("\n近い行:\n" + "\n".join(hints)) if hints else ""
            return f"ERROR: old_str not found in {path}.{hint_str}\n→ read_fileで現在の内容を確認してから再試行してください。"
        if count > 1:
            return f"ERROR: old_str matches {count} locations in {path}. old_strをより具体的にしてください（前後の行を含めるなど）。"
        new_content = content.replace(old_str, new_str, 1)
        with open(full, "w", encoding="utf-8") as f:
            f.write(new_content)
        if path.replace("\\", "/").endswith("script.js"):
            check = _script_js_static_integrity_check(project)
            if not check.get("ok"):
                details = []
                if check.get("impact_lines"):
                    details.append("impact:\n" + "\n".join(check.get("impact_lines", [])))
                if check.get("violations"):
                    details.append("violations:\n" + "\n".join(check.get("violations", [])))
                if check.get("error"):
                    details.append(f"error:\n{check.get('error')}")
                return f"ERROR: script.js static check failed after edit. {check.get('summary')}\n" + ("\n".join(details) if details else "")
        # 変更行を特定して報告
        old_lines = content.splitlines()
        new_lines = new_content.splitlines()
        diff_count = sum(1 for a, b in zip(old_lines, new_lines) if a != b) + abs(len(new_lines) - len(old_lines))
        return f"ok: edited {path} ({diff_count} lines changed, total {len(new_lines)} lines)"
    except FileNotFoundError:
        return f"ERROR: {path} not found. write_fileで先に作成してください。"
    except Exception as e:
        return f"ERROR: {e}"


def read_file(path: str, start_line: int = None, end_line: int = None, project: str = "default") -> str:
    """
    ファイルを読む。start_line/end_line指定で行範囲を絞れる（1-indexed）。
    大きなファイルは get_outline で構造把握してから必要箇所だけ読むこと。
    """
    try:
        full, path = _project_path(project, path)
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.splitlines()
        total = len(lines)

        if start_line is not None or end_line is not None:
            s = max(1, start_line or 1) - 1
            e = min(total, end_line or total)
            selected = lines[s:e]
            numbered = "\n".join(f"{i+s+1:4d} | {line}" for i, line in enumerate(selected))
            return f"[{path} lines {s+1}-{e} / total {total}]\n{numbered}"

        # 全体読み込み: コンテキスト残量に応じて先頭+末尾を返す
        numbered = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
        return f"[{path} - {total} lines]\n{numbered}"
    except FileNotFoundError:
        return f"ERROR: {path} not found"
    except Exception as e:
        return f"ERROR: {e}"


def get_outline(path: str, project: str = "default") -> str:
    """
    ファイルの構造概要を返す（関数/クラス/HTML要素の行番号付き一覧）。
    数千行のファイルでも全体を読まずに構造把握できる。
    """
    try:
        full, path = _project_path(project, path)
        with open(full, "r", encoding="utf-8") as f:
            content = f.read()
        lines = content.splitlines()
        total = len(lines)
        items = []

        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""

        if ext == "py":
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [a.arg for a in node.args.args]
                        items.append(f"  L{node.lineno:4d} def {node.name}({', '.join(args)})")
                    elif isinstance(node, ast.ClassDef):
                        items.append(f"  L{node.lineno:4d} class {node.name}")
                items.sort(key=lambda x: int(x.split("L")[1].split()[0]))
            except Exception:
                pass

        if ext in ("js", "ts", "jsx", "tsx"):
            for i, line in enumerate(lines):
                stripped = line.strip()
                if re.match(r"(async\s+)?function\s+\w+|const\s+\w+\s*=\s*(async\s+)?\(|^\w+\s*[=:]\s*(async\s+)?function", stripped):
                    items.append(f"  L{i+1:4d} {stripped[:80]}")

        if ext in ("html", "htm"):
            for i, line in enumerate(lines):
                stripped = line.strip()
                if re.match(r"<(div|section|header|footer|nav|main|script|style)\s", stripped, re.I):
                    items.append(f"  L{i+1:4d} {stripped[:80]}")
                elif re.match(r"<script|<style", stripped, re.I):
                    items.append(f"  L{i+1:4d} {stripped[:60]}")

        if not items:
            # 汎用: 空でない行を10行おきにサンプリング
            sampled = [(i+1, l) for i, l in enumerate(lines) if l.strip()]
            step = max(1, len(sampled) // 30)
            items = [f"  L{n:4d} {l[:80]}" for n, l in sampled[::step]]

        outline = "\n".join(items) if items else "  (no structure detected)"
        return f"[{path} outline - {total} lines total]\n{outline}\n\n→ read_file(path, start_line=N, end_line=M) で特定行を読めます"
    except FileNotFoundError:
        return f"ERROR: {path} not found"
    except Exception as e:
        return f"ERROR: {e}"

def list_files(subdir: str = "", project: str = "default") -> str:
    try:
        project_root = _project_root(project)
        target = os.path.join(project_root, _normalize_project_relpath(subdir, project)) if subdir else project_root
        result = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            rel = os.path.relpath(root, project_root).replace("\\", "/")
            for f in files:
                path = (rel + "/" + f).lstrip("./").lstrip("/")
                if rel in (".", ""):
                    path = f
                if _should_hide_preview_path(path):
                    continue
                result.append(path)
        return "\n".join(result) if result else "(empty)"
    except Exception as e:
        return f"ERROR: {e}"


def search_in_files(query: str, subdir: str = "", project: str = "default", max_results: int = 100) -> str:
    """
    プロジェクト内テキストを横断検索する（簡易grep相当）。
    query: 検索文字列（正規表現ではなく部分一致）
    subdir: 検索対象サブディレクトリ（空ならプロジェクト全体）
    max_results: 最大ヒット件数（1〜300）
    """
    try:
        q = str(query or "").strip()
        if not q:
            return "ERROR: query is empty"
        max_results = max(1, min(int(max_results), 300))
        project_root = _project_root(project)
        target = os.path.join(project_root, _normalize_project_relpath(subdir, project)) if subdir else project_root
        hits = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                rel = os.path.relpath(os.path.join(root, fname), project_root).replace("\\", "/")
                if _should_hide_preview_path(rel):
                    continue
                full = os.path.join(root, fname)
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, start=1):
                            if q in line:
                                hits.append(f"{rel}:{i}: {line.rstrip()[:200]}")
                                if len(hits) >= max_results:
                                    return "\n".join(hits)
                except Exception:
                    continue
        return "\n".join(hits) if hits else f"(no matches for '{q}')"
    except Exception as e:
        return f"ERROR: {e}"


def make_dir(path: str, project: str = "default") -> str:
    """ディレクトリを作成する（なければ再帰作成）。"""
    try:
        full, rel = _project_path(project, path)
        os.makedirs(full, exist_ok=True)
        return f"ok: directory ensured at {rel}"
    except Exception as e:
        return f"ERROR: {e}"


def move_path(src: str, dst: str, project: str = "default", overwrite: bool = False) -> str:
    """ファイル/ディレクトリを移動またはリネームする。"""
    try:
        src_full, src_rel = _project_path(project, src)
        dst_full, dst_rel = _project_path(project, dst)
        if not os.path.exists(src_full):
            return f"ERROR: source not found: {src_rel}"
        if os.path.exists(dst_full) and not overwrite:
            return f"ERROR: destination exists: {dst_rel} (set overwrite=true to replace)"
        os.makedirs(os.path.dirname(dst_full), exist_ok=True)
        if os.path.exists(dst_full) and overwrite:
            if os.path.isdir(dst_full) and not os.path.islink(dst_full):
                _shutil.rmtree(dst_full)
            else:
                os.remove(dst_full)
        _shutil.move(src_full, dst_full)
        return f"ok: moved {src_rel} -> {dst_rel}"
    except Exception as e:
        return f"ERROR: {e}"


def delete_path(path: str, project: str = "default", recursive: bool = False) -> str:
    """
    ファイル/ディレクトリを削除する。
    ディレクトリ削除は recursive=true のときのみ許可。
    """
    try:
        full, rel = _project_path(project, path)
        if not os.path.exists(full):
            return f"ERROR: not found: {rel}"
        if os.path.isdir(full) and not os.path.islink(full):
            if not recursive:
                return f"ERROR: {rel} is directory. set recursive=true to delete"
            _shutil.rmtree(full)
        else:
            os.remove(full)
        return f"ok: deleted {rel}"
    except Exception as e:
        return f"ERROR: {e}"


def run_shell(command: str, project: str = "default", timeout: int = None) -> str:
    """
    プロジェクトディレクトリでシェルコマンドを実行する。
    例: run_shell(\"pytest -q\"), run_shell(\"npm run lint\")
    timeout: デフォルト45秒、最大300秒
    """
    try:
        cmd = str(command or "").strip()
        if not cmd:
            return "ERROR: command is empty"
        cwd = _project_root(project)
        _timeout = _clamp_docker_timeout("run_shell", timeout)
        cmd, preflight = _normalize_playwright_shell_command(cmd)
        final_cmd = f"{preflight}\n{cmd}" if preflight else cmd
        shell_bin = os.environ.get("SHELL", "/bin/sh")
        if os.name != "nt" and os.path.basename(shell_bin) == "sh":
            # /bin/sh では source が使えないため、POSIX互換の "." に置換する。
            final_cmd = re.sub(r"(?m)(^|\s)source(\s+)", r"\1.\2", final_cmd)
        result = _sp.run(
            final_cmd,
            shell=True,
            executable=None if os.name == "nt" else shell_bin,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_timeout,
            encoding="utf-8",
            errors="replace"
        )
        out = (result.stdout + result.stderr).strip()
        status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
        return f"[{status}] {final_cmd}\n{out[:4000] if out else '(no output)'}"
    except _sp.TimeoutExpired:
        return f"ERROR: timeout ({_clamp_docker_timeout('run_shell', timeout)}s)."
    except Exception as e:
        return f"ERROR: {e}"


def _normalize_playwright_shell_command(command: str) -> tuple[str, str]:
    """
    Playwright関連コマンドを project .venv 実行に正規化し、必要時のみ事前チェックを返す。
    """
    cmd = str(command or "").strip()
    if not cmd:
        return cmd, ""

    normalized = cmd
    normalized = re.sub(
        r"(?<![\w./-])python\s+-m\s+playwright\s+install\s+chromium\b",
        ".venv/bin/python -m playwright install chromium",
        normalized
    )
    normalized = re.sub(
        r"(?<![\w./-])playwright\s+install\s+chromium\b",
        ".venv/bin/python -m playwright install chromium",
        normalized
    )
    normalized = re.sub(
        r"(?<![\w./-])python\s+(_browser_run\.py)\b",
        r".venv/bin/python \1",
        normalized
    )

    needs_preflight = any(token in normalized for token in (
        "playwright install chromium",
        ".venv/bin/python -m playwright",
        ".venv/bin/python _browser_run.py",
    ))
    if not needs_preflight:
        return normalized, ""

    preflight = (
        "if [ ! -x .venv/bin/python ]; then echo 'ERROR: missing .venv/bin/python'; exit 1; fi\n"
        "echo '[playwright preflight] python -m playwright --version:'\n"
        ".venv/bin/python -m playwright --version\n"
        "echo '[playwright preflight] chromium executable check:'\n"
        "if ! .venv/bin/python - <<'PY'\n"
        "from pathlib import Path\n"
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    path = Path(p.chromium.executable_path)\n"
        "    print('chromium_executable=' + str(path))\n"
        "    raise SystemExit(0 if path.exists() else 1)\n"
        "PY\n"
        "then\n"
        "  echo '[playwright preflight] chromium missing -> install chromium'\n"
        "  .venv/bin/python -m playwright install chromium\n"
        "fi"
    )
    return normalized, preflight


def _should_hide_preview_path(rel_path: str) -> bool:
    normalized = str(rel_path or '').replace('\\', '/').strip('/')
    if not normalized:
        return True
    parts = [p for p in normalized.split('/') if p and p != '.']
    if not parts:
        return True
    if any(part.startswith('.') for part in parts):
        return True
    lower_name = parts[-1].lower()
    if lower_name in {'.history.db'}:
        return True
    if lower_name.endswith('_run.py') or lower_name.endswith('_venv_run.py'):
        return True
    return False

def _server_container_name(port: int) -> str:
    return f"codeagent_server_{port}"


_LOCAL_SERVER_PROCS: dict[int, _sp.Popen] = {}

def _is_docker_available() -> bool:
    """dockerコマンドの存在確認（Runpod等の非Docker環境対策）"""
    try:
        result = _sp.run(["docker", "--version"], capture_output=True, text=True)
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _docker_sys_venv_mount_args() -> list[str]:
    """
    ローカル起動時に作成した system venv を Docker に read-only マウントする。
    （venv配下の補助ファイル参照用。Docker操作そのものは docker CLI 経由で実施）
    """
    venv_dir = (os.environ.get("CODEAGENT_SYS_VENV_DIR", "") or "").strip()
    if not venv_dir:
        return []
    abs_venv = os.path.abspath(venv_dir)
    if not os.path.isdir(abs_venv):
        return []
    return ["-v", f"{abs_venv}:/opt/codeagent/venv_sys:ro"]


def _tool_runtime_policy(tool_name: str) -> str:
    """
    ツール実行バックエンドを返す。
    - default環境: Docker優先（従来互換）
    - Runpod環境:
        * Python系(run_python/run_file) は project venv を強制
        * それ以外は docker がなければ local を許容
    """
    if IS_RUNPOD_RUNTIME:
        if tool_name in {"run_python", "run_file"}:
            return "venv"
        return "docker_or_local"
    return "docker"


def _project_venv_python(project: str) -> str:
    project_dir = _project_root(project)
    if os.name == "nt":
        return os.path.join(project_dir, ".venv", "Scripts", "python.exe")
    return os.path.join(project_dir, ".venv", "bin", "python")

def _project_venv_pip(project: str) -> str:
    project_dir = _project_root(project)
    if os.name == "nt":
        return os.path.join(project_dir, ".venv", "Scripts", "pip.exe")
    return os.path.join(project_dir, ".venv", "bin", "pip")

def _create_project_venv(project: str) -> tuple[bool, str]:
    """
    Runpod/Linux環境でも失敗しにくいよう、複数候補で .venv 作成を試行する。
    """
    import shutil
    import sys

    project_dir = _project_root(project)
    os.makedirs(project_dir, exist_ok=True)
    venv_dir = os.path.join(project_dir, ".venv")
    if os.path.isdir(venv_dir):
        return True, "already exists"

    candidates: list[list[str]] = []
    py = sys.executable
    if py:
        candidates.append([py, "-m", "venv", venv_dir])
    py3 = shutil.which("python3")
    if py3 and (not py or os.path.realpath(py3) != os.path.realpath(py)):
        candidates.append([py3, "-m", "venv", venv_dir])
    py_default = shutil.which("python")
    if py_default and all(c[0] != py_default for c in candidates):
        candidates.append([py_default, "-m", "venv", venv_dir])
    if py:
        candidates.append([py, "-m", "virtualenv", venv_dir])

    errors = []
    for cmd in candidates:
        try:
            r = _sp.run(cmd, capture_output=True, text=True, timeout=120)
            if r.returncode == 0 and os.path.exists(_project_venv_python(project)):
                return True, f"created with: {' '.join(cmd[:3])}"
            err = (r.stderr or r.stdout or "").strip()
            errors.append(f"{' '.join(cmd[:3])}: {err[:140]}")
        except Exception as e:
            errors.append(f"{' '.join(cmd[:3])}: {e}")
    return False, " | ".join(errors[-3:])


def _run_python_in_project_venv(project: str, argv: list[str], timeout: int) -> str:
    project_dir = _project_root(project)
    venv_python = _project_venv_python(project)
    if not os.path.exists(venv_python):
        created, detail = _create_project_venv(project)
        if not created or not os.path.exists(venv_python):
            return (
                "ERROR: Runpod mode requires project venv for Python execution.\n"
                f"missing: {venv_python}\n"
                f"auto-create failed: {detail}\n"
                "実行前に setup_venv(requirements=[...]) を実行してください。"
            )
    try:
        result = _sp.run(
            [venv_python, *argv],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )
        out = (result.stdout + result.stderr).strip()
        status = "ok" if result.returncode == 0 else f"exit {result.returncode}"
        return f"[{status}] {' '.join(argv)}\n{out[:4000] if out else '(no output)'}"
    except _sp.TimeoutExpired:
        return f"ERROR: timeout ({timeout}s)."
    except Exception as e:
        return f"ERROR: {e}"


def _resolve_tool_backend(tool_name: str) -> str:
    """共通ポリシーに基づき、実際の実行バックエンドを解決する。"""
    policy = _tool_runtime_policy(tool_name)
    if policy == "docker_or_local":
        return "docker" if _is_docker_available() else "local"
    return policy


def _docker_unavailable_error(tool_name: str, local_hint: str = "") -> str:
    hint = f"\n{local_hint}" if local_hint else ""
    return f"ERROR: docker is not available for {tool_name}.{hint}"


def _run_python_in_docker(project: str, rel_path: str, timeout: int) -> str:
    if not _is_docker_available():
        return _docker_unavailable_error("run_python/run_file", "Runpodでは project .venv を用意して実行してください。")
    check = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", SANDBOX_CONTAINER],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    use_exec = check.returncode == 0 and check.stdout.strip() == "true"
    container_path = f"/app/{project}/{rel_path}"
    work_dir = f"/app/{project}"
    if use_exec:
        cmd = ["docker", "exec", "-w", work_dir, SANDBOX_CONTAINER, "python", container_path]
    else:
        cmd = [
            "docker", "run", "--rm",
            "--memory=512m", "--memory-swap=512m", "--cpus=2",
            "-w", work_dir,
            "-v", f"{os.path.abspath(WORK_DIR)}:/app",
            *_docker_sys_venv_mount_args(),
            "python:3.11", "python", container_path
        ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    out = result.stdout + result.stderr
    return out[:4000] if len(out) > 4000 else out


def _execute_python_entry(project: str, rel_path: str, timeout: int, tool_name: str = "run_python") -> str:
    backend = _resolve_tool_backend(tool_name)
    if backend == "venv":
        return _run_python_in_project_venv(project, [rel_path], timeout)
    return _run_python_in_docker(project, rel_path, timeout)

def _cleanup_server_containers():
    """CodeAgentサーバーコンテナを全て停止・削除（起動時・異常時に呼ぶ）"""
    if not _is_docker_available():
        print("[run_server] skip cleanup: docker command is not available")
        return
    result = _sp.run(
        ["docker", "ps", "-a", "--filter", "name=codeagent_server_",
         "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    for name in result.stdout.strip().splitlines():
        if name.startswith("codeagent_server_"):
            _sp.run(["docker", "rm", "-f", name], capture_output=True)
            print(f"[run_server] cleaned up: {name}")

def _run_server_local(port: int, abs_project_dir: str) -> str:
    old = _LOCAL_SERVER_PROCS.get(port)
    if old and old.poll() is None:
        old.terminate()
    cmd = [sys.executable, "-m", "http.server", str(port), "--bind", "0.0.0.0"]
    proc = _sp.Popen(cmd, cwd=abs_project_dir, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
    _LOCAL_SERVER_PROCS[port] = proc
    return f"ok: HTTP server running locally at http://localhost:{port}/ (Runpod local fallback)"


def _run_server_docker(port: int, abs_project_dir: str) -> str:
    if not _is_docker_available():
        return _docker_unavailable_error("run_server", "Runpodでは docker 未使用時に local fallback が利用されます。")
    import time, urllib.request
    container_name = _server_container_name(port)
    _sp.run(["docker", "rm", "-f", container_name], capture_output=True)
    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:{port}",
        "-v", f"{abs_project_dir}:/srv:ro",  # :ro で読み取り専用マウント
        *_docker_sys_venv_mount_args(),
        "--workdir", "/srv",
        "--memory", "128m",
        "--cpus", "0.5",
        "python:3.11-slim",
        "python", "-m", "http.server", str(port), "--bind", "0.0.0.0"
    ]
    result = _sp.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip()
        # ポート競合の場合は既存プロセスを探して報告
        if "port is already allocated" in err or "bind" in err:
            return f"ERROR: port {port} is already in use by another process.\n別のポートを試してください: run_server(port=8080)"
        return f"ERROR: docker run failed:\n{err[:300]}"

    # 起動確認（最大5秒待機）
    time.sleep(1.5)
    ok = False
    for _ in range(3):
        try:
            urllib.request.urlopen(f"http://localhost:{port}", timeout=2)
            ok = True
            break
        except Exception:
            time.sleep(1)

    if not ok:
        # 起動失敗時はコンテナを削除してクリーンな状態に戻す
        logs = _sp.run(["docker", "logs", container_name], capture_output=True, text=True)
        _sp.run(["docker", "rm", "-f", container_name], capture_output=True)
        return f"ERROR: server not responding after 5s. Container removed.\nlogs: {(logs.stdout+logs.stderr)[:300]}"

    html_files = sorted(f for f in os.listdir(abs_project_dir)
                        if f.endswith((".html",".htm")) and not f.startswith("."))
    links = "\n".join(f"  http://localhost:{port}/{f}" for f in html_files)
    return (f"ok: HTTP server running in Docker at http://localhost:{port}/\n"
            f"container: {container_name} (stop with stop_server)\n"
            f"HTML files:\n{links if links else '  (none yet)'}")


def run_server(port: int = 8888, project: str = "default") -> str:
    """
    共通準備を行い、環境ごとの実装（docker/local）へ委譲する。
    """
    project_dir = os.path.join(WORK_DIR, project)
    abs_project_dir = os.path.abspath(project_dir)
    if not os.path.exists(abs_project_dir):
        return f"ERROR: project dir not found: {abs_project_dir}"
    backend = _resolve_tool_backend("run_server")
    if backend == "local":
        return _run_server_local(port, abs_project_dir)
    return _run_server_docker(port, abs_project_dir)



def setup_venv(requirements: list = None, project: str = "default") -> str:
    """
    プロジェクトフォルダに .venv/ を構築し requirements.txt を生成・インストールする。
    Dockerで動作確認済みのパッケージを .venv/ にインストールしておく。
    ユーザーは activate → python app.py で即実行できる状態にする（ローカル自動実行はしない）。
    """
    project_dir = os.path.abspath(os.path.join(WORK_DIR, project))
    venv_dir = os.path.join(project_dir, ".venv")
    req_file = os.path.join(project_dir, "requirements.txt")
    os.makedirs(project_dir, exist_ok=True)

    # requirements.txt 生成
    reqs = requirements or []
    if reqs:
        with open(req_file, "w", encoding="utf-8") as f:
            f.write("\n".join(reqs) + "\n")

    # .venv 作成
    venv_existed = os.path.isdir(venv_dir)
    if not venv_existed:
        created, detail = _create_project_venv(project)
        if not created:
            manual_activate = "source .venv/bin/activate" if os.name != "nt" else ".venv\\Scripts\\activate"
            return (f"ok: requirements.txt generated ({', '.join(reqs)})\n"
                    f"WARNING: .venv creation failed: {detail}\n"
                    f"手動: python -m venv .venv && {manual_activate} && pip install -r requirements.txt")

    # pip install（Dockerで確認済みパッケージを.venvに導入）
    pip = _project_venv_pip(project)
    installed_msg = ""
    if reqs and os.path.exists(pip):
        r2 = _sp.run([pip, "install", "-r", req_file],
                     capture_output=True, text=True, timeout=300, cwd=project_dir)
        if r2.returncode != 0:
            installed_msg = f"\nWARNING: pip install error:\n{(r2.stdout+r2.stderr).strip()[-200:]}"
        else:
            installed_msg = f"\ninstalled: {', '.join(reqs)}"

    status = "already existed" if venv_existed else "created"
    act_win = ".venv\\Scripts\\activate"
    act_lin = "source .venv/bin/activate"
    return (f"ok: .venv {status}, requirements.txt generated{installed_msg}\n"
            f"\n【ユーザー向け実行手順】\n"
            f"  Windows: {act_win} → python app.py\n"
            f"  Linux/Mac: {act_lin} → python app.py")



# ──────────────────────────────────────────────────
# ブラウザ自動化ツール（Docker内 Playwright）
# ──────────────────────────────────────────────────

BROWSER_CONTAINER = "codeagent_browser"
BROWSER_IMAGE     = "mcr.microsoft.com/playwright/python:v1.49.0-jammy"

def _ensure_browser_container(project: str) -> bool:
    """Playwrightコンテナが起動中でなければ起動する（イメージも検証する）"""
    extra_hosts = ["--add-host=host.docker.internal:host-gateway"] if os.name != "nt" else []
    check = _sp.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", BROWSER_CONTAINER],
        capture_output=True, text=True
    )
    if check.returncode == 0 and check.stdout.strip() == "true":
        # イメージが正しいか確認（異なるイメージで起動している場合は再作成）
        img_check = _sp.run(
            ["docker", "inspect", "--format", "{{.Config.Image}}", BROWSER_CONTAINER],
            capture_output=True, text=True
        )
        current_image = img_check.stdout.strip() if img_check.returncode == 0 else ""
        if BROWSER_IMAGE in current_image or current_image in BROWSER_IMAGE:
            return True  # 正しいイメージで起動中
        print(f"[browser] wrong image detected ({current_image!r}), recreating with {BROWSER_IMAGE!r}")
    # 既存のコンテナを削除してから起動
    _sp.run(["docker", "rm", "-f", BROWSER_CONTAINER], capture_output=True)
    result = _sp.run([
        "docker", "run", "-d", "--name", BROWSER_CONTAINER,
        "--memory=1g", "--cpus=2",
        *extra_hosts,
        "-v", f"{os.path.abspath(WORK_DIR)}:/app",
        *_docker_sys_venv_mount_args(),
        BROWSER_IMAGE,
        "tail", "-f", "/dev/null"  # コンテナを起動したまま待機
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[browser] container start failed: {result.stderr[:200]}")
        return False
    import time; time.sleep(2)  # 起動待ち
    return True

def _build_default_browser_script(url: str, project: str) -> str:
    """URLだけ指定された場合に使う最小のPlaywrightスクリプトを生成する。"""
    target = str(url or "").strip() or "http://localhost:8888/"
    return (
        "from playwright.sync_api import sync_playwright\n"
        "with sync_playwright() as p:\n"
        "    browser = p.chromium.launch(headless=True)\n"
        "    context = browser.new_context()\n"
        "    page = context.new_page()\n"
        f"    page.goto({target!r})\n"
        "    page.wait_for_load_state('networkidle')\n"
        "    page.screenshot(path='screenshot.png', full_page=True)\n"
        "    print(page.title())\n"
    )


def run_browser(script: str = "", project: str = "default", timeout: int = None, url: str = "") -> str:
    """
    Playwright（Python）をDockerコンテナ内で実行してブラウザ自動化を行う。
    script: Playwrightを使ったPythonコード
    - from playwright.sync_api import sync_playwright を使う
    - headless=True でブラウザを起動すること
    - スクリーンショットは /app/{project}/screenshot.png に保存できる
    - ホスト上のrun_serverにアクセスする場合: http://host.docker.internal:8888/
      （Windows/Mac: host.docker.internalが使える。Linux: --add-host=host.docker.internal:host-gateway が必要）
    timeout: 実行タイムアウト秒数（デフォルト90s、最大300s）。タイムアウトエラー時のみ増やすこと。
    例:
      from playwright.sync_api import sync_playwright
      with sync_playwright() as p:
          browser = p.chromium.launch(headless=True)
          context = browser.new_context()
          page = context.new_page()
          page.goto("http://host.docker.internal:8888/")
          page.wait_for_load_state("networkidle")
          page.screenshot(path="/app/{project}/screenshot.png")
          print(page.title())
    """
    browser_script = str(script or "").strip()
    if not browser_script:
        browser_script = _build_default_browser_script(url=url, project=project)
    _timeout = _clamp_docker_timeout("run_browser", timeout)
    project_dir = os.path.join(WORK_DIR, project)
    os.makedirs(project_dir, exist_ok=True)
    script_path = os.path.join(project_dir, "_browser_run.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(browser_script)

    backend = _resolve_tool_backend("run_browser")
    if backend == "local":
        return _run_browser_local(project, _timeout)
    return _run_browser_docker(project, _timeout)


def _run_browser_local(project: str, timeout: int) -> str:
    """
    RunpodのDocker非利用時向け: project .venv でPlaywrightスクリプトを直接実行。
    """
    project_dir = os.path.join(WORK_DIR, project)
    venv_python = _project_venv_python(project)
    if not os.path.exists(venv_python):
        return (
            "ERROR: run_browser local fallback requires project .venv.\n"
            f"missing: {venv_python}\n"
            "setup_venv(requirements=[\"playwright\"]) 実行後に再試行してください。"
        )
    try:
        preflight = (
            "echo '[browser preflight] which python:'\n"
            "command -v .venv/bin/python\n"
            "echo '[browser preflight] python -V:'\n"
            ".venv/bin/python -V\n"
            "echo '[browser preflight] pip show playwright:'\n"
            ".venv/bin/pip show playwright\n"
        )
        run_cmd = f"{preflight}{venv_python} _browser_run.py"
        result = _sp.run(
            run_cmd,
            shell=True,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )
        out = (result.stdout + result.stderr).strip()
        if "No module named 'playwright'" in out:
            return (
                "ERROR: playwright module is missing in project .venv.\n"
                "Install with: .venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium"
            )
        if "Executable doesn't exist" in out and "playwright" in out.lower():
            return (
                "ERROR: Playwright browser binary is missing.\n"
                "Run: .venv/bin/python -m playwright install chromium"
            )
        ss_path = os.path.join(project_dir, "screenshot.png")
        if os.path.exists(ss_path):
            out += f"\n[screenshot saved: screenshot.png ({os.path.getsize(ss_path)} bytes)]"
        return out[:4000] or "(no output)"
    except _sp.TimeoutExpired:
        return f"ERROR: timeout ({timeout}s). 処理に時間がかかる場合は timeout を増やしてください（最大300s）。"
    except Exception as e:
        return f"ERROR: {e}"


def _run_browser_docker(project: str, timeout: int) -> str:
    if not _is_docker_available():
        return _docker_unavailable_error("run_browser", "Runpodでは project .venv + playwright で local fallback 実行できます。")
    if not _ensure_browser_container(project):
        use_exec = False
    else:
        use_exec = True
    project_dir = os.path.join(WORK_DIR, project)
    # Linux環境でのhost.docker.internal対応
    extra_hosts = ["--add-host=host.docker.internal:host-gateway"] if os.name != "nt" else []
    if use_exec:
        cmd = ["docker", "exec", "-w", f"/app/{project}",
               BROWSER_CONTAINER, "python", f"/app/{project}/_browser_run.py"]
    else:
        cmd = [
            "docker", "run", "--rm",
            "--memory=1g", "--cpus=2",
            *extra_hosts,
            "-v", f"{os.path.abspath(WORK_DIR)}:/app",
            *_docker_sys_venv_mount_args(),
            BROWSER_IMAGE,
            "python", f"/app/{project}/_browser_run.py"
        ]

    try:
        result = _sp.run(cmd, capture_output=True, text=True, timeout=timeout,
                         encoding="utf-8", errors="replace")
        out = (result.stdout + result.stderr).strip()
        # playwrightモジュールが見つからない場合はコンテナのイメージが不正→再作成して再試行
        if use_exec and "No module named 'playwright'" in out:
            print("[browser] playwright missing in container, force-recreating with correct image...")
            _sp.run(["docker", "rm", "-f", BROWSER_CONTAINER], capture_output=True)
            if _ensure_browser_container(project):
                cmd2 = ["docker", "exec", "-w", f"/app/{project}",
                        BROWSER_CONTAINER, "python", f"/app/{project}/_browser_run.py"]
                result2 = _sp.run(cmd2, capture_output=True, text=True, timeout=timeout,
                                  encoding="utf-8", errors="replace")
                out = (result2.stdout + result2.stderr).strip()
            else:
                return "ERROR: Playwrightコンテナの再作成に失敗しました。Dockerが利用可能か確認してください。"
        # スクリーンショットが保存されたか確認
        ss_path = os.path.join(project_dir, "screenshot.png")
        if os.path.exists(ss_path):
            out += f"\n[screenshot saved: screenshot.png ({os.path.getsize(ss_path)} bytes)]"
        return out[:4000] or "(no output)"
    except _sp.TimeoutExpired:
        return f"ERROR: timeout ({timeout}s). 処理に時間がかかる場合は timeout パラメータを増やして再実行してください（最大300s）。"
    except Exception as e:
        return f"ERROR: {e}"


# ──────────────────────────────────────────────────
# npm / Node.js 実行環境ツール（Docker内）
# ──────────────────────────────────────────────────

NODE_IMAGE   = "node:20-slim"
NODE_MODULES_VOLUME = "codeagent_node_modules"  # プロジェクト間で共有

def _run_npm_local(command: str, project: str, timeout: int) -> str:
    if _sp.run(["npm", "--version"], capture_output=True, text=True).returncode != 0:
        return "ERROR: npm is not available (docker/local both unavailable)."
    return run_shell(f"npm {command}", project=project, timeout=timeout)


def _run_npm_docker(command: str, project_dir: str, timeout: int) -> str:
    if not _is_docker_available():
        return _docker_unavailable_error("run_npm", "Runpodでは npm ローカル実行にフォールバックします。")
    cmd = [
        "docker", "run", "--rm",
        "--memory=1g", "--cpus=2",
        "-w", "/app",
        "-v", f"{project_dir}:/app",
        *_docker_sys_venv_mount_args(),
        "-v", f"{BROWSER_CONTAINER}_node_modules:/app/node_modules",
        NODE_IMAGE,
        "sh", "-c", f"npm {command} 2>&1"
    ]
    _sp.run(["docker", "volume", "create", NODE_MODULES_VOLUME], capture_output=True)
    try:
        result = _sp.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        out = (result.stdout + result.stderr).strip()
        return out[:4000] or "(no output, exit code: " + str(result.returncode) + ")"
    except _sp.TimeoutExpired:
        return f"ERROR: timeout ({timeout}s). npm installなど時間のかかる処理は timeout パラメータを増やして再実行してください（最大600s）。"
    except Exception as e:
        return f"ERROR: {e}"


def run_npm(command: str, project: str = "default", timeout: int = None) -> str:
    """
    Node.js/npm コマンドをDockerコンテナ内で実行する。
    command: 実行するnpmコマンド（例: "test", "run build", "install"）
    プロジェクトフォルダをマウントして実行する。
    package.jsonが存在すること。
    timeout: 実行タイムアウト秒数（デフォルト120s、最大600s）。npm installなど長い処理でタイムアウト時に増やすこと。
    例: run_npm("test") → npm test を実行
        run_npm("run build") → npm run build を実行
        run_npm("install") → npm install を実行
    """
    project_dir = os.path.abspath(os.path.join(WORK_DIR, project))
    pkg_json = os.path.join(project_dir, "package.json")

    if not os.path.exists(pkg_json) and not command.startswith("init"):
        return "ERROR: package.json not found. Run npm init or create package.json first."

    _timeout = _clamp_docker_timeout("run_npm", timeout)
    backend = _resolve_tool_backend("run_npm")
    if backend == "local":
        return _run_npm_local(command, project, _timeout)
    return _run_npm_docker(command, project_dir, _timeout)


def _run_node_local(project: str, timeout: int) -> str:
    if _sp.run(["node", "--version"], capture_output=True, text=True).returncode != 0:
        return "ERROR: node is not available (docker/local both unavailable)."
    return run_shell("node _node_run.js", project=project, timeout=timeout)


def _run_node_docker(project_dir: str, timeout: int) -> str:
    if not _is_docker_available():
        return _docker_unavailable_error("run_node", "Runpodでは node ローカル実行にフォールバックします。")
    cmd = [
        "docker", "run", "--rm",
        "--memory=512m", "--cpus=2",
        "-w", "/app",
        "-v", f"{project_dir}:/app",
        *_docker_sys_venv_mount_args(),
        "-v", f"{BROWSER_CONTAINER}_node_modules:/app/node_modules",
        NODE_IMAGE,
        "node", "/app/_node_run.js"
    ]
    _sp.run(["docker", "volume", "create", NODE_MODULES_VOLUME], capture_output=True)
    try:
        result = _sp.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        out = (result.stdout + result.stderr).strip()
        return out[:4000] or "(no output)"
    except _sp.TimeoutExpired:
        return f"ERROR: timeout ({timeout}s). 処理に時間がかかる場合は timeout パラメータを増やして再実行してください（最大300s）。"
    except Exception as e:
        return f"ERROR: {e}"


def run_node(script: str, project: str = "default", timeout: int = None) -> str:
    """
    JavaScriptコードをDockerコンテナ内のNode.js環境で実行する。
    Webサイトの動作テスト・ロジック検証・ビルドスクリプト実行に使う。
    例:
      const fs = require('fs');
      const content = fs.readFileSync('/app/index.html', 'utf8');
      console.log('file size:', content.length);
    """
    project_dir = os.path.abspath(os.path.join(WORK_DIR, project))
    os.makedirs(project_dir, exist_ok=True)
    script_path = os.path.join(project_dir, "_node_run.js")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    _timeout = _clamp_docker_timeout("run_node", timeout)
    backend = _resolve_tool_backend("run_node")
    if backend == "local":
        return _run_node_local(project, _timeout)
    return _run_node_docker(project_dir, _timeout)


def stop_server(port: int = 8888) -> str:
    """run_serverで起動したDockerサーバーを停止・削除する"""
    proc = _LOCAL_SERVER_PROCS.get(port)
    if proc and proc.poll() is None:
        proc.terminate()
        _LOCAL_SERVER_PROCS.pop(port, None)
        return f"ok: stopped local server on port {port}"
    if not _is_docker_available():
        return "already stopped (docker unavailable)"
    container_name = _server_container_name(port)
    result = _sp.run(["docker", "rm", "-f", container_name], capture_output=True, text=True)
    if result.returncode == 0:
        return f"ok: stopped server on port {port}"
    return f"already stopped (container not found)"


def write_file(path: str = "", content: str = "", project: str = "default") -> str:
    try:
        path = str(path or "").strip()
        if not path:
            return (
                "ERROR: write_file requires 'path' and 'content'.\n"
                "Example: write_file({\"path\":\"index.html\",\"content\":\"...\"})"
            )
        if content is None:
            content = ""
        if not isinstance(content, str):
            content = str(content)
        full, path = _project_path(project, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        if path.replace("\\", "/").endswith("script.js"):
            check = _script_js_static_integrity_check(project)
            impact = "\n".join(check.get("impact_lines", []))
            if not check.get("ok"):
                details = []
                if impact:
                    details.append("impact:\n" + impact)
                if check.get("violations"):
                    details.append("violations:\n" + "\n".join(check.get("violations", [])))
                if check.get("error"):
                    details.append(f"error:\n{check.get('error')}")
                return f"ERROR: wrote {len(content)} chars to {path}, but static check failed. {check.get('summary')}\n" + ("\n".join(details) if details else "")
            if impact:
                return f"ok: wrote {len(content)} chars to {path}\nstatic_check: {check.get('summary')}\nimpact:\n{impact}"
        preview = "\n".join(content.splitlines()[:3])
        return f"ok: wrote {len(content)} chars to {path}\npreview:\n{preview}"
    except Exception as e:
        return f"ERROR: {e}"

def patch_function(path: str, function_name: str, new_code: str, project: str = "default") -> str:
    try:
        full, path = _project_path(project, path)
        with open(full, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        lines = source.splitlines(keepends=True)

        target_node = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    target_node = node
                    break

        if target_node is None:
            return f"ERROR: function '{function_name}' not found in {path}"

        start = target_node.lineno - 1
        end = target_node.end_lineno

        if target_node.decorator_list:
            start = target_node.decorator_list[0].lineno - 1

        original_indent = len(lines[start]) - len(lines[start].lstrip())
        new_lines = textwrap.dedent(new_code).splitlines(keepends=True)
        indented_new = [" " * original_indent + l for l in new_lines]
        if not indented_new[-1].endswith("\n"):
            indented_new[-1] += "\n"

        new_source_lines = lines[:start] + indented_new + lines[end:]
        new_source = "".join(new_source_lines)

        ast.parse(new_source)  # 構文チェック

        with open(full, "w", encoding="utf-8") as f:
            f.write(new_source)

        return f"ok: patched function '{function_name}' in {path} (lines {start+1}-{end})"
    except SyntaxError as e:
        return f"SYNTAX ERROR in new_code: {e}"
    except Exception as e:
        return f"ERROR: {e}"

def run_python(code: str, project: str = "default", timeout: int = None) -> str:
    """
    Pythonコードをサンドボックス（Docker）で実行する。
    _run.py はプロジェクトフォルダ内に配置し、プロジェクトのファイルにアクセス可能。
    Dockerは WORK_DIR 全体をマウントし /app/{project}/ がプロジェクトフォルダ。
    timeout: 実行タイムアウト秒数（デフォルト30s、最大300s）。タイムアウトエラー時のみ増やすこと。
    """
    _timeout = _clamp_docker_timeout("run_python", timeout)
    try:
        project_dir = os.path.join(WORK_DIR, project)
        os.makedirs(project_dir, exist_ok=True)
        run_file_path = os.path.join(project_dir, "_run.py")
        with open(run_file_path, "w", encoding="utf-8") as f:
            f.write(code)
        return _execute_python_entry(project, "_run.py", _timeout, tool_name="run_python")
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout ({_timeout}s). 処理に時間がかかる場合は timeout パラメータを増やして再実行してください（最大300s）。"
    except Exception as e:
        return f"ERROR: {e}"

def run_file(path: str, project: str = "default", timeout: int = None) -> str:
    """
    プロジェクト内のPythonファイルをサンドボックスで実行する。
    path は プロジェクトフォルダ内の相対パス（例: "app.py", "tests/test_main.py"）。
    timeout: 実行タイムアウト秒数（デフォルト30s、最大300s）。タイムアウトエラー時のみ増やすこと。
    """
    _timeout = _clamp_docker_timeout("run_file", timeout)
    try:
        _, rel_path = _project_path(project, path)
        _, ext = os.path.splitext(rel_path.lower())
        if ext == ".js":
            return (
                "ERROR: .js files are restricted to Node/Browser runners.\n"
                "Use run_node(script=...) or run_browser(script=...) instead of run_file."
            )
        if ext != ".py":
            return (
                f"ERROR: unsupported file extension for run_file: {ext or '(none)'}.\n"
                "run_file supports Python files (.py) only."
            )
        return _execute_python_entry(project, rel_path, _timeout, tool_name="run_file")
    except subprocess.TimeoutExpired:
        return f"ERROR: timeout ({_timeout}s). 処理に時間がかかる場合は timeout パラメータを増やして再実行してください（最大300s）。"
    except Exception as e:
        return f"ERROR: {e}"

# =========================
# 検索クエリ無害化
# =========================
_SENSITIVE_PATTERNS = [
    # 長い英数字トークン（APIキー・ハッシュ等、32文字以上）
    (re.compile(r'\b[A-Za-z0-9_\-]{32,}\b'), '[REDACTED_KEY]'),
    # 認証情報パターン (key=xxx / token: xxx / secret=xxx)
    (re.compile(r'(?i)(api[_-]?key|token|bearer|secret|password|passwd|pwd|auth)[\s=:]+[^\s]{6,}'), '[REDACTED_AUTH]'),
    # sk-/pk-/ghp_ などのサービストークンプレフィックス
    (re.compile(r'(?i)\b(sk|pk|ghp|ghr|xox[bprs]|ya29)[_\-][A-Za-z0-9_\-]{10,}'), '[REDACTED_TOKEN]'),
    # Windowsフルパス (C:\Users\username\... / C:\AI\...)
    (re.compile(r'(?i)[A-Za-z]:\\(?:Users\\[^\\\s]+|[^\s]{3,})'), '[WIN_PATH]'),
    # Windowsユーザー名だけ (\Users\username)
    (re.compile(r'(?i)\\[Uu]sers\\([^\\\s]+)'), '\\Users\\[USER]'),
    # Unix home path (/home/username)
    (re.compile(r'/home/[^/\s]+'), '/home/[USER]'),
    # プライベートIPアドレス
    (re.compile(r'(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}'), '[LOCAL_IP]'),
    # localhostとポート
    (re.compile(r'localhost:\d+'), 'localhost:[PORT]'),
    # メールアドレス
    (re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'), '[EMAIL]'),
    # 電話番号（日本形式）
    (re.compile(r'0\d{1,4}[\-\s]?\d{1,4}[\-\s]?\d{4}'), '[PHONE]'),
]

# クエリ長制限（512文字超はブロック）
_MAX_QUERY_LEN = 512

def sanitize_query(query: str) -> tuple[str, list[str]]:
    """
    検索クエリから機密情報を除去する。
    戻り値: (無害化済みクエリ, 除去した項目のログ)
    除去ログはサーバーコンソールにのみ出力し、クライアントには返さない。
    """
    removed = []
    # 長さ制限
    if len(query) > _MAX_QUERY_LEN:
        removed.append(f"query_too_long: {len(query)} chars truncated to {_MAX_QUERY_LEN}")
        query = query[:_MAX_QUERY_LEN]

    sanitized = query
    for pattern, replacement in _SENSITIVE_PATTERNS:
        matches = pattern.findall(sanitized)
        if matches:
            sanitized = pattern.sub(replacement, sanitized)
            removed.append(f"redacted: {pattern.pattern[:40]!r} ({len(matches)} match)")

    cleaned = sanitized.strip()
    # 置換後にREDACTEDだらけになった場合はブロック
    redacted_ratio = cleaned.count('[REDACTED') / max(len(cleaned.split()), 1)
    if not cleaned or redacted_ratio > 0.6:
        return "", removed + ["blocked: query consisted mostly of sensitive data"]

    return cleaned, removed


def _format_web_search_items(items: list[dict], *, limit: int) -> list[str]:
    lines: list[str] = []
    for row in (items or [])[:limit]:
        title = str(row.get("title") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        url = str(row.get("url") or "").strip()
        if title and snippet:
            line = f"[{title[:80]}] {snippet[:150]}"
            if url and url != "about:blank":
                line += f" ({url[:140]})"
            lines.append(line)
        elif title:
            lines.append(f"[{title[:80]}]")
        elif snippet:
            lines.append(snippet[:150])
    return lines


def _format_provider_errors_for_context(provider_errors: dict | None, *, prefix: str = "provider_errors") -> str:
    if not isinstance(provider_errors, dict) or not provider_errors:
        return ""
    segments: list[str] = []
    for provider, errors in provider_errors.items():
        normalized_errors: list[str] = []
        if isinstance(errors, list):
            normalized_errors = [str(err).strip() for err in errors if str(err).strip()]
        elif errors is not None:
            text = str(errors).strip()
            if text:
                normalized_errors = [text]
        if not normalized_errors:
            continue
        segments.append(f"{provider}: {', '.join(normalized_errors[:2])}")
    if not segments:
        return ""
    return f"{prefix}: " + " | ".join(segments)


def _run_lightweight_prefetch_nexus_search_for_context(
    query: str,
    *,
    num_results: int,
    mode: str = "quick",
    depth: str = "quick",
    max_queries: int = 1,
    scope: str | list[str] | None = None,
    language: str | None = None,
) -> dict:
    """
    Nexus Evidence保存を行わない lightweight prefetch 用 Nexus Web検索ヘルパー。
    - plan_web_queries + run_web_search を内部実行
    - items と UI 向けイベントpayloadを構造化して返す
    """
    # これはNexus Evidence保存を行わない lightweight prefetch であり、nexus_web_search とは別用途。
    global _search_enabled

    empty_payload = {
        "provider_errors": {},
        "skipped_providers": {},
        "non_fatal": False,
        "message": "",
        "selected_provider": "unknown",
        "total_items": 0,
    }

    if not _search_enabled:
        return {
            "ok": False,
            "query": query,
            "message": "SEARCH_DISABLED: Web search is currently disabled. The user must enable it from the UI.",
            "items": [],
            "context_text": "SEARCH_DISABLED: Web search is currently disabled. The user must enable it from the UI.",
            "event_payload": empty_payload,
            "search_output": {},
            "stub_only_non_fatal": False,
        }

    safe_query, removed = sanitize_query(query)
    if not safe_query:
        blocked = "SEARCH_BLOCKED: Query contained only sensitive data and was not sent."
        return {
            "ok": False,
            "query": "",
            "message": blocked,
            "items": [],
            "context_text": blocked,
            "event_payload": empty_payload,
            "search_output": {},
            "stub_only_non_fatal": False,
        }
    if removed:
        print(f"[SEARCH][SANITIZED] original_len={len(query)} removed={removed}")

    requested_depth = (depth or mode or "quick").strip() or "quick"
    capped = max(1, min(int(num_results or _search_num_results or 5), 20))
    query_plan: list[str] = []
    try:
        query_plan = plan_web_queries(
            safe_query,
            mode=mode,
            depth=requested_depth,
            max_queries=max_queries,
            scope=scope,
            language=language,
        )
        search_output = run_web_search(
            query_plan,
            mode=mode,
            depth=requested_depth,
            max_results_per_query=capped,
            scope=scope,
            language=language,
        )
    except Exception as e:
        error_text = f"Search error: {e}"
        print(json.dumps({
            "event": "agent_lightweight_prefetch_web_search",
            "called": True,
            "invoked_path": "lightweight_prefetch",
            "queries": query_plan or [safe_query],
            "provider": "unknown",
            "total_items": 0,
            "provider_errors": {"exception": str(e)},
        }, ensure_ascii=False))
        return {
            "ok": False,
            "query": safe_query,
            "message": error_text,
            "items": [],
            "context_text": error_text,
            "event_payload": {
                **empty_payload,
                "message": error_text,
                "non_fatal": True,
            },
            "search_output": {},
            "stub_only_non_fatal": False,
        }

    items = search_output.get("items") or []
    selected_provider = str(search_output.get("selected_provider") or search_output.get("provider") or "unknown")
    provider_errors = search_output.get("provider_errors") or {}
    total_items = int(search_output.get("total_items") or len(items))
    print(json.dumps({
        "event": "agent_lightweight_prefetch_web_search",
        "called": True,
        "invoked_path": "lightweight_prefetch",
        "queries": query_plan or [safe_query],
        "provider": selected_provider,
        "total_items": total_items,
        "provider_errors": provider_errors,
    }, ensure_ascii=False))
    fallback_used = bool(search_output.get("fallback_used", False))
    non_fatal = bool(search_output.get("non_fatal", False))
    stub_only = bool(items) and all(bool(row.get("is_stub")) for row in items)
    stub_only_non_fatal = non_fatal and stub_only
    result_lines = _format_web_search_items(items, limit=capped)
    provider_errors_line = _format_provider_errors_for_context(provider_errors)
    meta_line = (
        f"meta: selected_provider={selected_provider} "
        f"fallback_used={str(fallback_used).lower()} "
        f"is_stub={str((non_fatal or stub_only)).lower()}"
    )
    if result_lines:
        context_parts = [meta_line]
        if provider_errors_line:
            context_parts.append(provider_errors_line)
        context_parts.append("Web検索結果:\n" + "\n".join(result_lines))
        context_text = "\n".join(context_parts)
    else:
        context_text = f"No results found for: {safe_query}"

    event_payload = {
        "provider_errors": search_output.get("provider_errors") or {},
        "skipped_providers": search_output.get("skipped_providers") or {},
        "non_fatal": non_fatal,
        "message": str(search_output.get("message") or ""),
        "selected_provider": selected_provider,
        "total_items": total_items,
    }
    return {
        "ok": True,
        "query": safe_query,
        "message": str(search_output.get("message") or ""),
        "items": items,
        "formatted_items": result_lines,
        "context_text": context_text[: (700 + capped * 220)],
        "event_payload": event_payload,
        "search_output": search_output,
        "lightweight_prefetch_search_output": search_output,
        "stub_only_non_fatal": stub_only_non_fatal,
    }


def _run_nexus_web_search_tool_with_evidence(
    topic: str,
    *,
    max_results_per_query: int = 5,
    mode: str = "standard",
    depth: str | None = None,
    language: str | None = None,
    scope: str | list[str] | None = None,
    max_queries: int = 4,
) -> dict:
    """正式ツール経路: execute_nexus_web_search を使い Evidence 保存付きで実行する。"""
    requested_depth = (depth or mode or "standard").strip() or "standard"
    safe_topic, removed = sanitize_query(topic)
    if removed:
        print(f"[SEARCH][SANITIZED] original_len={len(topic)} removed={removed}")
    if not safe_topic:
        return {
            "ok": False,
            "job_id": "",
            "query": "",
            "message": "SEARCH_BLOCKED: Query contained only sensitive data and was not sent.",
            "items": [],
            "saved_evidence": 0,
            "event_payload": {},
        }
    service_result = execute_nexus_web_search(
        safe_topic,
        mode=mode,
        depth=requested_depth,
        max_queries=max_queries,
        max_results_per_query=max_results_per_query,
        scope=scope,
        language=language,
    )
    search_output = dict(service_result.get("search") or {})
    items = search_output.get("items") or []
    result_lines = _format_web_search_items(items, limit=max(1, min(int(max_results_per_query or 5), 20)))
    provider = str(search_output.get("selected_provider") or search_output.get("provider") or "unknown")
    provider_errors = search_output.get("provider_errors") or {}
    total_items = int(search_output.get("total_items") or len(items))
    print(json.dumps({
        "event": "agent_nexus_web_search",
        "called": True,
        "invoked_tool": "nexus_web_search",
        "queries": service_result.get("queries") or [safe_topic],
        "provider": provider,
        "total_items": total_items,
        "provider_errors": provider_errors,
        "saved_evidence": int(service_result.get("saved_evidence") or 0),
        "job_id": str(service_result.get("job_id") or ""),
    }, ensure_ascii=False))
    message = str(search_output.get("message") or "")
    return {
        "ok": True,
        "job_id": str(service_result.get("job_id") or ""),
        "query": safe_topic,
        "queries": service_result.get("queries") or [safe_topic],
        "items": items,
        "formatted_items": result_lines,
        "saved_evidence": int(service_result.get("saved_evidence") or 0),
        "message": message,
        "event_payload": {
            "provider_errors": provider_errors,
            "non_fatal": bool(search_output.get("non_fatal", False)),
            "message": message,
            "selected_provider": provider,
            "total_items": total_items,
            "saved_evidence": int(service_result.get("saved_evidence") or 0),
            "job_id": str(service_result.get("job_id") or ""),
        },
        "tool_search_output": search_output,
    }


_TASK_SEARCH_PREFETCH_PATTERNS = (
    r"\b(search|web|lookup|latest|recent|news|current|today|update)\b",
    r"(調べて|検索|最新|ニュース|アップデート|確認して|確認したい|情報収集)",
)


def _should_prefetch_web_for_task(text: str, search_enabled: bool | str | int | None) -> bool:
    """
    タスク実行前のWeb検索プリフェッチ要否判定。
    - 検索トグルONなら常に True
    - それ以外はキーワード一致で True
    """
    if _resolve_effective_search_enabled(search_enabled):
        return True
    haystack = str(text or "").strip().lower()
    if not haystack:
        return False
    return any(re.search(pat, haystack, re.IGNORECASE) for pat in _TASK_SEARCH_PREFETCH_PATTERNS)


def _build_task_prefetch_context_block(search_result: dict, *, max_items: int = 5) -> str:
    items = search_result.get("items") or []
    if not items:
        return ""
    lines = _format_web_search_items(items, limit=max_items)
    if not lines:
        return ""
    query = str(search_result.get("query") or "").strip()
    header = f"【事前Web検索結果】query={query}" if query else "【事前Web検索結果】"
    provider_errors_line = _format_provider_errors_for_context(search_result.get("provider_errors"), prefix="provider_errors")
    body_lines = [header]
    if provider_errors_line:
        body_lines.append(provider_errors_line)
    body_lines.extend(f"- {line}" for line in lines)
    return "\n".join(body_lines)


def nexus_web_search(
    topic: str,
    max_results_per_query: int = 5,
    mode: str = "standard",
    depth: str | None = None,
    language: str | None = None,
    scope: str | list[str] | None = None,
    max_queries: int = 4,
) -> str:
    """Task/Agent向けの正式 Nexus WebSearch ツール（Evidence保存あり）。"""
    result = _run_nexus_web_search_tool_with_evidence(
        topic,
        max_results_per_query=max_results_per_query,
        mode=mode,
        depth=depth,
        max_queries=max_queries,
        scope=scope,
        language=language,
    )
    if not result.get("ok"):
        return str(result.get("message") or "No results found.")
    lines = result.get("formatted_items") or []
    message = str(result.get("message") or "")
    job_id = str(result.get("job_id") or "")
    saved_evidence = int(result.get("saved_evidence") or 0)
    header = f"job_id={job_id} saved_evidence={saved_evidence}"
    body = "\n".join(f"- {line}" for line in lines) if lines else (message or "No results found.")
    return f"{header}\n{body}"


# =========================
# Git ツール
# =========================

def _git_run(args: list, cwd: str) -> tuple:
    """gitコマンドを指定ディレクトリで実行し (returncode, stdout, stderr) を返す"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return -1, "", "git not found. Please install git."
    except subprocess.TimeoutExpired:
        return -1, "", "git command timed out"
    except Exception as e:
        return -1, "", str(e)


def _git_ensure_repo(cwd: str) -> str | None:
    """gitリポジトリがなければ初期化。エラーがあれば文字列を返す"""
    os.makedirs(cwd, exist_ok=True)
    if not os.path.exists(os.path.join(cwd, ".git")):
        rc, _, err = _git_run(["init"], cwd)
        if rc != 0:
            return f"ERROR: git init failed: {err}"
        _git_run(["config", "user.email", "codeagent@local"], cwd)
        _git_run(["config", "user.name", "CodeAgent"], cwd)
    else:
        rc_u, out_u, _ = _git_run(["config", "user.email"], cwd)
        if not out_u:
            _git_run(["config", "user.email", "codeagent@local"], cwd)
            _git_run(["config", "user.name", "CodeAgent"], cwd)
    return None


AUTO_SNAPSHOT_KEEP_N = max(5, int(os.environ.get("CODEAGENT_SNAPSHOT_KEEP_N", "50")))

def _archive_old_snapshot_rows(project: str, keep_n: int = AUTO_SNAPSHOT_KEEP_N):
    """snapshot_historyは最新N件のみ保持し、古い履歴はタグ＋メモへ退避する。"""
    with _db_lock:
        conn = get_db(project)
        try:
            rows = conn.execute(
                "SELECT id, job_id, task_id, commit_hash, stage FROM snapshot_history ORDER BY id DESC"
            ).fetchall()
            if len(rows) <= keep_n:
                return
            old_rows = rows[keep_n:]
            for row in old_rows:
                sid, job_id, task_id, commit_hash, stage = row
                safe_hash = re.sub(r"[^0-9a-fA-F]", "", commit_hash or "")[:12] or f"id{sid}"
                tag_name = f"snapshot-archive/{safe_hash}"
                _git_run(["tag", "-f", tag_name, commit_hash], CA_DATA_DIR)
                conn.execute(
                    """INSERT INTO snapshot_archive_notes
                       (job_id, task_id, commit_hash, stage, archived_tag, archived_at)
                       VALUES (?,?,?,?,?,?)""",
                    (job_id, task_id or "", commit_hash, stage, tag_name, datetime.now().isoformat())
                )
                conn.execute("DELETE FROM snapshot_history WHERE id=?", (sid,))
            conn.commit()
        finally:
            conn.close()


def auto_snapshot_ca_data(stage: str, job_id: str, task_id=None) -> dict:
    """
    CA_DATA_DIR の自動スナップショット。
    差分が無ければ commit は作らず skip する。
    """
    rc_git, _, git_err = _git_run(["--version"], CA_DATA_DIR)
    if rc_git != 0:
        print(f"[snapshot] skip: git unavailable ({git_err}) stage={stage} job={job_id} task={task_id}")
        return {
            "ok": True,
            "stage": stage,
            "skipped": True,
            "reason": "git unavailable",
            "commit_hash": "",
        }

    err = _git_ensure_repo(CA_DATA_DIR)
    if err:
        print(f"[snapshot] skip: git init/config not ready ({err}) stage={stage} job={job_id} task={task_id}")
        return {
            "ok": True,
            "stage": stage,
            "skipped": True,
            "reason": "git not initialized",
            "commit_hash": "",
        }
    _ensure_ca_data_gitignore()
    rc_add, _, err_add = _git_run(["add", "-A"], CA_DATA_DIR)
    if rc_add != 0:
        return {"ok": False, "stage": stage, "error": f"git add failed: {err_add}"}

    rc_diff, _, err_diff = _git_run(["diff", "--cached", "--quiet"], CA_DATA_DIR)
    if rc_diff == 0:
        rc_head, head_out, _ = _git_run(["rev-parse", "--short", "HEAD"], CA_DATA_DIR)
        return {
            "ok": True, "stage": stage, "skipped": True,
            "reason": "no diff", "commit_hash": head_out if rc_head == 0 else ""
        }
    if rc_diff not in (0, 1):
        return {"ok": False, "stage": stage, "error": f"git diff --cached failed: {err_diff}"}

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_text = "-" if task_id is None else str(task_id)
    msg = f"snapshot: {stage} | job={job_id} task={task_text} | {ts}"
    rc_commit, out_commit, err_commit = _git_run(["commit", "-m", msg], CA_DATA_DIR)
    if rc_commit != 0:
        if "nothing to commit" in (out_commit + err_commit):
            return {"ok": True, "stage": stage, "skipped": True, "reason": "nothing to commit", "commit_hash": ""}
        return {"ok": False, "stage": stage, "error": f"git commit failed: {err_commit or out_commit}"}

    rc_hash, commit_hash, err_hash = _git_run(["rev-parse", "HEAD"], CA_DATA_DIR)
    if rc_hash != 0:
        return {"ok": False, "stage": stage, "error": f"commit hash取得失敗: {err_hash}"}

    snapshot_history_add("default", job_id, task_id, commit_hash, stage)
    _archive_old_snapshot_rows("default")
    return {"ok": True, "stage": stage, "skipped": False, "commit_hash": commit_hash, "message": out_commit}


def git_status(project: str = "default") -> str:
    """プロジェクトのgit変更一覧を返す（M=変更, A=追加, ?=未追跡）"""
    cwd = os.path.join(WORK_DIR, project)
    err_msg = _git_ensure_repo(cwd)
    if err_msg:
        return err_msg
    rc, out, err = _git_run(["status", "--short"], cwd)
    if rc != 0:
        return f"ERROR: {err}"
    # ブランチ情報も追加
    rc2, branch, _ = _git_run(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    branch_str = f"[branch: {branch}]\n" if rc2 == 0 else ""
    return branch_str + (out if out else "clean (no changes)")


def git_diff(path: str = "", project: str = "default") -> str:
    """変更差分を返す。pathを指定するとそのファイルのみ表示"""
    cwd = os.path.join(WORK_DIR, project)
    if not os.path.exists(os.path.join(cwd, ".git")):
        return "ERROR: not a git repository. Use git_status to initialize."
    args = ["diff"] + ([path] if path else [])
    rc, out, err = _git_run(args, cwd)
    if rc != 0:
        return f"ERROR: {err}"
    if not out:
        args2 = ["diff", "--cached"] + ([path] if path else [])
        rc2, out2, _ = _git_run(args2, cwd)
        if out2:
            return f"[staged changes]\n{out2[:4000]}"
        return "no diff (clean)"
    return out[:4000]


def git_commit(message: str, project: str = "default") -> str:
    """全変更をステージして指定メッセージでコミットする"""
    cwd = os.path.join(WORK_DIR, project)
    err_msg = _git_ensure_repo(cwd)
    if err_msg:
        return err_msg
    rc_changed, out_changed, err_changed = _git_run(["status", "--porcelain"], cwd)
    if rc_changed != 0:
        return f"ERROR: git status failed: {err_changed}"
    changed_lines = [ln.strip() for ln in out_changed.splitlines() if ln.strip()]
    if any("script.js" in ln.replace("\\", "/") for ln in changed_lines):
        check = _script_js_static_integrity_check(project)
        if not check.get("ok"):
            detail = []
            if check.get("impact_lines"):
                detail.append("impact:\n" + "\n".join(check.get("impact_lines", [])))
            if check.get("violations"):
                detail.append("violations:\n" + "\n".join(check.get("violations", [])))
            if check.get("error"):
                detail.append(f"error:\n{check.get('error')}")
            return (
                "ERROR: commit blocked by script.js static integrity check.\n"
                f"reason: {check.get('summary')}\n" + ("\n".join(detail) if detail else "")
            )
    rc, _, err = _git_run(["add", "-A"], cwd)
    if rc != 0:
        return f"ERROR: git add failed: {err}"
    rc, out, err = _git_run(["commit", "-m", message], cwd)
    if rc != 0:
        if "nothing to commit" in (err + out):
            return "nothing to commit, working tree clean"
        return f"ERROR: git commit failed: {err or out}"
    return f"ok: committed\n{out}"


def git_checkout_branch(name: str, create: bool = True, project: str = "default") -> str:
    """ブランチを作成して切り替える。create=Falseは既存ブランチへの切り替えのみ"""
    cwd = os.path.join(WORK_DIR, project)
    if not os.path.exists(os.path.join(cwd, ".git")):
        return "ERROR: not a git repository. Use git_commit to initialize."
    args = ["checkout", "-b", name] if create else ["checkout", name]
    rc, out, err = _git_run(args, cwd)
    if rc != 0:
        if "already exists" in err:
            rc2, out2, err2 = _git_run(["checkout", name], cwd)
            if rc2 != 0:
                return f"ERROR: {err2}"
            return f"ok: switched to existing branch '{name}'"
        return f"ERROR: {err}"
    action = "created and switched to" if create else "switched to"
    return f"ok: {action} branch '{name}'"


def git_reset(mode: str = "hard", project: str = "default") -> str:
    """エージェントの変更を全てリセット。mode='hard'で全変更破棄、'soft'でステージのみ解除"""
    cwd = os.path.join(WORK_DIR, project)
    if not os.path.exists(os.path.join(cwd, ".git")):
        return "ERROR: not a git repository"
    if mode not in ("hard", "soft", "mixed"):
        mode = "hard"
    rc, out, err = _git_run(["reset", f"--{mode}", "HEAD"], cwd)
    if rc != 0:
        if "ambiguous argument" in err or "unknown revision" in err:
            _git_run(["rm", "-r", "--cached", "."], cwd)
            return "ok: unstaged all (no commits yet)"
        return f"ERROR: {err}"
    note = "\n(注: 未追跡ファイルは残ります)" if mode == "hard" else ""
    return f"ok: reset --{mode}\n{out}{note}"


# =========================
# MCP (Model Context Protocol) クライアント
# =========================

def mcp_call(server_url: str, tool_name: str, arguments: dict = None) -> str:
    """
    外部MCPサーバーのツールを呼び出す（MCPクライアント）。
    server_url: MCPサーバーのエンドポイントURL
    tool_name: 呼び出すツール名
    arguments: ツールへの引数dict
    """
    if arguments is None:
        arguments = {}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }
    try:
        resp = requests.post(
            server_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            code = data["error"].get("code", "")
            msg = data["error"].get("message", "")
            return f"ERROR: MCP error {code}: {msg}"
        result = data.get("result", {})
        content = result.get("content", [])
        if content:
            texts = [c.get("text", "") for c in content if c.get("type") == "text"]
            return "\n".join(texts) if texts else str(result)
        return str(result)
    except requests.exceptions.ConnectionError:
        return f"ERROR: Cannot connect to MCP server at {server_url}"
    except Exception as e:
        return f"ERROR: {e}"


def mcp_list_tools(server_url: str) -> str:
    """外部MCPサーバーのツール一覧を取得する"""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    try:
        resp = requests.post(server_url, json=payload,
                             headers={"Content-Type": "application/json"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        tools = data.get("result", {}).get("tools", [])
        if not tools:
            return "No tools available"
        lines = [f"- {t['name']}: {t.get('description','')[:80]}" for t in tools]
        return f"MCP tools at {server_url}:\n" + "\n".join(lines)
    except Exception as e:
        return f"ERROR: {e}"


# =========================
# モデルデータベース
# =========================

_model_db_lock = __import__("threading").Lock()


def model_db_exists() -> bool:
    return os.path.exists(MODEL_DB_PATH)


def _get_model_db(create_if_missing: bool = True):
    if (not create_if_missing) and (not os.path.exists(MODEL_DB_PATH)):
        return None
    conn = sqlite3.connect(MODEL_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            model_key TEXT DEFAULT '',
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            is_vlm INTEGER DEFAULT 0,
            vlm_enabled INTEGER DEFAULT 1,
            enabled INTEGER DEFAULT 1,
            vram_mb INTEGER DEFAULT -1,
            ram_mb INTEGER DEFAULT -1,
            load_sec REAL DEFAULT -1,
            tok_per_sec REAL DEFAULT -1,
            llm_url TEXT DEFAULT '',
            ctx_size INTEGER DEFAULT 16384,
            gpu_layers INTEGER DEFAULT 999,
            threads INTEGER DEFAULT 8,
            parser TEXT DEFAULT 'json',
            description TEXT DEFAULT '',
            parallel INTEGER DEFAULT -1,
            batch_size INTEGER DEFAULT -1,
            ubatch_size INTEGER DEFAULT -1,
            cache_type_k TEXT DEFAULT '',
            cache_type_v TEXT DEFAULT '',
            extra_args TEXT DEFAULT '',
            auto_roles TEXT DEFAULT '',
            benchmark_profiles TEXT DEFAULT '',
            has_mmproj INTEGER DEFAULT 0,
            mmproj_path TEXT DEFAULT '',
            quantization TEXT DEFAULT '',
            file_size_mb INTEGER DEFAULT -1,
            notes TEXT DEFAULT '',
            benchmarked_at TEXT DEFAULT '',
            proven_ngl INTEGER DEFAULT -1,
            ngl_ctx_profiles TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        )
    """)
    # 既存DBへのマイグレーション: 列が無ければ追加
    for ddl in [
        "ALTER TABLE models ADD COLUMN model_key TEXT DEFAULT ''",
        "ALTER TABLE models ADD COLUMN vlm_enabled INTEGER DEFAULT 1",
        "ALTER TABLE models ADD COLUMN enabled INTEGER DEFAULT 1",
        "ALTER TABLE models ADD COLUMN threads INTEGER DEFAULT 8",
        "ALTER TABLE models ADD COLUMN parser TEXT DEFAULT 'json'",
        "ALTER TABLE models ADD COLUMN description TEXT DEFAULT ''",
        "ALTER TABLE models ADD COLUMN parallel INTEGER DEFAULT -1",
        "ALTER TABLE models ADD COLUMN batch_size INTEGER DEFAULT -1",
        "ALTER TABLE models ADD COLUMN ubatch_size INTEGER DEFAULT -1",
        "ALTER TABLE models ADD COLUMN cache_type_k TEXT DEFAULT ''",
        "ALTER TABLE models ADD COLUMN cache_type_v TEXT DEFAULT ''",
        "ALTER TABLE models ADD COLUMN extra_args TEXT DEFAULT ''",
        "ALTER TABLE models ADD COLUMN auto_roles TEXT DEFAULT ''",
        "ALTER TABLE models ADD COLUMN benchmark_profiles TEXT DEFAULT ''",
        "ALTER TABLE models ADD COLUMN has_mmproj INTEGER DEFAULT 0",
        "ALTER TABLE models ADD COLUMN mmproj_path TEXT DEFAULT ''",
        "ALTER TABLE models ADD COLUMN proven_ngl INTEGER DEFAULT -1",
        "ALTER TABLE models ADD COLUMN ngl_ctx_profiles TEXT DEFAULT '{}'",
    ]:
        try:
            conn.execute(ddl)
            conn.commit()
        except Exception:
            pass

    # ユーザー設定テーブル（キーバリューストア）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    try:
        conn.execute("UPDATE models SET ctx_size=? WHERE ctx_size IS NULL OR ctx_size<=0", (_resolve_default_ctx_size(),))
    except Exception:
        pass
    conn.commit()
    return conn


def model_db_list() -> list:
    with _model_db_lock:
        conn = _get_model_db(create_if_missing=False)
        if conn is None:
            return []
        try:
            rows = conn.execute("SELECT * FROM models ORDER BY name ASC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def model_db_find_by_path(path: str) -> dict | None:
    norm = os.path.normpath(path or "")
    with _model_db_lock:
        conn = _get_model_db(create_if_missing=False)
        if conn is None:
            return None
        try:
            row = conn.execute("SELECT * FROM models WHERE path=?", (norm,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def seed_default_model_catalog():
    return


def model_db_add(info: dict) -> str:
    info = _infer_model_db_metadata(dict(info))
    normalized_path = os.path.normpath(info.get("path", "") or "")
    existing = None
    if normalized_path:
        existing = model_db_find_by_path(normalized_path)
    if not existing and info.get("model_key"):
        key = str(info.get("model_key")).strip()
        for row in model_db_list():
            if str(row.get("model_key", "")).strip() == key:
                existing = row
                break
    mid = (existing or {}).get("id") or info.get("id") or str(uuid.uuid4())[:12]
    now = datetime.now().isoformat()
    with _model_db_lock:
        conn = _get_model_db()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO models
                (id, model_key, name, path, is_vlm, vlm_enabled, enabled, vram_mb, ram_mb, load_sec, tok_per_sec,
                 llm_url, ctx_size, gpu_layers, threads, parser, description,
                 parallel, batch_size, ubatch_size, cache_type_k, cache_type_v, extra_args,
                 benchmark_profiles,
                 auto_roles, has_mmproj, mmproj_path, quantization, file_size_mb, notes, benchmarked_at, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                mid,
                info.get("model_key", ""),
                info.get("name", ""),
                normalized_path or info.get("path", ""),
                1 if info.get("is_vlm") else 0,
                1 if info.get("vlm_enabled", 1) else 0,
                1 if info.get("enabled", 1) else 0,
                info.get("vram_mb", -1),
                info.get("ram_mb", -1),
                info.get("load_sec", -1),
                info.get("tok_per_sec", -1),
                info.get("llm_url", ""),
                _resolve_ctx_size(info.get("ctx_size")),
                info.get("gpu_layers", 999),
                info.get("threads", 8),
                info.get("parser", "json"),
                info.get("description", ""),
                info.get("parallel", -1),
                info.get("batch_size", -1),
                info.get("ubatch_size", -1),
                info.get("cache_type_k", ""),
                info.get("cache_type_v", ""),
                info.get("extra_args", ""),
                info.get("benchmark_profiles", ""),
                info.get("auto_roles", ""),
                1 if info.get("has_mmproj") else 0,
                info.get("mmproj_path", ""),
                info.get("quantization", ""),
                info.get("file_size_mb", -1),
                info.get("notes", ""),
                info.get("benchmarked_at", ""),
                (existing or {}).get("created_at", info.get("created_at", now)),
            ))
            conn.commit()
            return mid
        finally:
            conn.close()


def model_db_delete(mid: str):
    with _model_db_lock:
        conn = _get_model_db(create_if_missing=False)
        if conn is None:
            return
        try:
            conn.execute("DELETE FROM models WHERE id=?", (mid,))
            conn.commit()
        finally:
            conn.close()


def model_db_update(mid: str, updates: dict):
    allowed = {"model_key", "name", "path", "is_vlm", "vlm_enabled", "enabled", "vram_mb", "ram_mb", "load_sec",
               "tok_per_sec", "llm_url", "ctx_size", "gpu_layers", "threads", "parser",
               "description", "parallel", "batch_size", "ubatch_size", "cache_type_k",
               "cache_type_v", "extra_args", "auto_roles", "benchmark_profiles", "has_mmproj", "mmproj_path", "quantization", "file_size_mb",
               "notes", "benchmarked_at", "proven_ngl", "ngl_ctx_profiles"}
    sets = {k: v for k, v in updates.items() if k in allowed}
    if "ctx_size" in sets:
        sets["ctx_size"] = _resolve_ctx_size(sets.get("ctx_size"))
    if not sets:
        return
    with _model_db_lock:
        conn = _get_model_db(create_if_missing=False)
        if conn is None:
            return
        try:
            clause = ", ".join(f"{k}=?" for k in sets)
            conn.execute(f"UPDATE models SET {clause} WHERE id=?", [*sets.values(), mid])
            conn.commit()
        finally:
            conn.close()


def _normalize_benchmark_profile(profile: dict, ctx: int, use_vlm: bool) -> dict:
    inf = profile.get("inference", {}) if isinstance(profile, dict) else {}
    log_vram = profile.get("log_gpu_mib", -1)
    log_ram = profile.get("log_cpu_mib", -1)
    counter_vram = profile.get("counter_vram_delta", -1)
    counter_ram = profile.get("counter_ram_delta", -1)
    vram_candidates = [float(v) for v in (log_vram, counter_vram) if isinstance(v, (int, float)) and float(v) > 0]
    ram_candidates = [float(v) for v in (log_ram, counter_ram) if isinstance(v, (int, float)) and float(v) > 0]
    chosen_vram = max(vram_candidates) if vram_candidates else -1
    chosen_ram = max(ram_candidates) if ram_candidates else -1
    return {
        "mode": "vlm" if use_vlm else "text",
        "ctx_size": ctx,
        "vram_mb": chosen_vram if isinstance(chosen_vram, (int, float)) else -1,
        "ram_mb": chosen_ram if isinstance(chosen_ram, (int, float)) else -1,
        "load_sec": profile.get("load_sec", -1),
        "tok_per_sec": inf.get("gen", -1) if inf.get("ok") else -1,
        "benchmarked_at": datetime.now().isoformat(),
    }


def _unload_active_llm_for_benchmark() -> None:
    """
    ベンチマーク実行前に、既存のLLM(プランナー/ルーター)を停止して
    VRAM/RAM競合による計測失敗を回避する。
    """
    try:
        if _model_manager._process is not None or _model_health_ok(_model_manager.llm_port):
            print("[Benchmark] unloading active LLM before benchmark")
        _model_manager._kill()
        _model_manager.current_key = ""
        _model_manager._status = "ready"
    except Exception as e:
        print(f"[Benchmark] unload warning: {e}")


def benchmark_model_record(model: dict, use_vlm: bool = False) -> dict:
    import sys as _sys
    bench_dir = os.path.dirname(os.path.abspath(__file__))
    if bench_dir not in _sys.path:
        _sys.path.insert(0, bench_dir)
    from benchmark_mem import (
        run_single_benchmark,
    )

    path = model["path"]
    ctx = _resolve_ctx_size(model.get("ctx_size"))
    ngl = model.get("gpu_layers", 999)
    mmproj_path = model.get("mmproj_path", "") if use_vlm else ""
    if not os.path.exists(path):
        return {"notes": f"BENCHMARK SKIP: file not found {path}"}
    if use_vlm and (not mmproj_path or not os.path.exists(mmproj_path)):
        return {"notes": "BENCHMARK SKIP: mmproj file not found"}

    _unload_active_llm_for_benchmark()
    result = run_single_benchmark(path, ctx=ctx, ngl=ngl, mmproj_path=mmproj_path)
    if not result.get("ok"):
        return {"notes": f"BENCHMARK FAIL: {result.get('error', 'unknown error')}"}
    profile = _normalize_benchmark_profile(result, ctx=ctx, use_vlm=use_vlm)
    return {
        **profile,
        "notes": f"{profile['mode']} gen={profile['tok_per_sec']} tok/s load={profile['load_sec']}s",
    }


def benchmark_model_profiles(model: dict) -> dict:
    profiles: dict[str, dict] = {}
    text_profile = benchmark_model_record(model, use_vlm=False)
    if "load_sec" in text_profile:
        profiles["text"] = text_profile
    if model.get("has_mmproj") and model.get("mmproj_path"):
        vlm_profile = benchmark_model_record(model, use_vlm=True)
        if "load_sec" in vlm_profile:
            profiles["vlm"] = vlm_profile

    active = profiles.get("text") or profiles.get("vlm")
    updates = {
        "benchmark_profiles": json.dumps(profiles, ensure_ascii=False),
    }
    if active:
        updates.update({
            "load_sec": active.get("load_sec", -1),
            "vram_mb": active.get("vram_mb", -1),
            "ram_mb": active.get("ram_mb", -1),
            "tok_per_sec": active.get("tok_per_sec", -1),
            "benchmarked_at": active.get("benchmarked_at", ""),
            "notes": f"text={profiles.get('text', {}).get('tok_per_sec', '-')} tok/s"
                     + (f" vlm={profiles.get('vlm', {}).get('tok_per_sec', '-')} tok/s" if "vlm" in profiles else ""),
        })
    elif text_profile.get("notes"):
        updates["notes"] = text_profile["notes"]
    return updates


# =========================
# ユーザー設定（DB保存）
# =========================

def _is_runpod_env() -> bool:
    return IS_RUNPOD_RUNTIME


def _default_llm_root_folder() -> str:
    if _is_runpod_env():
        return "/workspace/LLMs"
    if os.name == "nt":
        return r"C:\LLMs"
    return os.path.join(os.path.expanduser("~"), "LLMs")


def _default_llm_ctx_size() -> int:
    for key in ("LLAMA_CTX_SIZE", "DEFAULT_LLM_CTX_SIZE", "NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS"):
        raw = str(os.environ.get(key, "")).strip()
        if raw.isdigit():
            return max(512, min(65535, int(raw)))
    return 16384


def _parse_ctx_size_or_none(value) -> int | None:
    try:
        parsed = int(str(value).strip())
    except Exception:
        return None
    if parsed <= 0:
        return None
    return max(512, min(65535, parsed))


def _resolve_default_ctx_size() -> int:
    for key in ("LLAMA_CTX_SIZE", "DEFAULT_LLM_CTX_SIZE", "NEXUS_ANSWER_LLM_MAX_CONTEXT_TOKENS"):
        env_ctx = _parse_ctx_size_or_none(os.environ.get(key, ""))
        if env_ctx is not None:
            return env_ctx
    return 16384


def _resolve_ctx_size(value=None) -> int:
    parsed = _parse_ctx_size_or_none(value)
    return parsed if parsed is not None else _resolve_default_ctx_size()


# デフォルト設定定義
SETTINGS_DEFAULTS = {
    "llm_root_folder":    _default_llm_root_folder(),  # モデルのルートフォルダ
    "max_steps":          "20",
    "auto_select_option": "true",
    "auto_skill_gen":     "true",
    "search_enabled":     "false",
    "search_num":         "5",
    "streaming_enabled":  "true",
    "ctx_size":           str(_default_llm_ctx_size()),
    "summary_max_tokens": "200",
    "read_file_inject_max_chars": "16000",
    "llm_url":            "",
    "orchestration_policy": "ladder_fail_and_quality",
    "coder_primary": "",
    "coder_secondary": "",
    "coder_tertiary": "",
    "quality_check_enabled": "true",
    "feature_mode": "model_orchestration",
    "ensemble_execution_mode": "parallel",
    "ensemble_auto_switch_on_low_vram": "true",
    "gpu_static_backend": "auto",
    "gpu_usage_backend": "auto",
    "echo_tts_use_translation": "false",
    "sbv2_jp_extra_text_normalization": "true",
    "sbv2_jp_extra_english_to_katakana": "llm",
    "sbv2_jp_extra_emoji_policy": "skip",
    "sbv2_jp_extra_symbol_policy": "readable",
    "sbv2_jp_extra_url_policy": "skip",
    "sbv2_jp_extra_non_japanese_policy": "normalize_then_block",
    "sbv2_length": "1.0",
    "sbv2_sdp_ratio": "0.2",
    "sbv2_noise": "0.6",
    "sbv2_noise_w": "0.8",
    "sbv2_style_weight": "1.0",
    "sbv2_split_interval": "0.5",
    "sbv2_pitch_scale": "1.0",
    "sbv2_intonation_scale": "1.0",
}
for _role in MODEL_ROLE_OPTIONS:
    SETTINGS_DEFAULTS.setdefault(_role_setting_key(_role), "")

_SETTINGS_KEY_ALIASES_TO_CANONICAL = {
    "echo_sbv2_length": "sbv2_length",
    "echo_sbv2_sdp_ratio": "sbv2_sdp_ratio",
    "echo_sbv2_noise": "sbv2_noise",
    "echo_sbv2_noise_w": "sbv2_noise_w",
    "echo_sbv2_style_weight": "sbv2_style_weight",
    "echo_sbv2_split_interval": "sbv2_split_interval",
    "echo_sbv2_pitch_scale": "sbv2_pitch_scale",
    "echo_sbv2_intonation_scale": "sbv2_intonation_scale",
}


def _canonicalize_setting_key(key: str) -> str:
    return _SETTINGS_KEY_ALIASES_TO_CANONICAL.get(key, key)


def _normalize_non_japanese_policy_value(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("normalize_then_block", "normalize_then_warn", "normalize_then_allow"):
        return raw
    if raw == "block":
        return "normalize_then_block"
    if raw == "warn":
        return "normalize_then_warn"
    if raw == "allow":
        return "normalize_then_allow"
    return SETTINGS_DEFAULTS.get("sbv2_jp_extra_non_japanese_policy", "normalize_then_block")


def _canonicalize_settings_map(data: dict) -> dict:
    out = {}
    for raw_key, raw_value in (data or {}).items():
        key = _canonicalize_setting_key(str(raw_key))
        value = raw_value
        if key == "ctx_size":
            value = str(_resolve_ctx_size(raw_value))
        if key == "sbv2_jp_extra_non_japanese_policy":
            value = _normalize_non_japanese_policy_value(str(raw_value))
        out[key] = value
    return out

def settings_get(key: str) -> str:
    """1件取得。存在しなければデフォルト値を返す"""
    key = _canonicalize_setting_key(str(key))
    with _model_db_lock:
        conn = _get_model_db(create_if_missing=False)
        if conn is None:
            return SETTINGS_DEFAULTS.get(key, "")
        try:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            value = row["value"] if row else SETTINGS_DEFAULTS.get(key, "")
            if key == "ctx_size":
                return str(_resolve_ctx_size(value))
            return value
        finally:
            conn.close()

def settings_set(key: str, value: str):
    """1件保存（upsert）"""
    key = _canonicalize_setting_key(str(key))
    if key == "ctx_size":
        value = str(_resolve_ctx_size(value))
    if key == "sbv2_jp_extra_non_japanese_policy":
        value = _normalize_non_japanese_policy_value(str(value))
    now = datetime.now().isoformat()
    with _model_db_lock:
        conn = _get_model_db()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
                (key, str(value), now)
            )
            conn.commit()
        finally:
            conn.close()

def settings_get_all() -> dict:
    """全設定をdictで返す（未設定キーはデフォルト値で補完）"""
    with _model_db_lock:
        conn = _get_model_db(create_if_missing=False)
        if conn is None:
            return dict(SETTINGS_DEFAULTS)
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        finally:
            conn.close()
    result = dict(SETTINGS_DEFAULTS)
    restored = _canonicalize_settings_map({r["key"]: r["value"] for r in rows})
    result.update(restored)
    return result

def settings_set_bulk(data: dict):
    """複数キーを一括保存"""
    data = _canonicalize_settings_map(data or {})
    now = datetime.now().isoformat()
    with _model_db_lock:
        conn = _get_model_db()
        try:
            for key, value in data.items():
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?,?,?)",
                    (key, str(value), now)
                )
            conn.commit()
        finally:
            conn.close()


def _load_opencode_json() -> dict:
    if not os.path.exists(OPENCODE_CONFIG_PATH):
        return {}
    try:
        with open(OPENCODE_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_opencode_json(data: dict):
    try:
        with open(OPENCODE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[settings] opencode.json save warning: {e}")


def _sync_ensemble_settings_to_opencode_json():
    # ensemble設定はsettings(SQLite)を正とする。
    # 互換性のため関数は残すが、opencode.jsonへの書き戻しは行わない。
    return


def _load_ensemble_settings_from_opencode_json():
    data = _load_opencode_json()
    ensemble = data.get("ensemble", {})
    if not isinstance(ensemble, dict):
        return
    updates = {}
    execution_mode = str(ensemble.get("execution_mode", "")).strip().lower()
    if execution_mode in ("parallel", "serial"):
        updates["ensemble_execution_mode"] = execution_mode
    if "auto_switch_on_low_vram" in ensemble:
        updates["ensemble_auto_switch_on_low_vram"] = "true" if bool(ensemble.get("auto_switch_on_low_vram")) else "false"
    if updates:
        settings_set_bulk(updates)


def _restore_settings_from_db():
    """起動時にDBから設定を読み込んでサーバーグローバルに反映"""
    global _search_enabled, _llm_streaming, _current_n_ctx
    try:
        if not model_db_exists():
            print(f"[settings] model DB not found at {MODEL_DB_PATH}; using defaults")
            return
        all_s = settings_get_all()
        compat_updates = {}
        with _model_db_lock:
            conn = _get_model_db(create_if_missing=False)
            legacy_rows = []
            canonical_present_keys = set()
            raw_non_jp_policy_value = None
            if conn is not None:
                try:
                    q = ",".join("?" for _ in _SETTINGS_KEY_ALIASES_TO_CANONICAL)
                    legacy_rows = conn.execute(
                        f"SELECT key, value FROM settings WHERE key IN ({q})",
                        tuple(_SETTINGS_KEY_ALIASES_TO_CANONICAL.keys()),
                    ).fetchall()
                    canonical_targets = tuple(set(_SETTINGS_KEY_ALIASES_TO_CANONICAL.values()))
                    cq = ",".join("?" for _ in canonical_targets)
                    canonical_rows = conn.execute(
                        f"SELECT key FROM settings WHERE key IN ({cq})",
                        canonical_targets,
                    ).fetchall()
                    canonical_present_keys = {str(r["key"]) for r in canonical_rows}
                    policy_row = conn.execute(
                        "SELECT value FROM settings WHERE key=?",
                        ("sbv2_jp_extra_non_japanese_policy",),
                    ).fetchone()
                    if policy_row and policy_row["value"] is not None:
                        raw_non_jp_policy_value = str(policy_row["value"])
                finally:
                    conn.close()
        for row in legacy_rows:
            canonical_key = _canonicalize_setting_key(str(row["key"]))
            if canonical_key and canonical_key not in canonical_present_keys:
                compat_updates[canonical_key] = str(row["value"])
        raw_legacy_non_jp = raw_non_jp_policy_value if raw_non_jp_policy_value is not None else all_s.get("sbv2_jp_extra_non_japanese_policy", "")
        normalized_non_jp = _normalize_non_japanese_policy_value(str(raw_legacy_non_jp))
        if str(raw_legacy_non_jp) != normalized_non_jp:
            compat_updates["sbv2_jp_extra_non_japanese_policy"] = normalized_non_jp
        if compat_updates:
            settings_set_bulk(compat_updates)
            all_s.update(compat_updates)
        if "search_enabled" in all_s:
            _search_enabled = str(all_s["search_enabled"]).lower() in ("true", "1", "yes")
        if "streaming_enabled" in all_s:
            _llm_streaming = str(all_s["streaming_enabled"]).lower() in ("true", "1", "yes")
        if "ctx_size" in all_s:
            try:
                _current_n_ctx = max(512, min(int(all_s["ctx_size"]), 65535))
            except Exception:
                pass
        _sync_ensemble_settings_to_opencode_json()
        _apply_ensemble_execution_mode_guard()
        print(f"[settings] restored from DB: ctx={_current_n_ctx} stream={_llm_streaming} search={_search_enabled}")
    except Exception as e:
        print(f"[settings] restore warning: {e}")


def _cleanup_legacy_llm_settings():
    """過去版のLLM設定キーを settings テーブルから削除する。"""
    legacy_keys = (
        "max_output_tokens",
        "llm_port",
        "echo_sbv2_length",
        "echo_sbv2_sdp_ratio",
        "echo_sbv2_noise",
        "echo_sbv2_noise_w",
        "echo_sbv2_style_weight",
        "echo_sbv2_split_interval",
        "echo_sbv2_pitch_scale",
        "echo_sbv2_intonation_scale",
    )
    with _model_db_lock:
        conn = _get_model_db(create_if_missing=False)
        if conn is None:
            return
        try:
            q = ",".join("?" for _ in legacy_keys)
            conn.execute(f"DELETE FROM settings WHERE key IN ({q})", legacy_keys)
            conn.commit()
        finally:
            conn.close()


def _cleanup_legacy_catalog_rows():
    with _model_db_lock:
        conn = _get_model_db(create_if_missing=False)
        if conn is None:
            return
        try:
            conn.execute("DELETE FROM models WHERE notes='bundled' OR id LIKE 'catalog_%'")
            conn.commit()
        finally:
            conn.close()


# =========================
# リポジトリ設定（非機密 → settings テーブルに格納）
# =========================
_REPO_CONFIG_KEYS = [
    "github_username", "github_repo_name", "github_repo_visibility",
    "github_default_branch", "github_remote_url",
]
_REPO_CONFIG_DEFAULTS = {
    "github_username": "",
    "github_repo_name": "codeagent-data",
    "github_repo_visibility": "private",
    "github_default_branch": "main",
    "github_remote_url": "",
}

def repo_config_load() -> dict:
    """リポジトリ設定を settings テーブルからロード"""
    result = dict(_REPO_CONFIG_DEFAULTS)
    for key in _REPO_CONFIG_KEYS:
        val = settings_get(key)
        if val:
            result[key] = val
    return result

def repo_config_save(data: dict):
    """リポジトリ設定を settings テーブルに保存（機密キーはスキップ）"""
    filtered = {k: v for k, v in data.items() if k in _REPO_CONFIG_KEYS}
    settings_set_bulk(filtered)


_VLM_PATTERNS = re.compile(
    r"(?:llava|bakllava|moondream|idefics|minicpm.v|cogvlm|qwen.?vl|internvl|phi.?vision|"
    r"pixtral|llama.?3.?2.?vision|minicpm.?vision|smolvlm|paligemma|florence|"
    r"gemma.?3|janus|vision|vlm|mmproj|visual)", re.I)


def _detect_vlm(path: str, name: str) -> bool:
    return bool(_VLM_PATTERNS.search((os.path.basename(path) + " " + name).lower()))


def _get_file_size_mb(path: str) -> int:
    try:
        return int(os.path.getsize(path) / (1024 * 1024))
    except:
        return -1


def _read_meminfo_kb() -> tuple[int, int]:
    total_kb = 0
    avail_kb = 0
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        avail_kb = int(line.split()[1])
            return total_kb, avail_kb
    except Exception:
        pass
    return 0, 0


def _parse_int_maybe(v) -> int:
    s = str(v or "").strip().replace(",", "")
    return int(s) if s.isdigit() else -1


def _probe_gpu_static(backend: str) -> list[dict]:
    gpus: list[dict] = []
    if backend == "nvidia-smi":
        for cmd in [
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],  # 1
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],  # 2
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],              # 3
            ["nvidia-smi", "-L"],                                                                           # 4
            ["nvidia-smi", "dmon", "-s", "m", "-c", "1"],                                                  # 5
        ]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                for line in (r.stdout or "").splitlines():
                    parts = [x.strip() for x in line.split(",")]
                    if len(parts) >= 3:
                        total = _parse_int_maybe(parts[1]); x3 = _parse_int_maybe(parts[2])
                        if total > 0:
                            free = x3 if "free" in " ".join(cmd) else (max(0, total - max(0, x3)) if x3 >= 0 else -1)
                            gpus.append({"name": parts[0], "memory_total_mb": total, "memory_free_mb": free})
                    elif cmd[-1] == "-L" and "GPU " in line:
                        gpus.append({"name": line.strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                if gpus:
                    break
            except Exception:
                continue
    elif backend == "rocm-smi":
        # 5 strategies: rocm-smi json/text/alt json + rocminfo + rocm_agent_enumerator
        try:
            r = subprocess.run(["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"], capture_output=True, text=True, timeout=8)
            if r.returncode == 0 and (r.stdout or "").strip().startswith("{"):
                data = json.loads(r.stdout)
                for _, info in data.items():
                    if not isinstance(info, dict):
                        continue
                    total_b = info.get("VRAM Total Memory (B)") or info.get("VRAM Total Used Memory (B)")
                    used_b = info.get("VRAM Total Used Memory (B)")
                    if isinstance(total_b, (int, float)) and total_b > 0:
                        total_mb = int(total_b / (1024 * 1024))
                        used_mb = int((used_b or 0) / (1024 * 1024))
                        gpus.append({"name": str(info.get("Card series") or info.get("Card SKU") or "AMD GPU"), "memory_total_mb": total_mb, "memory_free_mb": max(0, total_mb - used_mb)})
        except Exception:
            pass
        if not gpus:
            for cmd in [
                ["rocm-smi", "--showproductname", "--showmeminfo", "vram"],                 # 2
                ["rocm-smi", "--showproductname", "--showmeminfo", "all", "--json"],        # 3
                ["rocminfo"],                                                                # 4
                ["rocm_agent_enumerator"],                                                   # 5
            ]:
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    out = r.stdout or ""
                    if cmd[0] == "rocminfo":
                        for ln in out.splitlines():
                            if "Marketing Name" in ln:
                                gpus.append({"name": ln.split(":", 1)[-1].strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                    elif cmd[0] == "rocm_agent_enumerator":
                        for ln in out.splitlines():
                            if ln.strip() and ln.strip() != "gfx000":
                                gpus.append({"name": f"AMD GPU {ln.strip()}", "memory_total_mb": -1, "memory_free_mb": -1})
                    else:
                        for ln in out.splitlines():
                            if "Card series" in ln or "Card SKU" in ln:
                                gpus.append({"name": ln.split(":", 1)[-1].strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                    if gpus:
                        break
                except Exception:
                    continue
    elif backend == "nvidia-proc":
        # 5 strategies all from proc/sys sources
        try:
            base = "/proc/driver/nvidia/gpus"  # 1
            if os.path.isdir(base):
                for name in os.listdir(base):
                    info_path = os.path.join(base, name, "information")
                    if os.path.exists(info_path):
                        gpu_name = "NVIDIA GPU"
                        with open(info_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                if line.lower().startswith("model:"):
                                    gpu_name = line.split(":", 1)[1].strip()
                        gpus.append({"name": gpu_name, "memory_total_mb": -1, "memory_free_mb": -1})
        except Exception:
            pass
        if not gpus and os.path.exists("/proc/driver/nvidia/version"):  # 2
            gpus.append({"name": "NVIDIA GPU (/proc version)", "memory_total_mb": -1, "memory_free_mb": -1})
        if not gpus:
            for path in ["/proc/modules", "/sys/module/nvidia/version", "/sys/class/drm"]:  # 3/4/5
                try:
                    if os.path.exists(path):
                        gpus.append({"name": "NVIDIA GPU (kernel module)", "memory_total_mb": -1, "memory_free_mb": -1})
                        break
                except Exception:
                    pass
    elif backend == "lspci":
        for cmd in [
            ["lspci"],                  # 1
            ["lspci", "-nn"],           # 2
            ["lspci", "-vnn"],          # 3
            ["lshw", "-C", "display"],  # 4
            ["hwinfo", "--gfxcard"],    # 5
        ]:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                for line in (r.stdout or "").splitlines():
                    low = line.lower()
                    if any(k in low for k in ["vga", "3d controller", "display", "model:"]) and any(v in low for v in ["nvidia", "amd", "advanced micro devices", "radeon", "geforce"]):
                        gpus.append({"name": line.split(":", 1)[-1].strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                if gpus:
                    break
            except Exception:
                continue
    elif backend == "windows-counter" and os.name == "nt":
        # 最優先: レジストリから64bit正確なVRAM値を取得 (AdapterRAM uint32オーバーフロー回避)
        try:
            import winreg
            reg_base = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            for ri in range(16):
                reg_sub = f"{reg_base}\\{ri:04d}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_sub) as rk:
                        try:
                            rname = str(winreg.QueryValueEx(rk, "DriverDesc")[0])
                        except OSError:
                            try:
                                rname = str(winreg.QueryValueEx(rk, "HardwareInformation.AdapterString")[0]).rstrip('\x00')
                            except OSError:
                                rname = ""
                        if not rname:
                            continue
                        vb = 0
                        for vkey in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                            try:
                                vb = int(winreg.QueryValueEx(rk, vkey)[0])
                                if vb > 0:
                                    break
                            except OSError:
                                continue
                        vmb = int(vb / (1024 * 1024)) if vb > 0 else -1
                        gpus.append({"name": rname, "memory_total_mb": vmb, "memory_free_mb": -1})
                except OSError:
                    continue
        except Exception:
            pass
        # フォールバック: WMI / CIM / PNP / wmic / dxdiag
        if not gpus:
            for ps in [
                "$gpu = Get-WmiObject Win32_VideoController | Where-Object { $_.AdapterRAM -gt 0 -and $_.Name -notmatch 'Virtual' } | Select-Object -First 1; "
                "$name = if ($gpu) { [string]$gpu.Name } else { 'Windows GPU' }; $totalB = if ($gpu) { [double]$gpu.AdapterRAM } else { 0 }; "
                "$obj = @{ name=$name; total_mb=[math]::Round($totalB/1MB) }; $obj | ConvertTo-Json -Compress",
                "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name,AdapterRAM | ConvertTo-Json -Compress",
                "Get-PnpDevice -Class Display | Select-Object -ExpandProperty FriendlyName | ConvertTo-Json -Compress",
                "wmic path win32_VideoController get name,AdapterRAM",
                "dxdiag /whql:off /dontskip /t $env:TEMP\\dxdiag_gpu.txt; Get-Content $env:TEMP\\dxdiag_gpu.txt",
            ]:
                try:
                    r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=12)
                    out = (r.stdout or "").strip()
                    if not out:
                        continue
                    data = None
                    try:
                        data = json.loads(out)
                    except Exception:
                        data = None
                    if isinstance(data, dict):
                        name = str(data.get("Name") or data.get("name") or "Windows GPU")
                        total_mb = int((data.get("AdapterRAM") or data.get("total_mb") or 0) / (1024 * 1024)) if isinstance(data.get("AdapterRAM"), (int, float)) else int(data.get("total_mb") or -1)
                        gpus.append({"name": name, "memory_total_mb": total_mb, "memory_free_mb": -1})
                    elif isinstance(data, list):
                        for row in data:
                            gpus.append({"name": str(row if isinstance(row, str) else row.get("name") or row.get("Name") or "Windows GPU"), "memory_total_mb": -1, "memory_free_mb": -1})
                    else:
                        for line in out.splitlines():
                            if line.strip() and "name" not in line.lower():
                                gpus.append({"name": line.strip(), "memory_total_mb": -1, "memory_free_mb": -1})
                    if gpus:
                        break
                except Exception:
                    continue
    return gpus


def _select_working_gpu_backend(setting_key: str, candidates: list[str]) -> tuple[str, list[dict]]:
    preferred = (settings_get(setting_key) or "auto").strip()
    if preferred and preferred not in ("auto", "none"):
        g = _probe_gpu_static(preferred)
        if g:
            return preferred, g
    for b in candidates:
        g = _probe_gpu_static(b)
        if g:
            settings_set(setting_key, b)
            return b, g
    settings_set(setting_key, "none")
    return "none", []


def get_system_hardware_info() -> dict:
    ram_total_mb = -1
    ram_available_mb = -1
    try:
        if os.name == "nt":
            ps = (
                "$os = Get-CimInstance Win32_OperatingSystem; "
                "$total = [math]::Round($os.TotalVisibleMemorySize / 1024); "
                "$avail = [math]::Round($os.FreePhysicalMemory / 1024); "
                "Write-Output \"$total,$avail\""
            )
            r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=3)
            out = r.stdout.strip()
            if "," in out:
                t, a = out.split(",", 1)
                ram_total_mb = int(t)
                ram_available_mb = int(a)
        else:
            t_kb, a_kb = _read_meminfo_kb()
            if t_kb > 0:
                ram_total_mb = int(t_kb / 1024)
            if a_kb > 0:
                ram_available_mb = int(a_kb / 1024)
    except Exception:
        pass

    candidates = ["nvidia-smi", "rocm-smi", "nvidia-proc", "lspci"] if os.name != "nt" else ["windows-counter", "nvidia-smi"]
    gpu_backend, gpus = _select_working_gpu_backend("gpu_static_backend", candidates)

    vram_total_mb = sum(g["memory_total_mb"] for g in gpus) if gpus else -1
    vram_free_mb = sum(g["memory_free_mb"] for g in gpus) if gpus else -1
    return {
        "os": platform.platform(),
        "is_runpod": _is_runpod_env(),
        "ram_total_mb": ram_total_mb,
        "ram_available_mb": ram_available_mb,
        "vram_total_mb": vram_total_mb,
        "vram_free_mb": vram_free_mb,
        "gpus": gpus,
        "gpu_backend": gpu_backend,
        "gpu_backend_selected": settings_get("gpu_static_backend") or "auto",
    }


def get_system_usage_info(debug_mode: bool = False) -> dict:
    """
    現在のCPU/GPU使用率とRAM/VRAM使用量を返す。
    可能な限り依存なしで取得し、取得不可項目は -1 を返す。
    """
    cpu_percent = -1.0
    ram_total_mb = -1
    ram_used_mb = -1
    ram_percent = -1.0
    try:
        import psutil  # type: ignore
        cpu_percent = float(psutil.cpu_percent(interval=0.15))
        vm = psutil.virtual_memory()
        ram_total_mb = int(vm.total / (1024 * 1024))
        ram_used_mb = int((vm.total - vm.available) / (1024 * 1024))
        ram_percent = float(vm.percent)
    except Exception:
        try:
            if os.name == "nt":
                ps = (
                    "$os = Get-CimInstance Win32_OperatingSystem; "
                    "$cpu = (Get-Counter '\\Processor(_Total)\\% Processor Time').CounterSamples[0].CookedValue; "
                    "$total = [math]::Round($os.TotalVisibleMemorySize / 1024); "
                    "$avail = [math]::Round($os.FreePhysicalMemory / 1024); "
                    "$used = $total - $avail; "
                    "$ramPct = if ($total -gt 0) { ($used / $total) * 100 } else { 0 }; "
                    "Write-Output (\"{0},{1},{2},{3}\" -f [math]::Round($cpu,1),$total,$used,[math]::Round($ramPct,1))"
                )
                r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=8)
                out = (r.stdout or "").strip()
                if "," in out:
                    cpu_s, total_s, used_s, pct_s = out.split(",", 3)
                    cpu_percent = float(cpu_s)
                    ram_total_mb = int(total_s)
                    ram_used_mb = int(used_s)
                    ram_percent = float(pct_s)
            else:
                if hasattr(os, "getloadavg"):
                    load1, _, _ = os.getloadavg()
                    c = os.cpu_count() or 1
                    cpu_percent = max(0.0, min(100.0, (load1 / c) * 100.0))
                t_kb, a_kb = _read_meminfo_kb()
                if t_kb > 0:
                    ram_total_mb = int(t_kb / 1024)
                if a_kb > 0 and ram_total_mb > 0:
                    ram_used_mb = max(0, ram_total_mb - int(a_kb / 1024))
                    ram_percent = (ram_used_mb / ram_total_mb) * 100.0
        except Exception:
            pass

    def _windows_registry_gpu_vram() -> tuple[str, int]:
        """Windowsレジストリから GPU 名と VRAM(MB) を取得。64bit値対応で4GB超も正確。"""
        if os.name != "nt":
            return ("", -1)
        try:
            import winreg
            base_path = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            best_name = ""
            best_vram_mb = -1
            for i in range(16):
                subkey = f"{base_path}\\{i:04d}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                        try:
                            name = str(winreg.QueryValueEx(key, "DriverDesc")[0])
                        except OSError:
                            name = ""
                        # まず qwMemorySize (64bit QWORD) を試す
                        vram_bytes = 0
                        try:
                            vram_bytes = int(winreg.QueryValueEx(key, "HardwareInformation.qwMemorySize")[0])
                        except OSError:
                            pass
                        # フォールバック: MemorySize (DWORD, 4GB超でオーバーフローの可能性)
                        if vram_bytes <= 0:
                            try:
                                vram_bytes = int(winreg.QueryValueEx(key, "HardwareInformation.MemorySize")[0])
                            except OSError:
                                pass
                        if vram_bytes <= 0:
                            try:
                                val = winreg.QueryValueEx(key, "HardwareInformation.AdapterString")[0]
                                if val and not name:
                                    name = str(val).rstrip('\x00')
                            except OSError:
                                pass
                            continue
                        vram_mb = int(vram_bytes / (1024 * 1024))
                        if vram_mb > best_vram_mb:
                            best_name = name
                            best_vram_mb = vram_mb
                except OSError:
                    continue
            return (best_name, best_vram_mb)
        except Exception:
            return ("", -1)

    def _windows_dxdiag_dedicated_vram_mb() -> int:
        if os.name != "nt":
            return -1
        now = _mm_time.time()
        with _usage_diag_lock:
            cached_mb = int(_windows_dxdiag_cache.get("mb", -1))
            checked_at = float(_windows_dxdiag_cache.get("checked_at", 0.0))
        # 成功値は10分、失敗値は30秒キャッシュしてポーリング遅延を防ぐ
        if cached_mb > 0 and (now - checked_at) < 600:
            return cached_mb
        if cached_mb <= 0 and (now - checked_at) < 30:
            return -1
        tf_path = ""
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(prefix="dxdiag_", suffix=".txt", delete=False) as tf:
                tf_path = tf.name
            subprocess.run(["dxdiag", "/64bit", "/whql:off", "/t", tf_path], capture_output=True, text=True, timeout=15)
            raw = b""
            with open(tf_path, "rb") as f:
                raw = f.read()
            txt = ""
            for enc in ("utf-16", "utf-8", "cp932"):
                try:
                    txt = raw.decode(enc)
                    if txt:
                        break
                except Exception:
                    continue
            if not txt:
                return -1
            m = re.search(r"Dedicated Memory:\s*([\d,]+)\s*(MB|GB)", txt, re.IGNORECASE)
            if not m:
                m = re.search(r"専用メモリ:\s*([\d,]+)\s*(MB|GB)", txt, re.IGNORECASE)
            if not m:
                return -1
            val = int(m.group(1).replace(",", ""))
            unit = (m.group(2) or "MB").upper()
            mb = int(val * 1024) if unit == "GB" else int(val)
            with _usage_diag_lock:
                _windows_dxdiag_cache["mb"] = mb
                _windows_dxdiag_cache["checked_at"] = now
            return mb
        except Exception:
            return -1
        finally:
            with _usage_diag_lock:
                # 失敗時もchecked_atだけ更新して連続実行を抑制
                if int(_windows_dxdiag_cache.get("mb", -1)) <= 0:
                    _windows_dxdiag_cache["checked_at"] = now
            try:
                if tf_path and os.path.exists(tf_path):
                    os.remove(tf_path)
            except Exception:
                pass

    def _windows_pdh_counter_max(path: str) -> float:
        """Windows PDHをctypesで直接読み、ワイルドカード展開したカウンタの最大値を返す。失敗時-1。"""
        if os.name != "nt":
            return -1.0
        try:
            import ctypes
            from ctypes import wintypes

            PDH_MORE_DATA = 0x800007D2
            PDH_FMT_DOUBLE = 0x00000200

            class _PDH_FMT_COUNTERVALUE_UNION(ctypes.Union):
                _fields_ = [("longValue", ctypes.c_long), ("doubleValue", ctypes.c_double), ("largeValue", ctypes.c_longlong)]

            class _PDH_FMT_COUNTERVALUE(ctypes.Structure):
                _fields_ = [("CStatus", wintypes.DWORD), ("u", _PDH_FMT_COUNTERVALUE_UNION)]

            pdh = ctypes.WinDLL("pdh")
            expand = pdh.PdhExpandWildCardPathW
            open_query = pdh.PdhOpenQueryW
            add_english = getattr(pdh, "PdhAddEnglishCounterW", None)
            add_counter = pdh.PdhAddCounterW
            collect = pdh.PdhCollectQueryData
            get_value = pdh.PdhGetFormattedCounterValue
            close_query = pdh.PdhCloseQuery

            # 1) wildcard展開
            size = wintypes.DWORD(0)
            rc = expand(None, path, None, ctypes.byref(size), 0)
            if rc not in (0, PDH_MORE_DATA) or size.value <= 0:
                return -1.0
            buf = ctypes.create_unicode_buffer(size.value)
            rc = expand(None, path, buf, ctypes.byref(size), 0)
            if rc != 0:
                return -1.0
            expanded = [p for p in buf[:size.value].split("\x00") if p]
            if not expanded:
                return -1.0

            # 2) 各カウンタを収集して最大値を採用
            best = -1.0
            for ctr_path in expanded:
                hq = ctypes.c_void_p()
                hc = ctypes.c_void_p()
                if open_query(None, 0, ctypes.byref(hq)) != 0 or not hq.value:
                    continue
                try:
                    if add_english:
                        add_rc = add_english(hq, ctr_path, 0, ctypes.byref(hc))
                        # 環境によってはEnglishカウンタ登録に失敗するため通常APIへフォールバック
                        if add_rc != 0:
                            add_rc = add_counter(hq, ctr_path, 0, ctypes.byref(hc))
                    else:
                        add_rc = add_counter(hq, ctr_path, 0, ctypes.byref(hc))
                    if add_rc != 0 or not hc.value:
                        continue
                    collect(hq)
                    _mm_time.sleep(0.05)
                    collect(hq)
                    ctype = wintypes.DWORD(0)
                    val = _PDH_FMT_COUNTERVALUE()
                    if get_value(hc, PDH_FMT_DOUBLE, ctypes.byref(ctype), ctypes.byref(val)) == 0:
                        v = float(val.u.doubleValue)
                        if v > best:
                            best = v
                finally:
                    close_query(hq)
            return best
        except Exception:
            return -1.0

    candidates = ["nvidia-smi", "rocm-smi", "nvidia-proc", "lspci"] if os.name != "nt" else ["windows-counter", "nvidia-smi"]
    selected = (settings_get("gpu_usage_backend") or "auto").strip()
    if selected in ("", "auto", "none"):
        selected, _ = _select_working_gpu_backend("gpu_usage_backend", candidates)
    gpus = []
    parse_summary: list[dict] = []
    nvidia_fail_reason = ""
    parse_source = "unknown"
    gpu_backend = selected if selected else "none"
    cmd_timeout_sec = 8 if debug_mode else 2
    if selected == "nvidia-smi":
        nvidia_cmds = [
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total", "--format=csv,noheader"],
            ["nvidia-smi", "-q", "-d", "UTILIZATION,MEMORY"],
            ["nvidia-smi", "dmon", "-s", "u", "-c", "1"],
            ["nvidia-smi", "-L"],
        ]
        for cmd in (nvidia_cmds if debug_mode else nvidia_cmds[:2]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                if r.returncode != 0 and not (r.stdout or "").strip():
                    parse_summary.append({
                        "cmd": " ".join(cmd),
                        "ok": False,
                        "reason": f"returncode={r.returncode}",
                        "stderr_head": (r.stderr or "").strip()[:120],
                    })
                    continue
                parsed_this_cmd = 0
                for line in (r.stdout or "").splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 4:
                        util = float(re.sub(r'[^0-9.]', '', parts[1]) or -1)
                        used = _parse_int_maybe(re.sub(r'[^0-9]', '', parts[2]))
                        total = _parse_int_maybe(re.sub(r'[^0-9]', '', parts[3]))
                        pct = (used / total * 100.0) if used >= 0 and total > 0 else -1.0
                        gpus.append({"name": parts[0], "util_percent": util, "vram_used_mb": used, "vram_total_mb": total, "vram_percent": pct})
                        parsed_this_cmd += 1
                parse_summary.append({
                    "cmd": " ".join(cmd),
                    "ok": parsed_this_cmd > 0,
                    "rows": parsed_this_cmd,
                })
                if gpus:
                    parse_source = "direct"
                    break
                nvidia_fail_reason = "parse fail"
            except FileNotFoundError:
                nvidia_fail_reason = "command not found"
                parse_summary.append({"cmd": " ".join(cmd), "ok": False, "reason": "command not found"})
                break
            except subprocess.TimeoutExpired:
                nvidia_fail_reason = "timeout"
                parse_summary.append({"cmd": " ".join(cmd), "ok": False, "reason": "timeout"})
                continue
            except Exception as e:
                nvidia_fail_reason = f"parse fail ({type(e).__name__})"
                parse_summary.append({"cmd": " ".join(cmd), "ok": False, "reason": f"parse fail: {type(e).__name__}"})
                continue
    elif selected == "rocm-smi":
        rocm_cmds = [
            ["rocm-smi", "--showuse", "--showmeminfo", "vram", "--json"],
            ["rocm-smi", "--showuse", "--showmemuse", "--json"],
            ["rocm-smi", "--showuse", "--showmemuse"],
            ["rocminfo"],
            ["rocm_agent_enumerator"],
        ]
        for cmd in (rocm_cmds if debug_mode else rocm_cmds[:2]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=cmd_timeout_sec)
                out = r.stdout or ""
                if "--json" in cmd:
                    data = json.loads(out or "{}")
                    for _, info in data.items() if isinstance(data, dict) else []:
                        if not isinstance(info, dict):
                            continue
                        util = float(str(info.get("GPU use (%)", "0")).replace("%", "") or -1)
                        vram_pct = float(str(info.get("GPU memory use (%)", "0")).replace("%", "") or -1)
                        vram_used_mb = -1
                        vram_total_mb = -1
                        # --showmeminfo vram provides VRAM Total/Used in bytes
                        total_b = info.get("VRAM Total Memory (B)")
                        used_b = info.get("VRAM Total Used Memory (B)")
                        if isinstance(total_b, (int, float)) and total_b > 0:
                            vram_total_mb = int(total_b / (1024 * 1024))
                            if isinstance(used_b, (int, float)) and used_b >= 0:
                                vram_used_mb = int(used_b / (1024 * 1024))
                                vram_pct = (vram_used_mb / vram_total_mb * 100.0) if vram_total_mb > 0 else -1.0
                        # --showmemuse provides GPU memory use (%) only; try GTT as fallback for total
                        if vram_total_mb < 0:
                            for key_total in ("VRAM Total Memory (B)", "GTT Total Memory (B)"):
                                tb = info.get(key_total)
                                if isinstance(tb, (int, float)) and tb > 0:
                                    vram_total_mb = int(tb / (1024 * 1024))
                                    break
                        if vram_used_mb < 0:
                            for key_used in ("VRAM Total Used Memory (B)", "GTT Total Used Memory (B)"):
                                ub = info.get(key_used)
                                if isinstance(ub, (int, float)) and ub >= 0:
                                    vram_used_mb = int(ub / (1024 * 1024))
                                    break
                        if vram_pct < 0 and vram_used_mb >= 0 and vram_total_mb > 0:
                            vram_pct = (vram_used_mb / vram_total_mb) * 100.0
                        gpus.append({"name": str(info.get("Card series") or info.get("Card SKU") or "AMD GPU"), "util_percent": util, "vram_used_mb": vram_used_mb, "vram_total_mb": vram_total_mb, "vram_percent": vram_pct})
                else:
                    for line in out.splitlines():
                        if "Card series" in line or "Card SKU" in line:
                            gpus.append({"name": line.split(":",1)[-1].strip(), "util_percent": -1, "vram_used_mb": -1, "vram_total_mb": -1, "vram_percent": -1})
                if gpus:
                    parse_source = "direct"
                    break
            except Exception:
                continue
    elif selected == "windows-counter" and os.name == "nt":
        # まずはPython(ctypes + PDH)で直接カウンタを読む
        py_util = _windows_pdh_counter_max(r"\GPU Engine(*)\Utilization Percentage")
        py_used_b = _windows_pdh_counter_max(r"\GPU Adapter Memory(*)\Dedicated Usage")
        py_ded_limit_b = _windows_pdh_counter_max(r"\GPU Adapter Memory(*)\Dedicated Limit")
        py_shr_limit_b = _windows_pdh_counter_max(r"\GPU Adapter Memory(*)\Shared Limit")
        py_total_b = max(py_ded_limit_b, py_shr_limit_b)
        # レジストリから GPU名 と VRAM総量(64bit正確値) を取得
        reg_name, reg_mb = _windows_registry_gpu_vram()
        # PDH Dedicated Limit が取れない場合のフォールバック順:
        # 1) レジストリ(64bit正確値) → 2) dxdiag
        if py_total_b <= 0:
            if reg_mb > 0:
                py_total_b = float(reg_mb * 1024 * 1024)
            else:
                dx_mb = _windows_dxdiag_dedicated_vram_mb()
                py_total_b = float(dx_mb * 1024 * 1024) if dx_mb > 0 else -1
        py_used_mb = int(round(py_used_b / (1024 * 1024))) if py_used_b >= 0 else -1
        py_total_mb = int(round(py_total_b / (1024 * 1024))) if py_total_b > 0 else -1
        py_pct = (py_used_mb / py_total_mb * 100.0) if py_used_mb >= 0 and py_total_mb > 0 else -1.0
        if py_util >= 0 or py_used_mb >= 0 or py_total_mb > 0:
            gpus.append({
                "name": reg_name or "Windows GPU",
                "util_percent": float(py_util),
                "vram_used_mb": py_used_mb,
                "vram_total_mb": py_total_mb,
                "vram_percent": py_pct,
            })
            parse_source = "direct"

        if gpus:
            pass
        else:
            windows_cmds = [
            "$adapters = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | "
            "  Where-Object { $_.AdapterRAM -gt 0 -and $_.Name -notmatch 'Virtual|Remote|Basic Display' }; "
            "$gpu = $adapters | Sort-Object AdapterRAM -Descending | Select-Object -First 1; "
            "$name = if ($gpu) { [string]$gpu.Name } else { 'Windows GPU' }; "
            "$totalB = if ($gpu) { [double]$gpu.AdapterRAM } else { -1 }; "
            "$engine = (Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples; "
            "$util = if ($engine) { [double](($engine | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$dedicated = (Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples; "
            "$usedB = if ($dedicated) { [double](($dedicated | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$dedicatedLimit = (Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Limit' -ErrorAction SilentlyContinue).CounterSamples; "
            "$dedicatedLimitB = if ($dedicatedLimit) { [double](($dedicatedLimit | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$sharedLimit = (Get-Counter '\\GPU Adapter Memory(*)\\Shared Limit' -ErrorAction SilentlyContinue).CounterSamples; "
            "$sharedLimitB = if ($sharedLimit) { [double](($sharedLimit | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$counterTotalB = [Math]::Max($dedicatedLimitB, $sharedLimitB); "
            "if ($totalB -le 0 -and $counterTotalB -gt 0) { $totalB = $counterTotalB }; "
            "$totalMb = if ($totalB -gt 0) { [math]::Round($totalB / 1MB) } else { -1 }; "
            "$usedMb = if ($usedB -ge 0) { [math]::Round($usedB / 1MB) } else { -1 }; "
            "$vramPct = if ($totalMb -gt 0 -and $usedMb -ge 0) { [math]::Round(($usedMb / $totalMb) * 100, 1) } else { -1 }; "
            "$obj=@{ name=$name; util=[math]::Round($util,1); total_mb=$totalMb; used_mb=$usedMb; vram_pct=$vramPct }; "
            "$obj|ConvertTo-Json -Compress",
            "$gpu = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | "
            "  Where-Object { $_.AdapterRAM -gt 0 -and $_.Name -notmatch 'Virtual|Remote|Basic Display' } | "
            "  Sort-Object AdapterRAM -Descending | Select-Object -First 1; "
            "$name = if ($gpu) { [string]$gpu.Name } else { 'Windows GPU' }; "
            "$totalB = if ($gpu) { [double]$gpu.AdapterRAM } else { -1 }; "
            "$engine = (Get-Counter '\\GPU Engine(*)\\Utilization Percentage' -ErrorAction SilentlyContinue).CounterSamples; "
            "$util = if ($engine) { [double](($engine | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$dedicated = (Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage' -ErrorAction SilentlyContinue).CounterSamples; "
            "$usedB = if ($dedicated) { [double](($dedicated | Measure-Object CookedValue -Maximum).Maximum) } else { -1 }; "
            "$totalMb = if ($totalB -gt 0) { [math]::Round($totalB / 1MB) } else { -1 }; "
            "$usedMb = if ($usedB -ge 0) { [math]::Round($usedB / 1MB) } else { -1 }; "
            "$vramPct = if ($totalMb -gt 0 -and $usedMb -ge 0) { [math]::Round(($usedMb / $totalMb) * 100, 1) } else { -1 }; "
            "$obj=@{ name=$name; util=[math]::Round($util,1); total_mb=$totalMb; used_mb=$usedMb; vram_pct=$vramPct }; "
            "$obj|ConvertTo-Json -Compress",
            "Get-CimInstance Win32_VideoController | Select-Object -First 1 Name,AdapterRAM | ConvertTo-Json -Compress",
            "wmic path win32_VideoController get name,AdapterRAM",
            "Get-PnpDevice -Class Display | ConvertTo-Json -Compress",
        ]
            for ps in (windows_cmds if debug_mode else windows_cmds[:2]):
                try:
                    r = subprocess.run(["powershell", "-Command", ps], capture_output=True, text=True, timeout=(10 if debug_mode else 6))
                    out = (r.stdout or "").strip()
                    if not out:
                        continue
                    try:
                        data = json.loads(out)
                        if isinstance(data, dict):
                            total = int((data.get("AdapterRAM") or 0) / (1024*1024)) if isinstance(data.get("AdapterRAM"), (int,float)) else int(data.get("total_mb") or -1)
                            if total <= 0:
                                total = _windows_dxdiag_dedicated_vram_mb()
                            if total <= 0:
                                total = -1
                            used = int(data.get("used_mb") or -1)
                            pct = float(data.get("vram_pct") or -1)
                            if pct < 0 and used >= 0 and total > 0:
                                pct = (used / total) * 100.0
                            gpus.append({
                                "name": str(data.get("name") or data.get("Name") or "Windows GPU"),
                                "util_percent": float(data.get("util") or -1),
                                "vram_used_mb": used,
                                "vram_total_mb": total,
                                "vram_percent": pct,
                            })
                    except Exception:
                        for ln in out.splitlines():
                            if ln.strip() and "name" not in ln.lower():
                                gpus.append({"name": ln.strip(), "util_percent": -1, "vram_used_mb": -1, "vram_total_mb": -1, "vram_percent": -1})
                    if gpus:
                        parse_source = "direct"
                        break
                except Exception:
                    continue
    if not gpus:
        static_list = _probe_gpu_static(selected if selected != "none" else candidates[0])
        gpus = [{"name": g.get("name","GPU"), "util_percent": -1, "vram_used_mb": -1, "vram_total_mb": g.get("memory_total_mb",-1), "vram_percent": -1} for g in static_list]
        gpu_backend = selected
        if gpus:
            parse_source = "fallback"

    vram_confidence = "unknown"
    if str(parse_source).startswith("direct"):
        vram_confidence = "direct"
    elif parse_source == "fallback":
        vram_confidence = "fallback"

    adopted_values = {
        "gpu_count": len(gpus),
        "gpu0_name": gpus[0].get("name", "") if gpus else "",
        "gpu0_vram_used_mb": gpus[0].get("vram_used_mb", -1) if gpus else -1,
        "gpu0_vram_total_mb": gpus[0].get("vram_total_mb", -1) if gpus else -1,
        "gpu0_util_percent": gpus[0].get("util_percent", -1) if gpus else -1,
    }
    diag = {
        "gpu_backend_selected": selected,
        "gpu_backend": gpu_backend,
        "parse_source": parse_source,
        "nvidia_smi_failure_reason": nvidia_fail_reason if selected == "nvidia-smi" else "",
        "raw_parse_summary": parse_summary,
        "adopted_values": adopted_values,
        "updated_at": datetime.now().isoformat(),
    }
    _set_last_usage_diag(diag)

    return {
        "cpu_percent": round(cpu_percent, 1) if cpu_percent >= 0 else -1,
        "ram_total_mb": ram_total_mb,
        "ram_used_mb": ram_used_mb,
        "ram_percent": round(ram_percent, 1) if ram_percent >= 0 else -1,
        "gpu_backend": gpu_backend,
        "gpu_backend_selected": selected,
        "vram_source_backend": gpu_backend,
        "vram_confidence": vram_confidence,
        "gpus": gpus,
        "updated_at": datetime.now().isoformat(),
    }


def _infer_quantization_from_name(name: str) -> str:
    up = (name or "").upper()
    for q in [
        "IQ1_S", "Q2_K", "IQ2_M", "IQ2_XS", "IQ3_M", "Q3_K_S", "Q3_K_M", "Q3_K_L",
        "Q4_0", "Q4_1", "Q4_K_S", "Q4_K_M", "Q5_0", "Q5_1", "Q5_K_S", "Q5_K_M",
        "Q6_K", "Q8_0", "F16", "BF16",
    ]:
        if q in up:
            return q
    return ""


def _infer_ctx_size_from_name(name: str, default_ctx: int | None = None) -> int:
    if default_ctx is None:
        default_ctx = _resolve_default_ctx_size()
    text = (name or "").lower()
    # 例: 32k / 128k / ctx4096
    mk = re.search(r"(\d{1,4})k(?:[^a-z0-9]|$)", text)
    if mk:
        k = int(mk.group(1))
        if 1 <= k <= 1024:
            return k * 1024
    mctx = re.search(r"ctx[_\-]?(\d{3,7})", text)
    if mctx:
        v = int(mctx.group(1))
        if 512 <= v <= 2_000_000:
            return v
    return default_ctx


def _infer_gpu_layers_for_estimate(file_size_mb: int, quantization: str) -> int:
    # ファイルサイズからざっくり層数を推定（未知時の保守的な目安）
    q = (quantization or "").upper()
    if file_size_mb <= 0:
        return 40
    if file_size_mb <= 2500:
        return 28
    if file_size_mb <= 5500:
        return 32
    if file_size_mb <= 11000:
        return 40
    if file_size_mb <= 22000:
        return 60
    if "Q2" in q or "IQ2" in q:
        return 70
    return 80


def _detect_gpu_vendor() -> str:
    """
    実行環境のGPUベンダーを検出して返す。
    戻り値: 'nvidia' | 'amd' | 'unknown'
    設定キャッシュ(gpu_static_backend)を優先参照し、未設定時のみ直接確認する。
    """
    cached = (settings_get("gpu_static_backend") or "").strip()
    if cached == "nvidia-smi":
        return "nvidia"
    if cached == "rocm-smi":
        return "amd"
    try:
        r = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return "nvidia"
    except Exception:
        pass
    try:
        r = subprocess.run(["rocm-smi", "--showproductname"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            return "amd"
    except Exception:
        pass
    return "unknown"


def _get_total_free_vram_mb() -> int:
    """nvidia-smiで全GPUの空きVRAM合計をMBで取得する。取得できない場合は-1を返す。"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            total = 0
            for line in r.stdout.splitlines():
                v = _parse_int_maybe(line.strip())
                if v > 0:
                    total += v
            if total > 0:
                return total
    except Exception:
        pass
    return -1


def _read_gguf_metadata(path: str) -> dict:
    """
    GGUFファイルのバイナリヘッダを解析してモデルアーキテクチャメタデータを返す。
    パース失敗時は空dictを返す（ベストエフォート）。
    """
    import struct as _struct
    result: dict = {}
    _TYPE_FMT = {
        0: ("<B", 1), 1: ("<b", 1), 2: ("<H", 2), 3: ("<h", 2),
        4: ("<I", 4), 5: ("<i", 4), 6: ("<f", 4), 7: ("<b", 1),
        10: ("<Q", 8), 11: ("<q", 8), 12: ("<d", 8),
    }
    # アーキテクチャ非依存でメタデータを収集するためのサフィックスマッチ
    _SUFFIXES_NEEDED = {
        ".block_count", ".embedding_length",
        ".attention.head_count", ".attention.head_count_kv",
    }
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"GGUF":
                return result
            f.read(4)  # version
            f.read(8)  # n_tensors
            n_kv = _struct.unpack("<Q", f.read(8))[0]

            def _read_str():
                length = _struct.unpack("<Q", f.read(8))[0]
                return f.read(length).decode("utf-8", errors="replace")

            def _read_val(vtype):
                if vtype == 8:   # STRING
                    return _read_str()
                if vtype == 9:   # ARRAY – skip elements, don't store
                    atype = _struct.unpack("<I", f.read(4))[0]
                    alen = _struct.unpack("<Q", f.read(8))[0]
                    for _ in range(alen):
                        _read_val(atype)
                    return None
                if vtype in _TYPE_FMT:
                    fmt, size = _TYPE_FMT[vtype]
                    return _struct.unpack(fmt, f.read(size))[0]
                raise ValueError(f"unknown GGUF type {vtype}")

            for _ in range(n_kv):
                key = _read_str()
                vtype = _struct.unpack("<I", f.read(4))[0]
                val = _read_val(vtype)
                if val is not None and any(key.endswith(s) for s in _SUFFIXES_NEEDED):
                    result[key] = val
                if key == "general.architecture" and val is not None:
                    result[key] = val
    except Exception:
        pass
    return result


def _calc_kv_cache_mb_from_gguf(path: str, ctx: int,
                                  cache_type_k: str = "f16",
                                  cache_type_v: str = "f16") -> int:
    """
    GGUFメタデータから正確なKVキャッシュサイズ(MB)を計算する。
    計算できない場合は0を返す（ヒューリスティックにフォールバックすること）。

    formula: n_layers × n_kv_heads × head_dim × ctx × (k_bytes + v_bytes)
    """
    meta = _read_gguf_metadata(path)
    if not meta:
        return 0

    n_layers = n_heads = n_kv_heads = embed_len = None
    for key, val in meta.items():
        if key.endswith(".block_count") and not n_layers:
            n_layers = val
        elif key.endswith(".embedding_length") and not embed_len:
            embed_len = val
        elif key.endswith(".attention.head_count") and not key.endswith(".head_count_kv") and not n_heads:
            n_heads = val
        elif key.endswith(".attention.head_count_kv") and not n_kv_heads:
            n_kv_heads = val

    if not (n_layers and n_heads and embed_len):
        return 0
    if not n_kv_heads:
        n_kv_heads = n_heads  # GQA非対応モデル

    head_dim = int(embed_len) // int(n_heads)
    _type_bytes = {
        "f32": 4.0, "f16": 2.0, "bf16": 2.0,
        "q8_0": 1.0, "q4_0": 0.5, "q4_1": 0.5625,
        "q5_0": 0.625, "q5_1": 0.6875,
    }
    k_b = _type_bytes.get((cache_type_k or "f16").lower(), 2.0)
    v_b = _type_bytes.get((cache_type_v or "f16").lower(), 2.0)

    kv_mb = int(n_layers) * int(n_kv_heads) * head_dim * int(ctx) * (k_b + v_b) / (1024 * 1024)
    result_mb = max(64, int(kv_mb))
    print(
        f"[GGUF] KV cache from metadata: layers={n_layers}, kv_heads={n_kv_heads}, "
        f"head_dim={head_dim}, ctx={ctx}, k={cache_type_k}/{k_b}B, v={cache_type_v}/{v_b}B "
        f"→ {result_mb}MB"
    )
    return result_mb


def _calc_safe_gpu_layers(spec: dict, force_gpu_layers: int = -1) -> dict:
    """
    VRAMに収まる安全なgpu_layersとKVキャッシュ量子化を決定する。
    Returns: {'gpu_layers': int, 'cache_type_k': str, 'cache_type_v': str}

    優先順位（高速→VRAM節約）:
      1. 全層 + KV f16 in VRAM         ← 最速・最高品質
      2. 全層 + KV q8_0 in VRAM        ← KV 50%削減、品質ほぼ同等
      3. 全層 + KV q4_0 in VRAM        ← KV 75%削減
      4. 部分層 + KV q4_0 in VRAM      ← 最終手段（--no-kv-offloadは使わない）

    NOTE: --no-kv-offload はPCIe帯域幅ボトルネックにより5~20x低速になるため使用しない。
    代わりにKVキャッシュ量子化でVRAMを節約しGPU上に保持する。
    """
    file_size_mb = int(spec.get("file_size_mb", 0) or 0)
    ctx = int(spec.get("ctx", _default_llm_ctx_size()) or _default_llm_ctx_size())
    model_path = spec.get("path", "")
    user_ck = (spec.get("cache_type_k") or "").strip()
    user_cv = (spec.get("cache_type_v") or "").strip()
    q = (spec.get("quantization", "") or "").upper()
    overhead_mb = 320   # llama-server固定オーバーヘッド
    cuda_base_mb = 750  # CUDAコンテキスト+cuBLAS固定（実測ベース）

    free_vram_mb = _get_total_free_vram_mb()
    if free_vram_mb <= 0 or file_size_mb <= 0:
        return {"gpu_layers": 999, "cache_type_k": user_ck, "cache_type_v": user_cv}

    def _kv_mb(ck: str, cv: str) -> int:
        # GGUFメタデータから正確計算を優先
        exact = _calc_kv_cache_mb_from_gguf(model_path, ctx, ck, cv) if model_path else 0
        if exact > 0:
            return exact
        # フォールバック: 量子化係数ベースのヒューリスティック
        kv_coef = 0.10
        if "Q2" in q or "IQ2" in q:    kv_coef = 0.05
        elif "Q3" in q or "IQ3" in q:  kv_coef = 0.06
        elif "Q4" in q:                 kv_coef = 0.08
        elif "Q5" in q:                 kv_coef = 0.10
        elif "Q6" in q:                 kv_coef = 0.12
        elif "Q8" in q:                 kv_coef = 0.16
        elif "F16" in q or "BF16" in q: kv_coef = 0.24
        # cache quantization補正
        if ck == "q8_0" or cv == "q8_0": kv_coef *= 0.5
        elif ck == "q4_0" or cv == "q4_0": kv_coef *= 0.25
        ctx_scale = max(0.25, min(8.0, ctx / 8192.0))
        return max(96, int(file_size_mb * kv_coef * ctx_scale))

    def _fitting_layers(kv_mb: int) -> int:
        available = max(0, free_vram_mb - overhead_mb - cuda_base_mb - kv_mb)
        est = _infer_gpu_layers_for_estimate(file_size_mb, q)
        layers = int(available * est / file_size_mb) if file_size_mb > 0 else 0
        if force_gpu_layers >= 0:
            layers = force_gpu_layers
        return max(0, min(est, layers))

    # ユーザーがKV型を明示指定している場合はそれを優先
    if user_ck and user_cv:
        kv = _kv_mb(user_ck, user_cv)
        total = file_size_mb + kv + overhead_mb + cuda_base_mb
        if total <= free_vram_mb:
            print(f"[ModelManager] 全層GPU+KV {user_ck}/{user_cv}: free={free_vram_mb}MB, kv={kv}MB")
            return {"gpu_layers": 999, "cache_type_k": user_ck, "cache_type_v": user_cv}
        fl = _fitting_layers(kv)
        print(f"[ModelManager] 部分オフロード(ユーザー指定KV {user_ck}): free={free_vram_mb}MB, kv={kv}MB, layers={fl}")
        return {"gpu_layers": fl, "cache_type_k": user_ck, "cache_type_v": user_cv}

    # ─── 自動KVキャッシュ量子化フェーズ ─────────────────────────
    # フェーズ1: 全層 + KV f16（デフォルト、最速）
    kv_f16 = _kv_mb("f16", "f16")
    if file_size_mb + kv_f16 + overhead_mb + cuda_base_mb <= free_vram_mb:
        print(f"[ModelManager] 全層GPU+KV f16: free={free_vram_mb}MB, model={file_size_mb}MB, kv={kv_f16}MB")
        return {"gpu_layers": 999, "cache_type_k": "", "cache_type_v": ""}

    # フェーズ2: 全層 + KV q8_0（50%削減、品質ほぼ同等）
    kv_q8 = _kv_mb("q8_0", "q8_0")
    if file_size_mb + kv_q8 + overhead_mb + cuda_base_mb <= free_vram_mb:
        print(f"[ModelManager] 全層GPU+KV q8_0: free={free_vram_mb}MB, kv {kv_f16}MB→{kv_q8}MB")
        return {"gpu_layers": 999, "cache_type_k": "q8_0", "cache_type_v": "q8_0"}

    # フェーズ3: 全層 + KV q4_0（75%削減）
    kv_q4 = _kv_mb("q4_0", "q4_0")
    if file_size_mb + kv_q4 + overhead_mb + cuda_base_mb <= free_vram_mb:
        print(f"[ModelManager] 全層GPU+KV q4_0: free={free_vram_mb}MB, kv {kv_f16}MB→{kv_q4}MB")
        return {"gpu_layers": 999, "cache_type_k": "q4_0", "cache_type_v": "q4_0"}

    # フェーズ4: 部分層 + KV q4_0（最終手段）
    fl = _fitting_layers(kv_q4)
    print(
        f"[ModelManager] 部分オフロード+KV q4_0: "
        f"free={free_vram_mb}MB, model={file_size_mb}MB, kv_q4={kv_q4}MB, "
        f"overhead+cuda={overhead_mb+cuda_base_mb}MB, layers={fl}"
    )
    return {"gpu_layers": fl, "cache_type_k": "q4_0", "cache_type_v": "q4_0"}


def _disk_free_mb(path: str) -> int:
    target = (path or "").strip() or _default_llm_root_folder()
    try:
        os.makedirs(target, exist_ok=True)
        usage = shutil.disk_usage(target)
        return int(usage.free / (1024 * 1024))
    except Exception:
        return -1


def _estimate_fit(file_size_mb: int, hw: dict, quantization: str = "", ctx_size: int | None = None, gpu_layers: int = -1, disk_free_mb: int = -1) -> dict:
    q = (quantization or "").upper()
    ctx = int(ctx_size or _default_llm_ctx_size())
    gl = int(gpu_layers or -1)
    if gl <= 0:
        gl = _infer_gpu_layers_for_estimate(file_size_mb, q)

    if file_size_mb > 0:
        # 定量子化ごとのKV係数（厳密値ではなく判定用の近似）
        kv_coef = 0.10
        if "Q2" in q or "IQ2" in q:
            kv_coef = 0.05
        elif "Q3" in q or "IQ3" in q:
            kv_coef = 0.06
        elif "Q4" in q:
            kv_coef = 0.08
        elif "Q5" in q:
            kv_coef = 0.10
        elif "Q6" in q:
            kv_coef = 0.12
        elif "Q8" in q:
            kv_coef = 0.16
        elif "F16" in q or "BF16" in q:
            kv_coef = 0.24

        ctx_scale = max(0.25, min(8.0, ctx / 8192.0))
        kv_cache_mb = max(96, int(file_size_mb * kv_coef * ctx_scale))
        assumed_total_layers = max(gl, 40)
        gpu_ratio = max(0.0, min(1.0, gl / float(assumed_total_layers)))
        base_vram_overhead = 320
        base_ram_overhead = 768
        est_vram_mb = int((file_size_mb * gpu_ratio) + (kv_cache_mb * gpu_ratio) + base_vram_overhead)
        est_ram_mb = int((file_size_mb * (1.0 - gpu_ratio) * 1.1) + (kv_cache_mb * (1.0 - gpu_ratio)) + base_ram_overhead)
    else:
        kv_cache_mb = -1
        est_vram_mb = -1
        est_ram_mb = -1
        gpu_ratio = 0.0

    vram_total = int(hw.get("vram_total_mb", -1) or -1)
    vram_free = int(hw.get("vram_free_mb", -1) or -1)
    ram_free = int(hw.get("ram_available_mb", -1) or -1)
    # 全層GPU搭載可否はVRAM最大値（total）で判定。既存LLMがロード中でも正しく評価できる
    full_offload = bool(est_vram_mb > 0 and vram_total > 0 and vram_total >= est_vram_mb)
    runtime_feasible = bool(est_ram_mb > 0 and ram_free > 0 and ram_free >= est_ram_mb)
    downloadable = bool(file_size_mb > 0 and disk_free_mb > 0 and disk_free_mb >= file_size_mb)

    reasons = []
    unknown_count = 0
    if file_size_mb <= 0:
        reasons.append("size不明")
        unknown_count += 1
    if vram_total <= 0:
        reasons.append("VRAM容量不明")
        unknown_count += 1
    elif est_vram_mb > 0 and vram_total < est_vram_mb:
        reasons.append(f"VRAM容量不足({vram_total}MB < {est_vram_mb}MB)")
    if ram_free <= 0:
        reasons.append("空きRAM不明")
        unknown_count += 1
    elif est_ram_mb > 0 and ram_free < est_ram_mb:
        reasons.append(f"RAM不足({ram_free}MB < {est_ram_mb}MB)")
    if disk_free_mb <= 0:
        reasons.append("保存先空き容量不明")
        unknown_count += 1
    elif file_size_mb > 0 and disk_free_mb < file_size_mb:
        reasons.append(f"保存容量不足({disk_free_mb}MB < {file_size_mb}MB)")
    if not q:
        unknown_count += 1
    if ctx_size <= 0:
        unknown_count += 1

    if unknown_count == 0:
        confidence = "high"
    elif unknown_count <= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "estimated_vram_mb": est_vram_mb,
        "estimated_ram_mb": est_ram_mb,
        "estimated_kv_cache_mb": kv_cache_mb,
        "assumed_gpu_layers": gl,
        "assumed_ctx_size": ctx,
        "assumed_quantization": q or "unknown",
        "downloadable": downloadable,
        "runtime_feasible": runtime_feasible,
        "full_offload_possible": full_offload,
        "estimate_confidence": confidence,
        "reason": " / ".join(reasons) if reasons else "実行・保存ともに条件を満たす見込み",
    }


def _fetch_hf_repo_file_sizes(model_id: str) -> dict[str, int]:
    """
    HFのsiblingsにsizeが無いケース向けに tree/files API からサイズを補完。
    """
    headers = {"accept": "application/json"}
    size_map: dict[str, int] = {}
    endpoints = [
        f"https://huggingface.co/api/models/{model_id}/tree/main",
        f"https://huggingface.co/api/models/{model_id}/files",
    ]
    for ep in endpoints:
        try:
            r = requests.get(ep, params={"recursive": "1", "expand": "1"}, headers=headers, timeout=30)
            if not r.ok:
                continue
            data = r.json()
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or item.get("rfilename") or item.get("name") or "").strip()
                size = int(item.get("size") or item.get("lfs", {}).get("size") or 0)
                if path and size > 0:
                    size_map[path] = size
        except Exception:
            continue
        if size_map:
            break
    return size_map


def _ensemble_selected_coder_specs() -> list[dict]:
    catalog = get_runtime_model_catalog(include_disabled=True)
    specs = []
    for mk in get_coder_ladder_keys(catalog):
        spec = catalog.get(mk, {})
        if not spec:
            continue
        vram_gb = float(spec.get("vram_gb", -1) or -1)
        vram_mb = int(vram_gb * 1024) if vram_gb > 0 else -1
        specs.append({
            "model_key": mk,
            "name": spec.get("name", mk),
            "estimated_vram_mb": vram_mb,
        })
    return specs


def get_ensemble_resource_status() -> dict:
    hw = get_system_hardware_info()
    free_vram_mb = int(hw.get("vram_free_mb", -1) or -1)
    models = _ensemble_selected_coder_specs()
    vram_reqs = [m["estimated_vram_mb"] for m in models if int(m.get("estimated_vram_mb", -1)) > 0]
    parallel_required = sum(vram_reqs) if vram_reqs else -1
    serial_required = max(vram_reqs) if vram_reqs else -1
    configured_mode = settings_get("ensemble_execution_mode") or "parallel"
    recommended_mode = configured_mode
    reason = "GPU情報不足のため推奨モード判定不可"
    if free_vram_mb > 0 and parallel_required > 0:
        if free_vram_mb >= parallel_required:
            recommended_mode = "parallel"
            reason = "空きVRAMで並列実行可能"
        elif serial_required > 0 and free_vram_mb >= serial_required:
            recommended_mode = "serial"
            reason = "並列は不足、シリアルなら実行可能"
        else:
            recommended_mode = "serial"
            reason = "空きVRAM不足のためシリアル推奨"
    warning = bool(recommended_mode == "serial" and configured_mode == "parallel")
    return {
        "configured_mode": configured_mode if configured_mode in ("parallel", "serial") else "parallel",
        "recommended_mode": recommended_mode,
        "auto_switch_on_low_vram": settings_get("ensemble_auto_switch_on_low_vram") != "false",
        "warning": warning,
        "reason": reason,
        "free_vram_mb": free_vram_mb,
        "required_vram_parallel_mb": parallel_required,
        "required_vram_serial_mb": serial_required,
        "models": models,
        "hardware": hw,
    }


def _apply_ensemble_execution_mode_guard() -> dict:
    status = get_ensemble_resource_status()
    configured = status.get("configured_mode", "parallel")
    if configured != "parallel":
        return status
    if not status.get("warning"):
        return status
    if not status.get("auto_switch_on_low_vram", True):
        return status
    settings_set("ensemble_execution_mode", "serial")
    _sync_ensemble_settings_to_opencode_json()
    status["configured_mode"] = "serial"
    status["switched_by_guard"] = True
    status["switch_reason"] = "low_vram_auto_switch"
    return status


def _guess_quantization(path: str) -> str:
    fname = os.path.basename(path).upper()
    for q in ["Q2_K", "IQ2_M", "IQ3_M", "Q3_K_S", "Q3_K_M", "Q3_K_L",
              "Q4_0", "Q4_K_S", "Q4_K_M", "Q5_K_S", "Q5_K_M", "Q6_K",
              "Q8_0", "F16", "BF16"]:
        if q in fname:
            return q
    return ""


def _choose_mmproj_for_model(model_path: str, mmproj_candidates: list[str], sibling_model_count: int = 1) -> str:
    if not mmproj_candidates:
        return ""
    model_stem = os.path.splitext(os.path.basename(model_path))[0].lower()
    model_parts = [p for p in re.split(r"[_.\-\s]+", model_stem) if len(p) >= 3 and p != "gguf"]
    scored: list[tuple[int, str]] = []
    for mmproj_path in mmproj_candidates:
        mmproj_stem = os.path.splitext(os.path.basename(mmproj_path))[0].lower()
        score = sum(1 for part in model_parts if part in mmproj_stem)
        scored.append((score, mmproj_path))
    scored.sort(key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    if len(mmproj_candidates) == 1 and sibling_model_count <= 1:
        return mmproj_candidates[0]
    return ""


def _infer_model_db_metadata(info: dict) -> dict:
    model_key = (info.get("model_key") or "").strip()
    if not model_key:
        model_key = _slugify_model_key(info.get("name") or os.path.splitext(os.path.basename(info.get("path", "")))[0])
    extra_args = info.get("extra_args", "")
    if isinstance(extra_args, list):
        extra_args = json.dumps(extra_args, ensure_ascii=False)
    return {
        **info,
        "model_key": model_key,
        "parser": (info.get("parser") or "").strip() or _infer_parser_name(
            info.get("name", ""),
            model_key,
            info.get("path", "")
        ),
        "description": info.get("description", "") or "",
        "threads": int(info.get("threads", 8) or 8),
        "parallel": int(info.get("parallel", -1) or -1),
        "batch_size": int(info.get("batch_size", -1) or -1),
        "ubatch_size": int(info.get("ubatch_size", -1) or -1),
        "cache_type_k": info.get("cache_type_k", "") or "",
        "cache_type_v": info.get("cache_type_v", "") or "",
        "extra_args": extra_args,
        "auto_roles": info.get("auto_roles", "") or "",
    }


def model_db_scan_folder(folder: str) -> list:
    """
    指定フォルダ（全サブフォルダ含む）のGGUFファイルを検索して
    モデル情報リストを返す（DBへの登録は含まない）
    """
    results = []
    if not os.path.isdir(folder):
        return results

    mmproj_by_dir: dict[str, list[str]] = {}
    model_files: list[tuple[str, str]] = []
    model_count_by_dir: dict[str, int] = {}

    for root, _dirs, files in os.walk(folder):
        for fname in files:
            if not fname.lower().endswith(".gguf"):
                continue
            full_path = os.path.join(root, fname)
            if "mmproj" in fname.lower():
                mmproj_by_dir.setdefault(root, []).append(full_path)
            else:
                model_files.append((root, full_path))
                model_count_by_dir[root] = model_count_by_dir.get(root, 0) + 1

    for root, full_path in model_files:
        fname = os.path.basename(full_path)
        rel = os.path.relpath(root, folder)
        top_dir = rel.split(os.sep)[0] if rel != "." else ""
        model_name = (top_dir + "/" if top_dir else "") + os.path.splitext(fname)[0]
        mmproj_candidates = mmproj_by_dir.get(root, [])
        mmproj_path = _choose_mmproj_for_model(full_path, mmproj_candidates, model_count_by_dir.get(root, 1))
        has_mmproj = bool(mmproj_path)
        is_vlm = _detect_vlm(full_path, model_name) or has_mmproj
        results.append(_infer_model_db_metadata({
            "name": model_name,
            "path": os.path.normpath(full_path),
            "is_vlm": is_vlm,
            "has_mmproj": has_mmproj,
            "mmproj_path": mmproj_path,
            "quantization": _guess_quantization(full_path),
            "file_size_mb": _get_file_size_mb(full_path),
            "vram_mb": -1, "ram_mb": -1, "load_sec": -1, "tok_per_sec": -1,
            "llm_url": "", "ctx_size": _resolve_default_ctx_size(), "gpu_layers": 999, "notes": "scanned",
        }))
    return results


# =========================
# JSON抽出（LLM出力が汚くても壊れない）
# =========================

def _sanitize_special_tokens(text: str) -> str:
    """
    <|token|> 形式の特殊トークンをメッセージ履歴に追加する前に除去する。
    llama.cppのチャットテンプレート適用時に特殊トークンが混入するとパースエラーが起きるため。
    """
    return re.sub(r'<\|[^|]+\|>', '', text)


def _parse_gpt_oss_channel(text: str):
    """
    GPT-OSS-20B の <|channel|>X to=Y <|message|>{...} 形式をエージェント形式に変換。
    <|constrain|>JSON 等の追加トークンも許容する。
    通常JSONが取れない場合のフォールバック。
    """
    # <|constrain|>JSON 等、channel名とメッセージの間に挟まる <|...|>WORD トークンを許容
    m = re.search(r'<\|channel\|>([\w.]+)(?:\s+to=([\w.]+))?(?:\s*<\|[^|]+\|>\w*)*\s*<\|message\|>(.*)', text, re.DOTALL)
    if not m:
        return None
    channel, tool, body = m.group(1), m.group(2), m.group(3).strip()
    try:
        args = json.loads(body)
    except Exception:
        mr = re.search(r'\{.*\}', body, re.DOTALL)
        args = json.loads(mr.group(0)) if mr else {}

    CHANNEL_MAP = {
        "container.exec":           "run_python",
        "repo_browser.list_files":  "list_files",
        "repo_browser.read_file":   "read_file",
        "file_editor.write":        "write_file",
        "file_editor.patch":        "patch_function",
        "web_search":               "web_search",
    }
    action = CHANNEL_MAP.get(tool or "", tool or channel)

    if channel == "final" or action == "final":
        # プランナーJSONの場合（tasksキーを持つ）はそのまま返す
        if "tasks" in args or "summary" in args:
            return args
        output = args.get("content", args.get("message", args.get("output", str(args))))
        return {"thought": "完了", "action": "final", "input": {}, "output": output}

    if action == "run_python":
        cmd = args.get("cmd", args.get("code", ""))
        if isinstance(cmd, list): cmd = " ".join(cmd)
        return {"thought": f"実行: {str(cmd)[:60]}", "action": "run_python", "input": {"code": str(cmd)}}

    if action == "list_files":
        return {"thought": "ファイル一覧", "action": "list_files", "input": {"subdir": args.get("subdir", "")}}

    if action == "read_file":
        path = args.get("path", args.get("file_path", args.get("filename", "")))
        return {"thought": f"読み込み: {path}", "action": "read_file", "input": {"path": path}}

    if action == "write_file":
        return {"thought": "書き込み", "action": "write_file", "input": args}

    # analysis channel: タスクJSONを含む場合はそのまま返す
    if channel == "analysis" and not tool:
        if "tasks" in args or "summary" in args:
            return args
        return {"thought": body[:100], "action": "list_files", "input": {"subdir": ""}}

    return {"thought": str(action), "action": action, "input": args}


def _compact_reply(action_obj: dict, max_chars: int = 500) -> str:
    """
    assistantのreplyをmessagesに追加する際、contentを省略してコンパクトにする。
    write_fileのcontent等巨大フィールドを短縮してコンテキスト節約。
    """
    if not action_obj:
        return ""
    compact = {}
    for k, v in action_obj.items():
        if k in ("input", "args") and isinstance(v, dict):
            compact_input = {}
            for ik, iv in v.items():
                iv_str = str(iv)
                if len(iv_str) > max_chars:
                    compact_input[ik] = iv_str[:max_chars] + f"...[{len(iv_str)-max_chars} chars omitted]"
                else:
                    compact_input[ik] = iv
            compact[k] = compact_input
        else:
            compact[k] = v
    try:
        return json.dumps(compact, ensure_ascii=False)
    except Exception:
        return str(action_obj)[:max_chars]


def _normalize_tool_input(action: str, tool_input) -> tuple[dict, list[str]]:
    """
    LLMが誤った引数名を返しても、主要ツールは自動で矯正する。
    戻り値: (normalized_input, notes)
    """
    notes: list[str] = []
    raw = tool_input if isinstance(tool_input, dict) else {}
    if not isinstance(tool_input, dict):
        notes.append("inputがdictではないため空dictとして扱いました。")
    elif isinstance(raw.get("input"), dict) and len(raw) == 1:
        # 一部モデルが {"input": {...}} を二重に返すため救済
        raw = raw["input"]
        notes.append("二重inputを展開: input -> (root)")

    alias_map = {
        "list_files": {"path": "subdir", "dir": "subdir", "directory": "subdir"},
        "read_file": {"file_path": "path", "filename": "path", "file": "path"},
        "write_file": {
            "file_path": "path", "filename": "path", "filepath": "path",
            "text": "content", "body": "content", "contents": "content"
        },
        "edit_file": {"file_path": "path", "filename": "path", "before": "old_str", "after": "new_str"},
        "run_python": {"cmd": "code", "script": "code"},
        "run_file": {"file_path": "path", "file": "path"},
    }
    mapping = alias_map.get(action, {})
    normalized = {}
    for k, v in raw.items():
        nk = mapping.get(k, k)
        normalized[nk] = v
        if nk != k:
            notes.append(f"引数名を補正: {k} -> {nk}")
    return normalized, notes


def _normalize_action_name(action: str) -> tuple[str, str | None]:
    """
    未知ツールになりやすい別名を既存ツールへ寄せる。
    戻り値: (normalized_action, note)
    """
    raw = str(action or "").strip().lower()
    alias = {
        "create_dir": "make_dir",
        "mkdir": "make_dir",
        "create_directory": "make_dir",
        "ls": "list_files",
        "cat_file": "read_file",
    }
    mapped = alias.get(raw, raw)
    if mapped != raw:
        return mapped, f"actionを補正: {raw} -> {mapped}"
    return mapped, None


def _prepare_tool_call(active_tools: dict, action: str, tool_input) -> tuple[dict | None, str | None, list[str]]:
    """
    ツール呼び出し前に引数を検証・補正する。
    戻り値: (safe_input, error_message, notes)
    """
    safe_input, notes = _normalize_tool_input(action, tool_input)
    fn = active_tools.get(action)
    if fn is None:
        return None, f"ERROR: unknown tool '{action}'", notes
    try:
        sig = inspect.signature(fn)
    except Exception:
        return safe_input, None, notes

    params = sig.parameters
    accepted = set(params.keys())
    dropped = [k for k in list(safe_input.keys()) if k not in accepted]
    for k in dropped:
        safe_input.pop(k, None)
    if dropped:
        notes.append(f"未対応引数を除外: {', '.join(dropped)}")

    required = [
        name for name, p in params.items()
        if p.default is inspect._empty
        and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    ]
    missing = [name for name in required if name not in safe_input]
    if missing:
        return None, (
            f"ERROR: 引数エラー - '{action}' に必須引数 {missing} が不足。"
            f" 使用可能引数: {sorted(accepted)}"
        ), notes

    # パス系引数の明らかな誤用（長文説明）を早期検出して自己修正を促す
    path_like_fields = [k for k in ("path", "subdir", "src", "dst") if k in safe_input]
    for key in path_like_fields:
        val = str(safe_input.get(key, "")).strip()
        if len(val) > 160 or ("\n" in val) or (len(val.split()) > 6 and "/" not in val and "." not in val):
            return None, (
                f"ERROR: 引数エラー - '{action}.{key}' はファイルパス/サブディレクトリを指定してください。"
                f" 長文説明は不可です。"
            ), notes
    return safe_input, None, notes


def _repair_truncated_json(text: str):
    """
    トークン上限で途中切れになったJSONを補完してパースを試みる。
    edit_fileのold_str/new_strが長い場合に発生しやすい。
    """
    # { で始まる部分を探す
    start = text.find('{')
    if start < 0:
        return None
    fragment = text[start:]

    # 既知フィールドのみ抽出してactionとthoughtを救済
    try:
        # thought と action だけ抽出できれば動作可能
        thought_m = re.search(r'"thought"\s*:\s*"((?:[^"\\]|\\.)*)"', fragment)
        action_m  = re.search(r'"action"\s*:\s*"(\w+)"', fragment)
        if not action_m:
            # チャンネル形式の前置コンテキストから action を推定
            # 例: <|channel|>final<|constrain|>JSON<|message|>{"thought":"完了","acti...
            channel_m = re.search(r'<\|channel\|>(final|analysis)\b', text)
            if channel_m:
                thought = thought_m.group(1) if thought_m else "完了"
                return {"thought": thought, "action": "final", "input": {}, "output": thought}
            return None

        action  = action_m.group(1)
        thought = thought_m.group(1) if thought_m else ""

        # inputフィールドを部分的に抽出
        input_m = re.search(r'"input"\s*:\s*(\{)', fragment)
        if not input_m:
            return {"thought": thought, "action": action, "input": {}}

        # inputの内容を括弧カウントで抽出
        depth, buf, i = 0, [], input_m.start(1)
        for ch in fragment[i:]:
            buf.append(ch)
            if ch == '{': depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    break
        input_str = "".join(buf)

        # 途中で切れていたら閉じ括弧を補完
        if depth > 0:
            input_str += "}" * depth

        # 文字列が切れていたら閉じる
        input_str = re.sub(r'(:\s*"[^"]*$)', lambda m: m.group(0) + '"', input_str)

        try:
            input_obj = json.loads(input_str)
        except Exception:
            # inputのパースも失敗したら既知フィールドだけ返す
            input_obj = {}

        return {"thought": thought, "action": action, "input": input_obj}
    except Exception:
        return None


def _extract_first_json_object(text: str):
    """
    文字列中から最初にデコード可能なJSONオブジェクトを抽出する。
    先頭/末尾に説明文が混ざっていても JSON 部分のみを取り出せるようにする。
    """
    if not text:
        return None
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[idx:])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def _repair_common_json_issues(text: str):
    """
    LLMが出しがちな軽微なJSON崩れを補正してパースを試みる。
    対象例:
    - ```json ... ``` フェンス付き
    - //, /* */ コメント混入
    - シングルクォート文字列/キー
    - 末尾カンマ
    - bare key（key: "value"）の未クォート
    """
    if not text:
        return None
    candidate = text.strip()

    # コードフェンス除去
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()

    # 先頭/末尾ノイズがある場合は最初の{〜最後の}を候補化
    lidx, ridx = candidate.find("{"), candidate.rfind("}")
    if lidx >= 0 and ridx > lidx:
        candidate = candidate[lidx:ridx + 1]

    # コメント除去
    candidate = re.sub(r"/\*.*?\*/", "", candidate, flags=re.DOTALL)
    candidate = re.sub(r"(^|[^:])//.*?$", r"\1", candidate, flags=re.MULTILINE)

    # スマートクォート正規化
    candidate = (candidate
                 .replace("“", '"')
                 .replace("”", '"')
                 .replace("’", "'")
                 .replace("‘", "'"))

    # シングルクォートのキーをダブルクォートへ
    def _sq_key_to_dq(match):
        key = match.group(2).replace('"', r'\"')
        return f'{match.group(1)}"{key}":'
    candidate = re.sub(
        r"([{\[,]\s*)'([^'\\]*(?:\\.[^'\\]*)*)'\s*:",
        _sq_key_to_dq,
        candidate,
    )
    # シングルクォートの値をダブルクォートへ
    candidate = re.sub(
        r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'(\s*[,}\]])",
        lambda m: ': "' + m.group(1).replace("\\'", "'").replace('"', r"\"") + '"' + m.group(2),
        candidate,
    )

    # bare key をクォート
    candidate = re.sub(
        r'([{\[,]\s*)([A-Za-z_][A-Za-z0-9_\-]*)\s*:',
        lambda m: f'{m.group(1)}"{m.group(2)}":',
        candidate,
    )

    # 末尾カンマ除去
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _extract_json_like_range(text: str) -> str:
    if not isinstance(text, str):
        return ""
    s = text.strip()
    if not s:
        return ""
    lidx = s.find("{")
    ridx = s.rfind("}")
    if lidx >= 0 and ridx > lidx:
        return s[lidx:ridx + 1].strip()
    return s


def _parse_agent_protocol_json(text: str) -> tuple[dict | None, str | None]:
    """
    Agent chat JSON protocol parser.
    1) 生JSON
    2) ```json フェンス除去
    3) JSONらしき範囲抽出
    """
    if not isinstance(text, str) or not text.strip():
        return None, "empty_output"
    raw = text.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None, None if isinstance(parsed, dict) else "not_object"
    except Exception:
        pass

    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
    if fence:
        fenced = fence.group(1).strip()
        try:
            parsed = json.loads(fenced)
            return parsed if isinstance(parsed, dict) else None, None if isinstance(parsed, dict) else "not_object"
        except Exception:
            pass

    candidate = _extract_json_like_range(raw)
    if candidate and candidate != raw:
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None, None if isinstance(parsed, dict) else "not_object"
        except Exception as e:
            return None, f"json_parse_failed:{e}"

    try:
        repaired = _repair_common_json_issues(raw)
        if isinstance(repaired, dict):
            return repaired, None
    except Exception:
        pass
    return None, "json_parse_failed"


def _validate_agent_action_payload(action_obj: dict) -> tuple[dict | None, str | None]:
    if not isinstance(action_obj, dict):
        return None, "payload_not_object"
    action = str(action_obj.get("action", "") or "").strip().lower()
    if action == "final":
        content = str(action_obj.get("content", "") or "").strip()
        if not content:
            return None, "final_content_empty"
        return {"action": "final", "content": content}, None
    if action == "tool":
        tool = str(action_obj.get("tool", "") or "").strip()
        args = action_obj.get("arguments", {})
        if tool != "nexus_web_search":
            return None, f"tool_not_allowed:{tool}"
        if not isinstance(args, dict):
            return None, "tool_arguments_not_object"
        topic = str(args.get("topic", "") or "").strip()
        if not topic:
            return None, "nexus_web_search_topic_empty"
        max_results_raw = args.get("max_results_per_query", 3)
        try:
            max_results = int(max_results_raw)
        except Exception:
            return None, "nexus_web_search_max_results_invalid"
        max_results = max(1, min(max_results, 10))
        return {
            "action": "tool",
            "tool": "nexus_web_search",
            "arguments": {"topic": topic, "max_results_per_query": max_results},
        }, None
    return None, f"unknown_action:{action}"


def extract_json(text: str, parser: str = "json"):
    """
    parser種別:
      "json"       - 標準JSON抽出
      "qwen_think" - <think>タグ除去後にJSON抽出（Qwen3.5/Coder-Next）
      "gpt_oss"    - チャンネル形式フォールバック付き（GPT-OSS-20B）
    """
    # qwen_think: <think>...</think> を除去してからパース
    if parser == "qwen_think":
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        # reasoning_contentの場合も同様に除去
        text = re.sub(r'<\|thinking\|>.*?<\|/thinking\|>', '', text, flags=re.DOTALL).strip()

    # 1. 通常のJSON
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. コードブロック内のJSON
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # 3. 軽微なJSON崩れを補正（single-quote/trailing-comma等）
    repaired_common = _repair_common_json_issues(text)
    if repaired_common is not None:
        print("[extract_json] repaired common JSON issues")
        return repaired_common

    # 4. テキスト中の最初のJSONオブジェクト（前後ノイズ許容）
    first_obj = _extract_first_json_object(text)
    if first_obj is not None:
        return first_obj

    # 5. 途中切れJSONの補完救済（トークン上限で切れた場合）
    repaired = _repair_truncated_json(text)
    if repaired and repaired.get("action"):
        print(f"[extract_json] repaired truncated JSON: action={repaired['action']}")
        return repaired

    # 6. GPT-OSS-20B チャンネル形式フォールバック
    gpt_oss = _parse_gpt_oss_channel(text)
    if gpt_oss:
        return gpt_oss

    return None


def _task_v2_apply_args_adapter(action_obj: dict) -> dict:
    """
    互換期間: 旧フォーマット input を新フォーマット args に寄せる。
    移行完了後に削除予定。
    """
    if not isinstance(action_obj, dict):
        return action_obj
    if isinstance(action_obj.get("args"), dict):
        return action_obj
    if isinstance(action_obj.get("input"), dict):
        patched = dict(action_obj)
        patched["args"] = patched.get("input", {})
        return patched
    return action_obj


_TASK_V2_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "required": ["thought", "action", "args"],
    "additionalProperties": True,
    "properties": {
        "thought": {"type": "string"},
        "action": {"type": "string", "minLength": 1},
        "args": {"type": "object"},
        "output": {"type": "string"},
    },
    "allOf": [
        {
            "if": {"properties": {"action": {"const": "final"}}},
            "then": {"required": ["output"]},
        },
        {
            "if": {"properties": {"action": {"not": {"const": "final"}}}},
            "then": {"not": {"required": ["output"]}},
        },
    ],
}

_TASK_V2_ONE_ACTION_MODE = str(os.environ.get("CODEAGENT_ONE_ACTION_MODE", "1")).lower() in {"1", "true", "yes", "on"}
_TASK_V2_RESPONSE_MAX_CHARS = max(500, min(int(os.environ.get("CODEAGENT_TASK_RESPONSE_MAX_CHARS", "900") or 900), 1000))


def _normalize_task_v2_reply_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    normalized = unicodedata.normalize("NFKC", text)
    replacements = {
        "\r\n": "\n",
        "\r": "\n",
        "，": ",",
        "：": ":",
        "；": ";",
        "（": "(",
        "）": ")",
        "｛": "{",
        "｝": "}",
        "［": "[",
        "］": "]",
        "＂": '"',
        "＼": "\\",
    }
    for before, after in replacements.items():
        normalized = normalized.replace(before, after)
    return normalized


def _force_summarize_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= max_chars:
        return compact
    head = max(120, int(max_chars * 0.55))
    tail = max(60, max_chars - head - 16)
    return f"{compact[:head]} ... {compact[-tail:]}"


def _has_multi_action_enumeration(action: str) -> bool:
    a = str(action or "").strip().lower()
    if not a:
        return False
    separators = [",", " and ", " then ", "->", "=>", "/", "|", "\n", "→", "、", "と"]
    return any(sep in a for sep in separators)


def _validate_task_v2_response_schema(raw: dict) -> tuple[bool, str]:
    if not isinstance(raw, dict):
        return False, "response is not an object"
    if _jsonschema is not None:
        try:
            _jsonschema.validate(instance=raw, schema=_TASK_V2_RESPONSE_SCHEMA)
        except Exception as e:
            return False, f"schema validation failed: {e}"
    else:
        required = ("thought", "action", "args")
        for key in required:
            if key not in raw:
                return False, f"missing required field: {key}"
        if not isinstance(raw.get("thought"), str):
            return False, "thought must be string"
        if not isinstance(raw.get("action"), str) or not str(raw.get("action", "")).strip():
            return False, "action must be non-empty string"
        if not isinstance(raw.get("args"), dict):
            return False, "args must be object"
        action_lower = str(raw.get("action", "")).strip().lower()
        if action_lower == "final" and not isinstance(raw.get("output"), str):
            return False, "final requires string output"
        if action_lower != "final" and "output" in raw:
            return False, "non-final action must not include output"

    if _TASK_V2_ONE_ACTION_MODE and _has_multi_action_enumeration(str(raw.get("action", ""))):
        return False, "one-step-one-action mode forbids multi-action enumeration"
    return True, ""


def _enforce_task_v2_response_limits(raw: dict) -> tuple[dict, bool]:
    changed = False
    patched = dict(raw)
    for key in ("thought", "output"):
        if key in patched and isinstance(patched.get(key), str) and len(patched[key]) > _TASK_V2_RESPONSE_MAX_CHARS:
            patched[key] = _force_summarize_text(patched[key], _TASK_V2_RESPONSE_MAX_CHARS)
            changed = True
    return patched, changed


def _parse_task_v2_action(text: str, parser: str = "json") -> dict | None:
    """
    Task v2専用パーサ:
    - まず厳密に json.loads を試し、失敗時は extract_json で救済する
    - schema検証に失敗した場合は非JSON扱い（None）でリトライさせる
    """
    if parser == "qwen_think":
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
        text = re.sub(r'<\|thinking\|>.*?<\|/thinking\|>', '', text, flags=re.DOTALL).strip()
    text = _normalize_task_v2_reply_text(text)
    try:
        raw = json.loads(text)
    except Exception:
        # strict JSON失敗時は「最初のJSONオブジェクト抽出」を最優先し、
        # 取れない場合のみ既存の救済パーサにフォールバックする。
        raw = _extract_first_json_object(text) or extract_json(text, parser=parser)
    if not isinstance(raw, dict):
        return None

    raw = _task_v2_apply_args_adapter(raw)
    if raw.get("thought") is None:
        raw["thought"] = ""
    elif not isinstance(raw.get("thought"), str):
        raw["thought"] = str(raw.get("thought"))
    if "action" in raw and not isinstance(raw.get("action"), str):
        raw["action"] = str(raw.get("action"))
    if "args" in raw and raw.get("args") is None:
        raw["args"] = {}
    valid, _reason = _validate_task_v2_response_schema(raw)
    if not valid:
        return None
    raw, _ = _enforce_task_v2_response_limits(raw)
    return raw


def _parse_task_v2_action_with_retry(
    reply: str,
    messages: list[dict],
    llm_url: str,
    parser: str = "json",
    max_retry: int = 1,
) -> tuple[dict | None, str, dict]:
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "tps": 0}
    normalized_reply = _normalize_task_v2_reply_text(reply)
    action_obj = _parse_task_v2_action(normalized_reply, parser=parser)
    if action_obj is not None:
        return action_obj, normalized_reply, usage

    current_reply = normalized_reply
    for _ in range(max(0, int(max_retry or 0))):
        fix_prompt = (
            "前回出力は無効です。JSON Schemaを厳守して再生成してください。"
            " thought/action/argsを必須にし、actionがfinal以外ならoutputを含めないこと。"
            " 1ステップ1アクションのみ。actionに複数ツール名を列挙しない。"
            f" thought/outputは{_TASK_V2_RESPONSE_MAX_CHARS}文字以内に要約する。"
            " 外部出力として有効なのはactionのみ（thoughtは内部用の短文）。"
        )
        retry_messages = list(messages) + [
            {"role": "assistant", "content": _sanitize_special_tokens(current_reply)[:700]},
            {"role": "user", "content": fix_prompt},
        ]
        retry_reply, retry_usage = call_llm_chat(retry_messages, llm_url=llm_url)
        if not retry_usage.get("prompt_tokens"):
            retry_usage = {**retry_usage, "prompt_tokens": _estimate_tokens(retry_messages)}
        current_reply = _normalize_task_v2_reply_text(retry_reply)
        action_obj = _parse_task_v2_action(current_reply, parser=parser)
        usage = retry_usage
        if action_obj is not None:
            return action_obj, current_reply, usage
    return None, current_reply, usage

# =========================
# LLM呼び出し
# =========================

def call_llm_chat(messages: list, llm_url: str = "", max_output_tokens: int | None = None) -> tuple:
    """
    chatモード専用: JSON強制なし、通常の会話応答。
    thinking モデル対応: content が空なら reasoning_content を使用。
    llama-server 500 (GPT-OSS-20Bのチャンネル形式) でもボディを読む。
    (content, usage_dict) を返す。
    """
    url = llm_url.strip() or LLM_URL
    prompt_tok = _estimate_tokens(messages)
    avail = max(256, _current_n_ctx - prompt_tok - 64)
    requested_cap = 32768 if max_output_tokens is None else max(256, int(max_output_tokens))
    max_out = min(avail, requested_cap, 32768)
    if avail <= 256:
        print(f"[CTX WARNING] コンテキスト長不足: n_ctx={_current_n_ctx} prompt_tokens≈{prompt_tok} 残余={avail} — 出力が極端に短くなる可能性があります")
    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_out,
    }
    # Qwen3.5/Coder: enable_thinking=falseをAPIで指定（--reasoning-budget 0と二重保険）
    if _model_manager.current_parser == "qwen_think":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    try:
        import time as _time
        t0 = _time.perf_counter()
        res = requests.post(url, json=payload, timeout=600)
        elapsed = _time.perf_counter() - t0
        # 500でもボディを読む（GPT-OSS-20Bのチャンネル形式出力対応）
        try:
            data = res.json()
        except Exception:
            if not res.ok:
                raise requests.RequestException(f"HTTP {res.status_code}: {res.text[:200]}")
            raise
        # llama-server 500 エラーオブジェクトの場合、error.message からテキストを抽出
        if "error" in data and "choices" not in data:
            err_msg = data["error"].get("message", "") if isinstance(data["error"], dict) else str(data["error"])
            err_lower = err_msg.lower()
            if any(kw in err_lower for kw in ("context", "token", "exceed", "too long", "kv cache")):
                ctx_msg = f"[CTX ERROR] コンテキスト長が不足しています: {err_msg[:200]} (n_ctx={_current_n_ctx}, prompt≈{prompt_tok})"
                print(ctx_msg)
                raise HTTPException(status_code=413, detail=ctx_msg)
            print(f"[LLM] server error: {err_msg[:100]}")
            # チャンネル形式のテキストを抽出して返す
            content = err_msg
        else:
            msg = data["choices"][0]["message"]
            content = msg.get("content", "") or ""
            if not content.strip():
                content = msg.get("reasoning_content", "") or ""
        usage = data.get("usage", {})
        comp_tokens = usage.get("completion_tokens", 0)
        tps = round(comp_tokens / elapsed, 1) if elapsed > 0 and comp_tokens > 0 else 0
        return content, {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": comp_tokens,
            "total_tokens": usage.get("total_tokens", 0),
            "tps": tps,
        }
    except requests.exceptions.ReadTimeout as e:
        # タイムアウト時は一度だけリトライ（コンテキストを半分に減らして）
        print(f"[call_llm_chat] timeout, retrying with trimmed context...")
        messages = _trim_messages(messages, _current_n_ctx // 2, reserve_output=_calc_reserve_output(_current_n_ctx // 2, ratio=0.22))
        payload["messages"] = messages
        payload["max_tokens"] = min(
            _current_n_ctx // 2 - _estimate_tokens(messages) - 64,
            requested_cap,
            32768
        )
        try:
            res = requests.post(url, json=payload, timeout=300)
            data = res.json()
            content = (data.get("choices",[{}])[0].get("message",{}).get("content","") or
                       data.get("choices",[{}])[0].get("message",{}).get("reasoning_content",""))
            return content, {"prompt_tokens":0,"completion_tokens":0,"tps":0}
        except Exception as e2:
            raise HTTPException(status_code=502, detail=f"LLM unreachable after retry ({url}): {e2}")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"LLM unreachable ({url}): {e}")


def call_llm_chat_streaming(messages: list, llm_url: str = ""):
    """
    stream=True でLLMを呼び出すジェネレータ。
    - 生成中: {"type":"llm_streaming","tps":N,"tokens":N} を約1秒ごとにyield
    - 完了時: {"type":"llm_done","content":str,"usage":dict} をyield
    - エラー時: {"type":"llm_error","status_code":N,"error":str} をyield
    """
    import time as _t
    url = llm_url.strip() or LLM_URL
    prompt_tok = _estimate_tokens(messages)
    avail = max(256, _current_n_ctx - prompt_tok - 64)
    max_tokens = min(avail, 32768)
    if avail <= 256:
        print(f"[CTX WARNING] コンテキスト長不足 (streaming): n_ctx={_current_n_ctx} prompt≈{prompt_tok} 残余={avail}")
        yield {"type": "llm_error", "status_code": 413,
               "error": f"[CTX ERROR] コンテキスト長が不足しています (n_ctx={_current_n_ctx}, prompt≈{prompt_tok}, 残余={avail})。設定でコンテキスト長を増やすか会話履歴をリセットしてください。"}
        return
    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if _model_manager.current_parser == "qwen_think":
        payload["chat_template_kwargs"] = {"enable_thinking": False}

    t0 = _t.perf_counter()
    last_emit = t0
    content = ""
    comp_tokens = 0
    prompt_tokens = 0

    try:
        with requests.post(url, json=payload, stream=True, timeout=600) as resp:
            if resp.status_code == 413 or resp.status_code == 400:
                err_body = resp.text[:300]
                ctx_msg = f"[CTX ERROR] コンテキスト長が不足しています (HTTP {resp.status_code}): {err_body}"
                print(ctx_msg)
                yield {"type": "llm_error", "status_code": resp.status_code, "error": ctx_msg}
                return
            if resp.status_code >= 400:
                yield {"type": "llm_error", "status_code": resp.status_code,
                       "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
                return
            for raw_line in resp.iter_lines():
                line = (raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line).strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except Exception:
                    continue
                # コンテキスト超過エラーをストリーム内で検出
                if "error" in chunk and "choices" not in chunk:
                    err_msg = chunk["error"].get("message", "") if isinstance(chunk["error"], dict) else str(chunk["error"])
                    err_lower = err_msg.lower()
                    if any(kw in err_lower for kw in ("context", "token", "exceed", "too long", "kv cache")):
                        ctx_msg = f"[CTX ERROR] コンテキスト長が不足しています: {err_msg[:200]}"
                        print(ctx_msg)
                        yield {"type": "llm_error", "status_code": 413, "error": ctx_msg}
                        return
                    yield {"type": "llm_error", "status_code": 500, "error": err_msg[:200]}
                    return
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                token_text = delta.get("content") or delta.get("reasoning_content") or ""
                content += token_text
                # llama.cppは最終チャンクにusageを含める
                if chunk.get("usage"):
                    u = chunk["usage"]
                    prompt_tokens = u.get("prompt_tokens", 0)
                    comp_tokens = u.get("completion_tokens", 0)
                elif token_text:
                    comp_tokens += 1  # usageが来るまでの近似カウント
                # 約1秒ごとにTPS進捗を通知（DB書き込み負荷を抑えるため）
                now = _t.perf_counter()
                if now - last_emit >= 1.0:
                    elapsed = now - t0
                    tps = round(comp_tokens / elapsed, 1) if elapsed > 0 else 0
                    yield {"type": "llm_streaming", "tps": tps, "tokens": comp_tokens}
                    last_emit = now
    except requests.exceptions.ReadTimeout:
        yield {"type": "llm_error", "status_code": 408, "error": "LLM timeout (streaming)"}
        return
    except requests.RequestException as e:
        yield {"type": "llm_error", "status_code": 502, "error": str(e)}
        return

    elapsed = _t.perf_counter() - t0
    if comp_tokens == 0:
        comp_tokens = max(1, len(content.split()))
    tps = round(comp_tokens / elapsed, 1) if elapsed > 0 and comp_tokens > 0 else 0
    yield {
        "type": "llm_done",
        "content": content,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": comp_tokens,
            "tps": tps,
        }
    }


def call_llm(messages: list, llm_url: str = "") -> tuple:
    """
    (content, usage_dict) を返す。
    usage_dict = {"prompt_tokens":N, "completion_tokens":N, "tps":N}
    エージェントツール用: JSON出力を強制。
    """
    url = llm_url.strip() or LLM_URL
    prompt_tok = _estimate_tokens(messages)
    avail = max(256, _current_n_ctx - prompt_tok - 64)
    max_out = min(avail, 32768)
    if avail <= 256:
        print(f"[CTX WARNING] コンテキスト長不足 (agent): n_ctx={_current_n_ctx} prompt≈{prompt_tok} 残余={avail}")
    payload = {
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_out,
    }
    # Qwen3.5/Coder: enable_thinking=falseをAPIで指定
    if _model_manager.current_parser == "qwen_think":
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    try:
        import time as _time
        t0 = _time.perf_counter()
        res = requests.post(url, json=payload, timeout=600)
        elapsed = _time.perf_counter() - t0
        try:
            data = res.json()
        except Exception:
            if not res.ok:
                raise requests.RequestException(f"HTTP {res.status_code}: {res.text[:200]}")
            raise
        if "error" in data and "choices" not in data:
            err_msg = data["error"].get("message", "") if isinstance(data["error"], dict) else str(data["error"])
            err_lower = err_msg.lower()
            if any(kw in err_lower for kw in ("context", "token", "exceed", "too long", "kv cache")):
                ctx_msg = f"[CTX ERROR] コンテキスト長が不足しています: {err_msg[:200]} (n_ctx={_current_n_ctx}, prompt≈{prompt_tok})"
                print(ctx_msg)
                raise HTTPException(status_code=413, detail=ctx_msg)
            print(f"[LLM] server error (agent): {err_msg[:100]}")
            content = err_msg  # チャンネル形式テキストとして扱う
        else:
            msg = data["choices"][0]["message"]
            content = msg.get("content", "") or ""
            if not content.strip():
                content = msg.get("reasoning_content", "") or ""
        usage = data.get("usage", {})
        comp_tokens = usage.get("completion_tokens", 0)
        tps = round(comp_tokens / elapsed, 1) if elapsed > 0 and comp_tokens > 0 else 0
        usage_info = {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": comp_tokens,
            "total_tokens": usage.get("total_tokens", 0),
            "tps": tps,
        }
        return content, usage_info
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"LLM unreachable ({url}): {e}")

# =========================
# システムプロンプト
# =========================

CHAT_SYSTEM_PROMPT = """あなたは親切で知識豊富なAIアシスタントです。
ユーザーの質問・会話に対して、自然で分かりやすい言葉で返答してください。
コードの作成・修正・ファイル操作などの具体的な作業が必要な場合は、その旨を伝えてTaskモードへの切り替えを促してください。"""

TASK_V2_SYSTEM_PROMPT = """あなたはコード編集・実行AIです。

【絶対ルール】
- 必ず純粋なJSONオブジェクトのみを出力する。それ以外は一切禁止。
- <|channel|>や<|start|>などの特殊トークンは使わない。
- マークダウン、説明文、コードブロック(```)も禁止。
- 最初の文字は必ず { であること。
- thought は内部用の短文（最大900文字）にし、外部に見せるべき内容は action / args / output にのみ含める。
- ツール実行結果がERRORの場合、同じaction+同じ引数を繰り返さない。必ずエラー内容を読んで引数や手順を変更する。
- 1ステップ1アクション。action に複数ツール名を列挙しない。
- 最新情報・外部調査・ニュース・価格・仕様確認のように時点依存の情報が必要な場合、最初に nexus_web_search を実行して根拠を取得する。

【出力形式】（このフォーマット厳守）
{"thought":"考えていること","action":"ツール名","args":{ツールの引数}}

【最終回答】
{"thought":"完了","action":"final","args":{},"output":"ユーザーへの回答"}

【ツール一覧】
- list_files: {"subdir": ""}
- get_outline: {"path": "foo.py"}  ← 大きなファイルの構造把握（関数/クラス/HTML要素と行番号）
- read_file: {"path": "foo.py"}  または {"path": "foo.py", "start_line": 10, "end_line": 50}
- write_file: {"path": "foo.py", "content": "..."}  ← 新規作成・全体上書き専用
- edit_file: {"path": "foo.py", "old_str": "変更前の文字列（一意）", "new_str": "変更後"}  ← 差分修正（推奨）
- search_in_files: {"query": "TODO", "subdir": "src"}  ← プロジェクト内全文検索
- make_dir: {"path": "src/utils"}  ← ディレクトリ作成
- move_path: {"src": "old.py", "dst": "src/new.py"}  ← ファイル/ディレクトリ移動・改名
- delete_path: {"path": "tmp.txt"}  or {"path":"build","recursive":true}  ← ファイル/ディレクトリ削除
- patch_function: {"path": "foo.py", "function_name": "bar", "new_code": "def bar(): ..."}
- run_python: {"code": "print('hello')"}  ← project引数不要（自動設定）/ タイムアウト時: {"code":"...","timeout":60} (max 300s) ※Runpodではproject .venvを使用
- run_file: {"path": "foo.py"}  ← プロジェクト内の相対パス、project引数不要 / タイムアウト時: {"path":"...","timeout":60} (max 300s) ※Runpodではproject .venvを使用
- run_shell: {"command": "pytest -q"}  ← プロジェクトディレクトリでシェルコマンド実行 / タイムアウト時: {"command":"...","timeout":120} (max 300s)
- run_server: {"port": 8888}  ← 【最終タスクのみ】DockerでHTTPサーバー起動
- stop_server: {"port": 8888}  ← 起動したサーバーを停止
- run_browser: {"script": "from playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n  b=p.chromium.launch(headless=True)\n  c=b.new_context()\n  pg=c.new_page()\n  pg.goto('http://host.docker.internal:8888/')\n  pg.wait_for_load_state('networkidle')\n  pg.screenshot(path='/app/{project}/screenshot.png')\n  print(pg.title())"}  ← Playwright（Python）でブラウザ自動化・スクリーンショット・動作確認 / タイムアウト時: {"script":"...","timeout":120} (max 300s)
- run_npm: {"command": "test"}  ← npm コマンドをDockerで実行（test/install/run build等）/ タイムアウト時: {"command":"install","timeout":300} (max 600s)
- run_node: {"script": "console.log(require('./script.js'))"}  ← JSコードをNode.jsで実行・テスト / タイムアウト時: {"script":"...","timeout":60} (max 300s)
- setup_venv: {"requirements": ["flask","numpy"]}  ← Pythonプロジェクトで.venv構築＋requirements.txt生成（実行はユーザーが行う）
- nexus_web_search: {"topic": "検索クエリ", "max_results_per_query": 5, "mode": "standard", "depth": "standard", "scope": ["news"], "language": "ja"}  ← Web検索を実行し、検索結果をNexus Evidenceとして保存してjob_idを返却。返却されたjob_idは nexus_build_report / nexus_export_bundle に接続可能
- clarify: {"question": "質問", "options": ["選択肢1", "選択肢2"]}
- git_status: {"project": "..."}  ← プロジェクトのgit変更一覧（M=変更 A=追加 ?=未追跡）。タスク開始前に実行推奨
- git_diff: {"path": "foo.py", "project": "..."}  ← 差分確認。pathを省略すると全体差分
- git_commit: {"message": "feat: 機能追加", "project": "..."}  ← 全変更をステージ→コミット
- git_checkout_branch: {"name": "feature/xxx", "create": true, "project": "..."}  ← ブランチ作成・切替
- git_reset: {"mode": "hard", "project": "..."}  ← 変更を全て破棄（エージェントのミス修正用Undo）。mode: hard/soft/mixed
- mcp_call: {"server_url": "http://...", "tool_name": "tool", "arguments": {}}  ← 外部MCPサーバーのツール呼び出し
- mcp_list_tools: {"server_url": "http://..."}  ← 外部MCPサーバーのツール一覧取得

【戦略】
1. まず list_files でファイル構成を把握
2. 大きなファイル（100行超）は get_outline で構造確認 → read_file(start_line, end_line) で必要箇所だけ読む
3. 既存ファイルの修正は edit_file を使う（write_file は新規作成か全体刷新のみ）
4. edit_file の old_str は一意に特定できる十分な文字列にすること（前後の行を含める）
5. 実行後エラーがあれば必ず自分で修正して再実行
6. HTTPサーバー起動は run_python ではなく run_server を使う（run_pythonはサーバー系タイムアウトする）
7. 要件が曖昧な場合は clarify でユーザーに確認
7.5. ツール結果の解釈は出力テキストに厳密に従うこと。出力に書かれていない .venv / Docker Compose / Runpod 設定不備を推測で断定しない。
7.6. 最新情報・外部調査・ニュース・価格・仕様確認が必要な場合は、必ず nexus_web_search を使って根拠を取得する。
9. 【Gitワークフロー】タスク開始時に git_checkout_branch でfeatureブランチを作成し、
   完了後に git_commit でコミットすること。失敗時は git_reset で即座に復元できる。
8. 【タイムアウト対策】"ERROR: timeout (Xs)" が返ってきた場合:
   a. まず処理を分割・軽量化して再試行（最優先）
   b. 分割が困難な場合のみ timeout パラメータを推定実行時間で指定して再実行（その実行限りの一時設定）
   c. 上限: run_python/run_file/run_browser/run_node=300s、run_npm=600s
   d. 常軌を逸する値（上限超）は自動的にクランプされる
8. 【プロジェクト種別フロー】

   【HTML/JSプロジェクト】
   通常タスク: write_file でHTML/CSS/JS作成
   動作確認タスク（最終）:
     1. run_server でDockerHTTPサーバー起動
     2. run_browser でPlaywrightによるブラウザ確認・スクリーンショット取得
     3. run_npm("test") でJSユニットテスト（package.jsonがある場合）
     4. run_node でJSロジックの単体テスト

   【Pythonプロジェクト】
   通常タスク: write_file でPythonコード作成
   動作確認タスク（最終）:
     1. run_python で動作確認・ユニットテスト（標準環境はDocker / Runpodはproject .venv）
     2. WebアプリはFlask等: run_server → run_browser でブラウザ確認+スクショ
     3. setup_venv(requirements=["flask","numpy",...]) でローカルvenv構築
        → .venv/ と requirements.txt を生成・pip installまで完了
        → ユーザーが activate → python app.py で即実行できる状態

   ※ 全ファイルはプロジェクトフォルダ直下に配置する
   ※ .venv/ は絶対パスを含むため移動不可・プロジェクト固定"""

def _build_system_prompt(project: str = "") -> str:
    """
    SYSTEM_PROMPTにスキル一覧を注入して返す（OpenClaw互換）。
    スキルは ./skills/ の SKILL.md から自動ロード。
    {project} プレースホルダーを実際のプロジェクト名に置換する。
    """
    base = TASK_V2_SYSTEM_PROMPT.replace("{project}", project) if project else TASK_V2_SYSTEM_PROMPT
    usage_fn = globals().get("_build_tool_success_playbook")
    usage_guide = usage_fn(project) if usage_fn else ""
    inject_fn = globals().get("_skills_to_prompt_injection")
    injection = inject_fn() if inject_fn else ""
    return base + usage_guide + injection


def _build_tool_success_playbook(project: str = "") -> str:
    """
    Claude/Codex/OpenCode系の失敗抑止パターンをツール実行前ガイドとして注入する。
    - schema first（必須引数確認）
    - runtime aware（local / Runpod 差分）
    - fail fast（同一失敗の反復禁止）
    """
    runtime = "runpod" if IS_RUNPOD_RUNTIME else "local"
    runtime_note = (
        "- Runpod: run_python/run_file/run_browser は project配下 .venv を優先。"
        " playwright不足時は setup_venv(requirements=[\"playwright\"]) → .venv/bin/playwright install chromium。\n"
        if runtime == "runpod" else
        "- Local: Docker優先。Docker不可時のみローカルフォールバックを使う。"
        " エラー文に従って依存を最小追加する。\n"
    )

    # 主要失敗を誘発しやすいツールは具体例を明示
    targeted = """
【Tool Success Playbook / 実行前チェック】
1) actionは1回に1つ。必ず JSON のみで返す。
2) 実行前に required引数を自己検証（不足があれば実行せず修正）。
3) ERROR時は「同じaction+同じ引数」を繰り返さず、引数か手順を変更。
4) 破壊的操作（delete_path/git_reset）は read_file/git_status などで事前確認してから実行。
5) 長文説明を path/subdir/src/dst に入れない。ファイルパスのみ指定。
""" + runtime_note + f"""
【高頻度で失敗しやすいツールの具体ルール】
- write_file: 必須は path, content。例: {{"path":"index.html","content":"..."}}。
  既存修正は edit_file 優先。write_fileは新規作成か全体置換のみ。
- run_browser: script未指定なら url を渡す。例: {{"url":"http://localhost:8888/","timeout":120}}。
  script指定時はPlaywrightのPythonコードを渡す。
- run_shell: command には1つの目的だけを書く（例: "pytest -q"）。
  失敗時は install と test を分割して再実行。
- git系: 開始時 git_status、完了時 git_diff → git_commit の順。
  projectは通常 "{project or 'default'}" を使う。
"""
    # 全ツールの最低限スキーマ（required/optional）を短く列挙
    sig_lines = []
    for name, fn in sorted((globals().get("TOOLS") or {}).items()):
        try:
            sig = inspect.signature(fn)
            req, opt = [], []
            for p in sig.parameters.values():
                if p.kind not in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
                    continue
                if p.default is inspect._empty:
                    req.append(p.name)
                else:
                    opt.append(p.name)
            sig_lines.append(f"- {name}: required={req or ['(none)']}, optional={opt or ['(none)']}")
        except Exception:
            continue
    schema = "\n".join(sig_lines[:40])  # プロンプト肥大化を防ぐ安全上限
    return targeted + "\n【Tool Schema Quick Reference】\n" + schema + "\n"


# =========================
# ツールレジストリ
# =========================

TOOLS = {
    "read_file": read_file,
    "list_files": list_files,
    "search_in_files": search_in_files,
    "write_file": write_file,
    "edit_file": edit_file,
    "make_dir": make_dir,
    "move_path": move_path,
    "delete_path": delete_path,
    "get_outline": get_outline,
    "patch_function": patch_function,
    "run_shell": run_shell,
    "run_python": run_python,
    "run_file": run_file,
    "run_server": run_server,
    "run_browser": run_browser,
    "run_npm": run_npm,
    "run_node": run_node,
    "setup_venv": setup_venv,
    "stop_server": stop_server,
    "nexus_web_search": nexus_web_search,
    # Git ツール
    "git_status": git_status,
    "git_diff": git_diff,
    "git_commit": git_commit,
    "git_checkout_branch": git_checkout_branch,
    "git_reset": git_reset,
    # MCP クライアント
    "mcp_call": mcp_call,
    "mcp_list_tools": mcp_list_tools,
}

# =========================
# リクエストモデル
# =========================

class ChatRequest(BaseModel):
    message: str
    max_steps: int = 20
    project: str = "default"
    search_enabled: bool | None = None
    llm_url: str = ""
    audio_base64: str = ""
    audio_format: str = "webm"
    voice_language: str = "ja"
    interruption: bool = False
    barge_in: bool = False
    partial_transcript: str = ""
    mode: str = "task"          # "chat" → direct LLM call, "task" → agent loop
    chat_history: list = []     # 会話履歴（chat モード時に使用）

class ProjectRequest(BaseModel):
    name: str
    overwrite: bool = False

class LLMTestRequest(BaseModel):
    url: str

class JobRequest(BaseModel):
    message: str
    project: str = "default"
    mode: str = "task"
    max_steps: int = 20
    search_enabled: bool | None = None
    llm_url: str = ""
    approved_tasks: list = None
    chat_history: list = []
    recommended_model: str = ""   # planが推奨したモデルキー（空なら自動判断）
    auto_select_option: bool = True  # True: プランナーLLMが対応案を自動選択 / False: ユーザー手動選択
    auto_skill_generation: bool = True  # True: 失敗時に不足スキルを自動生成して再試行


class AgentTaskDecisionRequest(BaseModel):
    project: str
    decision: str


class AgentTaskReviseRequest(BaseModel):
    project: str
    instruction: str = ""
    title: str = ""
    detail: str = ""


class AgentTaskProjectRequest(BaseModel):
    project: str


@dataclass
class AgentProjectState:
    running: bool = False
    currentTask: str | None = None
    loopCount: int = 0
    lastActions: list[str] = field(default_factory=list)
    session: AgentSession | None = None
    tool_registry_logged: bool = False


@dataclass
class AgentState:
    projects: dict[str, AgentProjectState] = field(default_factory=dict)


agent_state = AgentState()
agent_state_lock = threading.Lock()


def _require_project_key(payload: dict | None) -> str:
    project = str((payload or {}).get("project", "")).strip()
    if not project:
        raise HTTPException(status_code=400, detail="project is required")
    return _normalize_project_name(project)


def _get_or_create_agent_project_state(project_key: str) -> AgentProjectState:
    state = agent_state.projects.get(project_key)
    if state is None:
        state = AgentProjectState()
        agent_state.projects[project_key] = state
    return state


def _log_agent_registry_tools(project: str, *, reason: str) -> None:
    try:
        default_tools = sorted(create_default_registry().list_tools())
    except Exception as exc:
        print(json.dumps({
            "event": "agent_tool_registry_snapshot_error",
            "project": project,
            "reason": reason,
            "error": str(exc),
        }, ensure_ascii=False))
        return
    print(json.dumps({
        "event": "agent_tool_registry_snapshot",
        "project": project,
        "reason": reason,
        "tool_count": len(default_tools),
        "tools": default_tools,
        "has_nexus_web_search": "nexus_web_search" in default_tools,
    }, ensure_ascii=False))


def _execute_agent_session_queue(
    *,
    req_message: str,
    project: str,
    llm_url: str = "",
    max_steps: int = 20,
    search_enabled: bool | None = None,
) -> dict:
    with agent_state_lock:
        project_state = agent_state.projects.get(project)
        session = project_state.session if project_state else None
    if session is None:
        return {"status": "idle", "executed": [], "deferred": 0}

    executed: list[dict] = []
    search_events: list[dict] = []
    effective_search_enabled = _resolve_effective_search_enabled(search_enabled)
    ready_tasks = session.pop_executable_tasks(max_tasks=2, min_priority=0.5, min_confidence=0.6)
    for queued_task in ready_tasks:
        with agent_state_lock:
            if project in agent_state.projects:
                agent_state.projects[project].loopCount += 1
            action = f"task:{queued_task.id}"
            if project in agent_state.projects:
                agent_state.projects[project].lastActions.append(action)
                if len(agent_state.projects[project].lastActions) > 50:
                    agent_state.projects[project].lastActions = agent_state.projects[project].lastActions[-50:]
        snapshot_turns = list((queued_task.execution_snapshot or {}).get("frozen_turns", []))
        result = execute_task(
            task_detail=queued_task.detail,
            context="",
            max_steps=max_steps,
            project=project,
            search_enabled=effective_search_enabled,
            llm_url=_resolve_runtime_llm_url(llm_url),
            chat_history=snapshot_turns[-8:] if snapshot_turns else session.conversation_state.get("turns", [])[-8:],
        )
        queued_task.status = "done" if result.get("status") == "done" else "failed"
        steps = result.get("steps", []) or []
        web_search_calls = [
            s for s in steps
            if isinstance(s, dict)
            and s.get("type") == "tool_call"
            and s.get("action") == "nexus_web_search"
        ]
        web_search_event_type = "agent_nexus_web_search_used" if web_search_calls else "agent_nexus_web_search_not_used"
        web_search_event = {
            "type": web_search_event_type,
            # backward compatibility for consumers still expecting old event names.
            "legacy_type": "agent_web_search_used" if web_search_calls else "agent_web_search_not_used",
            "task_id": queued_task.id,
            "count": len(web_search_calls),
        }
        search_events.append(web_search_event)
        executed.append(
            {
                "task_id": queued_task.id,
                "title": queued_task.title,
                "priority": queued_task.priority,
                "confidence": queued_task.confidence,
                "status": queued_task.status,
                "output": result.get("output", ""),
                "steps": steps,
                "search_event": web_search_event,
            }
        )

    return {
        "status": "running" if project_state and project_state.running else "stopped",
        "intent_summary": session.conversation_state.get("intent_counts", {}),
        "executed": executed,
        "events": search_events,
        "deferred": len(session.execution_queue),
        "current_task": req_message,
    }


def _resolve_effective_search_enabled(requested: bool | str | int | None) -> bool:
    if requested is None:
        return bool(_search_enabled)
    if isinstance(requested, bool):
        return requested
    return str(requested).strip().lower() in ("true", "1", "yes", "on")

def execute_chat_with_optional_web_search(
    message: str,
    *,
    max_steps: int = 6,
    search_enabled: bool = False,
    llm_url: str = "",
    chat_history: list | None = None,
    on_event=None,
) -> dict:
    """
    chatモード専用の軽量実行。
    - search_enabled=False: 1回の通常チャット応答
    - search_enabled=True: nexus_web_searchのみを使える最小ループ（タスク実行ツールは使わない）
    """
    history_msgs = []
    for h in (chat_history or [])[-8:]:
        role = h.get("role", "user")
        text = str(h.get("text", ""))[:800]
        if role in ("user", "assistant") and text:
            history_msgs.append({"role": role, "content": text})

    if not search_enabled:
        messages = [
            {"role": "system", "content": "あなたはCodeAgentです。ユーザーの質問に丁寧に答えてください。コードが必要な場合はmarkdownで記述してください。"},
            *history_msgs,
            {"role": "user", "content": message},
        ]
        messages = _trim_messages(messages, _current_n_ctx, reserve_output=_calc_reserve_output(_current_n_ctx, ratio=0.22))
        chat_reply, usage = call_llm_chat(messages, llm_url=llm_url)
        return {"status": "done", "output": chat_reply, "usage": usage, "steps": []}

    CHAT_SEARCH_PROMPT = """You are CodeAgent in agent mode.
Return valid JSON object only. No markdown. No pseudo tags like <|tool_call> or call:nexus_web_search.

Allowed response formats (strict):
1) Tool call:
{"action":"tool","tool":"nexus_web_search","arguments":{"topic":"横浜 有名な公園","max_results_per_query":3}}
2) Final answer:
{"action":"final","content":"回答本文"}

Rules:
- Do not output any text before/after JSON.
- Only nexus_web_search is allowed as tool.
- nexus_web_search schema:
  - name: nexus_web_search
  - arguments.topic: string (required)
  - arguments.max_results_per_query: number (optional, default 3)
- If no tool is needed, return final immediately.
- At most 2 tool calls, and then return final.
"""
    messages = [
        {"role": "system", "content": CHAT_SEARCH_PROMPT},
        *history_msgs,
        {"role": "user", "content": message},
    ]
    steps = []
    agent_debug_logs: list[dict] = []
    searches_used = 0
    last_stub_only_non_fatal = False
    safe_max_steps = max(2, min(int(max_steps or 6), 8))

    for step in range(safe_max_steps):
        messages = _trim_messages(messages, _current_n_ctx, reserve_output=_calc_reserve_output(_current_n_ctx, ratio=0.22))
        if on_event:
            on_event({"type": "llm_thinking", "step_num": step + 1, "max_steps": safe_max_steps})
        reply, usage = call_llm_chat(messages, llm_url=llm_url)
        raw_reply = str(reply or "")
        action_obj, parse_error = _parse_agent_protocol_json(raw_reply)
        retry_used = False
        if action_obj is None:
            retry_used = True
            messages.append({"role": "assistant", "content": _sanitize_special_tokens(raw_reply)[:800]})
            messages.append({"role": "user", "content": "valid JSONのみで再出力してください。"})
            retry_reply, retry_usage = call_llm_chat(messages, llm_url=llm_url)
            if retry_usage.get("prompt_tokens"):
                usage = retry_usage
            raw_reply = str(retry_reply or "")
            action_obj, parse_error = _parse_agent_protocol_json(raw_reply)

        validated_obj = None
        validation_error = None
        if action_obj is not None:
            validated_obj, validation_error = _validate_agent_action_payload(action_obj)

        debug_item = {
            "step": step + 1,
            "raw_model_output": raw_reply[:1200],
            "parsed_action": (validated_obj or action_obj or {}).get("action", ""),
            "selected_tool": (validated_obj or action_obj or {}).get("tool", ""),
            "tool_arguments": (validated_obj or action_obj or {}).get("arguments", {}),
            "tool_result_summary": "",
            "parse_error": parse_error or validation_error or "",
            "retry_used": retry_used,
        }

        if validated_obj is None:
            agent_debug_logs.append(debug_item)
            if step >= safe_max_steps - 1:
                break
            messages.append({"role": "assistant", "content": _sanitize_special_tokens(raw_reply)[:800]})
            messages.append({"role": "user", "content": "JSONオブジェクトのみ。actionは tool または final だけを使ってください。"})
            continue

        action = validated_obj.get("action", "")

        if action == "final":
            out = str(validated_obj.get("content", "") or "").strip()
            if last_stub_only_non_fatal:
                out = f"{out}\n\n[注記] 検索provider失敗（stub）"
            debug_item["tool_result_summary"] = "final_response"
            agent_debug_logs.append(debug_item)
            return {"status": "done", "output": out, "usage": usage, "steps": steps, "logs": agent_debug_logs}

        if searches_used >= 2:
            debug_item["parse_error"] = "nexus_web_search_limit_reached"
            agent_debug_logs.append(debug_item)
            messages.append({"role": "assistant", "content": _sanitize_special_tokens(raw_reply)})
            messages.append({
                "role": "user",
                "content": "Tool call上限(2回)に達しました。final JSONで回答してください。",
            })
            continue

        tool_input = validated_obj.get("arguments", {}) or {}
        query = str(tool_input.get("topic", "") or "").strip()
        num_results = int(tool_input.get("max_results_per_query", 3) or 3)

        if on_event:
            on_event({
                "type": "tool_call",
                "step_num": step + 1,
                "action": "nexus_web_search",
                "input": {"topic": query, "max_results_per_query": num_results},
            })
        search_result = _run_nexus_web_search_tool_with_evidence(
            query,
            max_results_per_query=num_results,
            mode="quick",
            depth="quick",
            max_queries=1,
        )
        result_lines = search_result.get("formatted_items") or []
        result_text = "\n".join(f"- {line}" for line in result_lines) if result_lines else str(search_result.get("message") or "")
        last_stub_only_non_fatal = bool(search_result.get("event_payload", {}).get("non_fatal", False)) and not bool(search_result.get("items"))
        searches_used += 1
        preview = result_text[:400]
        debug_item["tool_result_summary"] = preview
        agent_debug_logs.append(debug_item)
        steps.append({"step": step + 1, "type": "tool", "action": "nexus_web_search", "input": {"topic": query, "max_results_per_query": num_results}})
        if on_event:
            on_event({
                "type": "tool_result",
                "step_num": step + 1,
                "action": "nexus_web_search",
                "result_preview": preview,
                "payload": search_result.get("event_payload") or {},
            })
        messages.append({"role": "assistant", "content": _sanitize_special_tokens(raw_reply)})
        stub_notice = "\n\n[注記] 検索provider失敗（stub）" if last_stub_only_non_fatal else ""
        messages.append({
            "role": "user",
            "content": (
                f"tool result:\n{result_text}{stub_notice}\n\n"
                "次はJSONオブジェクトのみで返答してください。"
                "追加検索が必要なら action=tool、不要なら action=final を返してください。"
            ),
        })

    fallback = "検索を試みましたが最終回答を構築できませんでした。質問を少し具体化してください。"
    return {"status": "error", "error": "chat_web_search_loop_exhausted", "output": fallback, "steps": steps, "logs": agent_debug_logs}

def _is_task_engine_v2_enabled() -> bool:
    """TASK_ENGINE_V2=true のときだけ新しいタスク実行経路を有効化する。"""
    return os.environ.get("TASK_ENGINE_V2", "false").strip().lower() in {"1", "true", "yes", "on"}

def _task_engine_v2_phase() -> int:
    raw = os.environ.get("TASK_ENGINE_V2_PHASE", "1").strip()
    try:
        return max(1, min(4, int(raw)))
    except Exception:
        return 1


def _is_dev_dogfood_mode(llm_url: str = "") -> bool:
    env = os.environ.get("CODEAGENT_ENV", "").strip().lower()
    if env in {"dev", "development", "local", "dogfood"}:
        return True
    url = (llm_url or "").strip().lower()
    return any(h in url for h in ("localhost", "127.0.0.1", "::1"))


def _infer_task_type(task_title: str, task_detail: str) -> str:
    text = f"{task_title}\n{task_detail}".lower()
    if any(k in text for k in ("test", "pytest", "検証", "verify", "動作確認")):
        return "test"
    if any(k in text for k in ("docs", "readme", "document", "説明")):
        return "docs"
    if any(k in text for k in ("refactor", "cleanup", "整理")):
        return "refactor"
    return "code"


def _is_task_type_in_rollout(task_type: str) -> bool:
    allow_raw = os.environ.get("TASK_ENGINE_V2_TASK_TYPES", "code,refactor").strip()
    allow = {v.strip().lower() for v in allow_raw.split(",") if v.strip()}
    return task_type.lower() in allow


def _should_use_task_engine_v2(task_title: str, task_detail: str, llm_url: str = "") -> bool:
    if not _is_task_engine_v2_enabled():
        return False
    phase = _task_engine_v2_phase()
    if phase == 1:
        return _is_dev_dogfood_mode(llm_url=llm_url)
    if phase == 2:
        return _is_dev_dogfood_mode(llm_url=llm_url) and _is_task_type_in_rollout(_infer_task_type(task_title, task_detail))
    return True


class _TaskV2Planner(Planner):
    def __init__(self, messages: list[dict], llm_url: str, max_steps: int, parser: str) -> None:
        self._messages = messages
        self._llm_url = llm_url
        self._max_steps = max_steps
        self._parser = parser
        self._turn = 0
        self._consecutive_json_errors = 0
        self._last_history_len = 0

    def create_plan(self, objective: str, context: dict) -> Plan:
        plan_steps = ["Analyze objective", "Use one tool/action", "Iterate until final"]
        return Plan(goal=objective, steps=plan_steps, metadata={"context": context})

    def choose_next_action(self, plan: Plan, history: list[ToolResult]) -> Action | None:
        self._append_history_to_messages(history)
        if self._turn >= self._max_steps:
            return Action(id=f"v2-{self._turn}", tool="__final__", input={"output": f"ステップ上限 ({self._max_steps})", "error": True})

        self._turn += 1
        reply, usage = call_llm_chat(self._messages, llm_url=self._llm_url)
        action_obj = _parse_task_v2_action(reply, parser=self._parser)
        if action_obj is None:
            self._consecutive_json_errors += 1
            feedback = 'JSON形式のみで出力してください。例: {"action":"list_files","args":{"subdir":""}}'
            self._messages.append({"role": "assistant", "content": _sanitize_special_tokens((reply or "")[:500])})
            self._messages.append({"role": "user", "content": feedback})
            if self._consecutive_json_errors >= 3:
                return Action(id=f"v2-{self._turn}", tool="__final__", input={"output": "JSON出力失敗（3回連続）", "error": True})
            return Action(id=f"v2-{self._turn}", tool="__retry__", input={"reason": "json_parse_failed"})

        self._consecutive_json_errors = 0
        action = str(action_obj.get("action", "") or "").strip().lower()
        action, note = _normalize_action_name(action)
        thought = action_obj.get("thought", "")
        args = action_obj.get("args", {})
        if note:
            thought = f"{thought} ({note})".strip()
        payload = {
            "args": args if isinstance(args, dict) else {},
            "thought": thought,
            "usage": usage or {},
            "raw_action": action_obj,
        }
        if action in {"stop", "done", "finish", "complete", "end", "final"}:
            payload["output"] = action_obj.get("output", thought or "完了")
            return Action(id=f"v2-{self._turn}", tool="__final__", input=payload)
        return Action(id=f"v2-{self._turn}", tool=action, input=payload)

    def _append_history_to_messages(self, history: list[ToolResult]) -> None:
        if self._last_history_len >= len(history):
            return
        for item in history[self._last_history_len:]:
            output = item.output if isinstance(item.output, dict) else {"raw": item.output}
            compact = output.get("compact_reply", "")
            if compact:
                self._messages.append({"role": "assistant", "content": _sanitize_special_tokens(compact)})
            result_text = str(output.get("result", output.get("error") or ""))[:2000]
            if result_text:
                self._messages.append({"role": "user", "content": f"実行結果:\n{result_text}"})
        self._last_history_len = len(history)


class _TaskV2Executor(Executor):
    def __init__(self, registry: ToolRegistry, active_tools: dict, max_retries: int = 2) -> None:
        super().__init__(max_retries=max_retries)
        self.registry = registry
        self.active_tools = active_tools

    def _execute_once(self, action: Action) -> ToolResult:
        if action.tool == "__retry__":
            return ToolResult(action_id=action.id, success=False, output={"error": "json_parse_failed"}, error="json_parse_failed")
        if action.tool == "__final__":
            return ToolResult(action_id=action.id, success=True, output={"final": True, "output": action.input.get("output", ""), "error": bool(action.input.get("error"))})

        thought = action.input.get("thought", "")
        tool_input = action.input.get("args", {})
        safe_input, prep_error, prep_notes = _prepare_tool_call(self.active_tools, action.tool, tool_input)
        if prep_error:
            return ToolResult(
                action_id=action.id,
                success=False,
                output={"action": action.tool, "input": tool_input, "thought": thought, "error": prep_error},
                error=prep_error,
            )
        handler = self.registry.get(action.tool)
        if handler is None:
            return ToolResult(action_id=action.id, success=False, output={"error": f"unknown tool: {action.tool}"}, error=f"unknown tool: {action.tool}")
        result = handler(Action(id=action.id, tool=action.tool, input=safe_input))
        result_text = str(result.output)
        output = {
            "action": action.tool,
            "input": safe_input,
            "thought": thought,
            "result": result.output,
            "result_preview": result_text[:200],
            "compact_reply": _compact_reply({"action": action.tool, "args": safe_input, "thought": thought}, max_chars=300),
            "notes": prep_notes,
        }
        result.output = output
        return result


class _TaskV2Evaluator(Evaluator):
    def evaluate(self, plan: Plan, history: list[ToolResult]) -> Evaluation:
        if not history:
            return Evaluation(passed=False, feedback="not_started", done=False)
        latest = history[-1]
        payload = latest.output if isinstance(latest.output, dict) else {}
        if payload.get("final"):
            return Evaluation(passed=not payload.get("error", False), feedback="final", done=True)
        return super().evaluate(plan=plan, history=history)


def _build_task_v2_file_candidates(project: str, max_files: int = 24, max_chars_each: int = 8000) -> list[dict]:
    candidates: list[dict] = []
    project_root = os.path.join(WORK_DIR, project)
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", "__pycache__", "node_modules"}]
        for name in files:
            if len(candidates) >= max_files:
                return candidates
            path = os.path.join(root, name)
            rel = os.path.relpath(path, project_root).replace("\\", "/")
            try:
                content = open(path, "r", encoding="utf-8").read(max_chars_each)
            except Exception:
                continue
            candidates.append({"path": rel, "content": content})
    return candidates


def execute_task_stream_v2(task_detail: str, context: str = "", max_steps: int = 15, project: str = "default",
                           search_enabled: bool = True, llm_url: str = "", job_id: str = "", task_id: int = 0, task_title: str = ""):
    project_prompt = _build_system_prompt(project)
    user_content = task_detail if not context else f"【前のタスクの結果】\n{context}\n\n【今のタスク】\n{task_detail}"
    messages = [{"role": "system", "content": project_prompt}, {"role": "user", "content": user_content}]

    active_tools = dict(TOOLS)
    if not search_enabled:
        # search_enabled=false の場合は nexus_web_search ツールを公開しない。
        active_tools.pop("nexus_web_search", None)
    active_tools.update(_load_skill_functions())
    import functools as _ft3
    for _pt in ("read_file", "write_file", "edit_file", "get_outline", "patch_function", "list_files", "search_in_files",
                "make_dir", "move_path", "delete_path", "run_shell", "run_python", "run_file", "run_server", "setup_venv"):
        if _pt in active_tools:
            active_tools[_pt] = _ft3.partial(active_tools[_pt], project=project)

    registry = ToolRegistry()
    for name, fn in active_tools.items():
        registry.register(name, lambda tool_input, _fn=fn, _name=name: ToolResult(action_id=_name, success=not str((_r := _fn(**tool_input))).startswith("ERROR:"), output=_r, error=None if not str(_r).startswith("ERROR:") else str(_r)))

    context_builder = TaskV2ContextBuilder(
        file_summary_cache=FileSummaryCache(max_summary_tokens=_get_summary_token_limit())
    )
    runtime_state = {
        "plan": task_title or task_detail[:120],
        "current_step": "",
        "file_candidates": _build_task_v2_file_candidates(project=project),
    }
    context_builder.build(objective=task_detail, runtime_state=runtime_state)

    memory = HybridMemoryStore(
        long_term_saver=lambda entry: memory_save(entry),
        long_term_searcher=lambda query, limit: memory_search(query, limit=limit),
    )
    planner = _TaskV2Planner(messages=messages, llm_url=llm_url, max_steps=max_steps, parser=_model_manager.current_parser)
    executor = _TaskV2Executor(registry=registry, active_tools=active_tools, max_retries=2)
    evaluator = _TaskV2Evaluator()
    loop = build_agent_loop(planner=planner, executor=executor, evaluator=evaluator, context_builder=context_builder, memory_store=memory)
    evaluation, history = loop.run_once(objective=task_detail, runtime_state=runtime_state)

    steps = []
    prompt_tokens = 0
    completion_tokens = 0
    for idx, item in enumerate(history, 1):
        payload = item.output if isinstance(item.output, dict) else {}
        if payload.get("final"):
            continue
        usage = payload.get("usage", {})
        prompt_tokens = max(prompt_tokens, int(usage.get("prompt_tokens", 0) or 0))
        completion_tokens = max(completion_tokens, int(usage.get("completion_tokens", 0) or 0))
        yield {"type": "tool_call", "action": payload.get("action"), "thought": payload.get("thought", ""), "step_num": idx, "max_steps": max_steps}
        yield {"type": "tool_result", "action": payload.get("action"), "result_preview": str(payload.get("result_preview", ""))}
        steps.append({"step": idx - 1, "type": "tool_call", "action": payload.get("action"), "input": payload.get("input", {}), "result_preview": str(payload.get("result_preview", ""))})

    final_output = ""
    final_error = None
    if history and isinstance(history[-1].output, dict) and history[-1].output.get("final"):
        final_output = str(history[-1].output.get("output", "") or "")
        if history[-1].output.get("error"):
            final_error = final_output or "task failed"
    elif evaluation.done and evaluation.passed:
        final_output = evaluation.feedback or "完了"
    else:
        final_error = evaluation.feedback or "task failed"

    if final_error:
        yield {"type": "task_error", "task_id": task_id, "title": task_title, "error": final_error, "steps": steps}
        return
    yield {"type": "task_done", "task_id": task_id, "title": task_title, "output": final_output, "steps": steps,
           "total_steps": len(steps), "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "tps": 0}

def run_task_mode_stream(
    task_detail: str,
    context: str = "",
    max_steps: int = 15,
    project: str = "default",
    search_enabled: bool = True,
    llm_url: str = "",
    job_id: str = "",
    task_id: int = 0,
    task_title: str = "",
):
    """
    taskモードの実行入口。
    - デフォルト: 旧実装 execute_task_stream
    - TASK_ENGINE_V2=true: 新実装入口（現段階は既存実装へフォールバック）
    """
    if _should_use_task_engine_v2(task_title=task_title, task_detail=task_detail, llm_url=llm_url):
        return execute_task_stream_v2(
            task_detail=task_detail,
            context=context,
            max_steps=max_steps,
            project=project,
            search_enabled=search_enabled,
            llm_url=llm_url,
            job_id=job_id,
            task_id=task_id,
            task_title=task_title,
        )

    return execute_task_stream(
        task_detail=task_detail,
        context=context,
        max_steps=max_steps,
        project=project,
        search_enabled=search_enabled,
        llm_url=llm_url,
        job_id=job_id,
        task_id=task_id,
        task_title=task_title,
    )

def run_job_background(job_id: str, req: "JobRequest"):
    """
    バックグラウンドスレッドで実行。
    全イベントをDBに書き込み続ける（ブラウザが閉じても継続）。
    """
    project = req.project
    effective_search_enabled = _resolve_effective_search_enabled(req.search_enabled)
    seq = 0

    # clarify待機用のEventを登録
    _ev = _wait_threading.Event()
    _job_wait_events[job_id] = _ev

    def write(event_type: str, data: dict):
        nonlocal seq
        job_append_step(project, job_id, seq, event_type, data)
        # clarifyイベントが来たらjobをwaiting_inputに更新
        if event_type == "clarify":
            job_update_status(project, job_id, "waiting_input")
        # ジョブログに蓄積（サーバー側で全INFOを記録）
        log_entry = {"type": event_type, "seq": seq}
        if event_type == "tool_call":
            log_entry.update({
                "action": data.get("action",""),
                "thought": data.get("thought",""),  # 文字数制限なし
                "step_num": data.get("step_num"),
            })
        elif event_type == "tool_result":
            log_entry["result_preview"] = data.get("result_preview","")
        elif event_type in ("task_done","task_error","task_start"):
            log_entry.update({
                "task_id": data.get("task_id"),
                "title": data.get("title",""),
                "error": data.get("error",""),
            })
        elif event_type == "skill_hint":
            log_entry.update({
                "missing_tool": data.get("missing_tool",""),
                "thought": data.get("thought",""),
            })
        job_log_append(job_id, log_entry)
        seq += 1

    try:
        job_update_status(project, job_id, "running")

        if req.mode == "chat":
            exec_url = _resolve_runtime_llm_url(req.llm_url)
            chat_result = execute_chat_with_optional_web_search(
                req.message,
                max_steps=req.max_steps,
                search_enabled=effective_search_enabled,
                llm_url=exec_url,
                chat_history=req.chat_history,
                on_event=lambda ev: write(ev.get("type", "chat_step"), ev),
            )
            chat_output = chat_result.get("output") or chat_result.get("error") or ""
            write("done", {
                "result": chat_output,
                "status": "done" if chat_result.get("status") == "done" else "error",
                "usage": chat_result.get("usage", {}),
                "steps": chat_result.get("steps", []),
            })
            save_session(job_id, project, req.message, "chat", {
                "output": chat_output,
                "status": chat_result.get("status", "done"),
                "steps": chat_result.get("steps", []),
            })


        else:
            # taskモード: plan → モデル選択 → verify
            if req.approved_tasks:
                todos = req.approved_tasks
                plan_result = None
                print(f"[JOB {job_id}] approved_tasks count: {len(todos)}")
                for t in todos:
                    print(f"  task id={t.get('id')} title={t.get('title','')[:40]}")
            else:
                plan_result = plan(req.message, project)
                todos = plan_result.get("tasks", [])
                print(f"[JOB {job_id}] planned tasks count: {len(todos)}")

            write("plan", {"tasks": todos, "total": len(todos)})
            total = len(todos)
            print(f"[JOB {job_id}] total tasks to execute: {total}")
            results = []
            context = ""

            # ── プランニング後・実行前にモデル選択 ──
            # モデル選択: UIで手動指定 > Auto（heuristic_classify）
            forced_model = (req.recommended_model or "").strip()
            runtime_catalog = get_runtime_model_catalog()
            if forced_model and forced_model != "auto" and forced_model in runtime_catalog:
                # UIで手動選択されたモデルを使用
                best_key = forced_model
                print(f"[ModelManager] user selected: {best_key}")
            else:
                # Auto or 未指定: 現在のモデルをそのまま使う（切り替えしない）
                best_key = _model_manager.current_key
                print(f"[ModelManager] auto: keeping current model {best_key}")

            if best_key != _model_manager.current_key and runtime_catalog.get(best_key, {}).get("path"):
                write("model_switching", {
                    "from": _model_manager.current_key,
                    "to": best_key,
                    "model_name": runtime_catalog.get(best_key, {}).get("name", best_key),
                    "eta_sec": runtime_catalog.get(best_key, {}).get("load_sec", 60),
                    "message": f"Loading {runtime_catalog.get(best_key,{}).get('name',best_key)}..."
                })
                def _on_switch(ev):
                    write(ev.get("type","model_event"), ev)
                switched = _model_manager.ensure_model(best_key, on_event=_on_switch)
                if not switched:
                    print(f"[ModelManager] switch to {best_key} failed, staying on current model")
                    write("model_event", {"message": "Switch failed, using current model"})
                # model_readyはensure_model内のemitで既に発火（重複しない）
            else:
                print(f"[ModelManager] no switch needed for {best_key}")

            orchestration_policy = settings_get("orchestration_policy") or "ladder_fail_and_quality"
            quality_check_enabled = settings_get("quality_check_enabled") != "false"
            coder_ladder = get_coder_ladder_keys(runtime_catalog)
            feature_mode = settings_get("feature_mode") or "model_orchestration"
            if feature_mode == "ensemble":
                ensemble_status = _apply_ensemble_execution_mode_guard()
                write("ensemble_mode", {
                    "mode": ensemble_status.get("configured_mode", "parallel"),
                    "recommended_mode": ensemble_status.get("recommended_mode", "parallel"),
                    "warning": bool(ensemble_status.get("warning")),
                    "reason": ensemble_status.get("reason", ""),
                    "auto_switched": bool(ensemble_status.get("switched_by_guard")),
                    "free_vram_mb": ensemble_status.get("free_vram_mb", -1),
                    "required_vram_parallel_mb": ensemble_status.get("required_vram_parallel_mb", -1),
                    "required_vram_serial_mb": ensemble_status.get("required_vram_serial_mb", -1),
                })
            write("feature_mode", {"mode": feature_mode})

            for i, todo in enumerate(todos):
              try:  # ← per-task guard: 1タスクの例外がジョブ全体を止めないよう保護
                pre_snapshot = auto_snapshot_ca_data("pre-task snapshot", job_id, todo.get("id", i + 1))
                pre_snapshot_hash = pre_snapshot.get("commit_hash", "") if pre_snapshot.get("ok") else ""
                write("snapshot", {
                    "stage": "pre-task snapshot",
                    "task_id": todo.get("id", i + 1),
                    "ok": bool(pre_snapshot.get("ok")),
                    "skipped": bool(pre_snapshot.get("skipped")),
                    "reason": pre_snapshot.get("reason", ""),
                    "commit_hash": pre_snapshot_hash,
                    "error": pre_snapshot.get("error", ""),
                })

                write("task_start", {
                    "task_id": todo["id"], "title": todo["title"],
                    "task_index": i, "total": total
                })

                # run_task_mode_stream を使ってステップごとに書き込む
                task_steps = []
                task_status = "pending"  # done/error/pendingで区別
                task_output = ""

                # req.llm_urlが明示されていればそちら、なければModelManagerのURL
                task_url = _resolve_runtime_llm_url(req.llm_url)
                try:
                    for ev in run_task_mode_stream(
                        task_detail=todo["detail"], context=context,
                        max_steps=req.max_steps, project=project,
                        search_enabled=effective_search_enabled, llm_url=task_url,
                        job_id=job_id,
                        task_id=todo.get("id", i+1),
                        task_title=todo.get("title", ""),
                    ):
                        write(ev.get("type","step"), ev)
                        etype = ev.get("type","")
                        if etype == "clarify":
                            # clarify: waiting_input はwrite内で設定済み。再開待ち
                            _job_wait_events[job_id].wait(timeout=300)
                            _job_wait_events[job_id].clear()
                        if etype == "task_done":
                            task_status = "done"
                            task_output = ev.get("output","")
                            task_steps = ev.get("steps",[])
                        elif etype == "task_error":
                            task_status = "error"
                            task_output = ev.get("error","") or task_output
                except Exception as _task_ex:
                    # HTTPException(502/413)などがタスクループを突き抜けないよう捕捉
                    err_msg = str(_task_ex)
                    print(f"[JOB {job_id}] task {i+1}/{total} exception: {err_msg[:100]}")
                    write("task_error", {"task_id": todo["id"], "error": f"[exception] {err_msg[:200]}"})
                    task_status = "error"
                    task_output = f"[exception] {err_msg[:200]}"



                # ── 4段階フォールバック ─────────────────────────────────
                # Stage 1: 同じアプローチで再試行（一時的エラー・タイムアウト対応）
                # Stage 2: 別アプローチで再試行
                # Stage 3: 最小構成で再試行
                # Stage 4: 複数対応案をLLMが生成 → ユーザーが選択 → 再実行
                # ────────────────────────────────────────────────────────

                def _summarize_exploration_steps(_steps, limit=6):
                    exp_actions = {"list_files", "get_outline", "read_file", "search_in_files"}
                    chunks = []
                    for _s in _steps:
                        if _s.get("type") != "tool_call":
                            continue
                        _a = _s.get("action", "")
                        if _a not in exp_actions:
                            continue
                        _inp = _s.get("input", {}) if isinstance(_s.get("input"), dict) else {}
                        _target = (_inp.get("path") or _inp.get("subdir") or _inp.get("query") or "")
                        _preview = str(_s.get("result_preview", "")).replace("\n", " ")[:90]
                        chunks.append(f"{_a}({_target})=>{_preview}")
                    if not chunks:
                        return ""
                    return " / ".join(chunks[-limit:])

                def _run_stage(title_prefix, ctx, steps_limit, run_url=None):
                    """run_task_mode_streamを安全に実行してtask_status/outputを返す"""
                    _steps, _status, _output = [], "pending", ""
                    _url = run_url or task_url
                    try:
                        write("task_start", {
                            "task_id": todo["id"], "title": f"{title_prefix}{todo['title']}",
                            "task_index": i, "total": total
                        })
                        for ev in run_task_mode_stream(
                            task_detail=todo["detail"], context=ctx,
                            max_steps=steps_limit, project=project,
                            search_enabled=effective_search_enabled, llm_url=_url,
                            job_id=job_id,
                            task_id=todo.get("id", i+1),
                            task_title=f"{title_prefix}{todo.get('title','')}",
                        ):
                            write(ev.get("type","step"), ev)
                            etype = ev.get("type","")
                            if etype == "task_done":
                                _status = "done"
                                _output = ev.get("output","")
                                _steps  = ev.get("steps",[])
                            elif etype == "task_error":
                                _status = "error"
                                _output = ev.get("error","") or _output
                    except Exception as _ex:
                        _status = "error"
                        _output = f"[exception] {str(_ex)[:200]}"
                    return _steps, _status, _output

                def _classify_orchestration_error(err_text: str) -> str:
                    msg = (err_text or "").lower()
                    if "playwright: not found" in msg:
                        return "playwright_not_found"
                    if "targetclosederror" in msg:
                        return "target_closed_env"
                    return ""

                def _run_browser_precheck_flow() -> str:
                    checks = [
                        run_shell(command=".venv/bin/python -m playwright --version", project=project, timeout=60),
                        run_shell(
                            command=(
                                ".venv/bin/python - <<'PY'\n"
                                "from playwright.sync_api import sync_playwright\n"
                                "with sync_playwright() as p:\n"
                                "    print('chromium_executable=' + p.chromium.executable_path)\n"
                                "PY"
                            ),
                            project=project,
                            timeout=90,
                        ),
                    ]
                    return "\n\n".join(str(c) for c in checks if c)

                def _run_playwright_env_repair_flow() -> str:
                    repair_logs = [
                        setup_venv(requirements=["playwright"], project=project),
                        run_shell(
                            command=".venv/bin/pip install --upgrade pip playwright && .venv/bin/python -m playwright install chromium",
                            project=project,
                            timeout=300,
                        ),
                    ]
                    repair_logs.append(_run_browser_precheck_flow())
                    return "\n\n".join(str(c) for c in repair_logs if c)

                last_error_key = ""
                same_error_streak = 0

                def _update_same_error_streak(err_text: str) -> int:
                    nonlocal last_error_key, same_error_streak
                    key = " ".join((err_text or "").strip().split()).lower()[:220]
                    if not key:
                        last_error_key = ""
                        same_error_streak = 0
                        return 0
                    if key == last_error_key:
                        same_error_streak += 1
                    else:
                        last_error_key = key
                        same_error_streak = 1
                    return same_error_streak

                # Stage 1: 同じアプローチで再試行
                if task_status in ("error", "pending"):
                    err0 = task_output or "不明なエラー"
                    err0_type = _classify_orchestration_error(err0)
                    _update_same_error_streak(err0)
                    loop_summary0 = _summarize_exploration_steps(task_steps)
                    loop_note0 = ""
                    if loop_summary0:
                        loop_note0 = f"【直前の探索結果要約】{loop_summary0}\n同じ探索シーケンスを繰り返さないこと。\n"
                    preflight_note0 = ""
                    if err0_type == "playwright_not_found":
                        repair_log = _run_playwright_env_repair_flow()
                        preflight_note0 = (
                            "\n【オーケストレーション指示】Playwright 環境修復フローを実行済みです。"
                            " run_browser 再実行前は必ず前提チェック結果を確認してください。"
                            f"\n【環境修復ログ】\n{repair_log[:1200]}"
                        )
                    elif err0_type == "target_closed_env":
                        preflight_log = _run_browser_precheck_flow()
                        preflight_note0 = (
                            "\n【オーケストレーション指示】TargetClosedError を環境依存エラーとして分類。"
                            " Playwright 再インストールは行わず、ブラウザを閉じる順序と終了処理（close / context manager）を見直してから再実行してください。"
                            f"\n【run_browser 前提チェック】\n{preflight_log[:800]}"
                        )
                    print(f"[JOB {job_id}] task {i+1}/{total} stage1 same-approach retry")
                    # メモリ参照: 類似エラーの過去の解決策を注入
                    _mem_hits1 = memory_search(f"{todo['title']} {err0}", limit=2)
                    _mem_note1 = ""
                    if _mem_hits1:
                        _mem_note1 = "\n\n【過去の類似エラーと解決策（メモリ）】\n" + "\n".join(
                            f"- {h['title']}: {h['content'][:200]}" for h in _mem_hits1
                        )
                    ctx1 = (f"{context}\n\n【前回エラー】{err0[:200]}\n\n"
                            f"【指示】前回と同じタスクをもう一度実行してください。"
                            f"エラーの原因を確認して修正してから再実行してください。"
                            f"{loop_note0}"
                            f"{preflight_note0}"
                            f"{_mem_note1}")
                    task_steps, task_status, task_output = _run_stage("[再試行] ", ctx1, req.max_steps)

                # Stage 2: 別アプローチで再試行
                if task_status in ("error", "pending"):
                    err1 = task_output or err0
                    err1_type = _classify_orchestration_error(err1)
                    err1_streak = _update_same_error_streak(err1)
                    if err1_streak >= 2:
                        print(f"[JOB {job_id}] task {i+1}/{total} abort retry on same error twice")
                        collect_ctx = (
                            f"{context}\n\n【同一エラー連続検出】{err1[:200]}\n"
                            "【次アクション】設定確認ログ収集を実施してください。\n"
                            "- run_shell で `pwd && ls -la .venv/bin` を実行\n"
                            "- run_shell で `.venv/bin/python -m playwright --version` を実行\n"
                            "- run_shell で `.venv/bin/python -m playwright install chromium --dry-run` を実行\n"
                            "- run_browser は実行しない\n"
                        )
                        task_steps, task_status, task_output = _run_stage("[設定確認ログ収集] ", collect_ctx, req.max_steps)
                        err2 = task_output or err1
                    else:
                        loop_summary1 = _summarize_exploration_steps(task_steps)
                        loop_note1 = ""
                        if loop_summary1:
                            loop_note1 = f"\n【直前の探索結果要約】{loop_summary1}\n上記と同じ探索シーケンスは禁止。編集対象を先に固定すること。"
                        preflight_note1 = ""
                        if err1_type == "playwright_not_found":
                            repair_log = _run_playwright_env_repair_flow()
                            preflight_note1 = (
                                "\n【オーケストレーション指示】`playwright: not found` のため、"
                                " venv固定コマンドで再セットアップ済みです。"
                                f"\n【環境修復ログ】\n{repair_log[:1200]}"
                            )
                        elif err1_type == "target_closed_env":
                            preflight_log = _run_browser_precheck_flow()
                            preflight_note1 = (
                                "\n【オーケストレーション指示】TargetClosedError（環境依存）を再検出。"
                                " 再インストールループは禁止し、ブラウザ終了処理を修正してから再試行してください。"
                                f"\n【run_browser 前提チェック】\n{preflight_log[:800]}"
                            )
                        print(f"[JOB {job_id}] task {i+1}/{total} stage2 different-approach")
                        # メモリ参照: 複合エラーの解決策を追加注入
                        _mem_hits2 = memory_search(f"{err0} {err1}", limit=2)
                        _mem_note2 = ""
                        if _mem_hits2:
                            _mem_note2 = "\n\n【過去の知識（メモリ）】\n" + "\n".join(
                                f"- {h['title']}: {h['content'][:200]}" for h in _mem_hits2
                            )
                        ctx2 = (f"{context}\n\n【前回エラー×2】\n1回目: {err0[:100]}\n2回目: {err1[:100]}\n\n"
                                f"【指示】これまでと異なるアプローチで実行してください。\n"
                                f"例: write_file→edit_file / run_python→コード分割 / 大きなファイル→get_outline+部分編集"
                                f"{loop_note1}"
                                f"{preflight_note1}"
                                f"{_mem_note2}")
                        task_steps, task_status, task_output = _run_stage("[別アプローチ] ", ctx2, req.max_steps)

                # Stage 3: 全失敗 → 複数対応案を生成 → LLM自動選択 or ユーザー手動選択
                if task_status in ("error", "pending"):
                    err2 = task_output or err1
                    print(f"[JOB {job_id}] task {i+1}/{total} stage3 generating options")

                    # 現在のモデルを記憶
                    prev_model_key = _model_manager.current_key

                    # コードLLMで対応案を生成
                    options_prompt = f"""タスクが3回試行しても完了できませんでした。
【タスク】{todo['title']}
【詳細】{todo['detail'][:300]}
【エラー履歴】
1回目: {err0[:100]}
2回目: {err1[:100]}
3回目: {err2[:100]}

このタスクを完了させるための対応案を3件提示してください。
各案は異なる技術的アプローチで具体的に記述してください。

【重要な制約】
- 「スキップ」「タスクの省略」「次へ進む」のような案は絶対に提案しないこと
- 「ユーザーに委ねる」「手動実装依頼」「ユーザーが実装」のような案は絶対に提案しないこと
- 必ずコードエージェント自身が実行できる技術的な解決策を3件提案すること
- 例: ライブラリ変更、アルゴリズム変更、ファイル分割、別APIの使用、エラー原因の根本対処 など

JSON形式で出力:
{{"options": [
  {{"id": 1, "title": "案のタイトル（10字以内）", "description": "具体的な実施内容（2文以内）", "difficulty": "easy/medium/hard", "detail": "エージェントへの実行指示（詳細）"}},
  {{"id": 2, ...}},
  {{"id": 3, ...}}
]}}"""
                    try:
                        opt_reply, _ = call_llm_chat(
                            [{"role": "user", "content": options_prompt}],
                            llm_url=task_url
                        )
                        opt_parsed = extract_json(opt_reply, parser=_model_manager.current_parser)
                        options = opt_parsed.get("options", []) if opt_parsed else []
                    except Exception as _oe:
                        options = []
                        print(f"[JOB {job_id}] options generation failed: {_oe}")

                    if not options:
                        options = [
                            {"id": 1, "title": "タスク分割", "description": "タスクをより小さなステップに分割して段階的に実行", "difficulty": "medium", "detail": f"次のタスクを小さなステップに分割して、一つずつ確実に実行してください: {todo['detail'][:200]}"},
                            {"id": 2, "title": "最小実装", "description": "エラー箇所を特定して最小限の変更で問題を修正", "difficulty": "easy", "detail": f"エラーの根本原因を特定し、最小限の変更で問題を解決してください。別ライブラリや別APIの使用も検討してください。タスク: {todo['detail'][:150]}"},
                            {"id": 3, "title": "代替手段", "description": "別のツールやライブラリを使って同等の機能を実現", "difficulty": "hard", "detail": f"これまでのアプローチを完全に変え、別のライブラリ・ツール・手法で同じ目標を達成してください。タスク: {todo['detail'][:150]}"},
                        ]

                    # ──── 自動選択モード（プランナーLLM） ────
                    auto_select = req.auto_select_option if hasattr(req, 'auto_select_option') else True
                    chosen = None

                    if auto_select:
                        planner_key = choose_model_for_role("plan", include_disabled=True) or _model_manager.current_key
                        planner_spec = get_model_spec(planner_key)
                        write("model_switching", {
                            "from": prev_model_key,
                            "to": planner_key,
                            "model_name": planner_spec.get("name", "Planner"),
                            "eta_sec": planner_spec.get("load_sec", 30),
                            "message": "対応案を分析中: プランナーLLMをロード中..."
                        })
                        write("task_start", {
                            "task_id": todo["id"],
                            "title": f"[プランナー分析] {todo['title']}",
                            "task_index": i, "total": total
                        })

                        # コードLLMをアンロードしてプランナーをロード
                        planner_switched = _model_manager.ensure_model(
                            planner_key,
                            on_event=lambda ev: write(ev.get("type","model_event"), ev)
                        )
                        planner_url = _model_manager.llm_url

                        select_prompt = f"""あなたはコードエージェントのプランナーです。
以下の状況を分析して、3つの対応案の中から最適なものを1つ選んでください。

【ジョブ全体の目標】{req.message[:200]}
【失敗したタスク】{todo['title']}
【タスク詳細】{todo['detail'][:200]}
【前後のコンテキスト】{context[:300]}
【エラー履歴】
1回目: {err0[:80]}
2回目: {err1[:80]}
3回目: {err2[:80]}

【対応案】
""" + "\n".join(f"案{o['id']}: [{o['difficulty']}] {o['title']} — {o['description']}" for o in options) + f"""

【選択ルール】
- 「スキップ」「省略」「ユーザーに委ねる」内容の案は絶対に選ばないこと
- コードエージェントが自律的に実行できる技術的な解決策を選ぶこと
- エラー履歴を踏まえて最も根本解決できる案を選ぶこと

最も成功確率が高い案を1つ選んでJSON出力してください:
{{"choice": 1, "reason": "選択理由（1文）"}}"""

                        try:
                            sel_reply, _ = call_llm_chat(
                                [{"role": "user", "content": select_prompt}],
                                llm_url=planner_url
                            )
                            sel_parsed = extract_json(sel_reply, parser="gpt_oss")
                            choice_id = int(sel_parsed.get("choice", 1)) if sel_parsed else 1
                            reason = sel_parsed.get("reason", "") if sel_parsed else ""
                            chosen = next((o for o in options if o["id"] == choice_id), options[0])
                            print(f"[JOB {job_id}] planner chose option {choice_id}: {chosen['title']} — {reason}")
                            write("task_start", {
                                "task_id": todo["id"],
                                "title": f"[自動選択: {chosen['title']}] {todo['title']}",
                                "task_index": i, "total": total
                            })
                        except Exception as _se:
                            chosen = options[0]
                            reason = f"自動選択失敗({_se}): デフォルト案1を使用"
                            print(f"[JOB {job_id}] planner selection failed: {_se}")

                        # プランナーをアンロードしてコードLLMを復帰
                        prev_spec = get_model_spec(prev_model_key)
                        write("model_switching", {
                            "from": planner_key,
                            "to": prev_model_key,
                            "model_name": prev_spec.get("name", prev_model_key),
                            "eta_sec": prev_spec.get("load_sec", 30),
                            "message": f"プランナー選択完了: {chosen['title']} — コードLLMを復帰中..."
                        })
                        _model_manager.ensure_model(
                            prev_model_key,
                            on_event=lambda ev: write(ev.get("type","model_event"), ev)
                        )
                        task_url = _model_manager.llm_url

                        # 選択内容をUIに通知
                        write("task_options", {
                            "task_id": todo["id"],
                            "title": todo["title"],
                            "error": err2[:200],
                            "options": options,
                            "auto_chosen": chosen["id"],
                            "auto_reason": reason,
                            "job_id": job_id,
                        })

                    else:
                        # ──── 手動選択モード ────
                        write("task_options", {
                            "task_id": todo["id"],
                            "title": todo["title"],
                            "error": err2[:200],
                            "options": options,
                            "job_id": job_id,
                        })
                        job_update_status(project, job_id, "waiting_input")
                        _job_wait_events[job_id].wait(timeout=600)
                        _job_wait_events[job_id].clear()
                        job_update_status(project, job_id, "running")
                        chosen = _job_option_choices.pop(f"{job_id}_{todo['id']}", None)

                    # ── SKILL自動生成（auto_skill_generation が有効な場合） ──
                    auto_skill_gen = getattr(req, 'auto_skill_generation', True)
                    skill_context_note = ""
                    if auto_skill_gen:
                        try:
                            all_errors = f"{err0}\n{err1}\n{err2}"
                            existing_skill_lines = []
                            for skill in _active_skills()[:12]:
                                kw = ", ".join(skill.get("keywords", [])[:6])
                                existing_skill_lines.append(f"- {skill.get('name','')}: {skill.get('description','')} | keywords={kw}")
                            existing_skill_text = "\n".join(existing_skill_lines) or "(なし)"
                            skill_gen_prompt = f"""コードエージェントのタスク失敗を分析し、既存スキルで対応可能か、新規作成が必要かを厳密に判断してください。

【失敗したタスク】{todo['title']}
【エラー履歴】{all_errors[:400]}
【既存スキル候補】
{existing_skill_text}

ルール:
- 既存スキルと機能が近い場合は新規作成せず update を選ぶ
- 共通化できる場合も update を選び、target に既存スキル名を入れる
- 本当に新機能が必要な場合だけ create を選ぶ
- 不足がなければ decision=none
- JSON以外は返さない

【出力JSONのみ】
{{"decision":"none|create|update","target":"既存スキル名または空文字","merge_reason":"判断理由","skill":{{"name":"snake_case名","description":"説明","version":"1.0","os":["win32","linux"],"keywords":["kw"],"tool_code":"def name(project:str, arg:str)->str:\\n    return result","usage_example":"","rationale":"不足していた理由","source":"codeagent"}}}}"""
                            skill_reply, _ = call_llm_chat(
                                [{"role": "user", "content": skill_gen_prompt}],
                                llm_url=task_url
                            )
                            skill_parsed = extract_json(skill_reply, parser=_model_manager.current_parser)
                            decision = str((skill_parsed or {}).get("decision") or "").strip().lower()
                            new_skill = (skill_parsed or {}).get("skill")
                            target_skill = str((skill_parsed or {}).get("target") or "").strip()
                            merge_reason = str((skill_parsed or {}).get("merge_reason") or "").strip()
                            if decision in ("create", "update") and new_skill and new_skill.get("name") and new_skill.get("tool_code"):
                                if decision == "update" and target_skill:
                                    new_skill["name"] = target_skill
                                save_result = _upsert_skill(new_skill, merge_reason=merge_reason or "auto skill refinement", prefer_merge=True)
                                action_label = "更新" if save_result.get("action") == "updated" else "生成"
                                skill_context_note = f"\n\n【自動生成スキル】'{save_result.get('skill_name', new_skill['name'])}' スキルを{action_label}しました。このスキルを活用してタスクを実行してください。"
                                write("skill_generated", {
                                    "skill_name": save_result.get("skill_name", new_skill["name"]),
                                    "action": save_result.get("action", decision),
                                    "version": save_result.get("version", ""),
                                    "matched_skill": save_result.get("matched_skill", ""),
                                    "description": new_skill.get("description", ""),
                                    "rationale": merge_reason or new_skill.get("rationale", ""),
                                    "task_id": todo["id"],
                                })
                                print(f"[JOB {job_id}] auto-skill {save_result.get('action','created')}: {save_result.get('skill_name', new_skill['name'])}")
                        except Exception as _sge:
                            print(f"[JOB {job_id}] skill auto-generation failed: {_sge}")

                    # 選択案で再実行
                    if chosen:
                        chosen_title = chosen.get("title", "選択案")
                        ctx3 = (f"{context}\n\n【選択された対応案】{chosen_title}\n"
                                f"{chosen.get('description','')}\n\n"
                                f"【実行指示】{chosen.get('detail', todo['detail'])}"
                                f"{skill_context_note}")
                        task_steps, task_status, task_output = _run_stage(f"[{chosen_title}] ", ctx3, req.max_steps)
                    else:
                        task_status = "done"
                        task_output = f"[skipped by timeout] {todo['title']}"

                # Stage 5: コーダー段階的昇格（失敗時 / 品質基準未達）
                if feature_mode == "model_orchestration" and orchestration_policy != "off" and not req.llm_url.strip():
                    needs_quality_retry = (
                        orchestration_policy == "ladder_fail_and_quality"
                        and quality_check_enabled
                        and task_status == "done"
                        and (not _is_quality_output_ok(task_output))
                    )
                    needs_fail_retry = (task_status in ("error", "pending"))
                    if needs_fail_retry or needs_quality_retry:
                        current_key = _model_manager.current_key
                        tried_keys = {current_key}
                        for lvl, next_key in enumerate(coder_ladder, start=1):
                            if not next_key or next_key in tried_keys:
                                continue
                            tried_keys.add(next_key)
                            spec = get_model_spec(next_key)
                            if not spec.get("path"):
                                continue
                            write("model_switching", {
                                "from": _model_manager.current_key,
                                "to": next_key,
                                "model_name": spec.get("name", next_key),
                                "eta_sec": spec.get("load_sec", 30),
                                "message": f"Coder昇格 L{lvl}: {spec.get('name', next_key)}",
                            })
                            switched = _model_manager.ensure_model(
                                next_key,
                                on_event=lambda ev: write(ev.get("type", "model_event"), ev)
                            )
                            if not switched:
                                continue
                            task_url = _model_manager.llm_url
                            reason = "失敗リカバリ" if needs_fail_retry else "品質改善"
                            qctx = (
                                f"{context}\n\n【昇格実行】{reason}\n"
                                f"タスク出力を完成形に改善してください。\n"
                                f"- 省略/TODO/placeholderは禁止\n"
                                f"- 実行可能な具体コード・修正内容にすること\n"
                                f"- 既存ファイルとの整合性を保つこと\n"
                            )
                            task_steps, task_status, task_output = _run_stage(f"[Coder昇格L{lvl}] ", qctx, req.max_steps)
                            if task_status == "done" and (not quality_check_enabled or _is_quality_output_ok(task_output)):
                                break
                            needs_fail_retry = (task_status in ("error", "pending"))
                            needs_quality_retry = (
                                orchestration_policy == "ladder_fail_and_quality"
                                and quality_check_enabled
                                and task_status == "done"
                                and (not _is_quality_output_ok(task_output))
                            )
                            if not (needs_fail_retry or needs_quality_retry):
                                break

                print(f"[JOB {job_id}] task {i+1}/{total} '{todo['title'][:30]}' -> {task_status}")
                final_status = task_status if task_status == "done" else "error"
                results.append({"task_id": todo["id"], "title": todo["title"],
                                 "status": final_status, "output": task_output, "steps": task_steps})
                if final_status == "done":
                    post_snapshot = auto_snapshot_ca_data("post-task snapshot", job_id, todo.get("id", i + 1))
                    write("snapshot", {
                        "stage": "post-task snapshot",
                        "task_id": todo.get("id", i + 1),
                        "ok": bool(post_snapshot.get("ok")),
                        "skipped": bool(post_snapshot.get("skipped")),
                        "reason": post_snapshot.get("reason", ""),
                        "commit_hash": post_snapshot.get("commit_hash", ""),
                        "error": post_snapshot.get("error", ""),
                    })
                    try:
                        files_raw = list_files(subdir=project)
                        files_str = files_raw if files_raw != "(empty)" else "  (なし)"
                    except Exception:
                        files_str = "  (取得失敗)"
                    # context肥大化防止: task_output と files_str を制限
                    _out = (task_output or '完了')[:500]
                    _files = "\n".join(files_str.splitlines()[:30])
                    context = (
                        f"前のタスク「{todo['title']}」が完了しました。\n"
                        f"タスク結果: {_out}\n"
                        f"現在のプロジェクトファイル:\n{_files}\n"
                        f"次のタスクでこれらのファイルを参照してください。"
                    )
                    write("progress", {"pct": int((i+1)/total*100), "label": f"{i+1}/{total} done"})
                else:
                    rollback_result = {"ok": False, "note": "pre snapshot missing"}
                    if pre_snapshot_hash:
                        rc_reset, _, err_reset = _git_run(["reset", "--hard", pre_snapshot_hash], CA_DATA_DIR)
                        if rc_reset == 0:
                            rc_clean, _, err_clean = _git_run(["clean", "-fd"], CA_DATA_DIR)
                            rollback_result = {
                                "ok": rc_clean == 0,
                                "note": "rolled back to pre-task snapshot",
                                "error": err_clean if rc_clean != 0 else ""
                            }
                        else:
                            rollback_result = {"ok": False, "note": "git reset failed", "error": err_reset}
                    write("snapshot_rollback", {
                        "stage": "pre-task snapshot",
                        "task_id": todo.get("id", i + 1),
                        "target_commit": pre_snapshot_hash,
                        "ok": bool(rollback_result.get("ok")),
                        "note": rollback_result.get("note", ""),
                        "error": rollback_result.get("error", ""),
                    })
                    context = (
                        f"前のタスク「{todo['title']}」が全試行後もエラーになりました。\n"
                        f"エラー内容: {task_output or '不明'}\n"
                        f"このエラーを踏まえて次のタスクを実行してください。"
                    )
                    write("progress", {"pct": int((i+1)/total*100), "label": f"task {i+1}/{total} failed (skill proposed)"})

              except Exception as _per_task_ex:
                # 1タスクで予期しない例外が発生しても残りのタスクを継続する
                _per_task_msg = f"[per-task exception] {str(_per_task_ex)[:300]}"
                print(f"[JOB {job_id}] task {i+1}/{total} per-task exception: {_per_task_msg}")
                try:
                    write("task_error", {
                        "task_id": todo.get("id", i+1),
                        "title": todo.get("title", ""),
                        "error": _per_task_msg,
                    })
                except Exception:
                    pass
                # resultsにまだ記録されていなければエラーとして追加
                if not any(r.get("task_id") == todo.get("id") for r in results):
                    results.append({
                        "task_id": todo.get("id", i+1),
                        "title": todo.get("title", ""),
                        "status": "error",
                        "output": _per_task_msg,
                        "steps": [],
                    })

            done_count = sum(1 for r in results if r["status"] == "done")

            verify_rework_results = []

            # 検証フェーズ（approved_tasksの場合でも実行）
            if done_count == total:
                requirements = plan_result.get("requirements", ["指示された内容が正しく動作すること"]) if plan_result else ["指示された内容が正しく動作すること"]
                verification = plan_result.get("verification", ["動作確認"]) if plan_result else ["動作確認"]
                # verify_startはverify_and_fix内部で発火するため、ここでは不要
                verify_url = _resolve_runtime_llm_url(req.llm_url)
                verify_result = verify_and_fix(
                    user_message=req.message,
                    requirements=requirements,
                    verification_items=verification,
                    project=project, max_fix_rounds=2,
                    llm_url=verify_url, search_enabled=effective_search_enabled,
                    on_event=lambda ev: write(ev.get("type","verify"), ev)
                )
                # 検証失敗時は、失敗内容をタスク化して再修正 → 再検証を1回実施
                if verify_result and not verify_result.get("passed", True):
                    failed_issues = [i for i in (verify_result.get("issues") or []) if i.get("severity") == "critical"][:3]
                    if failed_issues:
                        write("verify_rework_start", {
                            "count": len(failed_issues),
                            "message": "検証失敗を受けて、関連タスクへ戻って再修正を実施します。"
                        })
                    for idx, issue in enumerate(failed_issues, start=1):
                        phase = str(issue.get("phase") or "検証")
                        desc = str(issue.get("description") or "詳細不明")
                        task_title = f"[verify-rework {idx}] {phase}: {desc[:80]}"
                        write("task_start", {
                            "task_id": f"verify_rework_{idx}",
                            "title": task_title,
                            "task_index": total + idx,
                            "total": total + len(failed_issues),
                        })
                        rework_prompt = f"""検証フェーズで失敗したため、該当実装を修正してください。

【ユーザー要求】
{req.message}

【失敗フェーズ】
{phase}

【失敗内容】
{desc}

【修正方針】
- 失敗原因に対応する実装を修正する
- 必要なら関連ファイルも含めて修正する
- 修正後に run_file / run_python / run_shell で自己検証してから完了する
"""
                        rw_steps, rw_status, rw_output = execute_task(
                            task_detail=rework_prompt,
                            project=project,
                            max_steps=max(6, min(int(req.max_steps or 10), 12)),
                            llm_url=verify_url
                        )
                        verify_rework_results.append({
                            "task_id": f"verify_rework_{idx}",
                            "title": task_title,
                            "status": "done" if rw_status == "done" else "error",
                            "output": rw_output,
                            "steps": rw_steps,
                        })
                    if failed_issues:
                        verify_result = verify_and_fix(
                            user_message=req.message,
                            requirements=requirements,
                            verification_items=verification,
                            project=project, max_fix_rounds=2,
                            llm_url=verify_url, search_enabled=effective_search_enabled,
                            on_event=lambda ev: write(ev.get("type", "verify"), ev)
                        )
                if (orchestration_policy == "ladder_fail_and_quality"
                        and not req.llm_url.strip()
                        and verify_result
                        and not verify_result.get("passed", True)):
                    for next_key in coder_ladder:
                        if not next_key or next_key == _model_manager.current_key:
                            continue
                        spec = get_model_spec(next_key)
                        if not spec.get("path"):
                            continue
                        write("model_switching", {
                            "from": _model_manager.current_key,
                            "to": next_key,
                            "model_name": spec.get("name", next_key),
                            "eta_sec": spec.get("load_sec", 30),
                            "message": f"検証不合格のため高品質モデルへ昇格: {spec.get('name', next_key)}",
                        })
                        if not _model_manager.ensure_model(next_key, on_event=lambda ev: write(ev.get("type","model_event"), ev)):
                            continue
                        verify_result = verify_and_fix(
                            user_message=req.message,
                            requirements=requirements,
                            verification_items=verification,
                            project=project, max_fix_rounds=2,
                            llm_url=_model_manager.llm_url, search_enabled=effective_search_enabled,
                            on_event=lambda ev: write(ev.get("type","verify"), ev)
                        )
                        if verify_result.get("passed", False):
                            break
            else:
                verify_result = None

            print(f"[JOB {job_id}] completed: {done_count}/{total} tasks done")
            verify_passed = True if not verify_result else bool(verify_result.get("passed", True))
            final = {
                "summary": f"{total}タスク中{done_count}件完了" + ("" if verify_passed else "（検証で失敗あり）"),
                "success": (done_count == total) and verify_passed,
                "tasks": results,
                "verify": verify_result,
                "verify_rework": verify_rework_results,
            }
            final_snapshot = auto_snapshot_ca_data("job-final snapshot", job_id, None)
            write("snapshot", {
                "stage": "job-final snapshot",
                "task_id": None,
                "ok": bool(final_snapshot.get("ok")),
                "skipped": bool(final_snapshot.get("skipped")),
                "reason": final_snapshot.get("reason", ""),
                "commit_hash": final_snapshot.get("commit_hash", ""),
                "error": final_snapshot.get("error", ""),
            })
            write("done", final)
            save_session(job_id, project, req.message, "task", final)

            # ジョブログを分析してスキル提案（バックグラウンドで実行）
            logs = job_log_get(job_id)
            has_issues = (
                any(e.get("type") == "skill_hint" for e in logs) or
                any(e.get("type") == "task_error" for e in logs) or
                done_count < total
            )
            if has_issues:
                try:
                    analysis = analyze_job_for_skills(job_id, project)
                    if analysis.get("proposals"):
                        write("skill_proposals", {
                            "proposals": analysis["proposals"],
                            "stats": analysis.get("stats", {}),
                            "auto": True,
                        })
                        print(f"[SKILLS] {len(analysis['proposals'])} proposals for job {job_id}")
                except Exception as e:
                    print(f"[SKILLS] auto-analyze error: {e}")

            # ジョブログからパーマネントメモリに知識を抽出（常時バックグラウンドで実行）
            _mem_llm_url = req.llm_url.strip() or LLM_URL
            import threading as _mem_thread
            def _memory_worker():
                result = _analyze_job_for_memory(job_id, project, _mem_llm_url)
                try:
                    if result and result.get("ok"):
                        saved = int(result.get("saved", 0) or 0)
                        reason = result.get("reason", "completed")
                        message = f"メモリ抽出が完了しました ({saved}件保存)" if saved > 0 else f"メモリ抽出が完了しました (保存なし: {reason})"
                        write("memory_done", {"job_id": job_id, "saved": saved, "reason": reason, "message": message})
                    else:
                        write("memory_done", {
                            "job_id": job_id,
                            "saved": 0,
                            "reason": (result or {}).get("reason", "unknown_error"),
                            "message": f"メモリ抽出でエラー: {(result or {}).get('reason', 'unknown_error')}",
                            "error": True
                        })
                except Exception:
                    pass
            _mem_thread.Thread(
                target=_memory_worker,
                daemon=True
            ).start()
            write("memory_analyzing", {"job_id": job_id, "message": "実行ログからメモリを抽出中..."})

        job_update_status(project, job_id, "done")

        # ジョブ完了後にチャット用ロールのモデルに戻す（次のジョブのため）
        chat_key = choose_model_for_role("chat")
        if not req.llm_url.strip() and chat_key and _model_manager.current_key != chat_key:
            _model_manager.ensure_model(chat_key)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"[JOB {job_id}] EXCEPTION: {type(e).__name__}: {e}")
        print(f"[JOB {job_id}] traceback:\n{tb}")
        write("error", {"error": f"{type(e).__name__}: {e}"})
        job_update_status(project, job_id, "error")
    finally:
        _job_wait_events.pop(job_id, None)
        _job_wait_answers.pop(job_id, None)

class TaskStreamRequest(BaseModel):
    message: str
    max_steps: int = 20
    project: str = "default"
    approved_tasks: list = None
    search_enabled: bool | None = None
    llm_url: str = ""


class TaskPlanRequest(BaseModel):
    input: str
    project_path: str = ""
    project_name: str = ""
    planning_mode: str = "standard"
    requirement_mode: str = "ask_when_needed"
    execution_mode: str = "plan_only"
    use_nexus: bool = True


class RequirementAnswerItem(BaseModel):
    question_id: str
    answer: str | list[str] | bool | None = None


class RequirementAnswerRequest(BaseModel):
    requirement_id: str
    answers: list[RequirementAnswerItem] = []
    skip_with_defaults: bool = False


class TaskContinueRequest(BaseModel):
    requirement_id: str
    planning_mode: str = "standard"
    requirement_mode: str = "ask_when_needed"
    execution_mode: str = "plan_only"
    use_nexus: bool = True
    project_path: str = ""
    project_name: str = ""

# =========================
# タスク分解プロンプト
# =========================

PLANNER_PROMPT = """あなたはソフトウェアアーキテクト兼タスク設計AIです。

ユーザーの指示を分析し、要件定義・実装方針・タスクリストを返してください。

【出力形式（JSONのみ・説明・前置き禁止）】
{
  "summary": "全体で何を達成するか（1〜2文）",
  "requirements": [
    "機能要件1: 具体的に何ができるか",
    "機能要件2: ...",
    "非機能要件: パフォーマンス・エラー処理・UX等"
  ],
  "approach": "実装方針（技術選択・アーキテクチャ・注意点を2〜4文で）",
  "verification": [
    "検証項目1: 何をもって完了とするか",
    "検証項目2: ..."
  ],
  "tasks": [
    {"id": 1, "title": "タスク名", "detail": "具体的な実装内容"},
    {"id": 2, "title": "...", "detail": "..."}
  ]
}

【ルール】
- requirementsは必ず3件以上（機能要件＋非機能要件）
- approachは技術的な根拠を含める
- verificationは実行可能なテスト・確認方法を書く
- tasksの最後は必ず「動作確認・検証」タスクを含める
- tasksは最大10件まで
- 単純な指示でも要件・方針・検証は省略しない

【単体テスト要否の判断基準】
単体テストタスク（"テストコード作成"等）は以下の場合のみ追加すること：
✅ 追加すべき場合:
  - Pythonプロジェクトで純粋な関数・クラス（ユーティリティ・ライブラリ・ロジック層）を実装する場合
  - 計算・変換・バリデーション等の入出力が明確な関数が複数含まれる場合
  - バグ修正・リファクタリングで既存ロジックの動作保証が必要な場合
❌ 追加不要な場合:
  - HTML/CSS/JavaScriptのみのフロントエンドプロジェクト（UIは目視確認・Playwrightで代替）
  - シンプルなスクリプト・1回限りの自動化タスク（テストより動作確認が適切）
  - Flask/FastAPI等のWebアプリ（結合テスト・ブラウザ確認が主体、単体は任意）
  - 設定ファイル変更・ドキュメント作成のみのタスク
  - データサイエンス・ML（学習スクリプト等は単体テストより出力検証が適切）"""

# Channel-style outputでも確実にパースできるシンプル版
PLANNER_PROMPT_SIMPLE = """あなたはタスク分解AIです。

ユーザーの指示を実行可能な小タスクのリストに分解してください。

【出力形式（JSONのみ）】
{"summary":"全体の目標（1文）","requirements":["要件1","要件2","非機能要件"],"approach":"実装方針（2文）","verification":["検証項目1","検証項目2"],"tasks":[{"id":1,"title":"タスク名","detail":"具体的な実装内容"},{"id":2,"title":"...","detail":"..."}]}

【ルール】
- 最初の文字は { であること
- tasksは3〜10件
- 最後のtaskは必ず動作確認
- JSONのみ出力・説明不要"""

# =========================
# プランナー
# =========================

def plan(user_message: str, project: str = "default") -> dict:
    """
    要件定義・実装方針・タスクリストを返す。
    プランナーは role=plan に割り当てられたモデルを使用。
    戻り値: {summary, requirements, approach, verification, tasks}
    """
    planner_key = choose_model_for_role("plan", include_disabled=True) or _model_manager.current_key
    if planner_key and _model_manager.current_key != planner_key:
        _model_manager.ensure_model(planner_key)
    parser = get_model_spec(planner_key).get("parser", "json")
    prompt = PLANNER_PROMPT  # 常に5フィールド完全版
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_message}
    ]
    # thinkingモデル対応: response_format強制なし
    reply, _usage = call_llm_chat(messages, llm_url=LLM_URL_PLANNER, max_output_tokens=16384)
    parsed = extract_json(reply, parser=parser)
    print(f"[PLAN] planner={planner_key or 'unknown'} parser={parser} parsed={'OK' if parsed and 'tasks' in parsed else 'FAIL'}")
    if parsed is None or 'tasks' not in parsed:
        print(f"[PLAN] fallback to single task. reply[:300]={reply[:300]}")

    if parsed is None or "tasks" not in parsed:
        return {
            "summary": user_message[:80],
            "requirements": ["指示された内容を実行する"],
            "approach": "ユーザーの指示をそのまま実行します。",
            "verification": ["実行完了を確認する"],
            "tasks": [{"id": 1, "title": "実行", "detail": user_message}]
        }

    # tasksが配列でない場合の補完
    if not isinstance(parsed.get("tasks"), list):
        parsed["tasks"] = [{"id": 1, "title": "実行", "detail": user_message}]

    return parsed

# =========================
# 単一タスク実行（共通ループ）
# =========================

def execute_task(task_detail: str, context: str = "", max_steps: int = 15, project: str = "default", on_step=None, search_enabled: bool = True, llm_url: str = "", chat_history: list = [], job_id: str = "") -> dict:
    """
    1タスクをエージェントループで実行する。
    context = 前のタスクの結果サマリー（引き継ぎ情報）
    on_step = ステップごとに呼ばれるコールバック(step_dict)
    job_id  = clarify待機に使うジョブID（空なら非対話モード）
    """
    project_dir = os.path.join(WORK_DIR, project)
    os.makedirs(project_dir, exist_ok=True)
    past_work = get_project_context(project)
    # ツールのパスはプロジェクトフォルダ内の相対パスで指定（例: "index.html", "src/app.py"）
    # プロジェクトフォルダ: workspace/{project}/
    project_note = f"\n\n【作業フォルダ】workspace/{project}/ - ファイルパスはこのフォルダ内の相対パスで指定してください。"
    base_prompt = _build_system_prompt(project) + project_note
    project_prompt = base_prompt + (f"\n\n{past_work}" if past_work else "")
    user_content = task_detail
    if context:
        user_content = f"【前のタスクの結果】\n{context}\n\n【今のタスク】\n{task_detail}"

    # パーマネントメモリ参照: 通常実行ループでも関連知識を注入する
    try:
        mem_query = task_detail
        mem_hits = memory_search(mem_query, limit=3)
        if mem_hits:
            mem_note = "\n\n【過去の経験・知識（メモリ）】\n" + "\n".join(
                f"- [{h['category']}] {h['title']}: {h['content'][:200]}"
                for h in mem_hits
            )
            user_content = user_content + mem_note
    except Exception:
        pass

    if _should_prefetch_web_for_task(task_detail, search_enabled):
        prefetch_result = _run_lightweight_prefetch_nexus_search_for_context(
            task_detail,
            num_results=_search_num_results,
            mode="quick",
            depth="quick",
            max_queries=1,
        )
        prefetch_block = _build_task_prefetch_context_block(prefetch_result, max_items=_search_num_results)
        if prefetch_block:
            user_content = f"{user_content}\n\n{prefetch_block}"
        if on_step:
            event_payload = prefetch_result.get("event_payload") or {}
            on_step({
                "type": "lightweight_search_prefetch",
                "query": prefetch_result.get("query", ""),
                "ok": bool(prefetch_result.get("ok", False)),
                "items": prefetch_result.get("items", []),
                "provider_errors": event_payload.get("provider_errors", {}),
                "non_fatal": bool(event_payload.get("non_fatal", False)),
                "message": event_payload.get("message") or prefetch_result.get("message", ""),
            })

    # Chat形式: 過去の会話履歴を先に並べる
    history_msgs = []
    for h in chat_history[-8:]:  # 直近8件まで
        role = h.get("role", "user")
        text = str(h.get("text", ""))[:800]  # 長すぎる履歴は切る
        if role in ("user", "assistant") and text:
            history_msgs.append({"role": role, "content": text})

    messages = [
        {"role": "system", "content": project_prompt},
        *history_msgs,
        {"role": "user", "content": user_content}
    ]

    # search_enabledに応じてツールセットを動的構築
    # スキルをTOOLSに動的追加（SKILL.mdのtool_codeを実行可能関数として登録）
    active_tools = dict(TOOLS)
    if k_skill := globals().get("_load_skill_functions"):
        for sname, sfn in k_skill().items():
            active_tools.setdefault(sname, sfn)  # 既存ツールは上書きしない
    if not search_enabled:
        # search_enabled=false の場合は nexus_web_search ツールを公開しない。
        active_tools.pop("nexus_web_search", None)
    # project引数を持つツールに現在のprojectを自動バインド
    _project_tools = ("read_file", "write_file", "edit_file", "get_outline",
                       "patch_function", "list_files", "search_in_files",
                       "make_dir", "move_path", "delete_path",
                       "run_shell", "run_python", "run_file", "run_server", "setup_venv",
                       "run_browser", "run_npm", "run_node")
    for _pt in _project_tools:
        if _pt in active_tools:
            _fn = active_tools[_pt]
            import functools as _ft
            active_tools[_pt] = _ft.partial(_fn, project=project)

    steps = []
    consecutive_errors = 0
    repeated_failures: dict[str, int] = {}

    for step in range(max_steps):
        # コンテキスト長チェック: 上限の80%を超えたら古いmessagesをtrim
        messages = _trim_messages(messages, _current_n_ctx, reserve_output=_calc_reserve_output(_current_n_ctx, ratio=0.30))
        # LLM生成前に「考え中」イベントを通知（UIのWorking表示を更新するため）
        if on_step:
            on_step({"type": "llm_thinking", "step_num": step + 1, "max_steps": max_steps})
        reply, _step_usage = call_llm_chat(messages, llm_url=llm_url)
        action_obj, reply, retry_usage = _parse_task_v2_action_with_retry(
            reply=reply,
            messages=messages,
            llm_url=llm_url,
            parser=_model_manager.current_parser,
            max_retry=1,
        )
        if retry_usage.get("prompt_tokens"):
            _step_usage = retry_usage

        if action_obj is None:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                return {"status": "error", "error": "JSON出力失敗", "steps": steps}
            # 特殊トークン (<|channel|> 等) を除去してからメッセージ履歴に追加
            # 除去しないと次回のLLM呼び出し時にllama.cppがチャットテンプレート適用に失敗する
            messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)})
            messages.append({
                "role": "user",
                "content": "エラー: JSON形式で出力してください。説明不要。{\"thought\":\"...\",\"action\":\"...\",\"args\":{...}} の形式のみ。"
            })
            steps.append({"step": step, "type": "json_retry", "raw": reply})
            continue
        else:
            consecutive_errors = 0

        action = str(action_obj.get("action", "") or "").strip().lower()
        action, action_note = _normalize_action_name(action)
        thought = action_obj.get("thought", "")
        tool_input = action_obj.get("args", {})
        if action_note:
            thought = f"{thought} ({action_note})".strip()
        if action in {"stop", "done", "finish", "complete", "end"}:
            action = "final"
            action_obj["action"] = "final"
            if not action_obj.get("output"):
                action_obj["output"] = thought or "Agent requested stop."

        # ── clarify: ユーザーに選択肢を提示して確認 ──
        if action == "clarify":
            question = tool_input.get("question", "確認が必要です")
            options = tool_input.get("options", [])
            steps.append({"step": step, "type": "clarify",
                           "thought": thought, "question": question, "options": options})
            if on_step:
                on_step({"step": step, "type": "clarify", "action": "clarify",
                          "thought": thought, "question": question, "options": options})

            if job_id and job_id in _job_wait_events:
                # バックグラウンドジョブ: Eventで待機
                _job_wait_events[job_id].wait(timeout=300)  # 最大5分待つ
                _job_wait_events[job_id].clear()
                answer = _job_wait_answers.pop(job_id, "（ユーザーは回答しませんでした）")
            elif not job_id:
                # 非対話モード: デフォルトで最初の選択肢を使用
                answer = options[0] if options else "（選択なし）"
            else:
                answer = "（回答待機タイムアウト）"

            messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)})
            messages.append({"role": "user", "content": f"ユーザーの選択: {answer}"})
            continue

        if action == "final":
            steps.append({"step": step, "type": "final", "thought": thought})
            return {
                "status": "done",
                "output": action_obj.get("output", ""),
                "steps": steps,
                "total_steps": step + 1
            }

        if action not in active_tools:
            messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)})
            messages.append({"role": "user", "content": f"ERROR: 不明なツール '{action}' — 使えるのは {list(active_tools.keys())} のみ"})
            steps.append({"step": step, "type": "unknown_tool", "action": action})
            continue

        safe_input, prep_error, prep_notes = _prepare_tool_call(active_tools, action, tool_input)
        if prep_error:
            result = prep_error
            if prep_notes:
                result += "\n" + " / ".join(prep_notes)
        else:
            call_key = f"{action}:{json.dumps(safe_input, ensure_ascii=False, sort_keys=True)}"
            if repeated_failures.get(call_key, 0) >= 2:
                result = ("ERROR: 同一の失敗ツール呼び出しを繰り返しています。"
                          " 直前のエラー内容を確認し、引数または手順を変更してください。")
            else:
                try:
                    result = active_tools[action](**safe_input)
                except TypeError as e:
                    result = f"ERROR: 引数が間違っています - {e}"

        step_info = {
            "step": step,
            "type": "tool_call",
            "action": action,
            "thought": thought,
            "input": safe_input if safe_input is not None else tool_input,
            "result_preview": str(result)[:200]
        }
        steps.append(step_info)
        if on_step:
            on_step(step_info)

        messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)})
        result_str = str(result)
        if action in ("write_file", "patch_function"):
            result_str = result_str[:400]
        elif action == "read_file":
            current_tokens = _estimate_tokens(messages)
            reserve_output = _calc_reserve_output(_current_n_ctx, ratio=0.30)
            remaining = _current_n_ctx - current_tokens - reserve_output
            read_file_cap = _get_read_file_inject_max_chars()
            max_read_chars = max(4000, min(remaining * 4, read_file_cap))
            if len(result_str) > max_read_chars:
                half = max_read_chars // 2
                result_str = (result_str[:half]
                    + f"\n\n[... {len(result_str) - max_read_chars} chars omitted ...]\n\n"
                    + result_str[-half:])
        else:
            max_result_chars = min(8000, max(2000, _current_n_ctx // 8))
            if len(result_str) > max_result_chars:
                result_str = result_str[:max_result_chars] + f"\n[... {len(result_str)-max_result_chars} chars truncated]"
        if str(result).strip().startswith("ERROR:") and safe_input is not None:
            call_key = f"{action}:{json.dumps(safe_input, ensure_ascii=False, sort_keys=True)}"
            repeated_failures[call_key] = repeated_failures.get(call_key, 0) + 1
            result_str += "\n\n注意: 同一引数での再実行は避け、エラー文を反映して次のアクションを変更すること。"
        elif safe_input is not None:
            call_key = f"{action}:{json.dumps(safe_input, ensure_ascii=False, sort_keys=True)}"
            repeated_failures.pop(call_key, None)
        messages.append({"role": "user", "content": f"実行結果:\n{result_str}"})

    return {"status": "error", "error": f"ステップ上限 ({max_steps}) に達しました", "steps": steps}

# =========================
# 検証エージェント（実装後の自動テスト・修正ループ）
# =========================

# =========================
# V字モデル検証エンジン（コード実行ベース）
# =========================

def _run_code_in_sandbox(code: str, project: str) -> tuple[bool, str]:
    """
    コードをDockerサンドボックスで実行して (成功, 出力) を返す。
    """
    result = run_python(code, project=project)
    ok = not (result.startswith("ERROR") or "Traceback" in result or "Error:" in result)
    return ok, result

def _generate_test_file(
    source_path: str, source_code: str, project: str
) -> tuple[str, str]:
    """
    LLMにテストコードを生成させる（1回だけ）。
    生成後はLLMを使わずコード実行で検証する。
    """
    prompt = f"""以下のPythonコードに対するunittestテストコードを生成してください。

【ファイル】{source_path}
【コード】
{source_code[:3000]}

【要件】
- import unittest を使う
- 各関数/クラスに対して正常系・異常系・境界値のテストを書く
- テストを実行したとき出力が "OK" で終わること
- モジュールのimportは sys.path を使って解決すること:
  import sys; sys.path.insert(0, f'/app/{project}')
- テストコード以外のテキストを含めないこと

テストコードのみ出力してください（```不要）:"""

    msgs = [{"role": "user", "content": prompt}]
    reply, _ = call_llm_chat(msgs)
    # コードブロックを除去
    import re as _re
    code = _re.sub(r'```(?:python)?\n?', '', reply).strip()
    test_path = source_path.replace('.py', '_test.py').replace('/', '_').lstrip('_')
    return test_path, code

def verify_and_fix(
    user_message: str,
    requirements: list,
    verification_items: list,
    project: str = "default",
    max_fix_rounds: int = 2,
    llm_url: str = "",
    search_enabled: bool = False,
    on_event=None
) -> dict:
    """
    V字モデルに基づく確定的検証フロー:
      Phase 1: 単体テスト（テストコード生成 → サンドボックス実行 → 失敗なら修正）
      Phase 2: 結合テスト（エンドツーエンド実行 → 失敗なら修正）
      Phase 3: 要件充足確認（各要件を実行で確認）
    LLMはテスト生成と修正指示にのみ使用。判定はコード実行結果で行う。
    """
    def emit(data: dict):
        if on_event:
            on_event(data)

    # 修正リトライ回数は呼び出し側の意図（max_fix_rounds）を優先。
    # 以前は最低6回に強制され、失敗時に長時間ループしやすかったため上限クランプのみ行う。
    fix_round_limit = max(1, min(int(max_fix_rounds or 1), 6))

    working_requirements = list(requirements or [])

    def _req_text() -> str:
        return "\n".join(f"- {r}" for r in working_requirements) if working_requirements else "（要件なし）"

    def _extract_failure_reason(raw: str, limit: int = 280) -> str:
        text = str(raw or "").strip()
        if not text:
            return "テスト出力が空のため原因不明"
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if any(k in s for k in ("AssertionError", "Traceback", "Error", "FAIL", "Exception")):
                return s[:limit]
        return text[:limit]

    def _append_failure_requirements(phase: str, reasons: list[str], related_tasks: list[str]):
        for idx, reason in enumerate(reasons, start=1):
            task_label = related_tasks[idx - 1] if idx - 1 < len(related_tasks) else "関連タスク"
            req = f"[{phase}失敗是正] {task_label}: {reason}"
            if req not in working_requirements:
                working_requirements.append(req)

    req_text = _req_text()
    verify_text = "\n".join(f"- {v}" for v in verification_items) if verification_items else "（検証項目なし）"
    all_issues = []
    phase_results = {}

    # プロジェクト内ファイルを収集
    project_path = os.path.join(WORK_DIR, project)
    py_files, html_files, other_files = [], [], []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if f.startswith('_'): continue
            rel = os.path.relpath(os.path.join(root, f), project_path)
            if f.endswith('.py') and not f.endswith('_test.py'):
                py_files.append(rel)
            elif f.endswith(('.html', '.htm')):
                html_files.append(rel)
            elif f.endswith(('.js', '.ts', '.css', '.json')):
                other_files.append(rel)
    is_html_project = bool(html_files) and not py_files

    emit({"type": "verify_start", "phase": "Phase 1: 単体テスト", "round": 0})

    # ── Phase 1: 単体テスト ──
    unit_results = []
    if is_html_project:
        emit({"type": "verify_phase", "phase": "単体テスト",
              "attempt": 0, "total": 0, "failed": 0,
              "summary": "HTMLプロジェクトのため単体テストをスキップ"})
    for py_file in ([] if is_html_project else py_files[:6]):
        full_path = os.path.join(project_path, py_file)
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()
        except Exception:
            continue

        if len(source.strip()) < 20:
            continue

        emit({"type": "verify_phase", "phase": "単体テスト",
              "attempt": 0, "total": 0, "failed": 0,
              "summary": f"Generating test for {py_file}"})

        # テストコード生成（LLM 1回のみ）
        test_name, test_code = _generate_test_file(py_file, source, project)
        if not test_code.strip():
            continue

        # テストファイルをworkspaceに書き込んでサンドボックス実行
        write_file(test_name, test_code, project=project)
        ok, output = _run_code_in_sandbox(
            f"import subprocess, sys\n"
            f"r = subprocess.run([sys.executable, '-m', 'unittest', '/app/{project}/{test_name}', '-v'], "
            f"capture_output=True, text=True, cwd='/app/{project}')\n"
            f"print(r.stdout + r.stderr)\n"
            f"sys.exit(r.returncode)",
            project
        )
        unit_results.append({
            "file": py_file, "test_file": test_name,
            "status": "pass" if ok else "fail",
            "output": output[:500]
        })

        emit({"type": "verify_phase", "phase": "単体テスト",
              "attempt": 0, "total": 1,
              "failed": 0 if ok else 1,
              "summary": f"{py_file}: {'PASS' if ok else 'FAIL'}"})

        # 失敗した場合は修正ループ
        if not ok:
            for fix_round in range(fix_round_limit):
                failure_reason = _extract_failure_reason(output)
                _append_failure_requirements("単体テスト", [failure_reason], [py_file])
                req_text = _req_text()
                # LLMに失敗原因を分析させてpatch
                fix_prompt = f"""以下のファイルがテストで失敗しました。コードを修正してください。

【ファイル】{py_file}
【現時点の要求（失敗理由を反映済み）】
{req_text}

【現在のコード】
{source[:2000]}

【テスト出力（失敗）】
{output[:1000]}

【失敗理由（要求へ追加済み）】
{failure_reason}

失敗理由に関連するタスク全体を見直し、要求を満たすまで再実施してください。
修正が必要な箇所をpatch_functionで修正してください。修正後finalで「fixed」と返してください。"""
                fix_result = execute_task(
                    task_detail=fix_prompt, project=project,
                    max_steps=10, llm_url=llm_url
                )
                # 修正後のソースを再読み込みして再テスト
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        source = f.read()
                except Exception:
                    break
                ok, output = _run_code_in_sandbox(
                    f"import subprocess, sys\n"
                    f"r = subprocess.run([sys.executable, '-m', 'unittest', '/app/{project}/{test_name}', '-v'], "
                    f"capture_output=True, text=True, cwd='/app/{project}')\n"
                    f"print(r.stdout + r.stderr)\n"
                    f"sys.exit(r.returncode)",
                    project
                )
                unit_results[-1]["status"] = "pass" if ok else "fail"
                unit_results[-1]["output"] = output[:500]
                if ok:
                    break

    unit_failed = [r for r in unit_results if r["status"] == "fail"]
    phase_results["unit"] = {"results": unit_results}
    all_issues += [{"severity": "critical", "phase": "単体テスト",
                    "description": f"{r['file']}: テスト失敗", "fix": ""} for r in unit_failed]

    emit({"type": "verify_phase", "phase": "単体テスト",
          "attempt": 0,
          "total": len(unit_results),
          "failed": len(unit_failed),
          "summary": f"{len(unit_results)-len(unit_failed)}/{len(unit_results)} pass"})

    # ── Phase 2: 結合テスト ──
    emit({"type": "verify_start", "phase": "Phase 2: 結合テスト", "round": 0})

    # メインの実行可能ファイルを特定して実行
    main_candidates = [f for f in py_files if any(
        n in f.lower() for n in ['main', 'app', 'run', 'server', 'demo']
    )]
    integ_results = []

    # 各要件に対応する結合テストコードをLLMに生成させて実行
    if is_html_project:
        integ_gen_prompt = f"""以下のHTML/CSSプロジェクトの検証スクリプトをPythonで生成してください。

【ユーザーの要求】
{user_message}

【検証項目】
{verify_text}

【HTMLファイル】
{', '.join(html_files[:5])}
【その他ファイル】
{', '.join(other_files[:5])}

【要件】
- import os, sys; project_dir = '/app/{project}' でファイルパスを構築する
- os.path.exists でファイル存在確認
- open(path).read() でHTMLを読んで文字列検索（from html.parser import HTMLParser も利用可）
- 各シナリオで print("SCENARIO: シナリオ名 - PASS") または print("SCENARIO: シナリオ名 - FAIL")
- サーバー起動・ブラウザ接続は行わない（ファイルベースの検証のみ）
- テストコード以外を含めないこと

テストコードのみ出力してください（```不要）:"""
    else:
        integ_gen_prompt = f"""以下の要件に対する結合テストコードを生成してください。

【ユーザーの要求】
{user_message}

【検証項目】
{verify_text}

【対象ファイル】
{', '.join(py_files[:5])}

【要件】
- import sys; sys.path.insert(0, '/app/{project}') を必ず含める
- 各シナリオを実行し、成功/失敗を出力する
- print("SCENARIO: シナリオ名 - PASS") または print("SCENARIO: シナリオ名 - FAIL") の形式で出力
- 例外は全てキャッチして FAIL として記録する
- テストコード以外を含めないこと

テストコードのみ出力してください（```不要）:"""

    msgs = [{"role": "user", "content": integ_gen_prompt}]
    integ_reply, _ = call_llm_chat(msgs)
    import re as _re2
    integ_code = _re2.sub(r'```(?:python)?\n?', '', integ_reply).strip()

    if integ_code:
        write_file("_integration_test.py", integ_code, project=project)
        ok, output = _run_code_in_sandbox(
            f"import subprocess, sys\n"
            f"r = subprocess.run([sys.executable, '/app/{project}/_integration_test.py'], "
            f"capture_output=True, text=True)\n"
            f"print(r.stdout + r.stderr)",
            project
        )
        # SCENARIO行を解析
        import re as _re3
        for m in _re3.finditer(r'SCENARIO:\s*(.+?)\s*-\s*(PASS|FAIL)', output):
            integ_results.append({
                "name": m.group(1).strip(),
                "status": "pass" if m.group(2) == "PASS" else "fail",
                "output": output[:300]
            })
        if not integ_results:
            # SCENARIO行がない場合は実行成否で判断
            integ_results.append({
                "name": "overall",
                "status": "pass" if ok else "fail",
                "output": output[:300]
            })

        # 失敗シナリオがあれば修正
        failed_integ = [r for r in integ_results if r["status"] == "fail"]
        if failed_integ:
            for fix_round in range(fix_round_limit):
                failure_reasons = [f"{r.get('name','scenario')}: {_extract_failure_reason(r.get('output',''))}" for r in failed_integ]
                related_tasks = [str(r.get("name", "integration_scenario")) for r in failed_integ]
                _append_failure_requirements("結合テスト", failure_reasons, related_tasks)
                req_text = _req_text()
                fix_prompt = f"""結合テストで以下が失敗しました。実装コードを修正してください。

【現時点の要求（失敗理由を反映済み）】
{req_text}

【失敗シナリオ】
{json.dumps(failed_integ, ensure_ascii=False)}

【テスト出力】
{output[:800]}

【失敗理由（要求へ追加済み）】
{json.dumps(failure_reasons, ensure_ascii=False)}

失敗理由に関連するタスク全体を見直し、要求を満たすまで再実施してください。
原因を特定してpatch_functionで修正し、修正後にrun_pythonで再テストしてください。finalで「fixed」と返してください。"""
                fix_result = execute_task(
                    task_detail=fix_prompt, project=project,
                    max_steps=12, llm_url=llm_url
                )
                ok, output = _run_code_in_sandbox(
                    f"import subprocess, sys\n"
                    f"r = subprocess.run([sys.executable, '/app/{project}/_integration_test.py'], "
                    f"capture_output=True, text=True)\n"
                    f"print(r.stdout + r.stderr)",
                    project
                )
                for r in integ_results:
                    pat = r["name"] + r" - PASS"
                    if pat in output:
                        r["status"] = "pass"
                        r["output"] = output[:300]
                failed_integ = [r for r in integ_results if r["status"] == "fail"]
                if all(r["status"] == "pass" for r in integ_results):
                    break

    failed_integ = [r for r in integ_results if r["status"] == "fail"]
    phase_results["integration"] = {"results": integ_results}
    all_issues += [{"severity": "critical", "phase": "結合テスト",
                    "description": r["name"], "fix": ""} for r in failed_integ]

    emit({"type": "verify_phase", "phase": "結合テスト",
          "attempt": 0, "total": len(integ_results),
          "failed": len(failed_integ),
          "summary": f"{len(integ_results)-len(failed_integ)}/{len(integ_results)} pass"})

    # ── Phase 3: 要件充足確認 ──
    emit({"type": "verify_start", "phase": "Phase 3: 要件充足確認", "round": 0})
    req_results = []
    req_score = 100

    for req_item in working_requirements[:8]:
        # 各要件についてコードで確認するスクリプトを生成・実行
        if is_html_project:
            chk_prompt = f"""以下の要件をHTMLファイルを読み込んで確認するPythonスクリプトを生成してください。

【要件】{req_item}
【HTMLファイル】{', '.join(html_files[:4])}
【その他ファイル】{', '.join(other_files[:4])}

【ルール】
- import os; project_dir = '/app/{project}' でファイルパス構築
- os.path.exists / open().read() / html.parser でファイルを検証する
- サーバー起動・外部接続は行わない（ファイルベースの検証のみ）
- 要件が満たされていれば print("REQUIREMENT_MET") を出力する
- 満たされていなければ print("REQUIREMENT_MISSING: 理由") を出力する
- テストコードのみ出力（```不要）"""
        else:
            chk_prompt = f"""以下の要件を確認するPythonスクリプトを生成してください。

【要件】{req_item}
【対象ファイル】{', '.join(py_files[:4])}

【ルール】
- import sys; sys.path.insert(0, '/app/{project}') を必ず含める
- 要件が満たされていれば print("REQUIREMENT_MET") を出力する
- 満たされていなければ print("REQUIREMENT_MISSING: 理由") を出力する
- テストコードのみ出力（```不要）"""

        msgs = [{"role": "user", "content": chk_prompt}]
        chk_reply, _ = call_llm_chat(msgs)
        chk_code = _re2.sub(r'```(?:python)?\n?', '', chk_reply).strip()
        if not chk_code:
            continue
        ok, output = _run_code_in_sandbox(chk_code, project)
        met = "REQUIREMENT_MET" in output
        req_results.append({"req": req_item[:60], "status": "met" if met else "missing",
                             "evidence": output[:200]})

    missing = [r for r in req_results if r["status"] == "missing"]
    if req_results:
        req_score = int((len(req_results) - len(missing)) / len(req_results) * 100)

    phase_results["requirements"] = {"results": req_results, "score": req_score}
    all_issues += [{"severity": "critical", "phase": "要件",
                    "description": r["req"], "fix": "実装が必要"} for r in missing]

    emit({"type": "verify_phase", "phase": "要件充足確認",
          "attempt": 0, "score": req_score,
          "missing": [r["req"] for r in missing],
          "summary": f"{len(req_results)-len(missing)}/{len(req_results)} met"})

    # ── 総合判定 ──
    # テスト対象がない場合はそのフェーズを満点扱い（HTML/JSプロジェクト等でPyファイルなし）
    unit_pass_rate = (len(unit_results) - len(unit_failed)) / len(unit_results) if unit_results else 1.0
    integ_pass_rate = (len(integ_results) - len(failed_integ)) / len(integ_results) if integ_results else 1.0
    total_score = int(unit_pass_rate * 40 + integ_pass_rate * 30 + req_score * 0.3)
    total_score = min(100, max(0, total_score))
    critical_count = len([i for i in all_issues if i.get("severity") == "critical"])
    passed = total_score >= 75 and critical_count == 0

    summary_parts = [
        f"単体テスト {len(unit_results)-len(unit_failed)}/{max(len(unit_results),1)} pass",
        f"結合テスト {len(integ_results)-len(failed_integ)}/{max(len(integ_results),1)} pass",
        f"要件充足 {req_score}/100",
    ]
    final_verdict = {
        "passed": passed, "score": total_score,
        "issues": all_issues,
        "summary": " | ".join(summary_parts),
        "phases": phase_results,
    }
    emit({"type": "verify_done", "passed": passed, "score": total_score,
          "issues": all_issues, "summary": final_verdict["summary"]})
    return final_verdict



# =========================
# 音声入力（Whisper / CPUオンデマンド）
# =========================

try:
    from faster_whisper import WhisperModel  # type: ignore
except Exception:
    WhisperModel = None

_voice_lock = threading.Lock()
_voice_model = None
_voice_model_name = "large-v3-turbo"
_voice_device = "cpu"
_voice_compute_type = "int8"

def _detect_voice_runtime_device() -> tuple[str, str]:
    """
    ASRの既定デバイスを自動判定する。
    - CUDAが利用可能なら cuda/float16
    - それ以外は cpu/int8
    """
    force = (os.environ.get("CODEAGENT_ASR_DEVICE", "") or "").strip().lower()
    if force in {"cpu", "cuda"}:
        return (force, "int8" if force == "cpu" else "float16")
    if shutil.which("nvidia-smi"):
        return ("cuda", "float16")
    return ("cpu", "int8")

_voice_device, _voice_compute_type = _detect_voice_runtime_device()

_VOICE_MODEL_CANDIDATES = [
    {"name": "large-v3-turbo", "priority": "accuracy", "note": "高精度・多言語対応（ローカル推奨）"},
    {"name": "small", "priority": "accuracy_ja_then_speed_then_lightweight", "note": "多言語・日本語精度と速度のバランス"},
    {"name": "base", "priority": "speed", "note": "smallより軽量・高速"},
    {"name": "tiny", "priority": "lightweight", "note": "最軽量（精度は低下）"},
]

def _voice_model_dir() -> str:
    if IS_RUNPOD_RUNTIME:
        # RunPod: LLMモデル(/workspace/LLMs)と同階層の /workspace/ASRModels に保存
        root = "/workspace/ASRModels"
    else:
        # ローカル: プロジェクト直下の models/ASRModels に保存
        root = os.path.join(BASE_DIR, "models", "ASRModels")
    os.makedirs(root, exist_ok=True)
    return root


def _voice_model_exists(model_name: str) -> bool:
    """モデルがローカルキャッシュに存在するか確認する。"""
    model_dir = _voice_model_dir()
    # faster-whisper は huggingface_hub 形式でキャッシュする
    # 例: models--Systran--faster-whisper-large-v3-turbo
    cache_name = f"models--Systran--faster-whisper-{model_name}"
    snap_dir = os.path.join(model_dir, cache_name, "snapshots")
    if os.path.isdir(snap_dir) and os.listdir(snap_dir):
        return True
    # 直接ディレクトリ形式（古いキャッシュ形式）も確認
    direct_dir = os.path.join(model_dir, model_name)
    if os.path.isdir(direct_dir) and os.listdir(direct_dir):
        return True
    return False

def voice_load(model_name: str = "small", device: str | None = None) -> dict:
    """WhisperモデルをCPU/GPU(RAM)へオンデマンドロードする。"""
    global _voice_model, _voice_model_name, _voice_device, _voice_compute_type
    if WhisperModel is None:
        raise RuntimeError("faster-whisper is not installed. install: pip install faster-whisper")
    if device is not None and device in ("cpu", "cuda"):
        _voice_device = device
        _voice_compute_type = "int8" if device == "cpu" else "float16"
    with _voice_lock:
        if _voice_model is not None and _voice_model_name == model_name and (device is None or _voice_device == device):
            return {"loaded": True, "model": _voice_model_name, "device": _voice_device, "compute_type": _voice_compute_type}
        _voice_model = WhisperModel(
            model_name,
            device=_voice_device,
            compute_type=_voice_compute_type,
            download_root=_voice_model_dir(),
        )
        _voice_model_name = model_name
        return {"loaded": True, "model": _voice_model_name, "device": _voice_device, "compute_type": _voice_compute_type}

def voice_unload() -> dict:
    """WhisperモデルをアンロードしてRAMを解放する。"""
    global _voice_model
    with _voice_lock:
        _voice_model = None
    return {"loaded": False}

def voice_status() -> dict:
    with _voice_lock:
        return {
            "loaded": _voice_model is not None,
            "model": _voice_model_name if _voice_model is not None else "",
            "device": _voice_device,
            "compute_type": _voice_compute_type,
            "candidates": _VOICE_MODEL_CANDIDATES,
        }

_ASR_PROFILE_PRESETS = {
    "fast": {"beam_size": 1, "best_of": 1},
    "balanced": {"beam_size": 2, "best_of": 2},
    "accurate": {"beam_size": 5, "best_of": 5},
}

ASR_POST_FILTER_MIN_CHARS = max(1, int(os.environ.get("ASR_POST_FILTER_MIN_CHARS", "2") or 2))
ASR_POST_FILTER_NO_SPEECH_REJECT = min(0.99, max(0.0, float(os.environ.get("ASR_POST_FILTER_NO_SPEECH_REJECT", "0.72") or 0.72)))
ASR_POST_FILTER_LOW_LOGPROB_REJECT = float(os.environ.get("ASR_POST_FILTER_LOW_LOGPROB_REJECT", "-1.05") or -1.05)
ASR_POST_FILTER_SHORT_TEXT_MAX_CHARS = max(1, int(os.environ.get("ASR_POST_FILTER_SHORT_TEXT_MAX_CHARS", "4") or 4))
ASR_POST_FILTER_REPETITION_MIN_TOKENS = max(4, int(os.environ.get("ASR_POST_FILTER_REPETITION_MIN_TOKENS", "8") or 8))
ASR_POST_FILTER_REPETITION_TOKEN_RATE_REJECT = min(0.98, max(0.30, float(os.environ.get("ASR_POST_FILTER_REPETITION_TOKEN_RATE_REJECT", "0.62") or 0.62)))
ASR_POST_FILTER_REPETITION_NGRAM_N = max(2, min(6, int(os.environ.get("ASR_POST_FILTER_REPETITION_NGRAM_N", "3") or 3)))
ASR_POST_FILTER_REPETITION_NGRAM_REPEAT_REJECT = max(2, int(os.environ.get("ASR_POST_FILTER_REPETITION_NGRAM_REPEAT_REJECT", "4") or 4))
ASR_POST_FILTER_REPETITION_RETRY_BEAM_ADD = max(0, int(os.environ.get("ASR_POST_FILTER_RETRY_BEAM_ADD", "2") or 2))
ASR_POST_FILTER_REPETITION_RETRY_BEST_OF_ADD = max(0, int(os.environ.get("ASR_POST_FILTER_RETRY_BEST_OF_ADD", "2") or 2))


def _resolve_asr_profile(profile: str | None) -> str:
    p = str(profile or "balanced").strip().lower()
    return p if p in _ASR_PROFILE_PRESETS else "balanced"


def _build_asr_transcribe_kwargs(
    asr_profile: str = "balanced",
    beam_size: int | None = None,
    best_of: int | None = None,
    no_speech_threshold: float | None = None,
    log_prob_threshold: float | None = None,
    compression_ratio_threshold: float | None = None,
) -> dict:
    profile = _resolve_asr_profile(asr_profile)
    preset = _ASR_PROFILE_PRESETS[profile]
    kwargs = {
        "beam_size": max(1, int(beam_size if beam_size is not None else preset["beam_size"])),
        "best_of": max(1, int(best_of if best_of is not None else preset["best_of"])),
        "temperature": 0.0,
        "condition_on_previous_text": False,
        "vad_filter": True,
        "word_timestamps": False,
    }
    if no_speech_threshold is not None:
        kwargs["no_speech_threshold"] = float(no_speech_threshold)
    if log_prob_threshold is not None:
        kwargs["log_prob_threshold"] = float(log_prob_threshold)
    if compression_ratio_threshold is not None:
        kwargs["compression_ratio_threshold"] = float(compression_ratio_threshold)
    return kwargs


def _asr_metrics(segments) -> dict:
    """faster-whisperセグメントから軽量指標を作る。"""
    no_speech_probs = []
    avg_logprobs = []
    seg_count = 0
    for seg in segments:
        seg_count += 1
        nsp = getattr(seg, "no_speech_prob", None)
        alp = getattr(seg, "avg_logprob", None)
        if isinstance(nsp, (int, float)):
            no_speech_probs.append(float(nsp))
        if isinstance(alp, (int, float)):
            avg_logprobs.append(float(alp))
    return {
        "segment_count": seg_count,
        "mean_no_speech_prob": (sum(no_speech_probs) / len(no_speech_probs)) if no_speech_probs else None,
        "max_no_speech_prob": max(no_speech_probs) if no_speech_probs else None,
        "mean_avg_logprob": (sum(avg_logprobs) / len(avg_logprobs)) if avg_logprobs else None,
        "min_avg_logprob": min(avg_logprobs) if avg_logprobs else None,
    }


def _resolve_asr_post_filter_config(raw: dict | None) -> dict:
    cfg = {
        "enabled": True,
        "reject_short_text": True,
        "reject_high_no_speech_prob": True,
        "reject_low_avg_logprob": True,
        "reject_short_word_low_conf": True,
        "reject_repetition_loop": True,
        "retry_repetition_once": True,
        "min_chars": ASR_POST_FILTER_MIN_CHARS,
        "no_speech_reject": ASR_POST_FILTER_NO_SPEECH_REJECT,
        "low_logprob_reject": ASR_POST_FILTER_LOW_LOGPROB_REJECT,
        "short_text_max_chars": ASR_POST_FILTER_SHORT_TEXT_MAX_CHARS,
        "short_word_max_words": 2,
        "short_word_low_logprob_reject": -0.85,
        "repetition_min_tokens": ASR_POST_FILTER_REPETITION_MIN_TOKENS,
        "repetition_token_rate_reject": ASR_POST_FILTER_REPETITION_TOKEN_RATE_REJECT,
        "repetition_ngram_n": ASR_POST_FILTER_REPETITION_NGRAM_N,
        "repetition_ngram_repeat_reject": ASR_POST_FILTER_REPETITION_NGRAM_REPEAT_REJECT,
        "retry_beam_add": ASR_POST_FILTER_REPETITION_RETRY_BEAM_ADD,
        "retry_best_of_add": ASR_POST_FILTER_REPETITION_RETRY_BEST_OF_ADD,
    }
    if not isinstance(raw, dict):
        return cfg
    try:
        if "enabled" in raw:
            cfg["enabled"] = bool(raw.get("enabled"))
        if "reject_short_text" in raw:
            cfg["reject_short_text"] = bool(raw.get("reject_short_text"))
        if "reject_high_no_speech_prob" in raw:
            cfg["reject_high_no_speech_prob"] = bool(raw.get("reject_high_no_speech_prob"))
        if "reject_low_avg_logprob" in raw:
            cfg["reject_low_avg_logprob"] = bool(raw.get("reject_low_avg_logprob"))
        if "reject_short_word_low_conf" in raw:
            cfg["reject_short_word_low_conf"] = bool(raw.get("reject_short_word_low_conf"))
        if "reject_repetition_loop" in raw:
            cfg["reject_repetition_loop"] = bool(raw.get("reject_repetition_loop"))
        if "retry_repetition_once" in raw:
            cfg["retry_repetition_once"] = bool(raw.get("retry_repetition_once"))
        if "min_chars" in raw:
            cfg["min_chars"] = max(1, int(raw.get("min_chars", cfg["min_chars"])))
        if "no_speech_reject" in raw:
            cfg["no_speech_reject"] = min(0.99, max(0.0, float(raw.get("no_speech_reject", cfg["no_speech_reject"]))))
        if "low_logprob_reject" in raw:
            cfg["low_logprob_reject"] = float(raw.get("low_logprob_reject", cfg["low_logprob_reject"]))
        if "short_text_max_chars" in raw:
            cfg["short_text_max_chars"] = max(1, int(raw.get("short_text_max_chars", cfg["short_text_max_chars"])))
        if "short_word_max_words" in raw:
            cfg["short_word_max_words"] = max(1, min(4, int(raw.get("short_word_max_words", cfg["short_word_max_words"]))))
        if "short_word_low_logprob_reject" in raw:
            cfg["short_word_low_logprob_reject"] = float(raw.get("short_word_low_logprob_reject", cfg["short_word_low_logprob_reject"]))
        if "repetition_min_tokens" in raw:
            cfg["repetition_min_tokens"] = max(4, int(raw.get("repetition_min_tokens", cfg["repetition_min_tokens"])))
        if "repetition_token_rate_reject" in raw:
            cfg["repetition_token_rate_reject"] = min(0.98, max(0.30, float(raw.get("repetition_token_rate_reject", cfg["repetition_token_rate_reject"]))))
        if "repetition_ngram_n" in raw:
            cfg["repetition_ngram_n"] = max(2, min(6, int(raw.get("repetition_ngram_n", cfg["repetition_ngram_n"]))))
        if "repetition_ngram_repeat_reject" in raw:
            cfg["repetition_ngram_repeat_reject"] = max(2, int(raw.get("repetition_ngram_repeat_reject", cfg["repetition_ngram_repeat_reject"])))
        if "retry_beam_add" in raw:
            cfg["retry_beam_add"] = max(0, int(raw.get("retry_beam_add", cfg["retry_beam_add"])))
        if "retry_best_of_add" in raw:
            cfg["retry_best_of_add"] = max(0, int(raw.get("retry_best_of_add", cfg["retry_best_of_add"])))
    except Exception:
        return cfg
    return cfg


def _detect_repetition_loop(text: str, config: dict | None = None) -> tuple[bool, dict]:
    cfg = _resolve_asr_post_filter_config(config)
    tokens = [t for t in re.findall(r"[A-Za-z0-9一-龥ぁ-んァ-ヶー]+", (text or "").lower()) if t]
    min_tokens = int(cfg.get("repetition_min_tokens", 8))
    if len(tokens) < min_tokens:
        return False, {"token_count": len(tokens)}
    uniq = len(set(tokens))
    repetition_rate = 1.0 - (float(uniq) / float(len(tokens)))
    n = int(cfg.get("repetition_ngram_n", 3))
    ngram_counts = {}
    max_repeat = 1
    if len(tokens) >= n:
        for i in range(0, len(tokens) - n + 1):
            ng = tuple(tokens[i:i + n])
            ngram_counts[ng] = ngram_counts.get(ng, 0) + 1
            if ngram_counts[ng] > max_repeat:
                max_repeat = ngram_counts[ng]
    is_loop = repetition_rate >= float(cfg.get("repetition_token_rate_reject", 0.62)) or max_repeat >= int(cfg.get("repetition_ngram_repeat_reject", 4))
    return is_loop, {
        "token_count": len(tokens),
        "unique_token_count": uniq,
        "token_repetition_rate": round(repetition_rate, 4),
        "ngram_n": n,
        "ngram_max_repeat": max_repeat,
    }

def voice_transcribe(
    audio_bytes: bytes,
    language: str = "auto",
    model_name: str = "large-v3-turbo",
    auto_unload: bool = False,
    audio_format: str = "webm",
    asr_profile: str = "balanced",
    beam_size: int | None = None,
    best_of: int | None = None,
    no_speech_threshold: float | None = None,
    log_prob_threshold: float | None = None,
    compression_ratio_threshold: float | None = None,
    asr_post_filter: dict | None = None,
) -> dict:
    """
    音声を文字起こしする。英語/日本語対応（Whisper多言語）。
    language: "ja" / "en" / "auto"
    """
    st = voice_load(model_name=model_name)
    lang = None if language == "auto" else language
    suffix = "." + re.sub(r"[^a-zA-Z0-9]", "", (audio_format or "webm")).lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(audio_bytes)
        temp_path = tf.name
    try:
        asr_profile = _resolve_asr_profile(asr_profile)
        filter_cfg = _resolve_asr_post_filter_config(asr_post_filter)
        transcribe_kwargs = _build_asr_transcribe_kwargs(
            asr_profile=asr_profile,
            beam_size=beam_size,
            best_of=best_of,
            no_speech_threshold=no_speech_threshold,
            log_prob_threshold=log_prob_threshold,
            compression_ratio_threshold=compression_ratio_threshold,
        )
        with _voice_lock:
            segments, info = _voice_model.transcribe(
                temp_path,
                language=lang,
                **transcribe_kwargs,
            )
            segments = list(segments)
            text = "".join(seg.text for seg in segments).strip()
            metrics = _asr_metrics(segments)
            rejected = False
            reject_reason = ""
            retry_applied = False
            looped, rep_detail = _detect_repetition_loop(text, filter_cfg)
            if bool(filter_cfg.get("enabled", True)) and bool(filter_cfg.get("reject_repetition_loop", True)) and looped:
                if bool(filter_cfg.get("retry_repetition_once", True)):
                    retry_kwargs = dict(transcribe_kwargs)
                    retry_kwargs["beam_size"] = max(1, int(retry_kwargs.get("beam_size", 1)) + int(filter_cfg.get("retry_beam_add", 2)))
                    retry_kwargs["best_of"] = max(1, int(retry_kwargs.get("best_of", 1)) + int(filter_cfg.get("retry_best_of_add", 2)))
                    retry_applied = True
                    segments_retry, info = _voice_model.transcribe(
                        temp_path,
                        language=lang,
                        **retry_kwargs,
                    )
                    segments_retry = list(segments_retry)
                    text = "".join(seg.text for seg in segments_retry).strip()
                    metrics = _asr_metrics(segments_retry)
                    looped_retry, rep_detail = _detect_repetition_loop(text, filter_cfg)
                    transcribe_kwargs = retry_kwargs
                    if looped_retry:
                        rejected = True
                        reject_reason = "repetition_loop"
                else:
                    rejected = True
                    reject_reason = "repetition_loop"
            if rejected:
                logging.info(
                    "voice_transcribe rejected: reject_reason=%s profile=%s detail=%s",
                    reject_reason, asr_profile, rep_detail,
                )
                text = ""
        if auto_unload:
            voice_unload()
        return {
            "text": text,
            "language": getattr(info, "language", language),
            "duration": getattr(info, "duration", 0.0),
            "model": st.get("model", model_name),
            "auto_unloaded": auto_unload,
            "asr_profile": asr_profile,
            "post_filter": {
                "enabled": bool(filter_cfg.get("enabled", True)),
                "rejected": rejected,
                "reject_reason": reject_reason,
                "retry_applied": retry_applied,
            },
            "asr_params": {
                "beam_size": transcribe_kwargs.get("beam_size"),
                "best_of": transcribe_kwargs.get("best_of"),
                "no_speech_threshold": transcribe_kwargs.get("no_speech_threshold"),
                "log_prob_threshold": transcribe_kwargs.get("log_prob_threshold"),
                "compression_ratio_threshold": transcribe_kwargs.get("compression_ratio_threshold"),
            },
            "metrics": metrics,
        }
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass

def _build_conversation_io(req: ChatRequest):
    has_audio = bool((req.audio_base64 or "").strip())
    if has_audio:
        return VoiceIOAdapter(
            message=req.message,
            audio_base64=req.audio_base64,
            language=req.voice_language or "ja",
            audio_format=req.audio_format or "webm",
            asr_transcribe=voice_transcribe,
            tts_synthesize=None,
            interruption=bool(req.interruption),
            barge_in=bool(req.barge_in),
            partial_transcript=req.partial_transcript or "",
        )
    return TextIOAdapter(req.message)


def _receive_user_turn(req: ChatRequest, io_adapter=None) -> ConversationTurn:
    io_adapter = io_adapter or _build_conversation_io(req)
    try:
        return io_adapter.receive_turn()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"voice transcription failed: {e}")


def _llm_endpoint_reachable(url: str, timeout_sec: float = 1.8) -> bool:
    target = (url or "").strip()
    if not target:
        return False
    base = re.sub(r"/v1/chat/completions/?$", "", target).rstrip("/")
    if not base:
        return False
    for path in ("/health", "/v1/models"):
        try:
            r = requests.get(base + path, timeout=timeout_sec)
            if r.status_code < 500:
                return True
        except Exception:
            pass
    return False


def _infer_startup_failure_hints(log_path: str, tail_lines: int = 200) -> list[str]:
    """
    llama-server起動ログから「VRAMへ載らない」原因候補を抽出する。
    最後の起動セクション（=== model-start ===以降）のみを対象とし、
    蓄積された過去ログから誤検知しないようにする。
    """
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
    except Exception:
        return []
    # 最後の起動セクションのみを対象にする（古い起動ログの誤検知防止）
    last_section_start = 0
    for i, line in enumerate(all_lines):
        if "model-start ===" in line:
            last_section_start = i + 1
    lines = all_lines[last_section_start:][-tail_lines:]
    if not lines:
        return []
    blob = "\n".join(lines).lower()
    hints: list[str] = []
    # ggml_cuda_init: found X devices は成功メッセージのため除外し、
    # 明確な失敗キーワードとの組み合わせのみ検知する
    if "cuda" in blob and ("not found" in blob or "failed" in blob or "error" in blob):
        hints.append("CUDA初期化失敗の可能性（CPUフォールバック）。GPUドライバ/ビルドを確認してください。")
    if "metal" in blob and "failed" in blob:
        hints.append("Metal初期化失敗の可能性（CPUフォールバック）。")
    if "hip" in blob and ("failed" in blob or "not found" in blob):
        hints.append("ROCm/HIP初期化失敗の可能性（CPUフォールバック）。")
    # llama-serverの内部ログでのn_gpu_layers=0のみ検知（起動コマンドのログ行は除外）
    if "n_gpu_layers = 0" in blob:
        hints.append("GPUレイヤーが0で起動している可能性。gpu_layers設定を確認してください。")
    if ("insufficient vram" in blob or "out of memory" in blob
            or "cudamalloc failed" in blob or "failed to allocate" in blob
            or "ggml_cuda_device_malloc" in blob):
        hints.append("VRAM不足（OOM）の可能性。ctx_size/gpu_layers/modelサイズを下げてください。")
    if "warning" in blob and "mmap" in blob:
        hints.append("mmap関連警告あり。ストレージや権限で読み込み性能が低下している可能性。")
    if "mmproj" in blob and ("not found" in blob or "missing" in blob or "failed" in blob):
        hints.append("VLM用mmprojの不足/不一致の可能性。modelと対応するmmprojを指定してください。")
    # GPUデバイスが見つからない場合（llama.cpp直接出力）
    import re as _re
    if _re.search(r"ggml_cuda_init.*found 0 devices", blob):
        hints.append("GPUデバイスが0件（CUDAデバイス未検出）。LLAMA_SERVER_PATHのバイナリにCUDAが組み込まれているか確認してください。")
    # GPUオフロードが0レイヤーの場合（CUDAあるがVRAMに載っていない）
    if _re.search(r"offloaded 0/\d+ layers to gpu", blob):
        hints.append("GPUオフロード0レイヤー（CPU動作）。ggml_cuda_initの結果と-ngl設定を確認してください。")
    elif _re.search(r"offloaded \d+/\d+ layers to gpu", blob):
        # 正常にGPUオフロードされていることを示す（ヒントなし）
        pass
    return list(dict.fromkeys(hints))


def _resolve_runtime_llm_url(requested_url: str = "") -> str:
    req_url = (requested_url or "").strip()
    if req_url and _llm_endpoint_reachable(req_url):
        return req_url
    manager_url = (_model_manager.llm_url or "").strip()
    if manager_url and _llm_endpoint_reachable(manager_url):
        return manager_url
    if req_url:
        return req_url
    return manager_url or LLM_URL_CHAT

# =========================
# エンドポイント: /chat（後方互換）
# =========================

@app.post("/chat")
def chat(req: ChatRequest):
    sid = str(uuid.uuid4())[:8]
    chat_url = _resolve_runtime_llm_url(req.llm_url)
    io_adapter = _build_conversation_io(req)
    user_turn = _receive_user_turn(req, io_adapter=io_adapter)
    message = (user_turn.text or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is empty")
    effective_search_enabled = _resolve_effective_search_enabled(req.search_enabled)
    result = execute_task(message, max_steps=req.max_steps, project=req.project,
                          search_enabled=effective_search_enabled, llm_url=chat_url)
    save_session(sid, req.project, message, "chat", result)
    if result["status"] == "done":
        sent = io_adapter.send_turn(ConversationTurn(text=result["output"], role="assistant"))
        return {
            "result": sent.get("text", result["output"]),
            "response": sent,
            "steps": result["steps"],
            "total_steps": result["total_steps"]
        }
    return {"error": result.get("error", "unknown"), "steps": result["steps"]}

# =========================
# エンドポイント: /plan（プラン生成のみ・承認フロー用）
# =========================

@app.post("/llm/test")
def llm_test(req: LLMTestRequest):
    """指定URLのLLMへの疎通確認と利用可能モデル一覧を返す"""
    url = req.url.strip().rstrip("/")
    # /v1/chat/completions 形式に補正
    if not url.endswith("/v1/chat/completions"):
        completions_url = url + ("/v1/chat/completions" if not url.endswith("/v1") else "/chat/completions")
    else:
        completions_url = url

    # ヘルスチェック
    health_url = url.replace("/v1/chat/completions", "").rstrip("/") + "/health"
    health_ok = False
    try:
        r = requests.get(health_url, timeout=4)
        health_ok = r.status_code == 200
    except Exception:
        pass

    # モデル一覧（OpenAI互換 /v1/models）
    models = []
    try:
        models_url = url.replace("/v1/chat/completions", "").rstrip("/") + "/v1/models"
        r = requests.get(models_url, timeout=4)
        if r.status_code == 200:
            data = r.json()
            models = [m.get("id", "") for m in data.get("data", [])]
    except Exception:
        pass

    # 簡易チャットテスト
    chat_ok = False
    chat_error = ""
    try:
        r = requests.post(completions_url, json={
            "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
            "temperature": 0,
            "max_tokens": 5
        }, timeout=15)
        chat_ok = r.status_code == 200
        if not chat_ok:
            chat_error = f"HTTP {r.status_code}"
    except Exception as e:
        chat_error = str(e)[:100]

    return {
        "url": completions_url,
        "health": health_ok,
        "chat": chat_ok,
        "chat_error": chat_error,
        "models": models
    }


def _phase1_llm_json(prompt: str, user_content: str) -> dict | None:
    try:
        reply, _usage = call_llm_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            llm_url=LLM_URL_PLANNER,
            max_output_tokens=16384,
        )
        return extract_json(reply, parser=_model_manager.current_parser)
    except Exception as exc:
        print(f"[PHASE1][LLM] warn: {exc}")
        return None


def _phase1_active_skills_safe() -> list:
    try:
        for fn_name in ("_active_skills", "active_skills", "get_active_skills"):
            fn = globals().get(fn_name)
            if callable(fn):
                result = fn()
                return result if isinstance(result, list) else []
    except Exception as exc:
        print(f"[Phase1Planning] active skills unavailable: {exc}")
    return []


_phase1_planning_runner = TaskPlanningRunner(
    ca_data_dir=CA_DATA_DIR,
    llm_json_fn=_phase1_llm_json,
    memory_search_fn=memory_search,
    active_skills_fn=_phase1_active_skills_safe,
    warning_logger=lambda msg: print(f"[PHASE1][NEXUS] {msg}"),
)


def _resolve_project_path_for_phase_planning(project_path: str, project_name: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    resolved_project_path = ""
    raw_project_path = (project_path or "").strip()
    raw_project_name = (project_name or "").strip()
    if raw_project_path:
        expanded = os.path.expanduser(raw_project_path)
        candidate = expanded if os.path.isabs(expanded) else os.path.join(WORK_DIR, expanded)
        candidate = os.path.abspath(candidate)
        if os.path.isdir(candidate):
            resolved_project_path = candidate
        else:
            warnings.append(f"project_path does not exist or is not a directory: {raw_project_path}. Fallback resolution was used.")

    if not resolved_project_path and raw_project_name:
        safe_project_name = os.path.basename(raw_project_name).strip()
        if safe_project_name:
            candidate = os.path.abspath(os.path.join(WORK_DIR, safe_project_name))
            if os.path.isdir(candidate):
                resolved_project_path = candidate
            else:
                warnings.append(f"project_name was not found under WORK_DIR: {safe_project_name}. Fallback resolution was used.")

    if not resolved_project_path:
        resolved_project_path = os.path.abspath(os.path.join(WORK_DIR, "default"))
        os.makedirs(resolved_project_path, exist_ok=True)
        warnings.append("project_path was not specified or was invalid. WORK_DIR/default was used.")
    return resolved_project_path, warnings


@app.post("/api/task/plan")
def api_task_plan(req: TaskPlanRequest):
    user_input = (req.input or "").strip()
    if not user_input:
        raise HTTPException(status_code=400, detail="input is empty")
    resolved_project_path, api_warnings = _resolve_project_path_for_phase_planning(req.project_path, req.project_name)
    try:
        result = _phase1_planning_runner.run(
            user_input=user_input,
            project_path=resolved_project_path,
            project_name=(req.project_name or "").strip(),
            planning_mode=(req.planning_mode or "standard").strip().lower(),
            requirement_mode=(req.requirement_mode or "ask_when_needed").strip(),
            execution_mode=(req.execution_mode or "plan_only").strip(),
            use_nexus=bool(req.use_nexus),
        )
        result_warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
        result["warnings"] = list(dict.fromkeys([*api_warnings, *[str(x) for x in result_warnings if str(x).strip()]]))
        result["resolved_project_path"] = resolved_project_path
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"plan generation failed: {exc}") from exc


@app.get("/api/plans/{plan_id}")
def api_get_plan(plan_id: str):
    try:
        return _phase1_planning_runner.storage.load_plan(plan_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plan not found")


@app.get("/api/plans/{plan_id}/markdown")
def api_get_plan_markdown(plan_id: str):
    try:
        markdown = _phase1_planning_runner.storage.read_plan_markdown(plan_id)
        return {"plan_id": plan_id, "markdown": markdown}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="plan markdown not found")


@app.get("/api/reviews/{review_id}")
def api_get_review(review_id: str):
    try:
        return _phase1_planning_runner.storage.load_review(review_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="review not found")


@app.get("/api/reviews/{review_id}/markdown")
def api_get_review_markdown(review_id: str):
    try:
        markdown = _phase1_planning_runner.storage.read_review_markdown(review_id)
        return {"review_id": review_id, "markdown": markdown}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="review markdown not found")


@app.get("/api/requirements/{requirement_id}")
def api_get_requirement(requirement_id: str):
    try:
        return _phase1_planning_runner.storage.load_requirement(requirement_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="requirement not found")


@app.get("/api/requirements/{requirement_id}/markdown")
def api_get_requirement_markdown(requirement_id: str):
    try:
        markdown = _phase1_planning_runner.storage.read_requirement_markdown(requirement_id)
        return {"requirement_id": requirement_id, "markdown": markdown}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="requirement markdown not found")


@app.post("/api/requirements/answer")
def api_answer_requirement(req: RequirementAnswerRequest):
    requirement_id = (req.requirement_id or "").strip()
    if not requirement_id:
        raise HTTPException(status_code=400, detail="requirement_id is empty")
    try:
        if req.skip_with_defaults:
            return _phase1_planning_runner.skip_requirement_questions(requirement_id=requirement_id)
        payload = [item.model_dump() for item in (req.answers or [])]
        return _phase1_planning_runner.answer_requirement_questions(requirement_id=requirement_id, answers=payload)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="requirement not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"requirement answer failed: {exc}") from exc


@app.post("/api/task/continue")
def api_task_continue(req: TaskContinueRequest):
    requirement_id = (req.requirement_id or "").strip()
    if not requirement_id:
        raise HTTPException(status_code=400, detail="requirement_id is empty")
    try:
        req_data = _phase1_planning_runner.storage.load_requirement(requirement_id)
        saved_project_path = str(req_data.get("resolved_project_path") or req_data.get("project_path") or "").strip()
        saved_project_name = str(req_data.get("project_name") or "").strip()
        continue_project_path = (req.project_path or "").strip() or saved_project_path
        continue_project_name = (req.project_name or "").strip() or saved_project_name
        resolved_project_path, api_warnings = _resolve_project_path_for_phase_planning(continue_project_path, continue_project_name)
        result = _phase1_planning_runner.continue_from_requirement(
            requirement_id=requirement_id,
            planning_mode=(req.planning_mode or "standard").strip().lower(),
            requirement_mode=(req.requirement_mode or "ask_when_needed").strip(),
            execution_mode=(req.execution_mode or "plan_only").strip(),
            use_nexus=bool(req.use_nexus),
            project_path=resolved_project_path,
            project_name=continue_project_name,
            resolved_project_path=resolved_project_path,
        )
        result_warnings = result.get("warnings") if isinstance(result.get("warnings"), list) else []
        result["warnings"] = list(dict.fromkeys([*api_warnings, *[str(x) for x in result_warnings if str(x).strip()]]))
        result["resolved_project_path"] = resolved_project_path
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="requirement not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"task continue failed: {exc}") from exc


@app.post("/plan")
def plan_only(req: ChatRequest):
    """要件定義・タスクリストを返す。モデル推奨情報も含む。"""
    io_adapter = _build_conversation_io(req)
    user_turn = _receive_user_turn(req, io_adapter=io_adapter)
    message = (user_turn.text or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is empty")
    try:
        result = plan(message, req.project)
        if not result.get("tasks"):
            result["tasks"] = [{"id": 1, "title": "実行", "detail": message}]
    except Exception as e:
        result = {
            "summary": message[:80],
            "requirements": [],
            "approach": "",
            "verification": [],
            "tasks": [{"id": 1, "title": "実行", "detail": message}]
        }
        print(f"[PLAN] error: {e}")

    recommended_key = _model_manager.classify(message, plan_result=result)
    # ※ basicのまま推奨（UIでAutoを選べば現在のモデルを使う）
    runtime_catalog = get_runtime_model_catalog()
    recommended_spec = runtime_catalog.get(recommended_key, {})
    current_key = _model_manager.current_key

    return {
        **result,
        "message": message,
        "project": req.project,
        "recommended_model": recommended_key,
        "recommended_model_name": recommended_spec.get("name", ""),
        "recommended_model_desc": recommended_spec.get("description", ""),
        "current_model": current_key,
        "model_switch_needed": recommended_key != current_key,
        "switch_eta_sec": recommended_spec.get("load_sec", 0) if recommended_key != current_key else 0,
        "catalog": {k: {"name": v["name"], "vram_gb": v["vram_gb"],
                        "available": bool(v["path"])}
                    for k, v in runtime_catalog.items()
                    if bool(v.get("path"))},
    }

@app.get("/voice/status")
def voice_status_api():
    return voice_status()

@app.post("/voice/load")
def voice_load_api(req: dict):
    model_name = str(req.get("model", "small")).strip() or "small"
    device = req.get("device")
    if device not in ("cpu", "cuda"):
        device = None
    return voice_load(model_name, device=device)

@app.post("/voice/unload")
def voice_unload_api():
    return voice_unload()

@app.post("/voice/transcribe")
def voice_transcribe_api(req: dict):
    audio_b64 = str(req.get("audio_base64", "")).strip()
    if not audio_b64:
        raise HTTPException(status_code=400, detail="audio_base64 required")
    language = str(req.get("language", "auto")).strip().lower() or "auto"
    if language not in {"auto", "ja", "en"}:
        language = "auto"
    model_name = str(req.get("model", "large-v3-turbo")).strip() or "large-v3-turbo"
    # モデルはサーバー終了まで RAM に常駐させる（unload しない）
    auto_unload = False
    audio_format = str(req.get("audio_format", "webm")).strip() or "webm"
    asr_profile = _resolve_asr_profile(req.get("asr_profile", "balanced"))
    beam_size = req.get("beam_size")
    best_of = req.get("best_of")
    no_speech_threshold = req.get("no_speech_threshold")
    log_prob_threshold = req.get("log_prob_threshold")
    compression_ratio_threshold = req.get("compression_ratio_threshold")
    asr_post_filter = req.get("asr_post_filter", {})
    try:
        beam_size = int(beam_size) if beam_size is not None else None
    except Exception:
        beam_size = None
    try:
        best_of = int(best_of) if best_of is not None else None
    except Exception:
        best_of = None
    try:
        no_speech_threshold = float(no_speech_threshold) if no_speech_threshold is not None else None
    except Exception:
        no_speech_threshold = None
    try:
        log_prob_threshold = float(log_prob_threshold) if log_prob_threshold is not None else None
    except Exception:
        log_prob_threshold = None
    try:
        compression_ratio_threshold = float(compression_ratio_threshold) if compression_ratio_threshold is not None else None
    except Exception:
        compression_ratio_threshold = None
    try:
        audio = base64.b64decode(audio_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid audio_base64: {e}")

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def stream():
        # モデル未キャッシュの場合はダウンロード通知を先に送信
        if not _voice_model_exists(model_name):
            storage_note = "（RunPod: 揮発ストレージ）" if IS_RUNPOD_RUNTIME else "（ローカル: models/ASRModels）"
            yield _sse({
                "type": "downloading",
                "message": (
                    f"Whisper {model_name} モデルをダウンロード中です {storage_note}。\n"
                    "初回のみ数分かかる場合があります。しばらくお待ちください..."
                ),
            })
        try:
            yield _sse({"type": "transcribing", "message": "音声を文字変換中です。しばらくお待ちください..."})
            result = voice_transcribe(
                audio,
                language=language,
                model_name=model_name,
                auto_unload=auto_unload,
                audio_format=audio_format,
                asr_profile=asr_profile,
                beam_size=beam_size,
                best_of=best_of,
                no_speech_threshold=no_speech_threshold,
                log_prob_threshold=log_prob_threshold,
                compression_ratio_threshold=compression_ratio_threshold,
                asr_post_filter=asr_post_filter if isinstance(asr_post_filter, dict) else {},
            )
            yield _sse({"type": "result", **result})
        except Exception as e:
            yield _sse({"type": "error", "detail": f"voice transcribe failed: {e}"})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )

# =========================
# TALK MODE / EchoVault
# =========================

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse as _FileResponse

# Echo セッション状態（session_id → dict）
_echo_sessions: dict = {}
_echo_voice_lock = threading.Lock()   # voice_transcribe 専用ロック（Echo用）
_echo_voice_model = None              # Echo用 Whisper モデル（通常ASRと分離）
_echo_voice_model_name = ""
_echo_debug_lock = threading.Lock()
_echo_debug_events: dict[str, list[dict]] = {}
_echo_debug_last_updated: dict[str, str] = {}
ECHO_DEBUG_LOG_PATH = os.path.join(LOG_DIR, "echo_debug.log")
_echo_save_lock = threading.Lock()
_echo_saving_sessions: set[str] = set()
_echo_minutes_lock = threading.Lock()
_echo_generating_minutes_sessions: set[str] = set()
# Echo ASRの軽量ポストフィルタ（CPU負荷ほぼゼロ）
ECHO_ASR_MIN_CHARS = ASR_POST_FILTER_MIN_CHARS
ECHO_ASR_NO_SPEECH_REJECT = ASR_POST_FILTER_NO_SPEECH_REJECT
ECHO_ASR_LOW_LOGPROB_REJECT = ASR_POST_FILTER_LOW_LOGPROB_REJECT
ECHO_ASR_SHORT_TEXT_MAX_CHARS = ASR_POST_FILTER_SHORT_TEXT_MAX_CHARS


def _echo_debug_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="milliseconds") + "Z"


def _echo_debug_append(session_id: str, seq: int | None, event_type: str, **fields):
    """Echo デバッグイベントをメモリ + JSONL ファイルへ追記する。"""
    sid = str(session_id or "unknown")
    payload = {
        "ts": _echo_debug_now_iso(),
        "session_id": sid,
        "seq": seq,
        "event": event_type,
        **fields,
    }
    line = json.dumps(payload, ensure_ascii=False)
    with _echo_debug_lock:
        bucket = _echo_debug_events.setdefault(sid, [])
        bucket.append(payload)
        if len(bucket) > 5000:
            del bucket[:-5000]
        _echo_debug_last_updated[sid] = payload["ts"]
        try:
            with open(ECHO_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            logging.error("echo debug log write failed: %s", e)


def _echo_pcm_s16le_to_wav_bytes(audio_bytes: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    """PCM(s16le) を WAV バイト列へ変換する。"""
    import io, wave
    with io.BytesIO() as bio:
        with wave.open(bio, "wb") as wf:
            wf.setnchannels(max(1, int(channels or 1)))
            wf.setsampwidth(2)  # s16le
            wf.setframerate(max(1, int(sample_rate or 16000)))
            wf.writeframes(audio_bytes or b"")
        return bio.getvalue()


def _echo_asr_metrics(segments) -> dict:
    return _asr_metrics(segments)


def _echo_should_reject_asr_text(text: str, metrics: dict) -> tuple[bool, str]:
    """誤検出を抑える軽量棄却ルール。"""
    return _echo_should_reject_asr_text_with_config(text, metrics, None)


def _echo_resolve_filter_config(raw: dict | None) -> dict:
    """Echo ASRポストフィルタ設定を通常ASRと同体系で解決する。"""
    return _resolve_asr_post_filter_config(raw)


def _echo_should_reject_asr_text_with_config(text: str, metrics: dict, config: dict | None, lang: str | None = None) -> tuple[bool, str]:
    """誤検出を抑える軽量棄却ルール（セッション設定対応）。"""
    cfg = _echo_resolve_filter_config(config)
    if not bool(cfg.get("enabled", True)):
        return False, ""
    text_len = len((text or "").strip())
    if bool(cfg.get("reject_short_text", True)) and text_len < int(cfg["min_chars"]):
        return True, "too_short_text"
    mean_nsp = metrics.get("mean_no_speech_prob")
    mean_logprob = metrics.get("mean_avg_logprob")
    if (
        bool(cfg.get("reject_high_no_speech_prob", True))
        and
        isinstance(mean_nsp, (int, float))
        and text_len <= int(cfg["short_text_max_chars"])
        and float(mean_nsp) >= float(cfg["no_speech_reject"])
    ):
        return True, "high_no_speech_prob"
    if (
        bool(cfg.get("reject_low_avg_logprob", True))
        and
        isinstance(mean_logprob, (int, float))
        and text_len <= int(cfg["short_text_max_chars"])
        and float(mean_logprob) <= float(cfg["low_logprob_reject"])
    ):
        return True, "low_avg_logprob"
    normalized_lang = _echo_normalize_lang(lang, text)
    if (
        normalized_lang == "en"
        and bool(cfg.get("reject_short_word_low_conf", True))
        and isinstance(mean_logprob, (int, float))
    ):
        word_count = len([w for w in (text or "").strip().split() if w])
        if (
            0 < word_count <= int(cfg.get("short_word_max_words", 2))
            and float(mean_logprob) <= float(cfg.get("short_word_low_logprob_reject", -0.85))
        ):
            return True, "short_word_low_conf"
    if bool(cfg.get("reject_repetition_loop", True)):
        looped, _detail = _detect_repetition_loop(text, cfg)
        if looped:
            return True, "repetition_loop"
    return False, ""


def _echo_build_recent_prompt_text(previous_text: str, latest_text: str, keep_chars: int = 40) -> str:
    """直近確定テキストを initial_prompt 用に保持する。"""
    keep = max(20, min(60, int(keep_chars or 40)))
    merged = (str(previous_text or "") + " " + str(latest_text or "")).strip()
    if not merged:
        return ""
    compact = re.sub(r"\s+", " ", merged)
    return compact[-keep:]


def _echo_trim_overlap_text(previous_text: str, current_text: str) -> tuple[str, dict]:
    """suffix/prefix一致で重複語を軽く除去する。"""
    prev = str(previous_text or "").strip()
    curr = str(current_text or "").strip()
    if not prev or not curr:
        return curr, {"overlap_chars": 0, "mode": "none"}
    prev_norm = re.sub(r"\s+", " ", prev)
    curr_norm = re.sub(r"\s+", " ", curr)
    max_overlap = min(len(prev_norm), len(curr_norm), 48)
    for n in range(max_overlap, 0, -1):
        if prev_norm[-n:] == curr_norm[:n]:
            trimmed = curr_norm[n:].lstrip()
            return trimmed, {"overlap_chars": n, "mode": "suffix_prefix"}
    return curr_norm, {"overlap_chars": 0, "mode": "none"}


def _echo_voice_transcribe(
    audio_bytes: bytes,
    language: str = "auto",
    model_name: str = "large-v3-turbo",
    audio_format: str = "webm",
    sample_rate: int = 16000,
    channels: int = 1,
    asr_profile: str = "balanced",
    beam_size: int | None = None,
    best_of: int | None = None,
    no_speech_threshold: float | None = None,
    log_prob_threshold: float | None = None,
    compression_ratio_threshold: float | None = None,
    asr_post_filter: dict | None = None,
    initial_prompt: str | None = None,
) -> dict:
    """Echo専用 voice_transcribe。_echo_voice_lock を使用し通常ASRと競合しない。"""
    global _echo_voice_model, _echo_voice_model_name
    from faster_whisper import WhisperModel  # type: ignore
    import tempfile, re as _re

    fmt = (audio_format or "webm").strip().lower()
    temp_path = None
    audio_input = None
    if fmt in {"pcm", "pcm_s16le", "s16le", "raw"}:
        try:
            import numpy as _np  # type: ignore

            pcm = _np.frombuffer(audio_bytes or b"", dtype=_np.int16)
            ch = max(1, int(channels or 1))
            if ch > 1 and pcm.size >= ch:
                frames = (pcm.size // ch) * ch
                pcm = pcm[:frames].reshape(-1, ch).mean(axis=1).astype(_np.int16)
            audio_input = pcm.astype(_np.float32) / 32768.0
        except Exception:
            # numpy未導入や異常データ時は従来どおりWAV経由へフォールバック
            audio_input = _echo_pcm_s16le_to_wav_bytes(audio_bytes, sample_rate=sample_rate, channels=channels)
            fmt = "wav"
    else:
        audio_input = audio_bytes
    if isinstance(audio_input, (bytes, bytearray)):
        suffix = "." + _re.sub(r"[^a-zA-Z0-9]", "", fmt or "webm")
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
            tf.write(audio_input)
            temp_path = tf.name
        audio_input = temp_path
    try:
        filter_cfg = _resolve_asr_post_filter_config(asr_post_filter)
        with _echo_voice_lock:
            if _echo_voice_model is None or _echo_voice_model_name != model_name:
                _echo_voice_model = WhisperModel(
                    model_name,
                    device=_voice_device,
                    compute_type=_voice_compute_type,
                    download_root=_voice_model_dir(),
                )
                _echo_voice_model_name = model_name
            lang_arg = None if language == "auto" else language
            asr_profile = _resolve_asr_profile(asr_profile)
            transcribe_kwargs = _build_asr_transcribe_kwargs(
                asr_profile=asr_profile,
                beam_size=beam_size,
                best_of=best_of,
                no_speech_threshold=no_speech_threshold,
                log_prob_threshold=log_prob_threshold,
                compression_ratio_threshold=compression_ratio_threshold,
            )
            prompt = str(initial_prompt or "").strip()
            if prompt:
                transcribe_kwargs["initial_prompt"] = prompt
            segments, info = _echo_voice_model.transcribe(
                audio_input,
                language=lang_arg,
                **transcribe_kwargs,
            )
            segments = list(segments)
            text = "".join(seg.text for seg in segments).strip()
            metrics = _echo_asr_metrics(segments)
            rejected = False
            reject_reason = ""
            retry_applied = False
            looped, rep_detail = _detect_repetition_loop(text, filter_cfg)
            if bool(filter_cfg.get("enabled", True)) and bool(filter_cfg.get("reject_repetition_loop", True)) and looped:
                if bool(filter_cfg.get("retry_repetition_once", True)):
                    retry_kwargs = dict(transcribe_kwargs)
                    retry_kwargs["beam_size"] = max(1, int(retry_kwargs.get("beam_size", 1)) + int(filter_cfg.get("retry_beam_add", 2)))
                    retry_kwargs["best_of"] = max(1, int(retry_kwargs.get("best_of", 1)) + int(filter_cfg.get("retry_best_of_add", 2)))
                    retry_applied = True
                    segments_retry, info = _echo_voice_model.transcribe(
                        audio_input,
                        language=lang_arg,
                        **retry_kwargs,
                    )
                    segments_retry = list(segments_retry)
                    text = "".join(seg.text for seg in segments_retry).strip()
                    metrics = _echo_asr_metrics(segments_retry)
                    looped_retry, rep_detail = _detect_repetition_loop(text, filter_cfg)
                    transcribe_kwargs = retry_kwargs
                    if looped_retry:
                        rejected = True
                        reject_reason = "repetition_loop"
                else:
                    rejected = True
                    reject_reason = "repetition_loop"
            if rejected:
                text = ""
                logging.info(
                    "echo_voice_transcribe rejected: reject_reason=%s profile=%s detail=%s",
                    reject_reason, asr_profile, rep_detail,
                )
        detected = _echo_normalize_lang(getattr(info, "language", language), text)
        return {
            "text": text,
            "language": detected,
            "duration": getattr(info, "duration", 0.0),
            "metrics": metrics,
            "asr_profile": asr_profile,
            "post_filter": {
                "enabled": bool(filter_cfg.get("enabled", True)),
                "rejected": rejected,
                "reject_reason": reject_reason,
                "retry_applied": retry_applied,
            },
        }
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except Exception:
                pass




def _echo_normalize_lang(lang: str | None, text: str = "") -> str:
    """Echo ASRの言語判定を ja/en の2値に正規化する。"""
    raw = str(lang or "").strip().lower()
    if raw.startswith("ja"):
        return "ja"
    if raw.startswith("en"):
        return "en"
    if any(("぀" <= c <= "ヿ") or ("一" <= c <= "鿿") for c in (text or "")):
        return "ja"
    return "en"

def _echo_do_translate(text: str, src_lang: str, llm_url: str = "") -> str:
    """LLM を使い text を翻訳する。src_lang: 'ja'→英訳, 'en'→和訳。"""
    target = "English" if src_lang == "ja" else "日本語"
    prompt = (
        f"Translate the following text to {target}. "
        "Output only the translation, no explanation.\n\n"
        f"{text}"
    )
    try:
        translate_url = llm_url.strip() or LLM_URL
        model_key = choose_model_for_role("translate")
        if model_key:
            # translate ロール専用URLを試みる
            catalog = get_runtime_model_catalog()
            if model_key in catalog:
                candidate_url = catalog[model_key].get("url", "").strip()
                if candidate_url:
                    translate_url = candidate_url
        content, _ = call_llm(
            [{"role": "user", "content": prompt}],
            llm_url=translate_url,
        )
        return (content or "").strip()
    except Exception as e:
        return f"[翻訳エラー: {e}]"


def _echo_guess_title_from_sentences(sentences: list[dict]) -> str:
    for s in sentences or []:
        text = str(s.get("text", "")).strip() or str(s.get("translated", "")).strip()
        if not text:
            continue
        first = re.split(r"[。．.!?！？\n]", text, maxsplit=1)[0].strip()
        first = re.sub(r"\s+", " ", first)
        if len(first) >= 4:
            return first[:30]
    return "会議録"


def _echo_generate_minutes(session: dict) -> dict:
    """LLM で議事録を生成し Markdown 文字列を返す。"""
    sentences = session.get("sentences", [])
    if not sentences:
        return ""
    import collections as _collections
    import re as _re

    def _guess_fallback_title(_sentences: list) -> str:
        """JSONパース失敗時の簡易タイトル推定。"""
        text_candidates = []
        for s in _sentences:
            t = str(s.get("text", "")).strip()
            tr = str(s.get("translated", "")).strip()
            if t:
                text_candidates.append(t)
            if tr:
                text_candidates.append(tr)
        if not text_candidates:
            return "会議録"

        # 1) 冒頭文から推定（句読点で短く区切る）
        first_line = text_candidates[0]
        first_short = _re.split(r"[。．.!?！？\n]", first_line, maxsplit=1)[0].strip()
        first_short = _re.sub(r"\s+", " ", first_short)
        if len(first_short) >= 4:
            return first_short[:30]

        # 2) 頻出語ベース
        joined = " ".join(text_candidates)
        tokens = _re.findall(r"[A-Za-z0-9一-龥ぁ-んァ-ヶー]{2,}", joined)
        stop_words = {
            "です", "ます", "する", "した", "して", "ある", "いる", "これ", "それ", "ため",
            "the", "and", "for", "with", "that", "this", "from", "have", "will",
        }
        words = [w for w in tokens if w.lower() not in stop_words]
        if words:
            top = [w for w, _ in _collections.Counter(words).most_common(2)]
            if top:
                return f"{'・'.join(top)} 会議"
        return "会議録"
    transcript_text = "\n".join(
        f"[{s.get('lang','?')}] {s.get('text','')} / {s.get('translated','')}"
        for s in sentences
    )
    prompt = (
        "以下は会議の文字起こしと翻訳ペアのリストです。\n"
        "次の要素を含む議事録を日本語の JSON 形式で出力してください:\n"
        '{"title": "...", "summary": "...", "topics": ["..."], "action_items": ["..."], "conclusions": ["..."]}\n\n'
        f"文字起こし:\n{transcript_text[:6000]}"
    )
    try:
        data: dict = {}
        err_holder: dict = {}

        def _minutes_llm_worker():
            try:
                content, _ = call_llm(
                    [{"role": "user", "content": prompt}],
                    llm_url=LLM_URL,
                )
                import json as _json
                raw = (content or "").strip()
                for marker in ["```json", "```"]:
                    if marker in raw:
                        raw = raw.split(marker, 1)[-1].rsplit("```", 1)[0].strip()
                data.update(_json.loads(raw))
            except Exception as _e:
                err_holder["error"] = _e

        t = threading.Thread(target=_minutes_llm_worker, daemon=True)
        t.start()
        t.join(timeout=120)
        if t.is_alive():
            raise TimeoutError("minutes generation timeout (>120s)")
        if "error" in err_holder:
            raise err_holder["error"]
    except Exception:
        fallback_title = _guess_fallback_title(sentences)
        data = {
            "title": fallback_title,
            "summary": "自動生成に失敗しました。文字起こしを参照してください。",
            "topics": [],
            "action_items": [],
            "conclusions": [],
        }
    return data


def _echovault_save_session(session: dict) -> str:
    """EchoVault にセッションファイルを保存。保存した主要ファイル名を返す。"""
    import datetime as _dt

    sentences = session.get("sentences", [])
    audio_buf: bytearray = session.get("buffer", bytearray())
    started_at: _dt.datetime = session.get("started_at", _dt.datetime.now())
    session_id: str = session.get("session_id", "unknown")

    create_minutes = bool(session.get("create_minutes", True))
    # タイトルは文字起こしから推定し、議事録生成の有無に依存しない
    title = _echo_guess_title_from_sentences(sentences)
    # ファイル名に使えない文字を除去
    import re as _re2
    safe_title = _re2.sub(r'[\\/:*?"<>|]', "_", title)[:40]
    safe_title = _re2.sub(r"[\s._-]+", "", safe_title)
    if not safe_title:
        safe_title = "会議録"
    ts = started_at.strftime("%Y-%m-%d_%H-%M")
    base = f"{ts}_{safe_title}"

    # 録音ファイル保存
    if audio_buf:
        buffer_format = str(session.get("buffer_format", "webm")).strip().lower()
        ext = "wav" if buffer_format in {"pcm", "pcm_s16le", "wav"} else "webm"
        audio_path = os.path.join(ECHOVAULT_DIR, f"{base}.{ext}")
        with open(audio_path, "wb") as f:
            f.write(bytes(audio_buf))

    # 文字起こしファイル保存
    transcript_lines = ["| # | 言語 | 原文 | 翻訳 |", "|---|------|------|------|"]
    for i, s in enumerate(sentences, 1):
        flag = "🇯🇵" if s.get("lang") == "ja" else "🇺🇸"
        orig = s.get("text", "").replace("|", "｜")
        trans = s.get("translated", "").replace("|", "｜")
        transcript_lines.append(f"| {i} | {flag} | {orig} | {trans} |")
    transcript_path = os.path.join(ECHOVAULT_DIR, f"{base}_transcript.md")
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(f"# 文字起こし — {title}\n\n")
        f.write(f"**日付:** {started_at.strftime('%Y-%m-%d %H:%M')}  \n")
        f.write(f"**セッション:** {session_id}\n\n")
        f.write("\n".join(transcript_lines) + "\n")

    if not create_minutes:
        return os.path.basename(transcript_path)

    # 議事録Markdown保存
    minutes_data = _echo_generate_minutes(session)
    minutes_path = os.path.join(ECHOVAULT_DIR, f"{base}_minutes.md")
    duration_sec = session.get("duration_sec", 0)
    dur_str = f"{int(duration_sec//3600):02d}:{int((duration_sec%3600)//60):02d}:{int(duration_sec%60):02d}"
    with open(minutes_path, "w", encoding="utf-8") as f:
        f.write(f"# 議事録 — {title}\n\n")
        f.write(f"**日付:** {started_at.strftime('%Y-%m-%d %H:%M')}  \n")
        f.write(f"**録音時間:** {dur_str}  \n")
        f.write(f"**セッション:** {session_id}\n\n")
        if isinstance(minutes_data, dict):
            f.write(f"## サマリー\n{minutes_data.get('summary','')}\n\n")
            topics = minutes_data.get("topics", [])
            if topics:
                f.write("## 議題\n" + "\n".join(f"- {t}" for t in topics) + "\n\n")
            ais = minutes_data.get("action_items", [])
            if ais:
                f.write("## アクションアイテム\n" + "\n".join(f"- [ ] {a}" for a in ais) + "\n\n")
            cons = minutes_data.get("conclusions", [])
            if cons:
                f.write("## 結論\n" + "\n".join(f"- {c}" for c in cons) + "\n\n")
        f.write("---\n## 文字起こし\n\n")
        f.write("\n".join(transcript_lines) + "\n")

    return os.path.basename(minutes_path)


def _echo_schedule_session_save(session_id: str, session: dict):
    """Echo stop後の保存をバックグラウンドで実行する。"""
    sid = str(session_id or "unknown")

    with _echo_save_lock:
        _echo_saving_sessions.add(sid)

    def _worker():
        try:
            fname = _echovault_save_session(session)
            _echo_debug_append(
                session_id=sid,
                seq=None,
                event_type="session_saved",
                filename=fname,
                sentence_count=len(session.get("sentences", [])),
            )
        except Exception as e:
            _echo_debug_append(
                session_id=sid,
                seq=None,
                event_type="session_save_error",
                error=str(e),
                traceback=traceback.format_exc(),
            )
        finally:
            with _echo_save_lock:
                _echo_saving_sessions.discard(sid)
            _echo_sessions.pop(sid, None)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


@app.get("/echo/save-status")
def echo_save_status():
    with _echo_save_lock:
        sessions = sorted(_echo_saving_sessions)
    with _echo_minutes_lock:
        generating_sessions = sorted(_echo_generating_minutes_sessions)
    return {
        "saving": len(sessions) > 0 or len(generating_sessions) > 0,
        "count": len(sessions),
        "session_ids": sessions[:20],
        "minutes_generating_count": len(generating_sessions),
        "minutes_generating_session_ids": generating_sessions[:20],
    }

@app.get("/echo/runtime-status")
def echo_runtime_status():
    with _echo_save_lock:
        saving_sessions = sorted(_echo_saving_sessions)
    with _echo_minutes_lock:
        minutes_sessions = sorted(_echo_generating_minutes_sessions)
    active_sessions = sorted(_echo_sessions.keys())
    return {
        "active": len(active_sessions) > 0 or len(saving_sessions) > 0 or len(minutes_sessions) > 0,
        "active_sessions": active_sessions[:20],
        "saving_sessions": saving_sessions[:20],
        "minutes_sessions": minutes_sessions[:20],
    }


@app.websocket("/echo/stream")
async def echo_stream_ws(websocket: WebSocket):
    import datetime as _dt, asyncio as _asyncio

    await websocket.accept()
    session_id = ""
    session: dict = {}
    language = "auto"
    model_name = "large-v3-turbo"
    chunk_audio_format = "webm"
    chunk_sample_rate = 16000
    chunk_channels = 1
    chunk_mime = "audio/webm"
    asr_profile = "balanced"
    asr_no_speech_threshold = None
    asr_log_prob_threshold = None
    asr_compression_ratio_threshold = None
    asr_device = ""
    processed_chunk_seqs: set[int] = set()
    async def send(payload: dict):
        try:
            await websocket.send_text(json.dumps(payload, ensure_ascii=False))
            if session_id:
                _echo_debug_append(
                    session_id=session_id,
                    seq=payload.get("seq"),
                    event_type="ws_send",
                    payload_type=payload.get("type"),
                )
        except Exception:
            pass

    try:
        while True:
            msg = await websocket.receive()

            if "text" in msg:
                try:
                    ev = json.loads(msg["text"])
                except Exception:
                    continue
                t = ev.get("type", "")

                if t == "start":
                    session_id = str(ev.get("session_id", ""))
                    language   = str(ev.get("language", "auto"))
                    model_name = str(ev.get("model", "large-v3-turbo"))
                    asr_profile = _resolve_asr_profile(ev.get("asr_profile", "balanced"))
                    try:
                        asr_no_speech_threshold = float(ev.get("no_speech_threshold")) if ev.get("no_speech_threshold") is not None else None
                    except Exception:
                        asr_no_speech_threshold = None
                    try:
                        asr_log_prob_threshold = float(ev.get("log_prob_threshold")) if ev.get("log_prob_threshold") is not None else None
                    except Exception:
                        asr_log_prob_threshold = None
                    try:
                        asr_compression_ratio_threshold = float(ev.get("compression_ratio_threshold")) if ev.get("compression_ratio_threshold") is not None else None
                    except Exception:
                        asr_compression_ratio_threshold = None
                    asr_device = str(ev.get("asr_device", "")).strip().lower()
                    chunk_audio_format = str(ev.get("audio_format", "webm")).strip().lower() or "webm"
                    chunk_sample_rate = int(ev.get("sample_rate", 16000) or 16000)
                    chunk_channels = int(ev.get("channels", 1) or 1)
                    chunk_mime = str(ev.get("mime", "audio/webm"))
                    translate_enabled = bool(ev.get("translate_enabled", True))
                    create_minutes = bool(ev.get("create_minutes", translate_enabled))
                    processed_chunk_seqs = set()
                    if asr_device in {"cpu", "cuda"}:
                        try:
                            st = voice_load(model_name=model_name, device=asr_device)
                            # Echo専用モデルは device 変更時に作り直す
                            with _echo_voice_lock:
                                global _echo_voice_model, _echo_voice_model_name
                                _echo_voice_model = None
                                _echo_voice_model_name = ""
                            await send({
                                "type": "ui_log",
                                "level": "info",
                                "summary": f"Echo ASR device set to {st.get('device', asr_device)}",
                            })
                        except Exception as e:
                            await send({
                                "type": "ui_log",
                                "level": "warn",
                                "summary": f"Echo ASR device apply failed: {e}",
                            })
                    asr_filter = _echo_resolve_filter_config(ev.get("asr_post_filter", {}))
                    session = {
                        "session_id": session_id,
                        "buffer": bytearray() if chunk_audio_format not in {"pcm", "pcm_s16le", "s16le", "raw"} else b"",
                        "pcm_buffer": bytearray(),
                        "sentences": [],
                        "started_at": _dt.datetime.now(),
                        "duration_sec": 0,
                        "lang": language,
                        "asr_profile": asr_profile,
                        "asr_no_speech_threshold": asr_no_speech_threshold,
                        "asr_log_prob_threshold": asr_log_prob_threshold,
                        "asr_compression_ratio_threshold": asr_compression_ratio_threshold,
                        "audio_format": chunk_audio_format,
                        "sample_rate": chunk_sample_rate,
                        "channels": chunk_channels,
                        "mime": chunk_mime,
                        "buffer_format": "webm",
                        "asr_filter": asr_filter,
                        "translate_enabled": translate_enabled,
                        "create_minutes": create_minutes,
                        "recent_confirmed_text": "",
                        "prompt_keep_chars": 40,
                    }
                    _echo_sessions[session_id] = session
                    _echo_debug_append(
                        session_id=session_id,
                        seq=None,
                        event_type="session_start",
                        language=language,
                        model_name=model_name,
                        asr_profile=asr_profile,
                        no_speech_threshold=asr_no_speech_threshold,
                        log_prob_threshold=asr_log_prob_threshold,
                        compression_ratio_threshold=asr_compression_ratio_threshold,
                        audio_format=chunk_audio_format,
                        sample_rate=chunk_sample_rate,
                        channels=chunk_channels,
                        asr_filter=asr_filter,
                        translate_enabled=translate_enabled,
                        create_minutes=create_minutes,
                    )
                    await send({"type": "status", "state": "recording"})

                elif t == "resume":
                    session_id = str(ev.get("session_id", ""))
                    if session_id in _echo_sessions:
                        session = _echo_sessions[session_id]
                        language   = session.get("lang", "auto")
                        asr_profile = _resolve_asr_profile(session.get("asr_profile", "balanced"))
                        asr_no_speech_threshold = session.get("asr_no_speech_threshold")
                        asr_log_prob_threshold = session.get("asr_log_prob_threshold")
                        asr_compression_ratio_threshold = session.get("asr_compression_ratio_threshold")
                        chunk_audio_format = str(session.get("audio_format", "webm"))
                        chunk_sample_rate = int(session.get("sample_rate", 16000))
                        chunk_channels = int(session.get("channels", 1))
                        chunk_mime = str(session.get("mime", "audio/webm"))
                        if "asr_filter" not in session:
                            session["asr_filter"] = _echo_resolve_filter_config({})
                        if "translate_enabled" not in session:
                            session["translate_enabled"] = True
                        if "create_minutes" not in session:
                            session["create_minutes"] = bool(session.get("translate_enabled", True))
                    else:
                        # セッション不明の場合は新規として扱う
                        session = {
                            "session_id": session_id,
                            "buffer": bytearray(),
                            "pcm_buffer": bytearray(),
                            "sentences": [],
                            "started_at": _dt.datetime.now(),
                            "duration_sec": 0,
                            "lang": language,
                            "asr_profile": asr_profile,
                            "asr_no_speech_threshold": asr_no_speech_threshold,
                            "asr_log_prob_threshold": asr_log_prob_threshold,
                            "asr_compression_ratio_threshold": asr_compression_ratio_threshold,
                            "audio_format": chunk_audio_format,
                            "sample_rate": chunk_sample_rate,
                            "channels": chunk_channels,
                            "mime": chunk_mime,
                            "buffer_format": "webm",
                            "asr_filter": _echo_resolve_filter_config({}),
                            "translate_enabled": True,
                            "create_minutes": True,
                            "recent_confirmed_text": "",
                            "prompt_keep_chars": 40,
                        }
                        _echo_sessions[session_id] = session
                    # 再接続時は同一チャンク再送を許容するため、重複除外セットを保持
                    _echo_debug_append(
                        session_id=session_id,
                        seq=None,
                        event_type="session_resume",
                    )
                    await send({"type": "status", "state": "recording"})

                elif t == "stop":
                    if session:
                        # 録音時間計算
                        if session.get("started_at"):
                            session["duration_sec"] = (_dt.datetime.now() - session["started_at"]).total_seconds()
                        # stop時は即座にWebSocketを閉じ、保存はバックグラウンドで継続
                        await send({"type": "status", "state": "saving"})
                        await send({"type": "session_stopping", "background_save": True})
                        _echo_debug_append(
                            session_id=session_id,
                            seq=None,
                            event_type="session_stop",
                            duration_sec=session.get("duration_sec", 0),
                            sentence_count=len(session.get("sentences", [])),
                        )
                        _echo_schedule_session_save(session_id, dict(session))
                    break

            elif "bytes" in msg:
                chunk = msg["bytes"]
                if not chunk or not session:
                    continue
                chunk_receive_iso = _echo_debug_now_iso()
                chunk_receive_perf = time.perf_counter()
                seq = None
                audio_bytes = bytes(chunk)
                if len(audio_bytes) >= 5:
                    try:
                        seq = int.from_bytes(audio_bytes[:4], "big", signed=False)
                        audio_bytes = audio_bytes[4:]
                    except Exception:
                        seq = None
                if seq is not None and seq in processed_chunk_seqs:
                    await send({"type": "ack", "seq": seq, "duplicate": True})
                    _echo_debug_append(
                        session_id=session_id,
                        seq=seq,
                        event_type="chunk_duplicate",
                        receive_ts=chunk_receive_iso,
                        bytes=len(audio_bytes or b""),
                        ack_ts=_echo_debug_now_iso(),
                    )
                    continue
                if not audio_bytes:
                    if seq is not None:
                        await send({"type": "ack", "seq": seq})
                        _echo_debug_append(
                            session_id=session_id,
                            seq=seq,
                            event_type="chunk_empty",
                            receive_ts=chunk_receive_iso,
                            bytes=0,
                            ack_ts=_echo_debug_now_iso(),
                        )
                    continue

                _echo_debug_append(
                    session_id=session_id,
                    seq=seq,
                    event_type="chunk_receive",
                    receive_ts=chunk_receive_iso,
                    bytes=len(audio_bytes or b""),
                )

                runtime_audio_format = str(session.get("audio_format", chunk_audio_format)).strip().lower()
                runtime_sample_rate = int(session.get("sample_rate", chunk_sample_rate) or 16000)
                runtime_channels = int(session.get("channels", chunk_channels) or 1)
                runtime_mime = str(session.get("mime", chunk_mime))
                if runtime_audio_format in {"pcm", "pcm_s16le", "s16le", "raw"}:
                    pcm_buf = session.setdefault("pcm_buffer", bytearray())
                    pcm_buf.extend(audio_bytes)
                    session["buffer"] = _echo_pcm_s16le_to_wav_bytes(
                        bytes(pcm_buf), sample_rate=runtime_sample_rate, channels=runtime_channels
                    )
                    session["buffer_format"] = "wav"
                else:
                    session["buffer"].extend(audio_bytes)
                    session["buffer_format"] = "webm"

                await send({"type": "status", "state": "transcribing"})
                try:
                    asr_start = time.perf_counter()
                    _echo_debug_append(
                        session_id=session_id,
                        seq=seq,
                        event_type="asr_start",
                        perf_ms=round(asr_start * 1000, 3),
                    )
                    res = await _asyncio.to_thread(
                        _echo_voice_transcribe,
                        audio_bytes,
                        language,
                        model_name,
                        runtime_audio_format,
                        runtime_sample_rate,
                        runtime_channels,
                        session.get("asr_profile", asr_profile),
                        None,
                        None,
                        session.get("asr_no_speech_threshold", asr_no_speech_threshold),
                        session.get("asr_log_prob_threshold", asr_log_prob_threshold),
                        session.get("asr_compression_ratio_threshold", asr_compression_ratio_threshold),
                        session.get("asr_filter", {}),
                        session.get("recent_confirmed_text", ""),
                    )
                    asr_end = time.perf_counter()
                    text = res.get("text", "").strip()
                    metrics = res.get("metrics", {}) if isinstance(res.get("metrics", {}), dict) else {}
                    post_filter = res.get("post_filter", {}) if isinstance(res.get("post_filter", {}), dict) else {}
                    _echo_debug_append(
                        session_id=session_id,
                        seq=seq,
                        event_type="asr_end",
                        perf_ms=round(asr_end * 1000, 3),
                        elapsed_ms=round((asr_end - asr_start) * 1000, 3),
                        result_chars=len(text),
                        mean_no_speech_prob=metrics.get("mean_no_speech_prob"),
                        mean_avg_logprob=metrics.get("mean_avg_logprob"),
                        post_filter=post_filter,
                    )
                    if bool(post_filter.get("rejected")) and str(post_filter.get("reject_reason", "")).strip() == "repetition_loop":
                        _echo_debug_append(
                            session_id=session_id,
                            seq=seq,
                            event_type="asr_reject",
                            reason="repetition_loop",
                            reject_reason="repetition_loop",
                            result_chars=len(text),
                        )
                        if seq is not None:
                            processed_chunk_seqs.add(seq)
                            await send({"type": "ack", "seq": seq, "filtered": True, "reason": "repetition_loop"})
                        await send({"type": "status", "state": "recording"})
                        continue
                    if text:
                        text_trimmed, overlap_meta = _echo_trim_overlap_text(
                            session.get("recent_confirmed_text", ""), text
                        )
                        text = text_trimmed.strip()
                        _echo_debug_append(
                            session_id=session_id,
                            seq=seq,
                            event_type="asr_overlap_trim",
                            overlap_meta=overlap_meta,
                            result_chars=len(text),
                        )
                    if text:
                        lang_det = _echo_normalize_lang(res.get("language", "auto"), text)
                        rejected, reject_reason = _echo_should_reject_asr_text_with_config(
                            text, metrics, session.get("asr_filter", {}), lang_det
                        )
                        if rejected:
                            _echo_debug_append(
                                session_id=session_id,
                                seq=seq,
                                event_type="asr_reject",
                                reason=reject_reason,
                                result_chars=len(text),
                                mean_no_speech_prob=metrics.get("mean_no_speech_prob"),
                                mean_avg_logprob=metrics.get("mean_avg_logprob"),
                            )
                            if seq is not None:
                                processed_chunk_seqs.add(seq)
                                await send({"type": "ack", "seq": seq, "filtered": True, "reason": reject_reason})
                            await send({"type": "status", "state": "recording"})
                            continue
                        sid = len(session["sentences"])
                        session["sentences"].append({
                            "id": sid, "text": text,
                            "lang": lang_det, "translated": ""
                        })
                        session["recent_confirmed_text"] = _echo_build_recent_prompt_text(
                            session.get("recent_confirmed_text", ""),
                            text,
                            session.get("prompt_keep_chars", 40),
                        )
                        await send({"type": "sentence", "id": sid, "text": text, "lang": lang_det})
                        # 翻訳（ASR後に順次実行）
                        if session.get("translate_enabled", True):
                            tr_start = time.perf_counter()
                            _echo_debug_append(
                                session_id=session_id,
                                seq=seq,
                                event_type="translate_start",
                                perf_ms=round(tr_start * 1000, 3),
                                src_lang=lang_det,
                                source_chars=len(text),
                            )
                            transl = await _asyncio.to_thread(_echo_do_translate, text, lang_det)
                            tr_end = time.perf_counter()
                            _echo_debug_append(
                                session_id=session_id,
                                seq=seq,
                                event_type="translate_end",
                                perf_ms=round(tr_end * 1000, 3),
                                elapsed_ms=round((tr_end - tr_start) * 1000, 3),
                                result_chars=len(transl or ""),
                            )
                            session["sentences"][sid]["translated"] = transl
                            tgt = "en" if lang_det == "ja" else "ja"
                            await send({"type": "translation", "id": sid, "translated": transl, "target_lang": tgt})
                    if seq is not None:
                        processed_chunk_seqs.add(seq)
                        await send({"type": "ack", "seq": seq})
                    _echo_debug_append(
                        session_id=session_id,
                        seq=seq,
                        event_type="chunk_done",
                        send_done_ts=_echo_debug_now_iso(),
                        ack_ts=_echo_debug_now_iso() if seq is not None else None,
                        elapsed_ms=round((time.perf_counter() - chunk_receive_perf) * 1000, 3),
                    )
                except Exception as e:
                    err_tb = traceback.format_exc()
                    print(
                        "[echo/asr-error]",
                        json.dumps(
                            {
                                "seq": seq,
                                "bytes": len(audio_bytes or b""),
                                "mime": runtime_mime,
                                "session_id": session_id,
                            },
                            ensure_ascii=False,
                        ),
                    )
                    logging.exception(
                        "echo ASR error session_id=%s seq=%s bytes=%s mime=%s",
                        session_id,
                        seq,
                        len(audio_bytes or b""),
                        runtime_mime,
                    )
                    severe_summary = (
                        f"[Echo重大エラー] ASR decode失敗 session={session_id} seq={seq} "
                        f"bytes={len(audio_bytes or b'')} mime={runtime_mime}"
                    )
                    _echo_debug_append(
                        session_id=session_id,
                        seq=seq,
                        event_type="chunk_error",
                        receive_ts=chunk_receive_iso,
                        elapsed_ms=round((time.perf_counter() - chunk_receive_perf) * 1000, 3),
                        error=str(e),
                        traceback=err_tb,
                    )
                    await send({"type": "error", "detail": f"ASR error: {e}", "summary": severe_summary})
                    await send({"type": "ui_log", "level": "error", "summary": severe_summary})
                    if seq is not None:
                        processed_chunk_seqs.add(seq)
                        await send({"type": "ack", "seq": seq, "error": True})
                        _echo_debug_append(
                            session_id=session_id,
                            seq=seq,
                            event_type="ack_error",
                            ack_ts=_echo_debug_now_iso(),
                        )
                await send({"type": "status", "state": "recording"})

    except WebSocketDisconnect:
        # 切断時はセッションを保持（クライアントが resume で再接続可能）
        pass
    except Exception as e:
        _echo_debug_append(
            session_id=session_id or "unknown",
            seq=None,
            event_type="ws_exception",
            error=str(e),
            traceback=traceback.format_exc(),
        )
        try:
            await send({"type": "error", "detail": str(e)})
        except Exception:
            pass


@app.get("/debug/echo")
def debug_echo(session_id: str | None = None, limit: int = 100):
    """Echo デバッグイベントの取得API。"""
    lim = max(1, min(int(limit or 100), 1000))
    with _echo_debug_lock:
        if session_id:
            sid = str(session_id)
            events = _echo_debug_events.get(sid, [])
            return {
                "session_id": sid,
                "count": len(events),
                "events": events[-lim:],
            }
        if not _echo_debug_last_updated:
            return {"session_id": None, "count": 0, "events": []}
        latest_sid = max(_echo_debug_last_updated.items(), key=lambda kv: kv[1])[0]
        events = _echo_debug_events.get(latest_sid, [])
        return {
            "session_id": latest_sid,
            "count": len(events),
            "events": events[-lim:],
        }


@app.get("/debu/echo")
def debug_echo_typo_redirect():
    """typo compatibility: /debu/echo -> /debug/echo"""
    return RedirectResponse(url="/debug/echo", status_code=307)


def _echo_group_key_for_filename(fname: str) -> str:
    stem, _ = os.path.splitext(os.path.basename(fname or ""))
    stem = re.sub(r"_(minutes|transcript)$", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_audio$", "", stem, flags=re.IGNORECASE)
    return stem


def _echo_build_upload_base_name(original_filename: str = "") -> str:
    now = datetime.now().strftime("%Y-%m-%d_%H-%M")
    stem = os.path.splitext(os.path.basename(original_filename or ""))[0]
    safe = re.sub(r'[^0-9A-Za-z一-龥ぁ-んァ-ヶー_-]', "_", stem).strip("_")
    safe = re.sub(r"[_-]+", "_", safe)
    if safe:
        safe = safe[:32]
        return f"{now}_upload_{safe}"
    return f"{now}_upload"


def _title_from_filename(fname: str) -> str:
    stem = _echo_group_key_for_filename(fname)
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}_?", "", stem)
    stem = re.sub(r"^upload_?", "", stem, flags=re.IGNORECASE)
    return stem or "会議録"


def _extract_title_from_md(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            for _ in range(40):
                line = f.readline()
                if not line:
                    break
                s = line.strip()
                if s.startswith("#"):
                    s = re.sub(r"^#+\s*", "", s)
                    s = re.sub(r"^(議事録|文字起こし)\s*[—-]\s*", "", s).strip()
                    if s:
                        return s
    except Exception:
        pass
    return ""


def _echo_parse_transcript_markdown(md: str) -> list[dict]:
    rows: list[dict] = []
    for line in (md or "").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if "言語" in s and "原文" in s and "翻訳" in s:
            continue
        if re.fullmatch(r"\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|", s):
            continue
        parts = [p.strip() for p in s.strip("|").split("|")]
        if len(parts) < 4:
            continue
        lang_cell = parts[1]
        lang = "ja" if ("🇯🇵" in lang_cell or "ja" in lang_cell.lower()) else "en"
        text = parts[2].replace("｜", "|")
        translated = parts[3].replace("｜", "|")
        if not text and not translated:
            continue
        rows.append({
            "id": len(rows),
            "lang": lang,
            "text": text,
            "translated": translated,
        })
    return rows


def _echo_generate_minutes_from_transcript_file(transcript_filename: str, overwrite: bool = True) -> str:
    safe = os.path.normpath(transcript_filename or "").lstrip("/\\")
    if not safe.endswith("_transcript.md"):
        raise HTTPException(status_code=400, detail="transcript_filename must end with _transcript.md")
    transcript_path = os.path.join(ECHOVAULT_DIR, safe)
    if not os.path.abspath(transcript_path).startswith(os.path.abspath(ECHOVAULT_DIR)):
        raise HTTPException(status_code=403, detail="不正なパス")
    if not os.path.isfile(transcript_path):
        raise HTTPException(status_code=404, detail="transcript file not found")

    base = re.sub(r"_transcript\.md$", "", safe, flags=re.IGNORECASE)
    minutes_filename = f"{base}_minutes.md"
    minutes_path = os.path.join(ECHOVAULT_DIR, minutes_filename)
    if (not overwrite) and os.path.isfile(minutes_path):
        return minutes_filename

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            md = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"transcript read failed: {e}")

    sentences = _echo_parse_transcript_markdown(md)
    if not sentences:
        raise HTTPException(status_code=400, detail="transcript has no sentence rows")
    started_at = datetime.fromtimestamp(os.path.getmtime(transcript_path))
    session = {
        "session_id": base,
        "sentences": sentences,
        "started_at": started_at,
        "duration_sec": 0,
        "create_minutes": True,
    }
    minutes_data = _echo_generate_minutes(session)
    title = (
        minutes_data.get("title", _extract_title_from_md(transcript_path) or _title_from_filename(transcript_filename))
        if isinstance(minutes_data, dict)
        else (_extract_title_from_md(transcript_path) or _title_from_filename(transcript_filename))
    )
    with open(minutes_path, "w", encoding="utf-8") as f:
        f.write(f"# 議事録 — {title}\n\n")
        f.write(f"**日付:** {started_at.strftime('%Y-%m-%d %H:%M')}  \n")
        f.write(f"**録音時間:** 00:00:00  \n")
        f.write(f"**セッション:** {base}\n\n")
        if isinstance(minutes_data, dict):
            f.write(f"## サマリー\n{minutes_data.get('summary','')}\n\n")
            topics = minutes_data.get("topics", [])
            if topics:
                f.write("## 議題\n" + "\n".join(f"- {t}" for t in topics) + "\n\n")
            ais = minutes_data.get("action_items", [])
            if ais:
                f.write("## アクションアイテム\n" + "\n".join(f"- [ ] {a}" for a in ais) + "\n\n")
            cons = minutes_data.get("conclusions", [])
            if cons:
                f.write("## 結論\n" + "\n".join(f"- {c}" for c in cons) + "\n\n")
        f.write("---\n## 文字起こし\n\n")
        with open(transcript_path, "r", encoding="utf-8") as tf:
            f.write(tf.read())
    return minutes_filename


@app.post("/echo/generate-minutes")
def echo_generate_minutes(req: dict):
    transcript_name = str((req or {}).get("transcript_filename", "")).strip()
    overwrite = bool((req or {}).get("overwrite", True))
    if not transcript_name:
        all_files = sorted(
            [f for f in os.listdir(ECHOVAULT_DIR) if f.endswith("_transcript.md")],
            key=lambda n: os.path.getmtime(os.path.join(ECHOVAULT_DIR, n)),
            reverse=True,
        )
        if not all_files:
            raise HTTPException(status_code=404, detail="transcript not found")
        for cand in all_files:
            cand_minutes = re.sub(r"_transcript\.md$", "_minutes.md", cand, flags=re.IGNORECASE)
            if not os.path.isfile(os.path.join(ECHOVAULT_DIR, cand_minutes)):
                transcript_name = cand
                break
        if not transcript_name:
            transcript_name = all_files[0]

    session_key = re.sub(r"_transcript\.md$", "", transcript_name, flags=re.IGNORECASE)
    with _echo_minutes_lock:
        if session_key in _echo_generating_minutes_sessions:
            raise HTTPException(status_code=409, detail="minutes generation already in progress")
        _echo_generating_minutes_sessions.add(session_key)
    try:
        filename = _echo_generate_minutes_from_transcript_file(transcript_name, overwrite=overwrite)
        return {"ok": True, "transcript": transcript_name, "filename": filename}
    finally:
        with _echo_minutes_lock:
            _echo_generating_minutes_sessions.discard(session_key)


@app.post("/echo/import-audio-transcript")
def echo_import_audio_transcript(req: dict):
    payload = req or {}
    transcript_text = str(payload.get("transcript_text", "")).strip()
    if not transcript_text:
        raise HTTPException(status_code=400, detail="transcript_text required")

    audio_b64 = str(payload.get("audio_base64", "")).strip()
    audio_format = str(payload.get("audio_format", "webm")).strip().lower() or "webm"
    if audio_format not in ECHO_UPLOAD_ALLOWED_FORMATS:
        raise HTTPException(status_code=400, detail=f"unsupported audio format: {audio_format}")

    language = str(payload.get("language", "auto")).strip().lower() or "auto"
    if language not in {"auto", "ja", "en"}:
        language = "auto"
    model = str(payload.get("model", "")).strip()
    asr_profile = _resolve_asr_profile(payload.get("asr_profile", "balanced"))
    original_filename = str(payload.get("original_filename", "")).strip()

    started_at = datetime.now()
    base = _echo_build_upload_base_name(original_filename)
    transcript_filename = f"{base}_transcript.md"
    transcript_path = os.path.join(ECHOVAULT_DIR, transcript_filename)

    audio_filename = ""
    audio_size = 0
    if audio_b64:
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"invalid audio_base64: {e}")
        audio_size = len(audio_bytes)
        if audio_size <= 0:
            raise HTTPException(status_code=400, detail="audio payload empty")
        if audio_size > ECHO_UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=413, detail=f"audio file too large (max {ECHO_UPLOAD_MAX_BYTES} bytes)")
        audio_filename = f"{base}.{audio_format}"
        audio_path = os.path.join(ECHOVAULT_DIR, audio_filename)
        with open(audio_path, "wb") as af:
            af.write(audio_bytes)

    title = _title_from_filename(transcript_filename)
    lang_flag = "🇯🇵" if language == "ja" else ("🇺🇸" if language == "en" else "🌐")
    safe_text = transcript_text.replace("|", "｜")
    lines = ["| # | 言語 | 原文 | 翻訳 |", "|---|------|------|------|", f"| 1 | {lang_flag} | {safe_text} |  |"]
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(f"# 文字起こし — {title}\n\n")
        f.write(f"**日付:** {started_at.strftime('%Y-%m-%d %H:%M')}  \n")
        f.write(f"**セッション:** {base}  \n")
        if model:
            f.write(f"**ASRモデル:** {model}  \n")
        f.write(f"**ASRプロファイル:** {asr_profile}  \n")
        f.write(f"**言語:** {language}\n\n")
        f.write("\n".join(lines) + "\n")

    return {
        "ok": True,
        "session": base,
        "transcript_filename": transcript_filename,
        "audio_filename": audio_filename,
        "audio_size": audio_size,
    }


@app.get("/echo/sessions")
def echo_list_sessions():
    """EchoVault フォルダのファイル一覧を返す。"""
    import datetime as _dt

    files = []
    try:
        for fname in sorted(os.listdir(ECHOVAULT_DIR)):
            fpath = os.path.join(ECHOVAULT_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            stat = os.stat(fpath)
            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
            title = ""
            if ext == "md":
                title = _extract_title_from_md(fpath)
            if not title:
                title = _title_from_filename(fname)
            files.append({
                "name": fname,
                "size": stat.st_size,
                "mtime": _dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "type": ext,
                "group_key": _echo_group_key_for_filename(fname),
            })
    except Exception as e:
        return {"files": [], "error": str(e)}
    # 新しい順
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": files}


@app.get("/echo/sessions/{filename:path}")
def echo_download_session(filename: str):
    """EchoVault ファイルをダウンロード。"""
    safe = os.path.normpath(filename).lstrip("/\\")
    fpath = os.path.join(ECHOVAULT_DIR, safe)
    if not os.path.abspath(fpath).startswith(os.path.abspath(ECHOVAULT_DIR)):
        raise HTTPException(status_code=403, detail="不正なパス")
    if not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    return _FileResponse(fpath, filename=safe)


@app.delete("/echo/sessions/{filename:path}")
def echo_delete_session(filename: str):
    """EchoVault ファイルを削除。"""
    safe = os.path.normpath(filename).lstrip("/\\")
    fpath = os.path.join(ECHOVAULT_DIR, safe)
    if not os.path.abspath(fpath).startswith(os.path.abspath(ECHOVAULT_DIR)):
        raise HTTPException(status_code=403, detail="不正なパス")
    if not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    os.remove(fpath)
    return {"deleted": safe}


# Echo ボイスクローン 参照音声ストレージ (IP → {audio:bytes, sr:int, name:str})
_echo_voice_ref: dict = {}
ECHO_REF_MAX_SECONDS = max(3, int(os.environ.get("ECHO_REF_MAX_SECONDS", "30") or 30))
_ECHO_VOICE_REF_DIR = os.path.join(CA_DATA_DIR, "echo_voice_ref")
_ECHO_VOICE_REF_META = os.path.join(_ECHO_VOICE_REF_DIR, "ref_meta.json")
_ECHO_VOICE_REF_AUDIO = os.path.join(_ECHO_VOICE_REF_DIR, "ref_audio.bin")


def _save_persisted_echo_voice_ref(ref: dict | None):
    os.makedirs(_ECHO_VOICE_REF_DIR, exist_ok=True)
    if not ref or not ref.get("audio"):
        for p in (_ECHO_VOICE_REF_AUDIO, _ECHO_VOICE_REF_META):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        return
    with open(_ECHO_VOICE_REF_AUDIO, "wb") as f:
        f.write(ref.get("audio", b""))
    with open(_ECHO_VOICE_REF_META, "w", encoding="utf-8") as f:
        json.dump({
            "name": ref.get("name", "ref-audio.wav"),
            "sr": int(ref.get("sr", 24000) or 24000),
            "ref_text": ref.get("ref_text", "") or "",
            "trimmed": bool(ref.get("trimmed", False)),
            "max_seconds": int(ECHO_REF_MAX_SECONDS),
            "updated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }, f, ensure_ascii=False, indent=2)


def _load_persisted_echo_voice_ref():
    if not (os.path.isfile(_ECHO_VOICE_REF_AUDIO) and os.path.isfile(_ECHO_VOICE_REF_META)):
        return
    try:
        with open(_ECHO_VOICE_REF_AUDIO, "rb") as f:
            audio = f.read()
        with open(_ECHO_VOICE_REF_META, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if not audio:
            return
        _echo_voice_ref.clear()
        _echo_voice_ref["global"] = {
            "audio": audio,
            "sr": int(meta.get("sr", 24000) or 24000),
            "name": str(meta.get("name", "ref-audio.wav"))[:80],
            "ref_text": str(meta.get("ref_text", "") or ""),
            "trimmed": bool(meta.get("trimmed", False)),
        }
        print(f"[Echo] restored persisted voice reference: {_echo_voice_ref['global']['name']} ({len(audio)} bytes)")
    except Exception as e:
        print(f"[Echo] failed to restore persisted voice reference: {e}")


def _echo_ref_audio_format_from_name(name: str) -> str:
    ext = os.path.splitext((name or "").lower())[1]
    if ext in {".wav"}:
        return "wav"
    if ext in {".mp3"}:
        return "mp3"
    if ext in {".flac"}:
        return "flac"
    if ext in {".ogg", ".oga"}:
        return "ogg"
    if ext in {".m4a", ".mp4"}:
        return "m4a"
    return "webm"


def _trim_ref_audio_if_needed(audio_bytes: bytes, max_seconds: int = ECHO_REF_MAX_SECONDS) -> tuple[bytes, bool]:
    """参照音声が長すぎる場合は先頭 max_seconds 秒にトリム（decode可能な形式のみ）。"""
    try:
        wav, sr = _sf_mod.read(io.BytesIO(audio_bytes))
        if sr <= 0:
            return audio_bytes, False
        max_samples = int(max_seconds * sr)
        if len(wav) <= max_samples:
            return audio_bytes, False
        trimmed = wav[:max_samples]
        buf = io.BytesIO()
        _sf_mod.write(buf, trimmed, samplerate=sr, format="WAV")
        return buf.getvalue(), True
    except Exception:
        # decode不能な形式はそのまま保持（フロント側正規化に期待）
        return audio_bytes, False


@app.post("/echo/voice-ref")
async def echo_voice_ref_post(req: dict, request: Request):
    """ボイスクローン用参照音声を保存する。"""
    import base64 as _b64
    b64 = str(req.get("audio_base64", "")).strip()
    if not b64:
        raise HTTPException(status_code=400, detail="audio_base64 required")
    try:
        audio_bytes = _b64.b64decode(b64)
    except Exception:
        raise HTTPException(status_code=400, detail="audio_base64 decode error")
    name = str(req.get("filename", "ref-audio.wav"))[:80]
    ref_text = str(req.get("ref_text", "") or "").strip()
    audio_format = _echo_ref_audio_format_from_name(name)
    audio_bytes, trimmed = _trim_ref_audio_if_needed(audio_bytes, ECHO_REF_MAX_SECONDS)
    asr_text = ""
    asr_error = ""
    # 参照テキスト未入力時はASRで補完（GPU優先）
    if not ref_text:
        try:
            try:
                voice_load(model_name="large-v3-turbo", device="cuda")
            except Exception:
                voice_load(model_name="large-v3-turbo", device="cpu")
            tr = voice_transcribe(
                audio_bytes,
                language="auto",
                model_name="large-v3-turbo",
                audio_format=audio_format,
                asr_profile="balanced",
            )
            asr_text = (tr.get("text", "") or "").strip()
            if asr_text:
                ref_text = asr_text
        except Exception as e:
            asr_error = str(e)
    _echo_voice_ref.clear()
    _echo_voice_ref["global"] = {
        "audio": audio_bytes,
        "sr": 24000,
        "name": name,
        "ref_text": ref_text,
        "trimmed": trimmed,
    }
    _save_persisted_echo_voice_ref(_echo_voice_ref["global"])
    return {
        "ok": True,
        "name": name,
        "size": len(audio_bytes),
        "ref_text": ref_text,
        "asr_generated": bool(asr_text),
        "asr_error": asr_error,
        "trimmed": trimmed,
        "max_seconds": ECHO_REF_MAX_SECONDS,
    }


@app.get("/echo/voice-ref")
async def echo_voice_ref_get(request: Request):
    """現在のボイスクローン参照音声情報を返す。"""
    import base64 as _b64
    ref = _echo_voice_ref.get("global")
    if not ref:
        return {"set": False}
    return {
        "set": True,
        "name": ref["name"],
        "size": len(ref["audio"]),
        "ref_text": ref.get("ref_text", ""),
        "trimmed": bool(ref.get("trimmed", False)),
        "max_seconds": ECHO_REF_MAX_SECONDS,
        "audio_base64": _b64.b64encode(ref["audio"]).decode("ascii"),
    }


@app.delete("/echo/voice-ref")
async def echo_voice_ref_delete(request: Request):
    """ボイスクローン参照音声をクリアする。"""
    _echo_voice_ref.clear()
    _save_persisted_echo_voice_ref(None)
    return {"ok": True}


# =========================
# TTS (Text-to-Speech) / CPUオンデマンド
# =========================


def _tts_data_dir() -> str:
    d = os.path.join(DEFAULT_CA_DATA_DIR, "tts")
    os.makedirs(d, exist_ok=True)
    return d


def _tts_jtalk_dir() -> str:
    return os.path.join(_tts_data_dir(), "open_jtalk_dic_utf_8-1.11")


def _tts_jtalk_exists() -> bool:
    d = _tts_jtalk_dir()
    return os.path.isdir(d) and bool(os.listdir(d))


def _ref_audio_dir() -> str:
    """参照音声 (voice clone) 保存ディレクトリ"""
    d = os.path.join(DEFAULT_CA_DATA_DIR, "ref_audio")
    os.makedirs(d, exist_ok=True)
    return d



def _build_tts_engine_registry() -> EngineRegistry:
    registry = EngineRegistry(_engines={}, _aliases={"stylebertvits2": "style_bert_vits2", "style-bert-vits2": "style_bert_vits2"})
    registry.register(
        StyleBertVITS2Runtime(),
        aliases=["stylebertvits2", "style-bert-vits2"],
    )
    return registry



_tts_engine_registry = _build_tts_engine_registry()


@app.get("/tts/status")
def tts_status_api():
    response = {
        "jtalk_exists": _tts_jtalk_exists(),
        "tts_startup_health": _tts_startup_health_snapshot,
    }
    response["engine_registry"] = _tts_engine_registry.collect_status()
    return response


@app.get("/debug/TTS")
def tts_debug_api(limit: int = 20):
    errors = _read_recent_tts_debug_entries(limit)
    return {"errors": errors, "count": len(errors)}


@app.get("/tts/voices")
async def tts_voices_api(engine: str = "style_bert_vits2"):
    try:
        runtime = _tts_engine_registry.get(raw_engine=engine)
    except KeyError:
        return {"voices": []}
    return await runtime.voices({"engine": engine})


@app.post("/tts/load")
def tts_load_api(req: dict = {}):
    engine = str(req.get("engine", "style_bert_vits2"))
    engine_key = _tts_engine_registry.resolve_engine_key(engine, req.get("engine_key"))

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def stream():
        try:
            runtime = _tts_engine_registry.get(raw_engine=engine, raw_engine_key=req.get("engine_key"))
        except KeyError:
            yield _sse({"type": "error", "detail": f"不明なエンジン: {engine}"})
            return

        def emit(payload: dict):
            payload.setdefault("engine", engine)
            payload.setdefault("engine_key", engine_key)
            payload.setdefault("engine_alias_normalized", engine_key)
            yield_payloads.append(payload)

        yield_payloads: list[dict] = []
        runtime.load_stream(req, emit=emit)
        for payload in yield_payloads:
            yield _sse(payload)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.post("/tts/unload")
def tts_unload_api(req: dict = {}):
    engine = str(req.get("engine", "style_bert_vits2"))
    try:
        runtime = _tts_engine_registry.get(raw_engine=engine, raw_engine_key=req.get("engine_key"))
    except KeyError:
        raise HTTPException(status_code=400, detail=f"不明なエンジン: {engine}")
    normalized_key = _tts_engine_registry.resolve_engine_key(engine, req.get("engine_key"))
    return {
        **runtime.unload(req),
        "engine": engine,
        "engine_key": normalized_key,
        "engine_alias_normalized": normalized_key,
    }


@app.post("/tts/translate-text")
async def tts_translate_text_api(req: dict = {}):
    """テキストを翻訳する。TTS 読み上げ前の言語変換に使用。
    EN テキスト → JP 翻訳、JP テキスト → EN 翻訳。
    """
    import asyncio as _asyncio_mod
    text = str(req.get("text", "")).strip()
    src_lang = str(req.get("src_lang", "auto"))
    if not text:
        return {"translated": text, "target_lang": src_lang}
    # 言語自動判定（ひらがな・カタカナ・漢字があれば ja）
    if src_lang == "auto":
        src_lang = "ja" if any('\u3040' <= c <= '\u9fff' for c in text) else "en"
    try:
        translated = await _asyncio_mod.to_thread(_echo_do_translate, text, src_lang)
    except Exception as e:
        return {"error": str(e), "translated": text, "target_lang": "en" if src_lang == "ja" else "ja"}
    target_lang = "en" if src_lang == "ja" else "ja"
    text_preview = text.replace("\n", "\\n")[:500]
    translated_preview = str(translated or "").replace("\n", "\\n")[:500]
    _style_bert_vits2_logger.info(
        '[Echo][translate_text] input="%s" output="%s" source_lang=%s target_lang=%s',
        text_preview,
        translated_preview,
        src_lang,
        target_lang,
    )
    return {"translated": translated, "target_lang": target_lang, "src_lang": src_lang}


_REF_AUDIO_ALLOWED_EXT = {".wav", ".mp3", ".flac", ".ogg", ".webm"}

_STYLE_BERT_VITS2_DEFAULT_REPO_DIR = "/app/Style-Bert-VITS2"
_STYLE_BERT_VITS2_DEFAULT_VENV_DIR = "/app/Style-Bert-VITS2/.venv"
_STYLE_BERT_VITS2_DEFAULT_INIT_FLAG = os.path.join(_STYLE_BERT_VITS2_BASE_DIR, ".initialized")
_STYLE_BERT_VITS2_LEGACY_MODELS_DIR = "/app/Style-Bert-VITS2/model_assets"
_STYLE_BERT_VITS2_MODELS_DIR_ENV = "CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR"
_STYLE_BERT_VITS2_UPSTREAM_MODELS_DIR_ENVS = (
    "STYLE_BERT_VITS2_MODELS_DIR",
    "STYLE_BERT_VITS2_MODEL_ASSETS_DIR",
)
_STYLE_BERT_VITS2_REPO_DIR = os.environ.get(
    "CODEAGENT_STYLE_BERT_VITS2_REPO_DIR",
    _STYLE_BERT_VITS2_DEFAULT_REPO_DIR,
)
_STYLE_BERT_VITS2_VENV_DIR = os.environ.get(
    "CODEAGENT_STYLE_BERT_VITS2_VENV_DIR",
    _STYLE_BERT_VITS2_DEFAULT_VENV_DIR,
)
_STYLE_BERT_VITS2_INIT_FLAG = os.environ.get(
    "CODEAGENT_STYLE_BERT_VITS2_INIT_FLAG",
    _STYLE_BERT_VITS2_DEFAULT_INIT_FLAG,
)
_STYLE_BERT_VITS2_UI_ERROR = (
    "Style-Bert-VITS2 の準備に失敗しました。"
    f"検査先: {_STYLE_BERT_VITS2_MODELS_DIR}（legacy: {_STYLE_BERT_VITS2_LEGACY_MODELS_DIR}）。"
    "サーバーログを確認してください。"
)
_style_bert_vits2_init_lock = threading.Lock()
_style_bert_vits2_logger = logging.getLogger("style_bert_vits2")
_STYLE_BERT_VITS2_REQUIRED_MODEL_FILES = {"config.json", "style_vectors.npy"}
_STYLE_BERT_VITS2_REQUIRED_WEIGHT_EXTENSIONS = {".safetensors", ".pth", ".pt", ".onnx"}
_STYLE_BERT_VITS2_IGNORED_MODEL_DIRS = {"__pycache__", "cache", ".cache", "tmp", "temp", "logs"}
_STYLE_BERT_VITS2_PTH_BLOCK_BEGIN = "# --- CodeAgent Style-Bert-VITS2 managed paths (begin) ---"
_STYLE_BERT_VITS2_PTH_BLOCK_END = "# --- CodeAgent Style-Bert-VITS2 managed paths (end) ---"


def _style_bert_vits2_is_valid_model_dir_name(name: str) -> bool:
    normalized = str(name or "").strip()
    if not normalized or normalized.startswith("."):
        return False
    return normalized.lower() not in _STYLE_BERT_VITS2_IGNORED_MODEL_DIRS


def _style_bert_vits2_list_models() -> list[str]:
    os.makedirs(_STYLE_BERT_VITS2_MODELS_DIR, exist_ok=True)
    valid_models: list[str] = []
    for name in sorted(os.listdir(_STYLE_BERT_VITS2_MODELS_DIR)):
        path = os.path.join(_STYLE_BERT_VITS2_MODELS_DIR, name)
        if not os.path.isdir(path):
            continue
        if not _style_bert_vits2_is_valid_model_dir_name(name):
            continue
        if not _style_bert_vits2_model_has_required_assets(path):
            continue
        valid_models.append(name)
    return valid_models


def _style_bert_vits2_is_jp_extra(model_version: str | None) -> bool:
    return "jp-extra" in str(model_version or "").strip().lower()


def _style_bert_vits2_find_assets(model_dir: str) -> tuple[str, str, str]:
    config_path = os.path.join(model_dir, "config.json")
    style_vec_path = os.path.join(model_dir, "style_vectors.npy")
    weight_path = ""
    for root, _dirs, files in os.walk(model_dir):
        for filename in sorted(files):
            _, ext = os.path.splitext(filename)
            if ext.lower() in _STYLE_BERT_VITS2_REQUIRED_WEIGHT_EXTENSIONS:
                weight_path = os.path.join(root, filename)
                break
        if weight_path:
            break
    return config_path, style_vec_path, weight_path


def _style_bert_vits2_describe_model(model_id: str) -> dict:
    model_dir = os.path.join(_STYLE_BERT_VITS2_MODELS_DIR, model_id)
    config_path, style_vec_path, weight_path = _style_bert_vits2_find_assets(model_dir)
    config: dict = {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        config = {}
    model_version = str(config.get("version") or "").strip()
    is_jp_extra = _style_bert_vits2_is_jp_extra(model_version)
    spk2id = config.get("spk2id") if isinstance(config.get("spk2id"), dict) else {}
    style2id = config.get("style2id") if isinstance(config.get("style2id"), dict) else {}
    speakers = [{"name": str(name), "id": int(idx)} for name, idx in spk2id.items()]
    styles = [str(name) for name in style2id.keys()]
    default_style = styles[0] if styles else "Neutral"
    default_speaker_id = speakers[0]["id"] if speakers else 0
    supported_languages = ["JP"] if is_jp_extra else ["JP", "EN", "ZH"]
    if not model_version and not is_jp_extra:
        supported_languages = ["JP"]
    return {
        "model": model_id,
        "display_name": model_id,
        "config_path": config_path,
        "weight_path": weight_path,
        "style_vec_path": style_vec_path,
        "model_version": model_version,
        "is_jp_extra": is_jp_extra,
        "speakers": speakers,
        "styles": styles,
        "default_style": default_style,
        "default_speaker_id": default_speaker_id,
        "supported_languages": supported_languages,
    }


def _style_bert_vits2_model_has_required_assets(model_dir: str) -> bool:
    file_names: set[str] = set()
    has_weight = False
    for _root, _dirs, files in os.walk(model_dir):
        for filename in files:
            file_names.add(filename)
            _, ext = os.path.splitext(filename)
            if ext.lower() in _STYLE_BERT_VITS2_REQUIRED_WEIGHT_EXTENSIONS:
                has_weight = True
    has_required_files = all(req in file_names for req in _STYLE_BERT_VITS2_REQUIRED_MODEL_FILES)
    return has_required_files and has_weight


def _style_bert_vits2_models_ready() -> tuple[bool, list[str], str]:
    models = _style_bert_vits2_list_models()
    if not models:
        return False, models, "no model directories found"
    for model_id in models:
        model_dir = os.path.join(_STYLE_BERT_VITS2_MODELS_DIR, model_id)
        if _style_bert_vits2_model_has_required_assets(model_dir):
            return True, models, ""
    return False, models, "model directories exist but required assets are missing"


def _style_bert_vits2_log_model_locations(prepare_id: str, stage: str) -> None:
    target_models = _style_bert_vits2_list_models()
    legacy_models: list[str] = []
    if os.path.isdir(_STYLE_BERT_VITS2_LEGACY_MODELS_DIR):
        for name in sorted(os.listdir(_STYLE_BERT_VITS2_LEGACY_MODELS_DIR)):
            legacy_path = os.path.join(_STYLE_BERT_VITS2_LEGACY_MODELS_DIR, name)
            if os.path.isdir(legacy_path):
                legacy_models.append(name)
    _style_bert_vits2_logger.info(
        "[Style-Bert-VITS2][prepare:%s] model location check stage=%s target_dir=%s target_models=%s legacy_dir=%s legacy_models=%s",
        prepare_id,
        stage,
        _STYLE_BERT_VITS2_MODELS_DIR,
        target_models,
        _STYLE_BERT_VITS2_LEGACY_MODELS_DIR,
        legacy_models,
    )


def _style_bert_vits2_migrate_legacy_models_if_needed(prepare_id: str) -> tuple[bool, list[str]]:
    if not os.path.isdir(_STYLE_BERT_VITS2_LEGACY_MODELS_DIR):
        return False, []
    os.makedirs(_STYLE_BERT_VITS2_MODELS_DIR, exist_ok=True)
    moved_paths: list[str] = []
    for name in sorted(os.listdir(_STYLE_BERT_VITS2_LEGACY_MODELS_DIR)):
        src = os.path.join(_STYLE_BERT_VITS2_LEGACY_MODELS_DIR, name)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(_STYLE_BERT_VITS2_MODELS_DIR, name)
        if os.path.exists(dst):
            _style_bert_vits2_logger.info(
                "[Style-Bert-VITS2][prepare:%s] legacy fallback skip existing dst=%s (src=%s)",
                prepare_id,
                dst,
                src,
            )
            continue
        try:
            shutil.move(src, dst)
            moved_paths.append(dst)
            _style_bert_vits2_logger.info(
                "[Style-Bert-VITS2][prepare:%s] legacy fallback moved model src=%s dst=%s",
                prepare_id,
                src,
                dst,
            )
        except Exception as move_error:
            shutil.copytree(src, dst, dirs_exist_ok=True)
            moved_paths.append(dst)
            _style_bert_vits2_logger.warning(
                "[Style-Bert-VITS2][prepare:%s] legacy fallback copied model src=%s dst=%s (move failed: %s)",
                prepare_id,
                src,
                dst,
                move_error,
            )
    return bool(moved_paths), moved_paths


def _style_bert_vits2_python_path() -> str:
    return os.path.join(_STYLE_BERT_VITS2_VENV_DIR, "bin", "python")


def _style_bert_vits2_site_packages_dir() -> str | None:
    lib_dir = os.path.join(_STYLE_BERT_VITS2_VENV_DIR, "lib")
    if not os.path.isdir(lib_dir):
        return None
    for name in sorted(os.listdir(lib_dir)):
        if not name.startswith("python"):
            continue
        candidate = os.path.join(lib_dir, name, "site-packages")
        if os.path.isdir(candidate):
            return candidate
    return None


def _style_bert_vits2_pth_file() -> str:
    site_packages = _style_bert_vits2_site_packages_dir()
    if site_packages:
        return os.path.join(site_packages, "_runpod_opt_venv.pth")
    # site-packages を見つけられない場合も、状態表示のため想定パスを返す
    return os.path.join(_STYLE_BERT_VITS2_VENV_DIR, "lib", "python*", "site-packages", "_runpod_opt_venv.pth")


def _style_bert_vits2_validate_prerequisites() -> tuple[bool, str]:
    if not os.path.isdir(_STYLE_BERT_VITS2_REPO_DIR):
        return False, f"repository directory not found: {_STYLE_BERT_VITS2_REPO_DIR}"
    if not os.path.isdir(_STYLE_BERT_VITS2_VENV_DIR):
        return False, f"venv directory not found: {_STYLE_BERT_VITS2_VENV_DIR}"
    python_path = _style_bert_vits2_python_path()
    if not os.path.isfile(python_path):
        return False, f"python executable not found: {python_path}"
    if not os.access(python_path, os.X_OK):
        return False, f"python executable is not executable: {python_path}"
    return True, ""


def _style_bert_vits2_ensure_pth_file() -> tuple[bool, str]:
    site_packages = _style_bert_vits2_site_packages_dir()
    if not site_packages:
        return False, f"site-packages directory not found under: {_STYLE_BERT_VITS2_VENV_DIR}"
    pth_file = os.path.join(site_packages, "_runpod_opt_venv.pth")
    runpod_candidates: list[str] = []
    opt_venv_lib_dir = "/opt/venv/lib"
    if os.path.isdir(opt_venv_lib_dir):
        for name in sorted(os.listdir(opt_venv_lib_dir)):
            candidate = os.path.join(opt_venv_lib_dir, name, "site-packages")
            if name.startswith("python") and os.path.isdir(candidate):
                runpod_candidates.append(candidate)
    if not runpod_candidates:
        runpod_candidates = ["/opt/venv/lib/python3.11/site-packages"]

    managed_paths: list[str] = [_STYLE_BERT_VITS2_REPO_DIR, *runpod_candidates]
    managed_lines = "\n".join(dict.fromkeys(managed_paths))
    managed_block = (
        f"{_STYLE_BERT_VITS2_PTH_BLOCK_BEGIN}\n"
        f"{managed_lines}\n"
        f"{_STYLE_BERT_VITS2_PTH_BLOCK_END}\n"
    )

    try:
        existing_content = ""
        if os.path.isfile(pth_file):
            with open(pth_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

        if _STYLE_BERT_VITS2_PTH_BLOCK_BEGIN in existing_content and _STYLE_BERT_VITS2_PTH_BLOCK_END in existing_content:
            block_pattern = (
                rf"{re.escape(_STYLE_BERT_VITS2_PTH_BLOCK_BEGIN)}\n.*?"
                rf"{re.escape(_STYLE_BERT_VITS2_PTH_BLOCK_END)}\n?"
            )
            new_content = re.sub(block_pattern, managed_block, existing_content, flags=re.DOTALL)
        elif existing_content.strip():
            suffix = "\n" if not existing_content.endswith("\n") else ""
            new_content = f"{existing_content}{suffix}{managed_block}"
        else:
            new_content = managed_block

        with open(pth_file, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return False, f"failed to create pth file: {pth_file} ({e})"
    return True, ""


def _style_bert_vits2_prepare_status() -> dict:
    python_path = _style_bert_vits2_python_path()
    pth_file = _style_bert_vits2_pth_file()
    return {
        "repo_exists": os.path.isdir(_STYLE_BERT_VITS2_REPO_DIR),
        "venv_exists": os.path.isdir(_STYLE_BERT_VITS2_VENV_DIR),
        "python_exists": os.path.isfile(python_path),
        "python_executable": os.path.isfile(python_path) and os.access(python_path, os.X_OK),
        "pth_exists": os.path.isfile(pth_file),
        "init_flag_exists": os.path.isfile(_STYLE_BERT_VITS2_INIT_FLAG),
        "models": _style_bert_vits2_list_models(),
        "repo_dir": _STYLE_BERT_VITS2_REPO_DIR,
        "venv_dir": _STYLE_BERT_VITS2_VENV_DIR,
        "python_path": python_path,
        "pth_file": pth_file,
        "init_flag_file": _STYLE_BERT_VITS2_INIT_FLAG,
        "models_dir": _STYLE_BERT_VITS2_MODELS_DIR,
    }


def _style_bert_vits2_runtime_importable() -> tuple[bool, str]:
    python_path = _style_bert_vits2_python_path()
    try:
        proc = subprocess.run(
            [python_path, "-c", "import style_bert_vits2"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception as e:
        return False, f"runtime import check failed unexpectedly: {e}"

    if proc.returncode == 0:
        return True, ""

    detail = (proc.stderr or proc.stdout or "").strip()
    if detail:
        return False, detail
    return False, f"python exited with code {proc.returncode}"


@app.get("/api/tts/engines")
def api_tts_engines():
    return {"engines": ["style_bert_vits2"]}


@app.post("/api/tts/style-bert-vits2/prepare")
def api_style_bert_vits2_prepare(req: dict = {}):
    req = req or {}
    requested_model = str(req.get("model", "") or "").strip()
    requested_device = str(req.get("device", "") or "").strip().lower()
    with _style_bert_vits2_init_lock:
        prepare_id = uuid.uuid4().hex[:8]
        _style_bert_vits2_logger.info(
            "[Style-Bert-VITS2][prepare:%s] start repo=%s venv=%s models=%s init_flag=%s",
            prepare_id,
            _STYLE_BERT_VITS2_REPO_DIR,
            _STYLE_BERT_VITS2_VENV_DIR,
            _STYLE_BERT_VITS2_MODELS_DIR,
            _STYLE_BERT_VITS2_INIT_FLAG,
        )
        ok, validation_error = _style_bert_vits2_validate_prerequisites()
        if not ok:
            raise StyleBertVITS2Error(
                status_code=500,
                user_message="初期準備失敗: 実行環境を確認してください。",
                log_detail=f"prerequisite check failed: {validation_error}",
            )

        ok, pth_error = _style_bert_vits2_ensure_pth_file()
        if not ok:
            raise StyleBertVITS2Error(
                status_code=500,
                user_message="初期準備失敗: 実行環境を確認してください。",
                log_detail=f"pth ensure failed: {pth_error}",
            )

        status = _style_bert_vits2_prepare_status()
        initialized_now = False
        initialize_action = "already_initialized"
        models_ready, models, model_check_error = _style_bert_vits2_models_ready()
        status["models"] = models
        status["models_ready"] = models_ready
        if not status["init_flag_exists"] or not models_ready:
            initialize_script = os.path.join(_STYLE_BERT_VITS2_REPO_DIR, "initialize.py")
            runtime_ok, runtime_error = _style_bert_vits2_runtime_importable()
            needs_initialize = (not runtime_ok) or (not models_ready)
            if needs_initialize:
                if not os.path.isfile(initialize_script):
                    raise StyleBertVITS2Error(
                        status_code=500,
                        user_message="initialize失敗: initialize.py が見つかりません。",
                        log_detail=(
                            f"initialize.py not found: {initialize_script}\n"
                            f"runtime import check error: {runtime_error}\n"
                            f"model readiness error: {model_check_error}"
                        ),
                    )
                python_path = _style_bert_vits2_python_path()
                cmd = [python_path, "initialize.py"]
                initialize_env = {**os.environ, "CI": "1", _STYLE_BERT_VITS2_MODELS_DIR_ENV: _STYLE_BERT_VITS2_MODELS_DIR}
                for env_name in _STYLE_BERT_VITS2_UPSTREAM_MODELS_DIR_ENVS:
                    initialize_env[env_name] = _STYLE_BERT_VITS2_MODELS_DIR
                initialize_action = "executed"
                _style_bert_vits2_logger.info(
                    "[Style-Bert-VITS2][prepare:%s] running initialize.py cmd=%s cwd=%s reason(runtime_ok=%s, models_ready=%s) models_dir_env=%s",
                    prepare_id,
                    cmd,
                    _STYLE_BERT_VITS2_REPO_DIR,
                    runtime_ok,
                    models_ready,
                    _STYLE_BERT_VITS2_MODELS_DIR,
                )
                try:
                    proc = subprocess.run(
                        cmd,
                        cwd=_STYLE_BERT_VITS2_REPO_DIR,
                        check=True,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        env=initialize_env,
                        timeout=900,
                    )
                    _style_bert_vits2_logger.info(
                        "[Style-Bert-VITS2][prepare:%s] initialize.py completed code=0",
                        prepare_id,
                    )
                    if proc.stdout:
                        _style_bert_vits2_logger.info(
                            "[Style-Bert-VITS2][prepare:%s] initialize.py stdout:\n%s",
                            prepare_id,
                            proc.stdout,
                        )
                    if proc.stderr:
                        _style_bert_vits2_logger.info(
                            "[Style-Bert-VITS2][prepare:%s] initialize.py stderr:\n%s",
                            prepare_id,
                            proc.stderr,
                        )
                except subprocess.TimeoutExpired as e:
                    raise StyleBertVITS2Error(
                        status_code=500,
                        user_message="initialize失敗: 初期化スクリプトがタイムアウトしました。",
                        log_detail=f"initialize.py timeout: {e}",
                    )
                except subprocess.CalledProcessError as e:
                    raise StyleBertVITS2Error(
                        status_code=500,
                        user_message="initialize失敗: 初期化スクリプトの実行に失敗しました。",
                        log_detail=(
                            "initialize.py failed: "
                            f"code={e.returncode}\nstdout:\n{e.stdout}\nstderr:\n{e.stderr}\n"
                            f"runtime import check error(before initialize): {runtime_error}\n"
                            f"model readiness error(before initialize): {model_check_error}"
                        ),
                    )
                except Exception as e:
                    raise StyleBertVITS2Error(
                        status_code=500,
                        user_message="initialize失敗: 初期化処理で予期しないエラーが発生しました。",
                        log_detail=f"initialize.py failed unexpectedly: {e}\n{traceback.format_exc()}",
                    )
            else:
                initialize_action = "skipped_importable_and_models_ready"
                _style_bert_vits2_logger.info(
                    "[Style-Bert-VITS2][prepare:%s] skip initialize.py because runtime import check and model assets check passed.",
                    prepare_id,
                )

            _style_bert_vits2_log_model_locations(prepare_id, "after_initialize_before_ready_check")
            models_ready_after, models_after, model_check_error_after = _style_bert_vits2_models_ready()
            if not models_ready_after:
                migrated, migrated_paths = _style_bert_vits2_migrate_legacy_models_if_needed(prepare_id)
                if migrated:
                    _style_bert_vits2_logger.info(
                        "[Style-Bert-VITS2][prepare:%s] legacy fallback migrated models=%s",
                        prepare_id,
                        migrated_paths,
                    )
                    _style_bert_vits2_log_model_locations(prepare_id, "after_legacy_fallback")
                    models_ready_after, models_after, model_check_error_after = _style_bert_vits2_models_ready()
            status["models"] = models_after
            status["models_ready"] = models_ready_after
            if not models_ready_after:
                raise StyleBertVITS2Error(
                    status_code=500,
                    user_message=(
                        "initialize失敗: モデルアセットの準備が完了しませんでした。"
                        f"検査先: {_STYLE_BERT_VITS2_MODELS_DIR}（legacy: {_STYLE_BERT_VITS2_LEGACY_MODELS_DIR}）"
                    ),
                    log_detail=(
                        "model assets not ready after prepare. "
                        f"before={model_check_error}, after={model_check_error_after}, models={models_after}"
                    ),
                )
            os.makedirs(os.path.dirname(_STYLE_BERT_VITS2_INIT_FLAG), exist_ok=True)
            with open(_STYLE_BERT_VITS2_INIT_FLAG, "w", encoding="utf-8") as f:
                f.write(datetime.utcnow().isoformat())
            initialized_now = True
            status["init_flag_exists"] = True
        status["initialized_now"] = initialized_now
        status["prepare_id"] = prepare_id
        status["initialize_action"] = initialize_action
        status["ready"] = bool(
            status["repo_exists"]
            and status["venv_exists"]
            and status["python_exists"]
            and status["python_executable"]
            and status["pth_exists"]
            and status["init_flag_exists"]
            and status.get("models_ready", False)
        )
        if status["ready"]:
            status["runtime_prepare"] = None
            try:
                runtime = _tts_engine_registry.get(raw_engine_key="style_bert_vits2")
                if hasattr(runtime, "prepare"):
                    preload_model = requested_model
                    if preload_model and not _style_bert_vits2_is_valid_model_dir_name(preload_model):
                        preload_model = ""
                    if preload_model:
                        ensure_model_exists(preload_model, _STYLE_BERT_VITS2_MODELS_DIR)
                    elif status.get("models"):
                        preload_model = status["models"][0]
                    prepare_payload = {"model": preload_model} if preload_model else {}
                    if requested_device:
                        prepare_payload["device"] = requested_device
                    preload_result = runtime.prepare(prepare_payload)
                    status["runtime_prepare"] = preload_result
                    if isinstance(status["runtime_prepare"], dict):
                        status["runtime_prepare"]["device"] = preload_result.get("device")
                        status["runtime_prepare"]["warmup_elapsed_ms"] = preload_result.get("warmup_elapsed_ms")
                        status["runtime_prepare"]["cache_hit"] = preload_result.get("cache_hit")
                    _style_bert_vits2_logger.info(
                        "[Style-Bert-VITS2][prepare:%s] worker_prepare result=%s",
                        prepare_id,
                        preload_result,
                    )
            except StyleBertVITS2Error:
                raise
            except Exception as preload_error:
                _style_bert_vits2_logger.info(
                    "[Style-Bert-VITS2][prepare:%s] worker prepare info: %s",
                    prepare_id,
                    preload_error,
                )

        _style_bert_vits2_logger.info(
            "[Style-Bert-VITS2][prepare:%s] done ready=%s initialized_now=%s action=%s",
            prepare_id,
            status["ready"],
            initialized_now,
            initialize_action,
        )
        return status
    # NOTE: ここに到達するのはStyleBertVITS2Errorを握りつぶした場合のみ
    raise HTTPException(status_code=500, detail=_STYLE_BERT_VITS2_UI_ERROR)


@app.exception_handler(StyleBertVITS2Error)
async def _handle_style_bert_vits2_error(_request: Request, exc: StyleBertVITS2Error):
    _style_bert_vits2_logger.error("[Style-Bert-VITS2] %s", exc.log_detail, exc_info=True)
    inspected_dirs = f"検査先: {_STYLE_BERT_VITS2_MODELS_DIR}（legacy: {_STYLE_BERT_VITS2_LEGACY_MODELS_DIR}）"
    user_message = exc.user_message if inspected_dirs in exc.user_message else f"{exc.user_message} {inspected_dirs}"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": user_message, "user_message": user_message},
    )


@app.get("/api/tts/style-bert-vits2/models")
def api_style_bert_vits2_models():
    models = _style_bert_vits2_list_models()
    detailed = [_style_bert_vits2_describe_model(model_id) for model_id in models]
    return {"models": models, "model_details": detailed}


@app.post("/api/tts/style-bert-vits2/preview-normalization")
def api_style_bert_vits2_preview_normalization(req: dict):
    try:
        runtime = _tts_engine_registry.get(raw_engine="style_bert_vits2")
    except KeyError:
        raise HTTPException(status_code=500, detail="style_bert_vits2 runtime unavailable")
    if not isinstance(runtime, StyleBertVITS2Runtime):
        raise HTTPException(status_code=500, detail="style_bert_vits2 runtime mismatch")
    return runtime.build_normalization_preview(req)


@app.post("/api/tts/style-bert-vits2/models/upload")
async def api_style_bert_vits2_models_upload(
    file: UploadFile,
    model_id: str = Form(default=""),
):
    _style_bert_vits2_logger.info(
        "[Style-Bert-VITS2][models/upload] start filename=%s model_id=%s models_dir=%s",
        file.filename,
        model_id,
        _STYLE_BERT_VITS2_MODELS_DIR,
    )
    imported = await import_model_zip(file, model_id=model_id or None)
    _style_bert_vits2_logger.info(
        "[Style-Bert-VITS2][models/upload] done model_id=%s path=%s models_dir=%s",
        imported["model_id"],
        imported["path"],
        _STYLE_BERT_VITS2_MODELS_DIR,
    )
    return {"model_id": imported["model_id"], "models": _style_bert_vits2_list_models()}


@app.post("/tts/ref-audio/upload")
async def tts_ref_audio_upload(file: UploadFile):
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in _REF_AUDIO_ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"許可されていない拡張子: {ext}. 使用可能: {sorted(_REF_AUDIO_ALLOWED_EXT)}")
    safe_name = os.path.basename(file.filename or "ref_audio" + ext)
    dest = os.path.join(_ref_audio_dir(), safe_name)
    data = await file.read()
    with open(dest, "wb") as f:
        f.write(data)
    return {"filename": safe_name, "size": len(data)}


@app.get("/tts/ref-audio/list")
def tts_ref_audio_list():
    d = _ref_audio_dir()
    result = []
    for fname in sorted(os.listdir(d)):
        ext = os.path.splitext(fname)[-1].lower()
        if ext in _REF_AUDIO_ALLOWED_EXT:
            fpath = os.path.join(d, fname)
            result.append({"filename": fname, "size": os.path.getsize(fpath)})
    return {"files": result}


@app.delete("/tts/ref-audio/{filename}")
def tts_ref_audio_delete(filename: str):
    safe_name = os.path.basename(filename)
    fpath = os.path.join(_ref_audio_dir(), safe_name)
    if not os.path.isfile(fpath):
        raise HTTPException(status_code=404, detail=f"ファイルが見つかりません: {safe_name}")
    os.remove(fpath)
    return {"deleted": safe_name}


@app.post("/tts/synthesize")
def tts_synthesize_api(req: dict):
    from fastapi.responses import Response as FastAPIResponse
    request_id = str(req.get("request_id") or uuid.uuid4().hex[:8])
    engine = str(req.get("engine", "style_bert_vits2"))
    text = str(req.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="text required")
    _style_bert_vits2_logger.info(
        "[TTS][synthesize:%s] request engine=%s text_len=%d model=%s speaker=%s",
        request_id,
        engine,
        len(text),
        str(req.get("model", "")).strip(),
        str(req.get("speaker_name", "")).strip() or str(req.get("speaker", "")).strip(),
    )
    req["request_id"] = request_id
    normalized_key = _tts_engine_registry.resolve_engine_key(engine, req.get("engine_key"))
    if normalized_key == "style_bert_vits2":
        model = str(req.get("model", "")).strip() or "koharune-ami"
        req["model"] = model
        ensure_model_exists(model, _STYLE_BERT_VITS2_MODELS_DIR)
        batch_items = _build_tts_batch_items_from_text(req, text)
        if len(batch_items) >= 2:
            batch_req = dict(req)
            batch_req["output"] = "zip"
            batch_req["items"] = batch_items
            batch_req["text"] = text
            batch_req["request_id"] = request_id
            _style_bert_vits2_logger.info(
                "[TTS][synthesize:%s] style_bert_vits2 multi-sentence batch route items=%d",
                request_id,
                len(batch_items),
            )
            batch_result = _run_tts_synthesize_batch(batch_req)
            zip_bytes = batch_result.get("zip_bytes", b"") if isinstance(batch_result, dict) else b""
            wav_chunks: list[bytes] = []
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                for item in manifest.get("items", []):
                    fname = str(item.get("filename", "")).strip()
                    if fname and fname.lower().endswith(".wav"):
                        wav_chunks.append(zf.read(fname))
            merged_wav = _merge_wav_bytes(wav_chunks)
            if not merged_wav:
                raise HTTPException(status_code=500, detail="batch synthesis returned empty audio")
            return FastAPIResponse(content=merged_wav, media_type="audio/wav")
    try:
        runtime = _tts_engine_registry.get(raw_engine=engine, raw_engine_key=req.get("engine_key"))
    except KeyError:
        raise HTTPException(status_code=400, detail=f"不明なエンジン: {engine}")

    try:
        audio_bytes, media_type = runtime.synthesize(req)
        _style_bert_vits2_logger.info(
            "[TTS][synthesize:%s] success engine=%s media_type=%s bytes=%d",
            request_id,
            normalized_key,
            media_type,
            len(audio_bytes or b""),
        )
    except ValueError as e:
        error_message = str(e)
        try:
            err_payload = json.loads(error_message)
        except Exception:
            err_payload = None
        if isinstance(err_payload, dict) and int(err_payload.get("status_code") or 0) == 422:
            _style_bert_vits2_logger.warning("[TTS][synthesize:%s] unprocessable_entity: %s", request_id, err_payload.get("error"))
            raise HTTPException(
                status_code=422,
                detail={
                    "error": err_payload.get("error") or "Unprocessable TTS input",
                    "text_preview": err_payload.get("text_preview") or "",
                    "effective_language": err_payload.get("effective_language") or "JP",
                    "model_version": err_payload.get("model_version") or "",
                },
            )
        if "worker protocol error" in error_message.lower():
            _style_bert_vits2_logger.error("[TTS][synthesize:%s] worker_protocol_error: %s", request_id, e)
            raise HTTPException(status_code=500, detail=error_message)
        _style_bert_vits2_logger.warning("[TTS][synthesize:%s] validation_error: %s", request_id, e)
        raise HTTPException(status_code=400, detail=error_message)
    except Exception as e:
        _style_bert_vits2_logger.error(
            "[TTS][synthesize:%s] failed engine=%s error=%s",
            request_id,
            normalized_key,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=str(e))
    return FastAPIResponse(content=audio_bytes, media_type=media_type)


def _sample_rate_from_wav_bytes(audio_bytes: bytes) -> int:
    import wave as _wave

    with _wave.open(io.BytesIO(audio_bytes), "rb") as wf:
        return int(wf.getframerate())


def _split_tts_batch_sentences(text: str) -> list[str]:
    clean = str(text or "").strip()
    if not clean:
        return []
    parts = re.split(r"(?<=[。！？\n])|(?<=[.!?])\s+", clean)
    return [str(part or "").strip() for part in parts if str(part or "").strip()]


def _build_tts_batch_items_from_text(req: dict, text: str) -> list[dict]:
    sentences = _split_tts_batch_sentences(text)
    if len(sentences) <= 1:
        return []
    items: list[dict] = []
    propagate_keys = (
        "style",
        "style_weight",
        "speaker",
        "speaker_name",
        "language",
        "speed",
        "caller",
        "route",
        "use_translation",
        "text_source",
        "raw_text",
        "translated_text",
        "sbv2_jp_extra_text_normalization",
        "sbv2_jp_extra_english_to_katakana",
        "sbv2_jp_extra_emoji_policy",
        "sbv2_jp_extra_symbol_policy",
        "sbv2_jp_extra_url_policy",
        "sbv2_jp_extra_non_japanese_policy",
        "length",
        "sdp_ratio",
        "noise",
        "noise_w",
        "split_interval",
        "line_split",
        "pitch_scale",
        "intonation_scale",
    )
    for index, sentence in enumerate(sentences, start=1):
        item: dict[str, object] = {"id": f"seg-{index:03d}", "text": sentence}
        for key in propagate_keys:
            if key in req:
                item[key] = req.get(key)
        items.append(item)
    return items


def _merge_wav_bytes(wav_chunks: list[bytes]) -> bytes:
    import wave as _wave

    valid_chunks = [chunk for chunk in wav_chunks if chunk]
    if not valid_chunks:
        return b""
    if len(valid_chunks) == 1:
        return valid_chunks[0]

    first_reader = _wave.open(io.BytesIO(valid_chunks[0]), "rb")
    try:
        params = first_reader.getparams()
        merged_frames = [first_reader.readframes(first_reader.getnframes())]
    finally:
        first_reader.close()

    for chunk in valid_chunks[1:]:
        reader = _wave.open(io.BytesIO(chunk), "rb")
        try:
            same_format = (
                reader.getnchannels() == params.nchannels
                and reader.getsampwidth() == params.sampwidth
                and reader.getframerate() == params.framerate
                and reader.getcomptype() == params.comptype
            )
            if not same_format:
                return valid_chunks[0]
            merged_frames.append(reader.readframes(reader.getnframes()))
        finally:
            reader.close()

    out = io.BytesIO()
    writer = _wave.open(out, "wb")
    try:
        writer.setparams(params)
        for frames in merged_frames:
            writer.writeframes(frames)
    finally:
        writer.close()
    return out.getvalue()


def _run_tts_synthesize_batch(req: dict):
    engine = str(req.get("engine", "style_bert_vits2"))
    model = str(req.get("model", "")).strip()
    device = str(req.get("device", "")).strip()
    output_format = str(req.get("output", "json") or "json").strip().lower()
    items = req.get("items")
    request_id = str(req.get("request_id") or uuid.uuid4().hex[:8])

    if output_format not in {"json", "zip", "wav"}:
        raise HTTPException(status_code=400, detail='output must be "json", "zip", or "wav"')
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items must be a non-empty list")

    normalized_key = _tts_engine_registry.resolve_engine_key(engine, req.get("engine_key"))
    if normalized_key == "style_bert_vits2" and not model:
        model = "koharune-ami"
    if normalized_key == "style_bert_vits2":
        ensure_model_exists(model, _STYLE_BERT_VITS2_MODELS_DIR)

    try:
        runtime = _tts_engine_registry.get(raw_engine=engine, raw_engine_key=req.get("engine_key"))
    except KeyError:
        raise HTTPException(status_code=400, detail=f"不明なエンジン: {engine}")

    # バッチ開始時に prepare 相当を実行（Style-Bert-VITS2 の事前ロード）
    if normalized_key == "style_bert_vits2" and hasattr(runtime, "prepare"):
        try:
            runtime.prepare({"model": model, "device": device})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"prepare failed: {e}")

    common_payload = dict(req)
    common_payload["engine"] = engine
    common_payload["request_id"] = request_id
    common_payload["model"] = model
    common_payload["device"] = device

    project = str(req.get("project", "default") or "default")
    job_id = job_create(
        project=project,
        message=f"tts_synthesize_batch request_id={request_id}",
        mode="tts_batch",
    )
    job_update_status(project, job_id, "running")
    seq = 0
    batch_started_at = time.perf_counter()
    item_elapsed_history_ms: list[int] = []
    current_item_id: str | None = None
    current_item_index = 0

    def _batch_progress_data(
        *,
        total: int,
        current: int,
        current_id: str | None,
        error: str | None = None,
    ) -> dict:
        elapsed_ms = int((time.perf_counter() - batch_started_at) * 1000)
        if current <= 0:
            estimated_remaining_ms = None
        elif current >= total:
            estimated_remaining_ms = 0
        elif item_elapsed_history_ms:
            estimated_remaining_ms = int(sum(item_elapsed_history_ms) / len(item_elapsed_history_ms) * (total - current))
        else:
            estimated_remaining_ms = None
        data = {
            "total": total,
            "current": current,
            "current_id": current_id,
            "elapsed_ms": elapsed_ms,
            "estimated_remaining_ms": estimated_remaining_ms,
        }
        if error:
            data["error"] = error
        return data

    def _append_batch_step(event_type: str, data: dict):
        nonlocal seq
        job_append_step(project, job_id, seq, event_type, data)
        seq += 1

    manifest: list[dict] = []
    json_items: list[dict] = []
    wav_chunks: list[bytes] = []
    zip_buffer = io.BytesIO() if output_format == "zip" else None
    zip_file = zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) if zip_buffer else None
    zip_tempdir_ctx = tempfile.TemporaryDirectory(prefix=f"tts_batch_{request_id}_") if output_format == "zip" else None

    try:
        total = len(items)
        _append_batch_step(
            "tts_batch_started",
            _batch_progress_data(total=total, current=0, current_id=None),
        )
        for index, raw_item in enumerate(items):
            if not isinstance(raw_item, dict):
                raise HTTPException(status_code=400, detail=f"items[{index}] must be object")
            text = str(raw_item.get("text", "")).strip()
            if not text:
                raise HTTPException(status_code=400, detail=f"items[{index}].text required")

            item_id = str(raw_item.get("id") or f"item-{index+1:03d}")
            current = index + 1
            current_item_id = item_id
            current_item_index = current
            _append_batch_step(
                "tts_batch_item_started",
                _batch_progress_data(total=total, current=current, current_id=item_id),
            )
            item_payload = dict(common_payload)
            item_payload.update(raw_item)
            item_payload["text"] = text
            # ループ中は model/device を固定し、再ロードを防ぐ
            item_payload["model"] = model
            item_payload["device"] = device
            item_payload["request_id"] = f"{request_id}-{index+1:03d}"

            item_infer_ms: int | None = None
            item_total_ms: int | None = None
            batch_route_mode = "legacy_b64"
            audio_bytes = b""
            sample_rate = 0
            output_bytes = 0
            started = time.perf_counter()
            if output_format == "zip" and normalized_key == "style_bert_vits2" and hasattr(runtime, "synthesize_batch_item_raw"):
                assert zip_tempdir_ctx is not None
                out_path = os.path.join(zip_tempdir_ctx.name, f"{index+1:03d}_{item_id}.wav")
                item_payload["return_mode"] = "file"
                item_payload["out_path"] = out_path
                raw_result = runtime.synthesize_batch_item_raw(item_payload)
                batch_route_mode = "raw_file"
                item_total_ms = int(raw_result.get("total_elapsed_ms") or 0)
                item_infer_ms = int(raw_result.get("infer_elapsed_ms") or 0)
                sample_rate = int(raw_result.get("sample_rate") or 0)
                output_bytes = int(raw_result.get("output_bytes") or 0)
                audio_path = str(raw_result.get("out_path") or out_path)
                if not audio_path or not os.path.isfile(audio_path):
                    raise HTTPException(status_code=500, detail=f"batch output file missing: {audio_path}")
            else:
                audio_bytes, _media_type = runtime.synthesize(item_payload)
                sample_rate = _sample_rate_from_wav_bytes(audio_bytes)
                output_bytes = len(audio_bytes)
            if output_format == "wav":
                if batch_route_mode == "raw_file":
                    with open(audio_path, "rb") as f:
                        wav_chunks.append(f.read())
                else:
                    wav_chunks.append(audio_bytes)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            item_elapsed_history_ms.append(elapsed_ms)
            filename = f"{index+1:03d}_{item_id}.wav"

            row = {
                "id": item_id,
                "filename": filename,
                "text": text,
                "elapsed_ms": elapsed_ms,
                "infer_ms": item_infer_ms,
                "total_ms": item_total_ms,
                "sample_rate": sample_rate,
                "output_bytes": output_bytes,
            }
            manifest.append(row)

            if output_format == "json":
                json_items.append(
                    {
                        **row,
                        "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
                    }
                )
            elif output_format == "zip":
                assert zip_file is not None
                if batch_route_mode == "raw_file":
                    zip_file.write(audio_path, arcname=filename)
                else:
                    zip_file.writestr(filename, audio_bytes)
            _style_bert_vits2_logger.info(
                "[TTS][batch_item:%s] idx=%d id=%s route=%s elapsed_ms=%d infer_ms=%s total_ms=%s bytes=%d",
                request_id,
                current,
                item_id,
                batch_route_mode,
                elapsed_ms,
                "-" if item_infer_ms is None else str(item_infer_ms),
                "-" if item_total_ms is None else str(item_total_ms),
                output_bytes,
            )
            _append_batch_step(
                "tts_batch_item_done",
                {
                    **_batch_progress_data(total=total, current=current, current_id=item_id),
                    "item_elapsed_ms": elapsed_ms,
                    "infer_ms": item_infer_ms,
                    "total_ms": item_total_ms,
                    "sample_rate": sample_rate,
                    "output_bytes": output_bytes,
                },
            )
            current_item_id = None

        _append_batch_step(
            "tts_batch_done",
            _batch_progress_data(total=total, current=total, current_id=None),
        )
        job_update_status(project, job_id, "done")

        if output_format == "json":
            return {
                "request_id": request_id,
                "engine": normalized_key,
                "model": model,
                "device": device,
                "project": project,
                "job_id": job_id,
                "items": json_items,
            }

        if output_format == "wav":
            merged_wav = _merge_wav_bytes(wav_chunks)
            if not merged_wav:
                raise HTTPException(status_code=500, detail="batch synthesis returned empty audio")
            return {
                "wav_bytes": merged_wav,
                "request_id": request_id,
                "engine": normalized_key,
                "model": model,
                "device": device,
                "project": project,
                "job_id": job_id,
            }

        assert zip_file is not None and zip_buffer is not None
        zip_file.writestr(
            "manifest.json",
            json.dumps(
                {
                    "request_id": request_id,
                    "engine": normalized_key,
                    "model": model,
                    "device": device,
                    "items": manifest,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        zip_file.close()
        zip_bytes = zip_buffer.getvalue()
        return {
            "zip_bytes": zip_bytes,
            "request_id": request_id,
            "engine": normalized_key,
            "model": model,
            "device": device,
            "project": project,
            "job_id": job_id,
        }
    except ValueError as e:
        error_message = str(e)
        err_payload = None
        try:
            err_payload = json.loads(error_message)
        except Exception:
            err_payload = None
        if isinstance(err_payload, dict) and int(err_payload.get("status_code") or 0) == 422:
            _style_bert_vits2_logger.warning(
                "[TTS][synthesize_batch:%s] unprocessable_entity: %s",
                request_id,
                err_payload.get("error"),
            )
            detail_payload = {
                "error": err_payload.get("error") or "Unprocessable TTS input",
                "text_preview": err_payload.get("text_preview") or "",
                "effective_language": err_payload.get("effective_language") or "JP",
                "model_version": err_payload.get("model_version") or "",
            }
            _append_batch_step(
                "tts_batch_failed",
                _batch_progress_data(
                    total=len(items),
                    current=current_item_index,
                    current_id=current_item_id,
                    error=str(detail_payload.get("error")),
                ),
            )
            job_update_status(project, job_id, "error")
            raise HTTPException(status_code=422, detail=detail_payload)
        _append_batch_step(
            "tts_batch_failed",
            _batch_progress_data(
                total=len(items),
                current=current_item_index,
                current_id=current_item_id,
                error=error_message,
            ),
        )
        job_update_status(project, job_id, "error")
        raise HTTPException(status_code=400, detail=error_message)
    except HTTPException:
        _append_batch_step(
            "tts_batch_failed",
            _batch_progress_data(
                total=len(items),
                current=current_item_index,
                current_id=current_item_id,
                error="http_exception",
            ),
        )
        job_update_status(project, job_id, "error")
        raise
    except Exception as e:
        _append_batch_step(
            "tts_batch_failed",
            _batch_progress_data(
                total=len(items),
                current=current_item_index,
                current_id=current_item_id,
                error=str(e),
            ),
        )
        job_update_status(project, job_id, "error")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if zip_file is not None:
            zip_file.close()
        if zip_tempdir_ctx is not None:
            zip_tempdir_ctx.cleanup()

@app.post("/tts/synthesize-batch")
def tts_synthesize_batch_api(req: dict):
    result = _run_tts_synthesize_batch(req)
    if isinstance(result, dict) and "wav_bytes" in result:
        wav_bytes = result["wav_bytes"]
        request_id = result["request_id"]
        project = result["project"]
        job_id = result["job_id"]
        return StreamingResponse(
            io.BytesIO(wav_bytes),
            media_type="audio/wav",
            headers={
                "Content-Disposition": f'attachment; filename="tts_batch_{request_id}.wav"',
                "X-Project": project,
                "X-Job-Id": job_id,
            },
        )
    if isinstance(result, dict) and "zip_bytes" in result:
        zip_bytes = result["zip_bytes"]
        request_id = result["request_id"]
        project = result["project"]
        job_id = result["job_id"]
        return StreamingResponse(
            io.BytesIO(zip_bytes),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="tts_batch_{request_id}.zip"',
                "X-Project": project,
                "X-Job-Id": job_id,
            },
        )
    return result


# =========================
# エンドポイント: /agent/start, /agent/stop
# =========================

@app.post("/agent/start")
async def agent_start(req: Request):
    body = await req.json()
    project = _require_project_key(body)
    task = str((body or {}).get("task", "")).strip()
    initial_context = (body or {}).get("initial_context")

    with agent_state_lock:
        project_state = _get_or_create_agent_project_state(project)
        if project_state.running:
            return {"status": "already_running", "project": project}
        project_state.running = True
        project_state.loopCount = 0
        project_state.currentTask = task or None
        project_state.lastActions = []
        project_state.session = AgentSession(project_key=project)
        project_state.tool_registry_logged = False

        ingest_meta = {
            "turn_id": None,
            "intent": "bootstrap",
            "extracted_tasks": [],
            "queued_count": 0,
        }

        if task:
            ingest_meta = project_state.session.ingest_user_turn(task)
        elif isinstance(initial_context, str) and initial_context.strip():
            ingest_meta = project_state.session.ingest_user_turn(initial_context.strip())
        elif isinstance(initial_context, list):
            loaded = 0
            for turn in initial_context:
                if not isinstance(turn, dict):
                    continue
                if str(turn.get("role", "")).lower() != "user":
                    continue
                text = str(turn.get("text", "")).strip()
                if not text:
                    continue
                project_state.session.ingest_user_turn(text)
                loaded += 1
            ingest_meta = {
                "turn_id": None,
                "intent": "bootstrap",
                "extracted_tasks": list(project_state.session.inferred_tasks[-5:]),
                "queued_count": len(project_state.session.execution_queue),
                "loaded_turns": loaded,
            }
        should_log_registry = not project_state.tool_registry_logged
        project_state.tool_registry_logged = True

    if should_log_registry:
        _log_agent_registry_tools(project, reason="/agent/start")

    return {"status": "started", "project": project, "mode": "session_bootstrap", "ingest": ingest_meta}


@app.post("/agent/stop")
async def agent_stop(req: Request):
    body = await req.json()
    project = _require_project_key(body)
    with agent_state_lock:
        project_state = agent_state.projects.get(project)
        if project_state is None or not project_state.running:
            return {"status": "stopped", "project": project}
        project_state.running = False
        project_state.currentTask = None
        project_state.lastActions = []
        project_state.session = None
    return {"status": "stopped", "project": project}


@app.post("/agent/turn")
async def agent_turn(req: Request):
    body = await req.json()
    message = str((body or {}).get("message", "")).strip()
    project = _require_project_key(body)
    llm_url = str((body or {}).get("llm_url", "")).strip()
    max_steps = int((body or {}).get("max_steps", 20) or 20)
    requested_search_enabled = (body or {}).get("search_enabled") if isinstance(body, dict) else None
    effective_search_enabled = _resolve_effective_search_enabled(requested_search_enabled)
    if not message:
        raise HTTPException(status_code=400, detail="message is empty")

    with agent_state_lock:
        project_state = agent_state.projects.get(project)
        if project_state is None or not project_state.running:
            raise HTTPException(status_code=409, detail="agent is not running")
        if project_state.session is None:
            project_state.session = AgentSession(project_key=project)
        ingest_meta = project_state.session.ingest_user_turn(message)
        should_log_registry = not project_state.tool_registry_logged
        project_state.tool_registry_logged = True

    if should_log_registry:
        _log_agent_registry_tools(project, reason="/agent/turn:first")

    chat_result = execute_chat_with_optional_web_search(
        message=message,
        max_steps=min(max_steps, 6),
        search_enabled=effective_search_enabled,
        llm_url=_resolve_runtime_llm_url(llm_url),
        chat_history=(project_state.session.conversation_state.get("turns", [])[:-1] if project_state.session else []),
    )
    reply = str(chat_result.get("output", ""))
    with agent_state_lock:
        current_state = agent_state.projects.get(project)
        if current_state and current_state.session is not None:
            current_state.session.append_assistant_turn(reply)

    queue_result = _execute_agent_session_queue(
        req_message=message,
        project=project,
        llm_url=llm_url,
        max_steps=max_steps,
        search_enabled=effective_search_enabled,
    )
    return {
        "status": "ok",
        "conversation": {"reply": reply, "usage": chat_result.get("usage", {}), "logs": chat_result.get("logs", [])},
        "search_enabled": effective_search_enabled,
        "ingest": ingest_meta,
        "execution": queue_result,
    }


@app.get("/agent/tasks")
def agent_tasks(project: str = ""):
    project_key = _require_project_key({"project": project})
    with agent_state_lock:
        project_state = agent_state.projects.get(project_key)
        if project_state is None or not project_state.running:
            raise HTTPException(status_code=409, detail="agent is not running")
        session = project_state.session
        if session is None:
            return {"tasks": []}
        tasks = [
            {
                "id": task.id,
                "title": task.title,
                "detail": task.detail,
                "priority": task.priority,
                "confidence": task.confidence,
                "status": task.status,
                "source_turn_id": task.source_turn_id,
                "rationale": task.rationale,
                "aliases": list(task.aliases),
                "revision_history": list(task.revision_history),
            }
            for task in session.list_tasks()
        ]
    return {"project": project_key, "tasks": tasks}


@app.post("/agent/tasks/{task_id}/decision")
def agent_task_decision(task_id: str, req: AgentTaskDecisionRequest):
    project_key = _require_project_key({"project": req.project})
    with agent_state_lock:
        project_state = agent_state.projects.get(project_key)
        if project_state is None or not project_state.running:
            raise HTTPException(status_code=409, detail="agent is not running")
        session = project_state.session
        if session is None:
            raise HTTPException(status_code=404, detail="agent session not found")
        task = session.decide_task(task_id, req.decision)
        if task is None:
            raise HTTPException(status_code=400, detail="invalid decision or task not found")
    return {"ok": True, "task_id": task.id, "status": task.status}


@app.post("/agent/tasks/{task_id}/run")
def agent_task_run(task_id: str, req: AgentTaskProjectRequest):
    project_key = _require_project_key({"project": req.project})
    with agent_state_lock:
        project_state = agent_state.projects.get(project_key)
        if project_state is None or not project_state.running:
            raise HTTPException(status_code=409, detail="agent is not running")
        session = project_state.session
        if session is None:
            raise HTTPException(status_code=404, detail="agent session not found")
        task = session.find_task_by_name_or_alias(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status in {"done", "running"}:
            return {"ok": True, "task_id": task.id, "status": task.status}
        task.status = "accepted"
    return {"ok": True, "task_id": task.id, "status": task.status}


@app.post("/agent/tasks/{task_id}/cancel")
def agent_task_cancel(task_id: str, req: AgentTaskProjectRequest):
    project_key = _require_project_key({"project": req.project})
    with agent_state_lock:
        project_state = agent_state.projects.get(project_key)
        if project_state is None or not project_state.running:
            raise HTTPException(status_code=409, detail="agent is not running")
        session = project_state.session
        if session is None:
            raise HTTPException(status_code=404, detail="agent session not found")
        task = session.find_task_by_name_or_alias(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status in {"done", "failed"}:
            return {"ok": True, "task_id": task.id, "status": task.status}
        task.status = "cancelled"
    return {"ok": True, "task_id": task.id, "status": task.status}


@app.post("/agent/tasks/{task_id}/revise")
def agent_task_revise(task_id: str, req: AgentTaskReviseRequest):
    project_key = _require_project_key({"project": req.project})
    with agent_state_lock:
        project_state = agent_state.projects.get(project_key)
        if project_state is None or not project_state.running:
            raise HTTPException(status_code=409, detail="agent is not running")
        session = project_state.session
        if session is None:
            raise HTTPException(status_code=404, detail="agent session not found")
        instruction = (req.instruction or "").strip()
        if not instruction:
            title_hint = (req.title or "").strip()
            detail_hint = (req.detail or "").strip()
            instruction = " / ".join([part for part in [title_hint, detail_hint] if part])
        task = session.revise_task(task_id, instruction, source_turn_id="api-revise")
        if task is None:
            raise HTTPException(status_code=400, detail="task not found or instruction is empty")
    return {
        "ok": True,
        "task_id": task.id,
        "status": task.status,
        "detail": task.detail,
        "revision_count": len(task.revision_history),
    }


# =========================
# エンドポイント: /task（SSEストリーミング）
# =========================

@app.post("/task")
def task(req: ChatRequest):
    """
    タスク分解 → 各タスクの進捗をSSEでリアルタイム配信する。
    イベント形式: data: <JSON>\n\n
    """
    def event(payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def stream():
        # Step 1: plan
        yield event({"type": "planning"})
        todos = plan(req.message, req.project)
        total = len(todos)
        yield event({"type": "plan", "tasks": todos, "total": total})

        results = []
        context = ""

        for idx, todo in enumerate(todos):
            # タスク開始イベント
            yield event({
                "type": "task_start",
                "task_id": todo["id"],
                "title": todo["title"],
                "index": idx,
                "total": total,
                "pct": int(idx / total * 100)
            })

            task_result = execute_task(
                task_detail=todo["detail"],
                context=context,
                max_steps=req.max_steps,
                project=req.project
            )

            results.append({"task_id": todo["id"], "title": todo["title"], **task_result})

            # タスク完了イベント
            yield event({
                "type": "task_done",
                "task_id": todo["id"],
                "title": todo["title"],
                "status": task_result["status"],
                "output": task_result.get("output", ""),
                "steps": task_result.get("steps", []),
                "index": idx,
                "total": total,
                "pct": int((idx + 1) / total * 100)
            })

            if task_result["status"] == "done":
                context = f"タスク「{todo['title']}」完了: {task_result['output']}"
            else:
                for remaining in todos[idx + 1:]:
                    results.append({
                        "task_id": remaining["id"],
                        "title": remaining["title"],
                        "status": "skipped",
                        "reason": f"前のタスク「{todo['title']}」が失敗したためスキップ"
                    })
                    yield event({"type": "task_done", "task_id": remaining["id"],
                                 "title": remaining["title"], "status": "skipped",
                                 "index": todos.index(remaining), "total": total,
                                 "pct": int((todos.index(remaining)+1)/total*100)})
                break

        done_count = sum(1 for r in results if r.get("status") == "done")
        all_done = done_count == len(todos)

        # 完了イベント
        yield event({
            "type": "complete",
            "summary": f"{total}タスク中{done_count}件完了",
            "success": all_done,
            "tasks": results,
            "pct": 100
        })

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return {
        "summary": f"{len(todos)}タスク中{done_count}件完了",
        "success": all_done,
        "tasks": results
    }


# =========================
# SSE: リアルタイム進捗ストリーム /stream
# =========================

@app.post("/stream")
async def stream(req: ChatRequest):
    """
    Server-Sent Events でエージェントの進捗をリアルタイム配信する。
    UIはこれを使う。/chat と /task は後方互換で残す。
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def event(type_: str, data: dict) -> str:
        return f"data: {json.dumps({'type': type_, **data}, ensure_ascii=False)}\n\n"

    def run_stream():
        # ── チャットモード: プランナーとエージェントループを完全にバイパス ──
        if req.mode == "chat":
            chat_url = _resolve_runtime_llm_url(req.llm_url)
            # 会話履歴を構築
            history_msgs: list[dict] = []
            for h in (req.chat_history or [])[-8:]:
                role = h.get("role", "user")
                text = str(h.get("text", h.get("content", "")))[:800]
                if role in ("user", "assistant") and text:
                    history_msgs.append({"role": role, "content": text})
            msgs = [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                *history_msgs,
                {"role": "user", "content": req.message},
            ]
            msgs = _trim_messages(msgs, _current_n_ctx, reserve_output=_calc_reserve_output(_current_n_ctx, ratio=0.22))
            yield event("plan", {
                "tasks": [{"id": 1, "title": req.message[:60], "detail": req.message}],
                "total": 1,
            })
            yield event("task_start", {
                "task_id": 1, "title": req.message[:60],
                "task_num": 1, "total_tasks": 1, "progress": 0,
            })
            reply = ""
            for _sev in call_llm_chat_streaming(msgs, llm_url=chat_url):
                if _sev["type"] == "llm_streaming":
                    yield _sev  # TPS進捗をそのまま転送
                elif _sev["type"] == "llm_done":
                    reply = _sev["content"]
                elif _sev["type"] == "llm_error":
                    yield event("task_error", {"error": _sev["error"], "steps": []})
                    return
            yield event("tool_call", {
                "task_id": 1, "step": 0, "step_num": 1, "max_steps": 1,
                "action": "final", "thought": "", "output": reply,
                "progress": 100, "tps": 0,
            })
            yield event("done", {
                "output": reply, "total_steps": 1,
                "all_steps": [{"step": 0, "type": "final", "thought": "", "output": reply}],
            })
            return

        # ── taskモード: plan + エージェントループ ──
        todos = plan(req.message, project=req.project)
        total_tasks = len(todos)

        yield event("plan", {
            "tasks": todos,
            "total": total_tasks
        })

        all_steps = []
        context = ""

        for task_idx, todo in enumerate(todos):
            task_num = task_idx + 1

            yield event("task_start", {
                "task_id": todo["id"],
                "title": todo["title"],
                "task_num": task_num,
                "total_tasks": total_tasks,
                "progress": int((task_idx / total_tasks) * 85)  # 完了まで85%をタスクに配分
            })

            # execute_task をステップごとにyieldできるよう展開
            project_dir = os.path.join(WORK_DIR, req.project)
            os.makedirs(project_dir, exist_ok=True)
            project_prompt = _build_system_prompt(req.project)

            user_content = todo["detail"]
            if context:
                user_content = f"【前のタスクの結果】\n{context}\n\n【今のタスク】\n{todo['detail']}"

            messages = [
                {"role": "system", "content": project_prompt},
                {"role": "user", "content": user_content}
            ]

            steps = []
            consecutive_errors = 0
            task_status = "error"
            task_output = ""

            for step in range(req.max_steps):
                # ステップ進捗: タスク内のステップをそのタスクの配分幅に分散
                task_share = 85 / total_tasks
                step_progress = int(
                    (task_idx / total_tasks) * 85
                    + (step / req.max_steps) * task_share
                )

                reply, _step_usage = call_llm_chat(messages)
                # APIがprompt_tokensを返さない場合はメッセージ長から推定
                if not _step_usage.get("prompt_tokens"):
                    _step_usage = {**_step_usage, "prompt_tokens": _estimate_tokens(messages)}
                action_obj, reply, retry_usage = _parse_task_v2_action_with_retry(
                    reply=reply,
                    messages=messages,
                    llm_url="",
                    parser=_model_manager.current_parser,
                    max_retry=1,
                )
                if retry_usage.get("prompt_tokens"):
                    _step_usage = retry_usage

                if action_obj is None:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        yield event("tool_call", {
                            "task_id": todo["id"], "step": step,
                            "step_num": step + 1, "max_steps": req.max_steps,
                            "action": "error",
                            "progress": step_progress, "tps": 0,
                        })
                        break
                    messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)})
                    messages.append({"role": "user", "content": "JSON形式で出力してください。"})
                    continue
                else:
                    consecutive_errors = 0

                action = action_obj.get("action", "")
                thought = action_obj.get("thought", "")
                tool_input = action_obj.get("args", {})

                if action == "final":
                    task_status = "done"
                    task_output = action_obj.get("output", "")
                    steps.append({"step": step, "type": "final"})
                    yield event("tool_call", {
                        "task_id": todo["id"],
                        "step": step,
                        "step_num": step + 1,
                        "max_steps": req.max_steps,
                        "action": "final",
                        "progress": int(((task_idx + 1) / total_tasks) * 85),
                        "prompt_tokens": _step_usage.get("prompt_tokens", 0),
                        "completion_tokens": _step_usage.get("completion_tokens", 0),
                        "tps": _step_usage.get("tps", 0),
                    })
                    break

                if action not in TOOLS:
                    messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)})
                    messages.append({"role": "user", "content": f"ERROR: 不明なツール '{action}'"})
                    continue

                try:
                    result = TOOLS[action](**tool_input)
                except TypeError as e:
                    result = f"ERROR: 引数エラー - {e}"

                step_data = {
                    "step": step, "type": "tool_call",
                    "action": action,
                    "input": tool_input,
                    "result_preview": str(result)[:300]
                }
                steps.append(step_data)
                all_steps.append(step_data)

                yield event("tool_call", {
                    "task_id": todo["id"],
                    "step": step,
                    "step_num": step + 1,
                    "max_steps": req.max_steps,
                    "action": action,
                    "result_preview": str(result)[:200],
                    "progress": step_progress,
                    "prompt_tokens": _step_usage.get("prompt_tokens", 0),
                    "completion_tokens": _step_usage.get("completion_tokens", 0),
                    "tps": _step_usage.get("tps", 0),
                })

                messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)})
                messages.append({"role": "user", "content": f"実行結果:\n{result}"})

            yield event("task_done", {
                "task_id": todo["id"],
                "title": todo["title"],
                "status": task_status,
                "output": task_output,
                "steps": steps,
                "task_num": task_num,
                "total_tasks": total_tasks,
                "progress": int(((task_idx + 1) / total_tasks) * 85)
            })

            if task_status == "done":
                context = f"タスク「{todo['title']}」完了: {task_output}"
            else:
                # 残タスクをスキップ
                for remaining in todos[task_idx + 1:]:
                    yield event("task_done", {
                        "task_id": remaining["id"],
                        "title": remaining["title"],
                        "status": "skipped",
                        "output": "",
                        "steps": [],
                        "progress": int(((task_idx + 1) / total_tasks) * 85)
                    })
                break

        # 最終イベント
        yield event("done", {
            "progress": 100,
            "all_steps": all_steps
        })

    def generate():
        for chunk in run_stream():
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

# =========================
# プロジェクト管理API
# =========================

@app.get("/projects")
def list_projects():
    """プロジェクト一覧を返す"""
    projects = []
    for name in sorted(os.listdir(WORK_DIR)):
        path = os.path.join(WORK_DIR, name)
        if os.path.isdir(path) and not name.startswith("_") and '{' not in name:
            files = []
            for root, _, fs in os.walk(path):
                for f in fs:
                    rel = os.path.relpath(os.path.join(root, f), path)
                    files.append(rel)
            projects.append({"name": name, "files": files, "file_count": len(files)})
    if not projects:
        # defaultプロジェクトを自動作成
        os.makedirs(os.path.join(WORK_DIR, "default"), exist_ok=True)
        projects = [{"name": "default", "files": [], "file_count": 0}]
    return {"projects": projects}

@app.post("/projects")
def create_project(req: ProjectRequest):
    """新規プロジェクトを作成する"""
    name = _normalize_project_name(req.name)
    path = _project_root(name)
    existed = os.path.isdir(path)
    has_files = existed and any(os.scandir(path))
    if existed and has_files and not req.overwrite:
        return {"created": name, "existed": True, "overwritten": False, "file_count": len(list(os.scandir(path)))}
    if req.overwrite:
        _reset_project_dir(name)
    else:
        os.makedirs(path, exist_ok=True)
    return {"created": name, "existed": existed, "overwritten": bool(req.overwrite and existed)}

@app.delete("/projects/{name}")
def delete_project(name: str):
    """プロジェクトを削除する"""
    import shutil
    path = _project_root(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Project not found")
    shutil.rmtree(path)
    return {"deleted": name}

@app.get("/projects/{name}/files")
def project_files(name: str):
    """Project file list for preview / file manager tabs."""
    path = _project_root(name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Project not found")
    files = []
    for root, dirs, fs in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in fs:
            rel = os.path.relpath(os.path.join(root, f), path).replace("\\", "/")
            if _should_hide_preview_path(rel):
                continue
            files.append(rel)
    return {"project": name, "files": sorted(files)}

@app.delete("/projects/{name}/files/{path:path}")
def delete_project_file(name: str, path: str):
    project_root = _project_root(name)
    if not os.path.isdir(project_root):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        full, rel = _project_path(name, path)
        full = _assert_within_project_root(name, full)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not os.path.exists(full):
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.isfile(full):
        raise HTTPException(status_code=400, detail="Target is not a file")
    os.remove(full)
    return {"project": _normalize_project_name(name), "deleted": rel}

@app.get("/projects/{name}/files/{path:path}/download")
def download_project_file(name: str, path: str):
    project_root = _project_root(name)
    if not os.path.isdir(project_root):
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        full, rel = _project_path(name, path)
        full = _assert_within_project_root(name, full)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=full,
        media_type="application/octet-stream",
        filename=os.path.basename(rel),
    )


@app.get("/projects/{name}/download")
def download_project(name: str, background_tasks: BackgroundTasks):
    """プロジェクトフォルダをzip化してダウンロードする。"""
    project = _normalize_project_name(name)
    root = _project_root(project)
    if not os.path.isdir(root):
        raise HTTPException(status_code=404, detail="Project not found")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    zip_path = tmp.name
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for base, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for fname in files:
                    abs_path = os.path.join(base, fname)
                    rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
                    zf.write(abs_path, arcname=f"{project}/{rel_path}")
    except Exception as e:
        try:
            os.remove(zip_path)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"zip creation failed: {e}")

    background_tasks.add_task(lambda p=zip_path: os.path.exists(p) and os.remove(p))
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"{project}.zip",
    )

def execute_task_stream(task_detail: str, context: str = "", max_steps: int = 15, project: str = "default", search_enabled: bool = True, llm_url: str = "", job_id: str = "", task_id: int = 0, task_title: str = ""):
    """
    execute_task のジェネレータ版。
    各ステップでイベントをyieldする。
    """
    project_dir = os.path.join(WORK_DIR, project)
    os.makedirs(project_dir, exist_ok=True)
    # GPT-OSS-20Bはチャンネル形式を出すためSYSTEM_PROMPTで特殊トークン禁止を明示済み
    project_prompt = _build_system_prompt(project)
    user_content = task_detail
    if context:
        user_content = f"【前のタスクの結果】\n{context}\n\n【今のタスク】\n{task_detail}"

    # パーマネントメモリ参照: タスクに関連する過去の知識を注入
    try:
        mem_query = f"{task_title} {task_detail}"
        mem_hits = memory_search(mem_query, limit=3)
        if mem_hits:
            mem_note = "\n\n【過去の経験・知識（メモリ）】\n" + "\n".join(
                f"- [{h['category']}] {h['title']}: {h['content'][:200]}"
                for h in mem_hits
            )
            user_content = user_content + mem_note
    except Exception:
        pass

    if _should_prefetch_web_for_task(task_detail, search_enabled):
        prefetch_result = _run_lightweight_prefetch_nexus_search_for_context(
            task_detail,
            num_results=_search_num_results,
            mode="quick",
            depth="quick",
            max_queries=1,
        )
        prefetch_block = _build_task_prefetch_context_block(prefetch_result, max_items=_search_num_results)
        if prefetch_block:
            user_content = f"{user_content}\n\n{prefetch_block}"
        event_payload = prefetch_result.get("event_payload") or {}
        yield {
            "type": "lightweight_search_prefetch",
            "task_id": task_id,
            "title": task_title,
            "query": prefetch_result.get("query", ""),
            "ok": bool(prefetch_result.get("ok", False)),
            "items": prefetch_result.get("items", []),
            "provider_errors": event_payload.get("provider_errors", {}),
            "non_fatal": bool(event_payload.get("non_fatal", False)),
            "message": event_payload.get("message") or prefetch_result.get("message", ""),
        }

    messages = [
        {"role": "system", "content": project_prompt},
        {"role": "user", "content": user_content}
    ]

    # スキルをTOOLSに動的追加（ホットリロード対応）
    active_tools = dict(TOOLS)
    if not search_enabled:
        # search_enabled=false の場合は nexus_web_search ツールを公開しない。
        active_tools.pop("nexus_web_search", None)
    skill_fns = _load_skill_functions()
    active_tools.update(skill_fns)
    # ファイル操作ツールにprojectを自動バインド
    _pt_list = ("read_file", "write_file", "edit_file", "get_outline",
                "patch_function", "list_files", "search_in_files",
                "make_dir", "move_path", "delete_path",
                "run_shell", "run_python", "run_file", "run_server", "setup_venv")
    import functools as _ft2
    for _pt in _pt_list:
        if _pt in active_tools:
            active_tools[_pt] = _ft2.partial(active_tools[_pt], project=project)
    steps = []
    consecutive_errors = 0
    repeated_failures: dict[str, int] = {}
    stagnation_window = 6
    stagnation_threshold = 0.8
    exploration_actions = {"list_files", "get_outline", "read_file", "search_in_files"}
    edit_actions = {"edit_file", "write_file", "patch_function"}
    recent_actions: list[str] = []
    recent_exploration_notes: list[str] = []
    stagnation_events = 0
    last_stagnation_summary = ""

    def _shorten(v, max_len: int = 80) -> str:
        s = str(v).replace("\n", " ").strip()
        if len(s) > max_len:
            return s[:max_len] + "..."
        return s

    def _summarize_recent_exploration(limit: int = 4) -> str:
        if not recent_exploration_notes:
            return "（直近の探索結果要約なし）"
        return " / ".join(recent_exploration_notes[-limit:])

    def _build_read_file_excerpt(text: str, max_chars: int = 4000) -> tuple[str, int]:
        result_size = len(text)
        if result_size <= max_chars:
            return text, result_size
        head = max_chars // 2
        tail = max_chars - head
        omitted = result_size - max_chars
        excerpt = (
            text[:head]
            + f"\n\n[... {omitted} chars omitted ...]\n\n"
            + text[-tail:]
        )
        return excerpt, result_size

    for step in range(max_steps):
        messages = _trim_messages(messages, _current_n_ctx, reserve_output=_calc_reserve_output(_current_n_ctx, ratio=0.30))

        if _llm_streaming:
            # ストリーミングモード: トークン生成中にTPS/tokenをリアルタイム通知
            reply, usage = None, {"prompt_tokens": 0, "completion_tokens": 0, "tps": 0}
            try:
                for _sev in call_llm_chat_streaming(messages, llm_url=llm_url):
                    if _sev["type"] == "llm_streaming":
                        yield _sev  # フロントエンドへTPS進捗を転送
                    elif _sev["type"] == "llm_done":
                        reply, usage = _sev["content"], _sev["usage"]
                        if not usage.get("prompt_tokens"):
                            usage = {**usage, "prompt_tokens": _estimate_tokens(messages)}
                    elif _sev["type"] == "llm_error":
                        raise HTTPException(
                            status_code=_sev.get("status_code", 502),
                            detail=_sev["error"]
                        )
            except HTTPException as _ctx_ex:
                if _ctx_ex.status_code == 413:
                    print(f"[execute_task_stream] context exceeded (stream), force trimming...")
                    messages = _trim_messages(messages, _current_n_ctx // 2, reserve_output=_calc_reserve_output(_current_n_ctx // 2, ratio=0.22))
                    for _sev in call_llm_chat_streaming(messages, llm_url=llm_url):
                        if _sev["type"] == "llm_done":
                            reply, usage = _sev["content"], _sev["usage"]
                        elif _sev["type"] == "llm_error":
                            yield {"type": "task_error", "error": f"Context exceeded after trim: {_sev['error']}", "steps": steps}
                            return
                    if reply is None:
                        yield {"type": "task_error", "error": "Context exceeded after trim", "steps": steps}
                        return
                else:
                    yield {"type": "task_error", "error": str(_ctx_ex.detail), "steps": steps}
                    return
        else:
            # 非ストリーミングモード: 生成中は「考え中」を表示
            yield {"type": "llm_thinking", "step_num": step + 1, "max_steps": max_steps}
            try:
                reply, usage = call_llm_chat(messages, llm_url=llm_url)
                if not usage.get("prompt_tokens"):
                    usage = {**usage, "prompt_tokens": _estimate_tokens(messages)}
            except HTTPException as _ctx_ex:
                if _ctx_ex.status_code == 413:
                    print(f"[execute_task_stream] context exceeded, force trimming...")
                    messages = _trim_messages(messages, _current_n_ctx // 2, reserve_output=_calc_reserve_output(_current_n_ctx // 2, ratio=0.22))
                    try:
                        reply, usage = call_llm_chat(messages, llm_url=llm_url)
                    except Exception as _e2:
                        yield {"type": "task_error", "error": f"Context exceeded after trim: {_e2}", "steps": steps}
                        return
                else:
                    yield {"type": "task_error", "error": str(_ctx_ex.detail), "steps": steps}
                    return

        action_obj, reply, retry_usage = _parse_task_v2_action_with_retry(
            reply=reply,
            messages=messages,
            llm_url=llm_url,
            parser=_model_manager.current_parser,
            max_retry=1,
        )
        if retry_usage.get("prompt_tokens"):
            usage = retry_usage

        if action_obj is None:
            consecutive_errors += 1
            # replyの内容から失敗原因をヒントに
            reply_preview = reply.strip()[:120] if reply else "(empty)"
            print(f"[execute_task] JSON fail #{consecutive_errors}: {reply_preview}")
            if consecutive_errors >= 5:
                yield {"type": "task_error", "task_id": task_id, "title": task_title,
                       "error": f"JSON出力失敗（5回連続）。最後の出力: {reply_preview}", "steps": steps}
                return
            # 失敗パターン別フィードバック
            if len(reply) > 2000:
                if '"edit_file"' in reply or '"old_str"' in reply:
                    fb = ('出力が途中で切れました。edit_fileのold_strが長すぎます。'
                          'old_strは変更箇所の前後2〜3行のみにして一意に特定できる最短の文字列にしてください。'
                          'new_strも必要最小限にしてください。')
                else:
                    fb = "出力が長すぎます。1ステップ1アクションのみ。短いJSONで出力してください。"
            elif reply.strip().startswith("<think>") or "</think>" in reply:
                fb = "thinking部分を除いたJSONのみを出力してください。最初の文字は{であること。"
            elif reply.strip().startswith("<|"):
                fb = "チャンネルトークンは使わず、JSONのみを出力してください。最初の文字は{であること。"
            else:
                fb = 'JSON形式のみで出力してください。最初の文字は{であること。例: {"thought":"考え","action":"list_files","args":{"subdir":""}}'
            messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)[:500]})
            messages.append({"role": "user", "content": fb})
            continue
        else:
            consecutive_errors = 0

        action = str(action_obj.get("action", "") or "").strip().lower()
        action, action_note = _normalize_action_name(action)
        thought = action_obj.get("thought", "")
        tool_input = action_obj.get("args", {})
        if action_note:
            thought = f"{thought} ({action_note})".strip()
        if action in {"stop", "done", "finish", "complete", "end"}:
            action = "final"
            action_obj["action"] = "final"
            if not action_obj.get("output"):
                action_obj["output"] = thought or "Agent requested stop."

        if action == "final":
            steps.append({"step": step, "type": "final"})
            yield {
                "type": "task_done",
                "task_id": task_id,
                "title": task_title,
                "output": action_obj.get("output", ""),
                "steps": steps,
                "total_steps": step + 1,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "tps": usage.get("tps", 0),
            }
            return

        # clarify: ユーザー選択待ち（unknown tool チェックより先に処理する）
        if action == "clarify":
            question = tool_input.get("question", "確認が必要です")
            options = tool_input.get("options", [])
            yield {
                "type": "clarify",
                "question": question,
                "options": options,
                "step_num": step + 1,
                "max_steps": max_steps,
            }
            # 呼び出し元 (run_job_background) がwait/resumeを担当
            continue

        if action not in active_tools:
            # 未知のツール → スキル候補として記録
            yield {"type": "skill_hint", "missing_tool": action}
            messages.append({"role": "assistant", "content": _sanitize_special_tokens(reply)})
            messages.append({"role": "user", "content": f"ERROR: unknown tool '{action}' — 使えるのは {list(active_tools.keys())} のみ。これらのツールで代替する。"})
            continue

        yield {
            "type": "tool_call",
            "action": action,
            "step_num": step + 1,
            "max_steps": max_steps,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "tps": usage.get("tps", 0),
        }

        safe_input, prep_error, prep_notes = _prepare_tool_call(active_tools, action, tool_input)
        if prep_error:
            result = prep_error
            if prep_notes:
                result += "\n" + " / ".join(prep_notes)
        else:
            call_key = f"{action}:{json.dumps(safe_input, ensure_ascii=False, sort_keys=True)}"
            if repeated_failures.get(call_key, 0) >= 2:
                result = ("ERROR: 同一の失敗ツール呼び出しを繰り返しています。"
                          " 直前のエラー内容を確認し、引数または手順を変更してください。")
            else:
                try:
                    result = active_tools[action](**safe_input)
                except TypeError as e:
                    result = f"ERROR: 引数エラー - {e}"

        result_text = str(result)
        step_record = {
            "step": step, "type": "tool_call",
            "action": action,
            "input": safe_input if safe_input is not None else tool_input, "result_preview": result_text[:200]
        }
        tool_result_event = {"type": "tool_result", "action": action, "result_preview": result_text[:200]}
        if action == "read_file":
            excerpt, result_size = _build_read_file_excerpt(result_text)
            step_record["result_excerpt"] = excerpt
            step_record["result_size"] = result_size
            tool_result_event["result_excerpt"] = excerpt
            tool_result_event["result_size"] = result_size
            print(f"[tool_result] read_file returned {result_size} chars")
        steps.append(step_record)
        yield tool_result_event

        recent_actions.append(action)
        if len(recent_actions) > stagnation_window:
            recent_actions = recent_actions[-stagnation_window:]
        if action in exploration_actions:
            _in = safe_input if safe_input is not None else tool_input
            _target = _shorten(
                _in.get("path")
                or _in.get("subdir")
                or _in.get("query")
                or _in.get("function_name")
                or ""
            ) if isinstance(_in, dict) else ""
            recent_exploration_notes.append(f"{action}({_target}) => {_shorten(result, 100)}")
            if len(recent_exploration_notes) > 12:
                recent_exploration_notes = recent_exploration_notes[-12:]

        # replyをmessagesに追加する際、write_fileのcontentなど巨大フィールドを省略
        compact = _compact_reply(action_obj, max_chars=300)
        messages.append({"role": "assistant", "content": _sanitize_special_tokens(compact or reply[:500])})
        result_str = result_text
        # write_file/patch_functionは成功メッセージ＋プレビューのみ
        if action in ("write_file", "patch_function"):
            result_str = result_str[:400]
        elif action == "read_file":
            # read_fileはファイル全体を渡す（コンテキスト余裕に応じて）
            # 現在使用トークン数を推定して残り容量を計算
            current_tokens = _estimate_tokens(messages)
            reserve_output = _calc_reserve_output(_current_n_ctx, ratio=0.30)
            remaining = _current_n_ctx - current_tokens - reserve_output  # 出力分を確保
            read_file_cap = _get_read_file_inject_max_chars()
            max_read_chars = max(4000, min(remaining * 4, read_file_cap))  # 4文字≒1トークン
            if len(result_str) > max_read_chars:
                # 先頭と末尾を両方表示（中間を省略）
                half = max_read_chars // 2
                result_str = (result_str[:half]
                    + f"\n\n[... {len(result_str) - max_read_chars} chars omitted ...]\n\n"
                    + result_str[-half:])
        else:
            max_result_chars = min(8000, max(2000, _current_n_ctx // 8))
            if len(result_str) > max_result_chars:
                result_str = result_str[:max_result_chars] + f"\n[... {len(result_str)-max_result_chars} chars truncated]"
        if str(result).strip().startswith("ERROR:") and safe_input is not None:
            call_key = f"{action}:{json.dumps(safe_input, ensure_ascii=False, sort_keys=True)}"
            repeated_failures[call_key] = repeated_failures.get(call_key, 0) + 1
            result_str += "\n\n注意: 同一引数での再実行は避け、エラー文を反映して次のアクションを変更すること。"
        elif safe_input is not None:
            call_key = f"{action}:{json.dumps(safe_input, ensure_ascii=False, sort_keys=True)}"
            repeated_failures.pop(call_key, None)
        messages.append({"role": "user", "content": f"実行結果:\n{result_str}"})

        if len(recent_actions) >= stagnation_window:
            window = recent_actions[-stagnation_window:]
            explore_count = sum(1 for a in window if a in exploration_actions)
            edit_count = sum(1 for a in window if a in edit_actions)
            explore_ratio = explore_count / max(1, len(window))
            if edit_count == 0 and explore_ratio >= stagnation_threshold:
                stagnation_events += 1
                last_stagnation_summary = _summarize_recent_exploration(limit=5)
                steps.append({
                    "step": step,
                    "type": "stagnation_detected",
                    "reason": "探索ループ検知",
                    "window": list(window),
                    "explore_ratio": round(explore_ratio, 3),
                    "summary": last_stagnation_summary,
                })
                yield {
                    "type": "progress",
                    "task_id": task_id,
                    "title": task_title,
                    "message": f"探索ループ検知: 直近{stagnation_window}ステップの探索比率={explore_ratio:.2f}。方針を強制切替します。",
                }
                messages.append({
                    "role": "user",
                    "content": (
                        "探索ループ検知。次アクションは必ず次のどちらかにしてください。\n"
                        "1) clarify で不足情報をユーザー確認する\n"
                        "2) 編集対象のファイル/行範囲を固定して最小編集を行う（edit_file/write_file/patch_function）\n"
                        f"直前探索の要約: {last_stagnation_summary}\n"
                        "同じ探索シーケンス（list_files/get_outline/read_file/search_in_filesのみの反復）を繰り返さないこと。"
                    )
                })
                if stagnation_events >= 2:
                    yield {
                        "type": "task_error",
                        "task_id": task_id,
                        "title": task_title,
                        "error": (
                            f"探索ループ検知により停止。直近要約: {last_stagnation_summary}"
                        ),
                        "steps": steps,
                    }
                    return

    if stagnation_events > 0:
        yield {
            "type": "task_error",
            "task_id": task_id,
            "title": task_title,
            "error": (
                f"ステップ上限 ({max_steps})。探索ループ検知あり（{stagnation_events}回）。"
                f" 直近要約: {last_stagnation_summary or _summarize_recent_exploration()}"
            ),
            "steps": steps,
        }
    else:
        yield {"type": "task_error", "task_id": task_id, "title": task_title, "error": f"ステップ上限 ({max_steps})", "steps": steps}

@app.post("/task/stream")
async def task_stream(req: TaskStreamRequest):
    """
    SSEでタスク進捗をリアルタイム配信する。
    approved_tasks が指定されていればプランニングをスキップ。
    イベント種別: plan / task_start / tool_call / tool_result / task_done / task_error / progress / done
    """
    def generate():
        session_id = str(uuid.uuid4())[:8]
        effective_search_enabled = _resolve_effective_search_enabled(req.search_enabled)

        def sse(data: dict) -> str:
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        # Step1: plan (または承認済みタスクをそのまま使用)
        plan_result = None
        if req.approved_tasks:
            todos = req.approved_tasks
        else:
            plan_result = plan(req.message, req.project)
            todos = plan_result.get("tasks", [])
        total = len(todos)
        yield sse({"type": "plan", "tasks": todos, "total": total})
        yield sse({"type": "progress", "pct": 0, "label": f"0/{total} tasks"})

        results = []
        context = ""

        for i, todo in enumerate(todos):
            yield sse({"type": "task_start", "task_id": todo["id"], "title": todo["title"],
                       "task_index": i, "total": total})

            # タスク内ステップ進捗: このタスクが占める全体の割合
            task_base_pct = int(i / total * 100)
            task_share = int(1 / total * 100)

            task_steps = []
            task_status = "error"
            task_output = ""

            for event in run_task_mode_stream(
                task_detail=todo["detail"],
                context=context,
                max_steps=req.max_steps,
                project=req.project,
                search_enabled=effective_search_enabled,
                llm_url=req.llm_url
            ):
                etype = event.get("type")

                if etype == "step_start":
                    step_num = event["step"]
                    max_s = event["max_steps"]
                    # ステップ進捗をタスク内の割合に変換
                    inner_pct = int(step_num / max_s * task_share)
                    pct = min(task_base_pct + inner_pct, 99)
                    yield sse({"type": "progress", "pct": pct,
                               "label": f"Task {i+1}/{total} · step {step_num+1}"})

                elif etype == "tool_call":
                    yield sse({**event, "task_id": todo["id"]})

                elif etype == "tool_result":
                    yield sse({**event, "task_id": todo["id"]})
                    task_steps.append(event)

                elif etype == "task_done":
                    task_status = "done"
                    task_output = event.get("output", "")
                    yield sse({"type": "task_done", "task_id": todo["id"],
                               "title": todo["title"], "output": task_output,
                               "steps": event.get("steps", [])})

                elif etype == "task_error":
                    task_status = "error"
                    yield sse({"type": "task_error", "task_id": todo["id"],
                               "title": todo["title"], "error": event.get("error", "")})

            results.append({"task_id": todo["id"], "title": todo["title"],
                            "status": task_status, "output": task_output})

            if task_status == "done":
                context = f"タスク「{todo['title']}」完了: {task_output}"
                done_pct = int((i + 1) / total * 100)
                yield sse({"type": "progress", "pct": done_pct,
                           "label": f"{i+1}/{total} done"})
            else:
                # 残りをスキップ
                for remaining in todos[i+1:]:
                    results.append({"task_id": remaining["id"], "title": remaining["title"],
                                    "status": "skipped"})
                    yield sse({"type": "task_skip", "task_id": remaining["id"],
                               "title": remaining["title"]})
                break

        done_count = sum(1 for r in results if r["status"] == "done")

        # 検証フェーズ（approved_tasks=Noneの通常実行かつ全タスク成功時のみ）
        verify_result = None
        if done_count == total and plan_result:
            yield sse({"type": "progress", "pct": 90, "label": "Verifying..."})
            requirements = plan_result.get("requirements", [])
            verification = plan_result.get("verification", [])

            def on_verify_event(ev):
                nonlocal verify_result
                yield_queue.append(sse({**ev, "task_id": "verify"}))

            # verify_and_fix をジェネレータとして呼び出せないため直接yield
            yield sse({"type": "verify_start", "phase": "検証フェーズ", "round": 0})

            verify_result = verify_and_fix(
                user_message=req.message,
                requirements=requirements,
                verification_items=verification,
                project=req.project,
                max_fix_rounds=2,
                llm_url=req.llm_url,
                search_enabled=effective_search_enabled,
            )

            yield sse({
                "type": "verify_done",
                "passed": verify_result.get("passed", True),
                "score": verify_result.get("score", 75),
                "issues": verify_result.get("issues", []),
                "summary": verify_result.get("summary", ""),
            })

        final_result = {
            "summary": f"{total}タスク中{done_count}件完了",
            "success": done_count == total,
            "tasks": results,
            "verify": verify_result,
        }
        save_session(session_id, req.project, req.message, "task", final_result)
        yield sse({"type": "progress", "pct": 100, "label": "Complete"})
        yield sse({"type": "done", **final_result})

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})

# =========================
# 履歴API
# =========================

@app.get("/projects/{name}/history")
def project_history(name: str, limit: int = 50):
    """プロジェクトの会話履歴を返す（古い順）"""
    try:
        conn = get_db(name)
        rows = conn.execute(
            "SELECT id, timestamp, mode, message, status, result FROM sessions ORDER BY timestamp ASC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        sessions = []
        for row in rows:
            s = {
                "id": row[0], "timestamp": row[1], "mode": row[2],
                "message": row[3], "status": row[4]
            }
            try:
                s["result"] = json.loads(row[5]) if row[5] else None
            except Exception:
                s["result"] = None
            sessions.append(s)
        return {"sessions": sessions}
    except Exception as e:
        return {"sessions": [], "error": str(e)}

# =========================
# llama.cpp プロパティ取得 (コンテキスト長など)
# =========================

@app.get("/llm/props")
def llm_props():
    """llama-serverのプロパティ(最大コンテキスト長等)を返す"""
    ui_max_ctx = 65535
    try:
        res = requests.get(f"http://127.0.0.1:{_model_manager.llm_port}/props", timeout=5)
        if res.status_code == 200:
            data = res.json()
            # /propsのn_ctxが信頼できる場合はそれを使用
            # ただし llama-server は /props で default_generation_settings.n_ctx を返す場合がある
            n_ctx = (data.get("default_generation_settings", {}).get("n_ctx")
                     or data.get("n_ctx")
                     or _current_n_ctx)
            return {
                "n_ctx": max(int(n_ctx or 0), ui_max_ctx),
                "n_ctx_runtime": int(n_ctx or _current_n_ctx),
                "n_ctx_train": data.get("n_ctx_train", n_ctx),
                "raw": {k: v for k, v in data.items() if k in ("n_ctx","n_ctx_train","model_path","total_slots")}
            }
    except Exception:
        pass
    # フォールバック: サーバー側の_current_n_ctxを返す（スライダーがずれない）
    return {"n_ctx": ui_max_ctx, "n_ctx_runtime": _current_n_ctx, "note": "using server default"}

# =========================
# コンテキスト長設定
# =========================

_current_n_ctx: int = _default_llm_ctx_size()             # コンテキストウィンドウ長
# モデル別推奨コンテキスト長の目安:
# Qwen3-Coder-Next  : 16384〜32768 (Q3_K_Sでは16384を推奨)
# Mistral-Small-3.2 : 16384〜32768
# Qwen3.5-9B        : 4096〜8192
# gpt-oss-20b       : 8192〜16384

@app.get("/llm/ctx")
def get_ctx():
    return {"n_ctx": _current_n_ctx}

@app.post("/llm/ctx")
def set_ctx(req: dict):
    """UIからコンテキスト長を変更する（llm_urlのmax_tokensに反映）"""
    global _current_n_ctx
    n = int(req.get("n_ctx", _current_n_ctx))
    _current_n_ctx = max(512, min(65535, n))
    return {"n_ctx": _current_n_ctx}

# =========================
# Web検索 有効/無効 API
# =========================

@app.get("/search/status")
def search_status():
    return {"enabled": _search_enabled, "num_results": _search_num_results}

@app.post("/search/num")
def search_set_num(req: dict):
    global _search_num_results
    n = max(1, min(20, int(req.get("num_results", 5))))
    _search_num_results = n
    return {"num_results": n}

@app.post("/search/enable")
def search_enable():
    global _search_enabled
    _search_enabled = True
    print("[SEARCH] Web search ENABLED by user")
    return {"enabled": True}

@app.post("/search/disable")
def search_disable():
    global _search_enabled
    _search_enabled = False
    print("[SEARCH] Web search DISABLED by user")
    return {"enabled": False}

# =========================
# LLMストリーミング 有効/無効 API
# =========================

@app.get("/streaming/status")
def streaming_status():
    return {"enabled": _llm_streaming}

@app.post("/streaming/enable")
def streaming_enable():
    global _llm_streaming
    _llm_streaming = True
    print("[STREAMING] LLM streaming ENABLED")
    return {"enabled": True}

@app.post("/streaming/disable")
def streaming_disable():
    global _llm_streaming
    _llm_streaming = False
    print("[STREAMING] LLM streaming DISABLED")
    return {"enabled": False}

# =========================
# ジョブ API（DB永続化・ブラウザ閉じても継続）
# =========================

@app.post("/jobs/submit")
def submit_job(req: JobRequest):
    """
    ジョブ登録。LFMでタスク分類 → 必要ならモデル切り替え → バックグラウンドで実行。
    """
    job_id = job_create(req.project, req.message, req.mode)
    # タスク分類はplan完了後(run_job_background内)に実行
    t = _job_threading.Thread(
        target=run_job_background, args=(job_id, req), daemon=True
    )
    t.start()
    return {
        "job_id": job_id,
        "status": "queued",
        "model": _model_manager.current_key,
    }

@app.get("/jobs/{job_id}")
def get_job(job_id: str, project: str = "default"):
    """ジョブの現在状態と全ステップを返す"""
    info = job_get(project, job_id)
    if not info:
        raise HTTPException(status_code=404, detail="Job not found")
    steps = job_get_steps(project, job_id)
    return {**info, "steps": steps, "step_count": len(steps)}

@app.get("/jobs/{job_id}/poll")
def poll_job(job_id: str, project: str = "default", after: int = -1):
    """after より後の新しいステップのみ返す（差分ポーリング）"""
    info = job_get(project, job_id)
    if not info:
        raise HTTPException(status_code=404, detail="Job not found")
    steps = job_get_steps(project, job_id, after_seq=after)
    return {"status": info["status"], "steps": steps}

@app.get("/jobs/{job_id}/stream")
def stream_job(job_id: str, project: str = "default", after: int = -1):
    """DBをポーリングしてSSEで差分配信。ブラウザが再接続してもOK。"""
    import time

    def generate():
        info = job_get(project, job_id)
        if not info:
            _err = json.dumps({"type":"error","error":"Job not found"})
            yield "data: " + _err + "\n\n"
            return

        last_seq = after
        while True:
            steps = job_get_steps(project, job_id, after_seq=last_seq)
            for s in steps:
                _ev = json.dumps({**s["data"], "type": s["type"], "seq": s["seq"]}, ensure_ascii=False)
                yield "data: " + _ev + "\n\n"
                last_seq = s["seq"]

            current = job_get(project, job_id)
            if current and current["status"] in ("done", "error"):
                _end = json.dumps({"type":"job_end","status": current["status"]})
                yield "data: " + _end + "\n\n"
                break

            time.sleep(0.5)  # 500ms間隔でDBをポーリング

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/projects/{name}/jobs")
def list_jobs(name: str, limit: int = 30):
    """プロジェクトのジョブ一覧を返す"""
    jobs = job_list(name, limit)
    return {"jobs": jobs}

@app.get("/model/status")
def model_status():
    """現在のモデル状態とカタログを返す"""
    return _model_manager.status_dict()

@app.post("/model/switch")
def model_switch(req: dict):
    """手動でモデルを切り替える。非同期で実行。"""
    key = req.get("model") or choose_model_for_role("chat", include_disabled=True)
    runtime_catalog = get_runtime_model_catalog()
    if key not in runtime_catalog:
        raise HTTPException(status_code=400, detail=f"Unknown model: {key}")
    import threading as _t
    def do_switch():
        _model_manager.ensure_model(key)
    _t.Thread(target=do_switch, daemon=True).start()
    return {"switching_to": key, "eta_sec": runtime_catalog[key]["load_sec"]}


@app.post("/model/auto-load")
def model_auto_load(req: dict | None = None):
    req = req or {}
    started, detail = schedule_default_model_load(
        reason=req.get("reason", "api"),
        force=bool(req.get("force", False))
    )
    return {"ok": True, "started": started, "detail": detail}

@app.post("/jobs/{job_id}/respond")
def respond_to_job(job_id: str, req: dict):
    """
    clarify待ち / task_options待ちのジョブにユーザーの回答を送信して再開させる。
    req: {
      "answer": "ユーザーの選択/入力",          # clarify用
      "task_id": 3,                              # task_options用
      "option": {"id":1,"title":"...","detail":"...", "description":"..."},  # task_options用
      "project": "プロジェクト名"
    }
    """
    answer = req.get("answer", "")
    task_id = req.get("task_id")
    option = req.get("option")
    project = req.get("project", "default")

    if job_id not in _job_wait_events:
        raise HTTPException(status_code=404, detail="Job not found or not waiting for input")

    # task_options選択を保存
    if task_id is not None and option:
        _job_option_choices[f"{job_id}_{task_id}"] = option
        print(f"[JOB {job_id}] user selected option for task {task_id}: {option.get('title','')}")

    # clarify回答を保存
    if answer:
        _job_wait_answers[job_id] = answer

    _job_wait_events[job_id].set()
    job_update_status(project, job_id, "running")
    return {"resumed": True, "answer": answer, "option": option}


# =========================
# =========================

# =========================
# ジョブログ収集・スキル提案
# =========================

_job_logs: dict = {}  # job_id -> list of log entries

def job_log_append(job_id: str, entry: dict):
    if job_id not in _job_logs:
        _job_logs[job_id] = []
    _job_logs[job_id].append(entry)
    if len(_job_logs[job_id]) > 500:
        _job_logs[job_id] = _job_logs[job_id][-500:]

def job_log_get(job_id: str) -> list:
    return _job_logs.get(job_id, [])

def job_log_clear(job_id: str):
    _job_logs.pop(job_id, None)

@app.get("/jobs/{job_id}/logs")
def get_job_logs_api(job_id: str, project: str = "default"):
    return {"job_id": job_id, "logs": job_log_get(job_id), "count": len(job_log_get(job_id))}

@app.post("/jobs/{job_id}/analyze_skills")
def analyze_job_for_skills(job_id: str, project: str = "default"):
    """ジョブログを分析して不足スキルを提案する"""
    logs = job_log_get(job_id)
    if not logs:
        return {"proposals": [], "reason": "no logs found"}

    missing_tools, errors, skill_hints = [], [], []
    for entry in logs:
        t = entry.get("type", "")
        if t == "skill_hint":
            skill_hints.append(entry.get("missing_tool", ""))
        elif t == "task_error":
            errors.append(entry.get("error", ""))
        elif t == "tool_result":
            r = entry.get("result_preview", "")
            if "unknown tool" in r and "'" in r:
                skill_hints.append(r.split("'")[1])

    tool_calls = [e for e in logs if e.get("type") == "tool_call"]
    log_summary = "\n".join(
        f"- {e.get('action','')}: {e.get('thought','')[:80]}"
        for e in tool_calls[-30:]
    )
    error_summary = "\n".join(e[:100] for e in errors[-5:])
    existing = [s["name"] for s in (globals().get("_active_skills", lambda: [])())]

    prompt = f"""コードエージェントの実行ログを分析し、不足していたツールを実現するスキルを最大3件提案してください。

【ツール呼び出し履歴】
{log_summary or "(なし)"}

【エラー】
{error_summary or "(なし)"}

【不足ツール】
{", ".join(set(missing_tools + skill_hints)) or "(なし)"}

【既存スキル】
{", ".join(existing) or "(なし)"}

【ルール】
- 既存スキルと重複しない / Windows/Python環境 / 実際に不足した機能を実装
- 不要なら {{"proposals":[]}}

【出力JSONのみ】
{{"proposals":[{{"name":"snake_case名","description":"説明","version":"1.0","os":["win32"],"keywords":["kw"],"tool_code":"def name(arg:str)->str:\n    return result","usage_example":"","rationale":"不足していた理由","source":"codeagent"}}]}}"""

    try:
        reply, _ = call_llm_chat(
            [{"role":"system","content":prompt},
             {"role":"user","content":"分析してください"}],
            llm_url=LLM_URL
        )
        parsed = extract_json(reply, parser=_model_manager.current_parser)
        proposals = parsed.get("proposals",[]) if parsed else []
        for p in proposals:
            p["source"] = "codeagent"
    except Exception as e:
        proposals = []
        print(f"[SKILLS] analyze error: {e}")

    return {
        "proposals": proposals,
        "stats": {
            "tool_calls": len(tool_calls),
            "errors": len(errors),
            "missing_tools": list(set(missing_tools + skill_hints)),
        }
    }

# スキル管理 v2 (OpenClaw互換 SKILL.md形式)
# =========================
# スコープ: workspace > global > bundled
# 形式: skills/スキル名/SKILL.md (YAMLフロントマター + Markdownコード)

# スキルフォルダ:
#   - ローカル既定: <CODEAGENT_CA_DATA_DIR>/skills
#   - Runpod既定: /workspace/ca_data/skills
#   - CODEAGENT_SKILLS_DIR で明示オーバーライド可
# ユーザー追加・CodeAgent提案スキルを共有資産として格納
os.makedirs(SKILLS_DIR, exist_ok=True)
# 後方互換のエイリアス
SKILLS_GLOBAL_DIR  = SKILLS_DIR
SKILLS_BUNDLED_DIR = SKILLS_DIR  # bundledも同じフォルダに統合

_skills_cache: dict = {}
_skills_cache_time: float = 0

def _parse_skill_md(path: str) -> dict | None:
    """SKILL.md をパースしてスキルdict返す"""
    try:
        text = open(path, encoding="utf-8").read()
        meta = {}
        body = text
        if text.startswith("---"):
            end = text.find("---", 3)
            if end > 0:
                yaml_block = text[3:end].strip()
                for line in yaml_block.splitlines():
                    m = re.match(r"^(\w+)\s*:\s*(.+)$", line)
                    if m:
                        key, val = m.group(1), m.group(2).strip()
                        if val.startswith("[") and val.endswith("]"):
                            val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
                        elif val.lower() in ("true","false"):
                            val = val.lower() == "true"
                        meta[key] = val
                body = text[end+3:].strip()
        code_m = re.search(r"```python\n(.*?)```", body, re.DOTALL)
        tool_code = code_m.group(1).strip() if code_m else ""
        ex_m = re.search(r"```(?:json)?\n(\{.*?\})\n```", body, re.DOTALL)
        usage_example = ex_m.group(1).strip() if ex_m else ""
        default_os = [sys.platform]
        os_list = meta.get("os", default_os)
        if isinstance(os_list, str): os_list = [os_list]
        kw = meta.get("keywords", [])
        if isinstance(kw, str): kw = [kw]
        skill = {
            "name":          meta.get("name", os.path.basename(os.path.dirname(path))),
            "description":   meta.get("description", ""),
            "version":       str(meta.get("version", "1.0")),
            "os":            os_list,
            "keywords":      kw,
            "user_invocable": meta.get("user_invocable", True),
            "source":        meta.get("source", "user"),
            "tool_code":     tool_code,
            "usage_example": usage_example,
            "body":          body,
            "path":          path,
            "scope":         "shared",
            "created_at":    str(meta.get("created_at", "")),
            "usage_count":   int(meta.get("usage_count", 0)) if str(meta.get("usage_count","0")).isdigit() else 0,
        }
        norm_os = [str(x).lower() for x in os_list]
        current = sys.platform.lower()
        compatible = (
            not norm_os
            or "all" in norm_os
            or current in norm_os
            or (current.startswith("linux") and "linux" in norm_os)
            or (current.startswith("win") and ("win32" in norm_os or "windows" in norm_os))
            or (current == "darwin" and ("darwin" in norm_os or "macos" in norm_os or "mac" in norm_os))
        )
        if not compatible:
            skill["_incompatible_os"] = True
        return skill
    except Exception as e:
        print(f"[SKILLS] parse error {path}: {e}")
        return None

def _load_all_skills(force: bool = False) -> dict:
    """
    SKILLS_DIR からスキルをロード（共有資産）。
    スキルは skills/スキル名/SKILL.md または skills/SKILL.md 形式。
    """
    global _skills_cache, _skills_cache_time
    import time as _t
    if not force and _t.time() - _skills_cache_time < 10:
        return _skills_cache
    merged = {}
    if not os.path.isdir(SKILLS_DIR):
        return merged
    for entry in sorted(os.listdir(SKILLS_DIR)):
        entry_path = os.path.join(SKILLS_DIR, entry)
        if os.path.isfile(entry_path) and entry.upper() == "SKILL.MD":
            skill = _parse_skill_md(entry_path)
        elif os.path.isdir(entry_path):
            md = os.path.join(entry_path, "SKILL.md")
            skill = _parse_skill_md(md) if os.path.exists(md) else None
        else:
            continue
        if skill:
            skill["scope"] = "shared"
            merged[skill["name"]] = skill
            print(f"[SKILLS] loaded: {skill['name']} ({skill.get('description','')[:40]})")
    _skills_cache = merged
    _skills_cache_time = _t.time()
    print(f"[SKILLS] total: {len(merged)} skills from {SKILLS_DIR}")
    return merged

def _active_skills() -> list:
    return [s for s in _load_all_skills().values() if not s.get("_incompatible_os")]

def _skills_to_prompt_injection() -> str:
    """
    アクティブなスキルをSYSTEM_PROMPTへ注入するテキスト（OpenClaw互換XML形式）。
    スキルのtool_codeはrun_pythonで実行可能。
    """
    # usage_count 降順でソート（よく使われるスキルを優先的にプロンプトに含める）
    skills = sorted(_active_skills(), key=lambda s: s.get("usage_count", 0), reverse=True)
    if not skills: return ""
    lines = ["\n\n【カスタムスキル（SKILL.md）】"]
    lines.append("<skills>")
    for s in skills[:20]:
        kw = ",".join(s.get("keywords", []))
        name = s["name"]
        desc = s.get("description","")
        lines.append(f'  <skill name="{name}" keywords="{kw}" action="{name}">{desc}</skill>')
    lines.append("</skills>")
    lines.append("スキルを使う場合: action=スキル名 でツールと同様に呼び出す。")
    lines.append(f"スキルのコードは {SKILLS_DIR} または /skills APIで確認可能。")
    return "\n".join(lines)

def _load_skill_functions() -> dict:
    """スキルのPythonコードを動的ロードしてTOOLSに追加できる形で返す"""
    result = {}
    for skill in _active_skills():
        code = skill.get("tool_code","").strip()
        if not code: continue
        try:
            ns = {}
            exec(compile(code, f"<skill:{skill['name']}>", "exec"), ns)
            fn_name = skill["name"].replace("-","_").replace(" ","_")
            fn = ns.get(fn_name) or next((v for k,v in ns.items() if callable(v) and not k.startswith("_")), None)
            if fn:
                result[skill["name"]] = fn
        except Exception as e:
            print(f"[SKILLS] load fn error {skill['name']}: {e}")
    return result

def _skill_terms(*values) -> set[str]:
    text = " ".join(str(v or "") for v in values).lower()
    return set(re.findall(r"[a-z0-9_+-]{2,}", text))

def _skill_similarity(existing: dict, incoming: dict) -> float:
    existing_name = str(existing.get("name", ""))
    incoming_name = str(incoming.get("name", ""))
    existing_desc = str(existing.get("description", ""))
    incoming_desc = str(incoming.get("description", ""))
    name_ratio = difflib.SequenceMatcher(None, existing_name.lower(), incoming_name.lower()).ratio()
    desc_ratio = difflib.SequenceMatcher(None, existing_desc.lower(), incoming_desc.lower()).ratio()
    existing_terms = _skill_terms(existing_name, existing_desc, existing.get("keywords", []))
    incoming_terms = _skill_terms(incoming_name, incoming_desc, incoming.get("keywords", []))
    overlap = len(existing_terms & incoming_terms) / max(1, len(existing_terms | incoming_terms)) if (existing_terms or incoming_terms) else 0.0
    return round(name_ratio * 0.45 + desc_ratio * 0.20 + overlap * 0.35, 4)

def _find_similar_skills(candidate: dict, limit: int = 3) -> list[dict]:
    scored = []
    for skill in _active_skills():
        score = _skill_similarity(skill, candidate)
        if score >= 0.35:
            scored.append({"skill": skill, "score": score})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]

def _bump_skill_version(version: str | None, part: str = "minor") -> str:
    nums = [int(x) for x in re.findall(r"\d+", str(version or "1.0"))]
    while len(nums) < 3:
        nums.append(0)
    major, minor, patch = nums[:3]
    if part == "major":
        major, minor, patch = major + 1, 0, 0
    elif part == "patch":
        patch += 1
    else:
        minor += 1
        patch = 0
    return f"{major}.{minor}" if patch == 0 else f"{major}.{minor}.{patch}"

def _merge_skill(existing: dict, incoming: dict, merge_reason: str = "") -> dict:
    merged = dict(existing)
    merged["name"] = existing.get("name") or incoming.get("name")
    existing_desc = str(existing.get("description", "")).strip()
    incoming_desc = str(incoming.get("description", "")).strip()
    merged["description"] = incoming_desc if len(incoming_desc) >= len(existing_desc) else existing_desc
    merged["keywords"] = sorted(set(existing.get("keywords", []) or []) | set(incoming.get("keywords", []) or []))
    merged["os"] = sorted(set(existing.get("os", []) or ["win32"]) | set(incoming.get("os", []) or ["win32"]))
    incoming_code = str(incoming.get("tool_code", "")).strip()
    if incoming_code:
        merged["tool_code"] = incoming_code
    merged["usage_example"] = incoming.get("usage_example") or existing.get("usage_example", "")
    merged["version"] = _bump_skill_version(existing.get("version"), "minor")
    merged["source"] = incoming.get("source") or existing.get("source") or "codeagent"
    rationale_parts = [str(existing.get("rationale", "")).strip(), str(incoming.get("rationale", "")).strip(), merge_reason.strip()]
    merged["rationale"] = "\n\n".join(part for part in rationale_parts if part)
    merged["usage_count"] = max(int(existing.get("usage_count", 0) or 0), int(incoming.get("usage_count", 0) or 0))
    return merged

def _upsert_skill(req: dict, merge_reason: str = "", prefer_merge: bool = True) -> dict:
    incoming = dict(req or {})
    name = str(incoming.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "name required")
    if name.lower() in {"name", "snake_case名", "skill", "new_skill"}:
        raise HTTPException(400, f"invalid skill name: {name}")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{3,64}", name):
        raise HTTPException(400, f"invalid skill name format: {name}")
    incoming["name"] = name
    incoming.setdefault("version", "1.0")
    incoming.setdefault("source", "user")
    _load_all_skills(force=True)
    skills = _load_all_skills()
    target = skills.get(name)
    similar = []
    if not target and prefer_merge:
        similar = _find_similar_skills(incoming, limit=3)
        if similar and similar[0]["score"] >= 0.72:
            target = similar[0]["skill"]

    if target:
        merged = _merge_skill(target, incoming, merge_reason)
        path = target.get("path") or _skill_save_path(target["name"])
        _write_skill_md(merged, path)
        _load_all_skills(force=True)
        return {"ok": True, "action": "updated", "path": path, "skill_name": merged["name"], "version": merged.get("version", ""), "matched_skill": target.get("name", ""), "similar": [{"name": s["skill"]["name"], "score": s["score"]} for s in similar]}

    path = _skill_save_path(name)
    _write_skill_md(incoming, path)
    _load_all_skills(force=True)
    return {"ok": True, "action": "created", "path": path, "skill_name": incoming["name"], "version": incoming.get("version", "1.0"), "similar": [{"name": s["skill"]["name"], "score": s["score"]} for s in similar]}

def _skill_save_path(name: str, scope: str = "shared") -> str:
    """スキルの保存先: SKILLS_DIR/スキル名/SKILL.md"""
    safe = "".join(c for c in name if c.isalnum() or c in "_-")
    d = os.path.join(SKILLS_DIR, safe)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "SKILL.md")

def _write_skill_md(skill: dict, path: str):
    default_os = ["linux", "win32"] if sys.platform.startswith("linux") else [sys.platform]
    os_list = skill.get("os", default_os)
    if isinstance(os_list, str): os_list = [os_list]
    kw = skill.get("keywords", [])
    if isinstance(kw, str): kw = [kw]
    source = skill.get("source", "user")  # "user" or "codeagent"
    lines = [
        "---",
        f"name: {skill['name']}",
        f"description: {skill.get('description','')}",
        f"version: \"{skill.get('version','1.0')}\"",
        f"os: [{', '.join(os_list)}]",
        f"keywords: [{', '.join(kw)}]",
        f"user_invocable: {str(skill.get('user_invocable',True)).lower()}",
        f"source: {source}",
        f"created_at: {datetime.now().isoformat()}",
        f"usage_count: {skill.get('usage_count',0)}",
        "---",
        "",
        "## 説明",
        skill.get("description",""),
        "",
        "## コード",
        "```python",
        skill.get("tool_code","# TODO: implement"),
        "```",
        "",
    ]
    if skill.get("usage_example"):
        lines += ["## 使用例", "```json", skill["usage_example"], "```", ""]
    if skill.get("rationale"):
        lines += ["## 追加理由", skill["rationale"], ""]
    open(path, "w", encoding="utf-8").write("\n".join(lines))

@app.get("/skills")
def list_skills_api():
    _load_all_skills(force=True)
    skills = _active_skills()
    return {
        "skills": skills,
        "count": len(skills),
        "paths": {
            "active": SKILLS_DIR,
            "default_local": DEFAULT_SKILLS_DIR_LOCAL,
            "default_runpod": DEFAULT_SKILLS_DIR_RUNPOD,
            "runtime": "runpod" if IS_RUNPOD_RUNTIME else "local",
        },
    }

@app.post("/skills")
def create_skill_api(req: dict):
    return _upsert_skill(req, merge_reason="manual save", prefer_merge=True)

@app.delete("/skills/{name}")
def delete_skill_api(name: str):
    skills = _load_all_skills()
    s = skills.get(name)
    if s and s.get("path"):
        import shutil
        skill_dir = os.path.dirname(s["path"])
        # スキルフォルダごと削除（SKILLS_DIR直下は保護）
        if os.path.isdir(skill_dir) and os.path.abspath(skill_dir) != os.path.abspath(SKILLS_DIR):
            shutil.rmtree(skill_dir, ignore_errors=True)
        elif os.path.exists(s["path"]):
            os.remove(s["path"])
    _load_all_skills(force=True)
    return {"ok": True}

@app.post("/skills/reload")
def reload_skills():
    skills = _load_all_skills(force=True)
    return {"ok": True, "count": len(skills)}


# =========================
# Git API
# =========================

@app.get("/git/status")
def git_status_api(project: str = "default"):
    return {"status": git_status(project), "project": project}

@app.post("/git/commit")
def git_commit_api(req: dict):
    project = req.get("project", "default")
    message = req.get("message", "CodeAgent commit")
    return {"result": git_commit(message, project)}

@app.post("/git/checkout")
def git_checkout_api(req: dict):
    project = req.get("project", "default")
    name = req.get("name", "")
    create = req.get("create", True)
    if not name:
        raise HTTPException(400, "branch name required")
    return {"result": git_checkout_branch(name, create, project)}

@app.post("/git/reset")
def git_reset_api(req: dict):
    project = req.get("project", "default")
    mode = req.get("mode", "hard")
    return {"result": git_reset(mode, project)}

@app.get("/git/diff")
def git_diff_api(project: str = "default", path: str = ""):
    return {"diff": git_diff(path, project)}

@app.get("/git/log")
def git_log_api(project: str = "default", limit: int = 10):
    cwd = os.path.join(WORK_DIR, project)
    if not os.path.exists(os.path.join(cwd, ".git")):
        return {"log": "no git repository", "commits": []}
    rc, out, err = _git_run(
        ["log", f"--max-count={limit}", "--pretty=format:%h|%s|%an|%ar"],
        cwd
    )
    commits = []
    if rc == 0 and out:
        for line in out.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({"hash": parts[0], "message": parts[1],
                                 "author": parts[2], "when": parts[3]})
    return {"commits": commits}


# =========================
# MCP サーバー API (JSON-RPC 2.0)
# =========================

@app.post("/mcp")
async def mcp_server_endpoint(request: Request):
    """
    MCPサーバーエンドポイント（JSON-RPC 2.0）。
    他エージェントからCodeAgentのツールをMCP経由で呼び出せる。
    """
    try:
        body = await request.json()
    except Exception:
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Parse error"}}

    method = body.get("method", "")
    req_id = body.get("id", 1)
    params = body.get("params", {})

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False}
            },
            "serverInfo": {"name": "codeagent", "version": "1.0"}
        })

    elif method == "notifications/initialized":
        return {}

    elif method == "ping":
        return ok({})

    elif method == "tools/list":
        import inspect
        tools_list = []
        for tname, fn in TOOLS.items():
            sig = inspect.signature(fn)
            props = {}
            required = []
            for pname, param in sig.parameters.items():
                if pname == "project":
                    continue
                ann = param.annotation
                ptype = "integer" if ann is int else ("boolean" if ann is bool else "string")
                props[pname] = {"type": ptype, "description": pname}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
            tools_list.append({
                "name": tname,
                "description": (fn.__doc__ or tname).strip().splitlines()[0][:120],
                "inputSchema": {"type": "object", "properties": props, "required": required}
            })
        return ok({"tools": tools_list})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        if tool_name not in TOOLS:
            return err(-32601, f"Tool not found: {tool_name}")
        try:
            result = TOOLS[tool_name](**arguments)
            return ok({"content": [{"type": "text", "text": str(result)}]})
        except TypeError as e:
            return err(-32602, f"Invalid params: {e}")
        except Exception as e:
            return err(-32603, f"Internal error: {e}")

    elif method == "resources/list":
        return ok({
            "resources": [
                {
                    "uri": "codeagent://tools",
                    "name": "CodeAgent Tools",
                    "description": "Registered tool names",
                    "mimeType": "application/json"
                },
                {
                    "uri": "codeagent://health",
                    "name": "CodeAgent Health",
                    "description": "Basic health report",
                    "mimeType": "application/json"
                }
            ]
        })

    elif method == "resources/read":
        uri = params.get("uri", "")
        if uri == "codeagent://tools":
            text = json.dumps({"tool_names": list(TOOLS.keys()), "count": len(TOOLS)}, ensure_ascii=False)
            return ok({"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]})
        if uri == "codeagent://health":
            text = json.dumps({"status": "ok", "service": "codeagent"}, ensure_ascii=False)
            return ok({"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]})
        return err(-32602, f"Unknown resource: {uri}")

    elif method == "prompts/list":
        return ok({"prompts": []})

    else:
        return err(-32601, f"Method not found: {method}")

@app.get("/mcp/info")
def mcp_info():
    """MCPサーバー情報とツール一覧を返す"""
    return {
        "name": "codeagent",
        "version": "1.0",
        "protocol": "2024-11-05",
        "endpoint": "/mcp",
        "tools_count": len(TOOLS),
        "tool_names": list(TOOLS.keys()),
    }


# =========================
# モデルデータベース API
# =========================

@app.get("/models/db")
def list_models_db_api():
    models = model_db_list()
    for model in models:
        model["ctx_size"] = _resolve_ctx_size(model.get("ctx_size"))
    return {"models": models, "count": len(models)}

@app.post("/models/db")
def add_model_db_api(req: dict):
    if not req.get("name") or not req.get("path"):
        raise HTTPException(400, "name and path required")
    req = dict(req or {})
    req["ctx_size"] = _resolve_ctx_size(req.get("ctx_size"))
    mid = model_db_add(req)
    schedule_default_model_load(reason="model_add")
    return {"ok": True, "id": mid}

@app.put("/models/db/{mid}")
def update_model_db_api(mid: str, req: dict):
    req = dict(req or {})
    if "ctx_size" in req:
        req["ctx_size"] = _resolve_ctx_size(req.get("ctx_size"))
    model_db_update(mid, req)
    return {"ok": True}

@app.delete("/models/db/{mid}")
def delete_model_db_api(mid: str):
    model_db_delete(mid)
    return {"ok": True}

@app.get("/models/db/status")
def model_db_status_api():
    models = model_db_list()
    benchmarked = [m for m in models if m.get("tok_per_sec", -1) > 0]
    has_vlm = any(m.get("is_vlm") for m in models)
    return {
        "db_exists": model_db_exists(),
        "has_models": len(models) > 0,
        "total": len(models),
        "benchmarked": len(benchmarked),
        "has_vlm": has_vlm,
        "db_path": MODEL_DB_PATH,
    }


@app.get("/models/hardware")
def model_hardware_api():
    return get_system_hardware_info()


@app.get("/models/gguf/search")
def search_gguf_models_api(
    q: str = "",
    sort: str = "downloads",
    limit: int = 20,
):
    query = (q or "").strip()
    if not query:
        raise HTTPException(400, "q required")
    limit = max(1, min(limit, 50))
    sort_key = "downloads" if sort not in ("downloads", "updated") else sort
    hf_sort = "downloads" if sort_key == "downloads" else "lastModified"
    try:
        resp = requests.get(
            "https://huggingface.co/api/models",
            params={
                "search": query,
                "sort": hf_sort,
                "direction": "-1",
                "limit": str(limit),
                "full": "true",
            },
            timeout=30,
        )
        resp.raise_for_status()
        rows = resp.json() if isinstance(resp.json(), list) else []
    except Exception as e:
        raise HTTPException(502, f"Hugging Face search failed: {e}")

    hw = get_system_hardware_info()
    root_folder = settings_get("llm_root_folder") or _default_llm_root_folder()
    free_disk_mb = _disk_free_mb(root_folder)
    results = []
    for row in rows:
        model_id = row.get("id", "")
        siblings = row.get("siblings", []) or []
        missing_size_files = []
        for s in siblings:
            nm = str(s.get("rfilename") or "")
            if nm.lower().endswith(".gguf") and int(s.get("size") or 0) <= 0:
                missing_size_files.append(nm)
        fallback_sizes = _fetch_hf_repo_file_sizes(model_id) if missing_size_files else {}
        ggufs = []
        for s in siblings:
            name = s.get("rfilename", "")
            if not name.lower().endswith(".gguf"):
                continue
            size_bytes = int(s.get("size") or 0)
            if size_bytes <= 0:
                size_bytes = int(fallback_sizes.get(name) or 0)
            quant = _infer_quantization_from_name(name)
            ctx_size = _infer_ctx_size_from_name(name, default_ctx=_default_llm_ctx_size())
            gpu_layers = _infer_gpu_layers_for_estimate(int(size_bytes / (1024 * 1024)) if size_bytes > 0 else -1, quant)
            size_mb = int(size_bytes / (1024 * 1024)) if size_bytes > 0 else -1
            fit = _estimate_fit(
                size_mb,
                hw,
                quantization=quant,
                ctx_size=ctx_size,
                gpu_layers=gpu_layers,
                disk_free_mb=free_disk_mb,
            )
            ggufs.append({
                "filename": name,
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "quantization": quant or "unknown",
                "ctx_size": ctx_size,
                "gpu_layers_assumed": gpu_layers,
                **fit,
            })
        if not ggufs:
            continue
        ggufs.sort(key=lambda x: x.get("size_bytes", 0), reverse=True)
        results.append({
            "model_id": model_id,
            "downloads": int(row.get("downloads") or 0),
            "likes": int(row.get("likes") or 0),
            "last_modified": row.get("lastModified", ""),
            "ggufs": ggufs,
        })
    return {
        "query": query,
        "sort": sort_key,
        "hardware": hw,
        "storage": {"folder": root_folder, "disk_free_mb": free_disk_mb},
        "results": results,
        "count": len(results),
    }


_gguf_dl_lock = threading.Lock()
_gguf_dl_jobs: dict[str, dict] = {}


def _set_gguf_dl_job(job_id: str, **updates):
    with _gguf_dl_lock:
        row = _gguf_dl_jobs.get(job_id, {"job_id": job_id})
        row.update(updates)
        _gguf_dl_jobs[job_id] = row


def _get_gguf_dl_job(job_id: str) -> dict | None:
    with _gguf_dl_lock:
        row = _gguf_dl_jobs.get(job_id)
        return dict(row) if row else None


def _run_gguf_download_job(job_id: str, model_id: str, safe_rel: str, folder: str, requested_ctx_size: int | None = None):
    target = os.path.join(folder, safe_rel)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp_target = target + ".part"
    url = f"https://huggingface.co/{model_id}/resolve/main/{safe_rel}?download=true"
    started = time.time()
    _set_gguf_dl_job(job_id, running=True, done=False, error="", downloaded_bytes=0, total_bytes=0, speed_mbps=0.0)
    try:
        with requests.get(url, stream=True, timeout=45) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"download failed: {(r.text or '')[:160]}")
            total = int(r.headers.get("Content-Length") or 0)
            _set_gguf_dl_job(job_id, total_bytes=total)
            downloaded = 0
            with open(tmp_target, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    elapsed = max(0.1, time.time() - started)
                    _set_gguf_dl_job(job_id, downloaded_bytes=downloaded, speed_mbps=round((downloaded / (1024 * 1024)) / elapsed, 2), progress=(downloaded / total) if total > 0 else -1)
        os.replace(tmp_target, target)
        file_size = os.path.getsize(target)
    except Exception as e:
        if os.path.exists(tmp_target):
            os.remove(tmp_target)
        _set_gguf_dl_job(job_id, running=False, done=True, error=str(e))
        return

    existing = model_db_find_by_path(target)
    model_name = f"{model_id}/{os.path.splitext(safe_rel)[0]}"
    record = _infer_model_db_metadata({
        "name": model_name, "path": target, "is_vlm": _detect_vlm(target, model_name),
        "has_mmproj": False, "mmproj_path": "", "quantization": _guess_quantization(target),
        "file_size_mb": int(file_size / (1024 * 1024)), "vram_mb": -1, "ram_mb": -1, "load_sec": -1, "tok_per_sec": -1,
        "llm_url": "", "ctx_size": _resolve_ctx_size(requested_ctx_size), "gpu_layers": 999, "notes": "downloaded",
    })
    if existing:
        model_db_update(existing["id"], record)
        model_id_db = existing["id"]
    else:
        model_id_db = model_db_add(record)
    _set_gguf_dl_job(job_id, running=False, done=True, progress=1.0, path=target, model_db_id=model_id_db)
    threading.Thread(
        target=_postprocess_downloaded_model,
        args=(model_id_db,),
        daemon=True
    ).start()


def _postprocess_downloaded_model(model_id_db: str):
    """
    GGUFダウンロード完了後に以下を実施:
      1) auto_roles未設定モデルに推奨ロールを初期化（既存ロールは変更しない）
      2) 決定済みロールに基づくデフォルトモデルの自動ロードを要求

    各段階は独立して実行し、どこかが失敗しても後続処理は継続する。
    ベンチマークはダウンロード時は実施しない（ユーザーが手動で実行）。
    """
    step_ok = {"auto_roles": False, "auto_load": False}

    try:
        all_models = model_db_list()
        role_lock = settings_get("role_lock") == "true"
        if all_models and not role_lock:
            _, recommendations = recommend_roles_with_planner(all_models)
            initialized_roles = 0
            for row in all_models:
                existing_roles = [x.strip() for x in str(row.get("auto_roles", "")).split(",") if x.strip()]
                if existing_roles:
                    continue  # DL後は空の場合のみ適用
                roles = recommendations.get(row["id"], [])
                if not roles:
                    continue
                model_db_update(row["id"], {"auto_roles": ",".join(roles)})
                initialized_roles += 1
            if initialized_roles > 0:
                print(f"[ModelDB] initialized auto_roles after GGUF download: {initialized_roles}")
        step_ok["auto_roles"] = True
    except Exception as e:
        print(f"[ModelDB] auto_roles step failed after GGUF download: {e}")

    try:
        started, detail = schedule_default_model_load(reason="gguf_download_complete")
        print(f"[ModelManager] auto-load after GGUF download: started={started} detail={detail}")
        step_ok["auto_load"] = bool(started)
    except Exception as e:
        print(f"[ModelManager] auto-load step failed after GGUF download: {e}")

    print(f"[ModelDB] postprocess after GGUF download finished: {step_ok}")


@app.post("/models/gguf/download")
def download_gguf_api(req: dict):
    model_id = (req.get("model_id") or "").strip()
    filename = (req.get("filename") or "").strip()
    if not model_id or not filename:
        raise HTTPException(400, "model_id and filename required")
    safe_rel = os.path.normpath(filename).replace("\\", "/")
    if safe_rel.startswith("../") or safe_rel == ".." or os.path.isabs(safe_rel):
        raise HTTPException(400, "invalid filename")

    folder = (req.get("folder") or settings_get("llm_root_folder") or _default_llm_root_folder()).strip()
    requested_ctx_size = _resolve_ctx_size(req.get("ctx_size"))
    if not folder:
        folder = _default_llm_root_folder()
    os.makedirs(folder, exist_ok=True)
    job_id = str(uuid.uuid4())[:8]
    _set_gguf_dl_job(job_id, model_id=model_id, filename=safe_rel, folder=folder, started_at=datetime.now().isoformat(), running=True, done=False)
    threading.Thread(target=_run_gguf_download_job, args=(job_id, model_id, safe_rel, folder, requested_ctx_size), daemon=True).start()
    return {
        "ok": True,
        "job_id": job_id,
        "benchmark_started": False,
    }


@app.get("/models/gguf/download/status")
def gguf_download_status_api(job_id: str):
    row = _get_gguf_dl_job(job_id)
    if not row:
        raise HTTPException(404, "download job not found")
    return row



_model_scan_lock = __import__("threading").Lock()
_model_scan_state: dict[str, object] = {
    "running": False,
    "done": False,
    "job_id": "",
    "folder": "",
    "phase": "idle",
    "current": 0,
    "total": 0,
    "summary": "",
    "planner_model": "",
    "initialized_roles": 0,
    "found": 0,
    "added": 0,
    "updated": 0,
    "benchmarked": 0,
    "error": "",
}


def _set_model_scan_state(**updates):
    with _model_scan_lock:
        _model_scan_state.update(updates)


def get_model_scan_state() -> dict:
    with _model_scan_lock:
        return dict(_model_scan_state)


def _run_model_scan_job(job_id: str, folder: str):
    _set_model_scan_state(
        running=True,
        done=False,
        job_id=job_id,
        folder=folder,
        phase="scan",
        current=0,
        total=0,
        summary="Scanning folders...",
        planner_model="",
        initialized_roles=0,
        found=0,
        added=0,
        updated=0,
        benchmarked=0,
        error="",
    )
    try:
        results = model_db_scan_folder(folder)
        total = len(results)
        _set_model_scan_state(total=total, found=total, summary="Preparing benchmarks...")
        added = 0
        updated = 0
        benchmarked = 0
        benchmark_failed = 0
        saved_models = []
        if total == 0:
            _set_model_scan_state(
                running=False,
                done=True,
                phase="done",
                summary="No GGUF models found.",
                models=[],
            )
            return
        # Step 1: 全モデルをDBに登録しつつ、有効モデルをベンチマーク
        benchmark_failed = 0
        for idx, m in enumerate(results, start=1):
            model_name = m.get("name") or os.path.basename(m.get("path", "")) or f"model {idx}"
            _set_model_scan_state(
                phase="benchmark",
                current=idx,
                total=total,
                summary=f"Benchmarking {model_name}",
            )
            existing = model_db_find_by_path(m["path"])
            if existing:
                model_db_update(existing["id"], m)
                model_id = existing["id"]
                updated += 1
            else:
                model_id = model_db_add(m)
                added += 1
            saved = model_db_find_by_path(m["path"]) or {"id": model_id, **m}
            # 有効モデルのみベンチマーク（無効モデルはスキップ）
            if int(saved.get("enabled", 1) or 1) != 0:
                try:
                    bm_updates = benchmark_model_profiles(saved)
                    model_db_update(model_id, bm_updates)
                    saved.update(bm_updates)
                    benchmarked += 1
                except Exception as e:
                    benchmark_failed += 1
                    model_db_update(model_id, {"notes": f"BENCHMARK ERROR: {e}"})
                    saved["notes"] = f"BENCHMARK ERROR: {e}"
                    print(f"[ModelDB] benchmark error during scan: {model_name}: {e}")
            saved_models.append(saved)
            _set_model_scan_state(
                added=added,
                updated=updated,
                benchmarked=benchmarked,
                error="" if benchmark_failed == 0 else f"benchmark_failed={benchmark_failed}",
            )

        _set_model_scan_state(
            phase="planner",
            current=total,
            total=total,
            summary="Choosing planner and recommended roles...",
        )
        planner_key, recommendations = recommend_roles_with_planner(saved_models)
        initialized_roles = 0
        role_lock = settings_get("role_lock") == "true"
        for model in saved_models:
            if role_lock:
                break  # ロックされている場合はロール更新をスキップ
            roles = recommendations.get(model["id"], [])
            if not roles:
                continue
            joined = ",".join(roles)
            model_db_update(model["id"], {"auto_roles": joined})
            model["auto_roles"] = joined
            initialized_roles += 1

        final_models = model_db_list()
        schedule_default_model_load(reason="scan_complete")
        _set_model_scan_state(
            running=False,
            done=True,
            phase="done",
            current=total,
            total=total,
            summary="Benchmark complete." if benchmark_failed == 0 else f"Benchmark complete with {benchmark_failed} error(s).",
            planner_model=planner_key,
            initialized_roles=initialized_roles,
            found=total,
            added=added,
            updated=updated,
            benchmarked=benchmarked,
            models=final_models,
        )
    except Exception as e:
        _set_model_scan_state(
            running=False,
            done=True,
            phase="error",
            summary="Benchmark failed.",
            error=str(e),
        )
        print(f"[ModelDB] scan error: {e}")

@app.post("/models/db/scan")
def scan_model_folder_api(req: dict):
    folder = req.get("folder", "")
    if not folder:
        raise HTTPException(400, "folder required")
    job_id = str(uuid.uuid4())[:8]
    state = get_model_scan_state()
    if state.get("running"):
        return {"ok": False, "running": True, "job_id": state.get("job_id", "")}
    import threading as _scan_thread
    _scan_thread.Thread(target=_run_model_scan_job, args=(job_id, folder), daemon=True).start()
    return {"ok": True, "running": True, "job_id": job_id}



@app.get("/models/db/scan/status")
def model_scan_status_api():
    return get_model_scan_state()

@app.post("/models/db/benchmark/{mid}")
def benchmark_model_api(mid: str):
    """
    指定モデルのベンチマークをバックグラウンドで実行する。
    benchmark_mem.pyの関数を流用してVRAM/RAM/速度を計測。
    """
    models = model_db_list()
    model = next((m for m in models if m["id"] == mid), None)
    if not model:
        raise HTTPException(404, "model not found")

    import threading as _bt
    def _run_bench():
        try:
            updates = benchmark_model_profiles(model)
            model_db_update(mid, updates)
            print(f"[ModelDB] benchmark done: {model['name']} {updates}")
        except Exception as e:
            model_db_update(mid, {"notes": f"BENCHMARK ERROR: {e}"})
            print(f"[ModelDB] benchmark error: {e}")
            return
        try:
            all_models = model_db_list()
            if all_models:
                role_lock = settings_get("role_lock") == "true"
                _, recommendations = recommend_roles_with_planner(all_models)
                initialized_roles = 0
                if not role_lock:
                    for row in all_models:
                        existing_roles = [x.strip() for x in str(row.get("auto_roles", "")).split(",") if x.strip()]
                        if existing_roles:
                            continue  # 個別ベンチは空の場合のみ適用
                        roles = recommendations.get(row["id"], [])
                        if roles:
                            model_db_update(row["id"], {"auto_roles": ",".join(roles)})
                            initialized_roles += 1
                if initialized_roles > 0:
                    print(f"[ModelDB] initialized auto_roles after benchmark: {initialized_roles}")
        except Exception as e:
            print(f"[ModelDB] auto_roles step failed after benchmark: {e}")
        schedule_default_model_load(reason="benchmark_complete")

    _bt.Thread(target=_run_bench, daemon=True).start()
    return {"ok": True, "message": f"Benchmarking {model['name']} in background..."}

@app.post("/models/db/toggle/{mid}")
def toggle_model_enabled(mid: str, req: dict):
    """モデルの有効/無効を切り替える"""
    enabled = req.get("enabled", True)
    model_db_update(mid, {"enabled": 1 if enabled else 0})
    return {"ok": True, "enabled": enabled}


@app.post("/models/db/toggle_vlm/{mid}")
def toggle_model_vlm_enabled(mid: str, req: dict):
    vlm_enabled = req.get("vlm_enabled", True)
    model_db_update(mid, {"vlm_enabled": 1 if vlm_enabled else 0})
    return {"ok": True, "vlm_enabled": bool(vlm_enabled)}


@app.get("/models/roles")
def get_model_role_assignments_api():
    catalog = get_runtime_model_catalog(include_disabled=True)
    models = model_db_list()
    task_map = get_runtime_task_model_map(catalog, include_disabled=True)
    planner_key = task_map.get("plan") or (next(iter(catalog.keys())) if catalog else "")
    assignments = {}
    auto_map = _get_auto_role_model_map(catalog)
    for role in MODEL_ROLE_OPTIONS:
        explicit = settings_get(_role_setting_key(role)).strip()
        chosen = task_map.get(role, "")
        if explicit and explicit in catalog:
            source = "explicit"
        elif role in auto_map:
            source = "auto"
        elif chosen:
            source = "planner_fallback"
        else:
            source = "unassigned"
        assignments[role] = {
            "model_key": chosen,
            "source": source,
        }
    return {
        "roles": list(MODEL_ROLE_OPTIONS),
        "planner_key": planner_key,
        "assignments": assignments,
        "models": [
            {
                "id": m.get("id", ""),
                "model_key": m.get("model_key", ""),
                "name": m.get("name", ""),
                "enabled": int(m.get("enabled", 1) or 1),
                "vlm_enabled": int(m.get("vlm_enabled", 1) or 1),
                "is_vlm": int(m.get("is_vlm", 0) or 0),
                "ctx_size": _resolve_ctx_size(m.get("ctx_size")),
                "auto_roles": [x.strip() for x in str(m.get("auto_roles", "")).split(",") if x.strip()],
            }
            for m in models
        ],
    }


@app.post("/models/roles")
def save_model_role_assignments_api(req: dict):
    assignments = req.get("assignments", {})
    if not isinstance(assignments, dict):
        raise HTTPException(400, "assignments must be an object")
    catalog = get_runtime_model_catalog(include_disabled=True)
    updates = {}
    for role, model_key in assignments.items():
        if role not in MODEL_ROLE_OPTIONS:
            continue
        key = str(model_key or "").strip()
        if key and key not in catalog:
            raise HTTPException(400, f"Unknown model for role {role}: {key}")
        updates[_role_setting_key(role)] = key
    if updates:
        settings_set_bulk(updates)
    return {"ok": True, "saved_roles": [k.removeprefix("role_model_") for k in updates.keys()]}


@app.get("/models/orchestration")
def get_model_orchestration_api():
    catalog = get_runtime_model_catalog(include_disabled=True)
    ladder = get_coder_ladder_keys(catalog)
    return {
        "feature_mode": settings_get("feature_mode") or "model_orchestration",
        "policy": settings_get("orchestration_policy") or "ladder_fail_and_quality",
        "quality_check_enabled": settings_get("quality_check_enabled") != "false",
        "coder_primary": settings_get("coder_primary"),
        "coder_secondary": settings_get("coder_secondary"),
        "coder_tertiary": settings_get("coder_tertiary"),
        "resolved_ladder": ladder,
        "models": [
            {
                "model_key": m.get("model_key", ""),
                "name": m.get("name", ""),
                "enabled": int(m.get("enabled", 1) or 1),
                "tok_per_sec": _model_text_tps(m),
            } for m in model_db_list()
        ],
    }


@app.post("/models/orchestration")
def save_model_orchestration_api(req: dict):
    feature_mode = str(req.get("feature_mode", "model_orchestration")).strip().lower() or "model_orchestration"
    if feature_mode not in ("model_orchestration", "ensemble"):
        raise HTTPException(400, "invalid feature_mode")
    policy = str(req.get("policy", "ladder_fail_and_quality")).strip() or "ladder_fail_and_quality"
    if policy not in ("off", "ladder_fail_only", "ladder_fail_and_quality"):
        raise HTTPException(400, "invalid policy")
    catalog = get_runtime_model_catalog(include_disabled=True)
    updates = {
        "feature_mode": feature_mode,
        "orchestration_policy": policy,
        "quality_check_enabled": "true" if req.get("quality_check_enabled", True) else "false",
    }
    for key in ("coder_primary", "coder_secondary", "coder_tertiary"):
        mk = str(req.get(key, "") or "").strip()
        if mk and mk not in catalog:
            raise HTTPException(400, f"unknown model key: {mk}")
        updates[key] = mk
    settings_set_bulk(updates)
    return {"ok": True, "saved": updates}


@app.get("/ensemble/settings")
def get_ensemble_settings_api():
    status = get_ensemble_resource_status()
    return {
        "execution_mode": status.get("configured_mode", "parallel"),
        "auto_switch_on_low_vram": status.get("auto_switch_on_low_vram", True),
        "status": status,
    }


@app.post("/ensemble/settings")
def save_ensemble_settings_api(req: dict):
    mode = str(req.get("execution_mode", "parallel")).strip().lower() or "parallel"
    if mode not in ("parallel", "serial"):
        raise HTTPException(400, "execution_mode must be parallel or serial")
    auto_switch = bool(req.get("auto_switch_on_low_vram", True))
    settings_set_bulk({
        "ensemble_execution_mode": mode,
        "ensemble_auto_switch_on_low_vram": "true" if auto_switch else "false",
    })
    _sync_ensemble_settings_to_opencode_json()
    status = _apply_ensemble_execution_mode_guard()
    return {"ok": True, "execution_mode": settings_get("ensemble_execution_mode"), "status": status}


@app.get("/ensemble/vram")
def get_ensemble_vram_api():
    return get_ensemble_resource_status()


# =========================
# ユーザー設定 API
# =========================

@app.get("/settings")
def get_settings_api():
    """全設定を返す（未設定はデフォルト値）"""
    return settings_get_all()

@app.post("/settings")
def save_settings_api(req: dict):
    """複数設定を一括保存"""
    req = {k: v for k, v in req.items() if k not in ("max_output_tokens", "llm_port")}
    if "ctx_size" in req:
        req["ctx_size"] = str(_resolve_ctx_size(req.get("ctx_size")))
    if "summary_max_tokens" in req:
        try:
            v = int(req["summary_max_tokens"])
            req["summary_max_tokens"] = str(v if v in (200, 400, 800) else _get_summary_token_limit())
        except Exception:
            req.pop("summary_max_tokens", None)
    if "read_file_inject_max_chars" in req:
        try:
            req["read_file_inject_max_chars"] = str(max(4000, min(120000, int(req["read_file_inject_max_chars"]))))
        except Exception:
            req.pop("read_file_inject_max_chars", None)
    if "ensemble_execution_mode" in req:
        req["ensemble_execution_mode"] = str(req.get("ensemble_execution_mode", "parallel")).strip().lower()
        if req["ensemble_execution_mode"] not in ("parallel", "serial"):
            req["ensemble_execution_mode"] = "parallel"
    if "ensemble_auto_switch_on_low_vram" in req:
        raw = str(req.get("ensemble_auto_switch_on_low_vram", "true")).strip().lower()
        req["ensemble_auto_switch_on_low_vram"] = "true" if raw in ("true", "1", "yes", "on") else "false"
    settings_set_bulk(req)
    if "ensemble_execution_mode" in req or "ensemble_auto_switch_on_low_vram" in req:
        _sync_ensemble_settings_to_opencode_json()
        _apply_ensemble_execution_mode_guard()
    # search/streaming などサーバー側フラグも同期
    global _search_enabled, _llm_streaming, _current_n_ctx
    if "search_enabled" in req:
        _search_enabled = str(req["search_enabled"]).lower() in ("true", "1", "yes")
    if "streaming_enabled" in req:
        _llm_streaming = str(req["streaming_enabled"]).lower() in ("true", "1", "yes")
    if "ctx_size" in req:
        try:
            _current_n_ctx = max(512, min(65535, int(req["ctx_size"])))
        except Exception:
            pass
    return {"ok": True, "saved": list(req.keys())}

@app.get("/settings/{key}")
def get_setting_api(key: str):
    return {"key": key, "value": settings_get(key)}

@app.put("/settings/{key}")
def set_setting_api(key: str, req: dict):
    value = req.get("value", "")
    if _canonicalize_setting_key(str(key)) == "ctx_size":
        value = str(_resolve_ctx_size(value))
    settings_set(key, value)
    return {"ok": True, "key": key, "value": value}

@app.get("/settings/defaults")
def get_settings_defaults():
    return SETTINGS_DEFAULTS


# =========================
# リポジトリ管理 API
# =========================

@app.get("/repo/config")
def get_repo_config():
    """リポジトリ設定取得（機密トークンは除く）"""
    cfg = repo_config_load()
    creds = creds_load()
    return {
        **cfg,
        "has_token": bool(creds.get("github_token")),
        "github_username_saved": creds.get("github_username", ""),
    }

@app.post("/repo/config")
async def save_repo_config(request: Request):
    """リポジトリ設定保存（トークンは機密ファイルへ、それ以外はDB）"""
    data = await request.json()
    # 機密情報を .codeagent/.credentials へ
    token = data.pop("github_token", None)
    cred_username = data.pop("github_username_cred", None)
    if token is not None or cred_username is not None:
        creds = creds_load()
        if token is not None:
            creds["github_token"] = token
        if cred_username is not None:
            creds["github_username"] = cred_username
        creds_save(creds)
    # 非機密設定を DB へ
    repo_config_save(data)
    return {"ok": True}

@app.post("/repo/init")
async def init_repo(request: Request):
    """GitHubリポジトリを作成してリモートを設定"""
    import threading as _t
    data = await request.json()
    cfg = repo_config_load()
    creds = creds_load()

    token = creds.get("github_token", "")
    username = creds.get("github_username", "") or cfg.get("github_username", "")
    repo_name = data.get("repo_name") or cfg.get("github_repo_name", "codeagent-data")
    visibility = data.get("visibility") or cfg.get("github_repo_visibility", "private")
    branch = data.get("branch") or cfg.get("github_default_branch", "main")

    if not token:
        err_msg = "GitHub Personal Access Token が設定されていません (設定モーダル → GitHub 連携でトークンを保存してください)"
        logger.warning("[GH] init skipped: %s", err_msg)
        return {"ok": False, "error": err_msg}
    if not username:
        err_msg = "GitHub ユーザー名が設定されていません"
        logger.warning("[GH] init skipped: %s", err_msg)
        return {"ok": False, "error": err_msg}

    # GitHub API でリポジトリ作成
    try:
        resp = requests.post(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={
                "name": repo_name,
                "private": (visibility == "private"),
                "description": "CodeAgent data repository (managed by CodeAgent)",
                "auto_init": False,
            },
            timeout=15,
        )
        if resp.status_code == 422:
            # Already exists
            pass
        elif not resp.ok:
            err_msg = f"GitHub API エラー: {resp.status_code} {resp.text[:200]}"
            logger.error("[GH] init error: %s", err_msg)
            return {"ok": False, "error": err_msg}
    except requests.RequestException as e:
        err_msg = f"GitHub API 接続エラー: {e}"
        logger.error("[GH] init error: %s", err_msg)
        return {"ok": False, "error": err_msg}

    remote_url = f"https://github.com/{username}/{repo_name}.git"
    clean_url = remote_url  # トークンなし版

    # ca_data/ でリポジトリを初期化
    os.makedirs(CA_DATA_DIR, exist_ok=True)
    rc, out, err = _git_run(["init", "-b", branch], CA_DATA_DIR)
    if rc != 0:
        # older git: init then rename branch
        _git_run(["init"], CA_DATA_DIR)
        _git_run(["checkout", "-b", branch], CA_DATA_DIR)

    _git_run(["config", "user.email", "codeagent@local"], CA_DATA_DIR)
    _git_run(["config", "user.name", "CodeAgent"], CA_DATA_DIR)

    # リモート設定（既存なら更新）
    rc2, _, _ = _git_run(["remote", "get-url", "origin"], CA_DATA_DIR)
    if rc2 == 0:
        _git_run(["remote", "set-url", "origin", clean_url], CA_DATA_DIR)
    else:
        _git_run(["remote", "add", "origin", clean_url], CA_DATA_DIR)

    # .gitignore 作成（ca_data/ 用）
    _ensure_ca_data_gitignore()

    # 設定保存
    repo_config_save({
        "github_repo_name": repo_name,
        "github_repo_visibility": visibility,
        "github_default_branch": branch,
        "github_remote_url": clean_url,
        "github_username": username,
    })

    return {"ok": True, "remote_url": clean_url, "repo": repo_name}

@app.post("/repo/sync")
async def sync_repo(request: Request):
    """ca_data/ の変更をコミットして GitHub へプッシュ"""
    data = await request.json()
    message = data.get("message") or f"chore: sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    cfg = repo_config_load()
    creds = creds_load()
    token = creds.get("github_token", "")
    username = creds.get("github_username", "") or cfg.get("github_username", "")
    repo_name = cfg.get("github_repo_name", "")
    branch = cfg.get("github_default_branch", "main")

    if not token:
        err_msg = "GitHub Personal Access Token が設定されていません (設定モーダル → GitHub 連携でトークンを保存してください)"
        logger.warning("[GH] sync skipped: %s", err_msg)
        return {"ok": False, "error": err_msg}
    if not username or not repo_name:
        err_msg = "リポジトリ設定が不完全です。先に Init を実行してください"
        logger.warning("[GH] sync skipped: %s", err_msg)
        return {"ok": False, "error": err_msg}

    auth_url = f"https://{token}@github.com/{username}/{repo_name}.git"
    clean_url = f"https://github.com/{username}/{repo_name}.git"

    _ensure_ca_data_gitignore()
    _git_run(["add", "-A"], CA_DATA_DIR)

    rc, out, err = _git_run(["commit", "-m", message], CA_DATA_DIR)
    if rc != 0 and "nothing to commit" not in out + err:
        return {"ok": False, "error": err or out}

    # 認証URLを一時設定してプッシュ
    _git_run(["remote", "set-url", "origin", auth_url], CA_DATA_DIR)
    try:
        rc, out, err = _git_run(["push", "-u", "origin", branch], CA_DATA_DIR)
    finally:
        _git_run(["remote", "set-url", "origin", clean_url], CA_DATA_DIR)

    if rc != 0:
        return {"ok": False, "error": err or out}

    return {"ok": True, "message": message, "branch": branch}

@app.get("/repo/test-connection")
def test_repo_connection():
    """GitHub API 接続確認（トークンの有効性・ユーザー情報・レートリミット）"""
    creds = creds_load()
    token = creds.get("github_token", "")
    if not token:
        return {"ok": False, "error": "GitHub Personal Access Token が設定されていません (.codeagent/ に保存してください)"}
    try:
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        # ユーザー情報取得
        user_resp = requests.get("https://api.github.com/user", headers=headers, timeout=10)
        if not user_resp.ok:
            return {"ok": False, "error": f"認証失敗 (HTTP {user_resp.status_code}): トークンが無効か期限切れです"}
        user = user_resp.json()
        # レートリミット取得
        rate_resp = requests.get("https://api.github.com/rate_limit", headers=headers, timeout=10)
        rate = {}
        if rate_resp.ok:
            core = rate_resp.json().get("rate", {})
            import datetime as _dt
            reset_ts = core.get("reset", 0)
            reset_str = _dt.datetime.fromtimestamp(reset_ts).strftime("%H:%M:%S") if reset_ts else "?"
            rate = {"remaining": core.get("remaining"), "limit": core.get("limit"), "reset": reset_str}
        return {
            "ok": True,
            "login": user.get("login", ""),
            "name": user.get("name", ""),
            "plan": user.get("plan", {}).get("name", "") if user.get("plan") else "",
            "public_repos": user.get("public_repos", 0),
            "private_repos": user.get("total_private_repos", 0),
            "rate_limit": rate,
        }
    except requests.RequestException as e:
        return {"ok": False, "error": f"通信エラー: {e}"}


@app.get("/repo/status")
def get_repo_status():
    """ca_data/ の Git ステータス取得"""
    if not os.path.exists(os.path.join(CA_DATA_DIR, ".git")):
        return {"initialized": False, "status": "リポジトリ未初期化"}
    rc, out, err = _git_run(["status", "--short"], CA_DATA_DIR)
    rc2, log, _ = _git_run(["log", "--oneline", "-5"], CA_DATA_DIR)
    cfg = repo_config_load()
    return {
        "initialized": True,
        "status": out or "clean",
        "recent_commits": log,
        "remote_url": cfg.get("github_remote_url", ""),
        "branch": cfg.get("github_default_branch", "main"),
    }


def _ensure_ca_data_gitignore():
    """ca_data/.gitignore を必要なら作成"""
    gi_path = os.path.join(CA_DATA_DIR, ".gitignore")
    if not os.path.exists(gi_path):
        with open(gi_path, "w", encoding="utf-8") as f:
            f.write(
                "# ワークスペース内の一時ファイル\n"
                "workspace/**/__pycache__/\n"
                "workspace/**/*.pyc\n"
                "workspace/**/*.pyo\n"
                "workspace/**/node_modules/\n"
                "workspace/**/.DS_Store\n"
                "# DB ジャーナル\n"
                "*.db-journal\n"
                "*.db-shm\n"
                "*.db-wal\n"
            )


# =========================
# パーマネントメモリ API
# =========================

@app.get("/memory")
def list_memory(q: str = ""):
    """メモリ一覧 or キーワード検索"""
    if q.strip():
        entries = memory_search(q.strip(), limit=50)
    else:
        entries = memory_get_all()
    return {"entries": entries, "count": len(entries)}

@app.post("/memory")
def create_memory(req: dict):
    if not req.get("title") or not req.get("content"):
        raise HTTPException(400, "title and content required")
    mid = memory_save(req)
    return {"ok": True, "id": mid}

@app.put("/memory/{mid}")
def update_memory(mid: str, req: dict):
    req["id"] = mid
    memory_save(req)
    return {"ok": True}

@app.delete("/memory/{mid}")
def delete_memory_api(mid: str):
    memory_delete(mid)
    return {"ok": True}

@app.post("/memory/analyze/{job_id}")
def trigger_memory_analysis(job_id: str, project: str = "default"):
    """指定ジョブのログからメモリを抽出（手動トリガー）"""
    import threading as _t
    _t.Thread(target=_analyze_job_for_memory, args=(job_id, project, LLM_URL), daemon=True).start()
    return {"ok": True, "message": f"memory analysis triggered for job {job_id}"}

@app.get("/system/usage")
def system_usage_api():
    return get_system_usage_info()

@app.get("/system/usage/debug")
def system_usage_debug_api():
    usage = get_system_usage_info()
    diag = _get_last_usage_diag()
    return {
        "gpu_backend_selected": diag.get("gpu_backend_selected", usage.get("gpu_backend_selected", "auto")),
        "gpu_backend": diag.get("gpu_backend", usage.get("gpu_backend", "none")),
        "raw_parse_summary": diag.get("raw_parse_summary", []),
        "parse_source": diag.get("parse_source", "unknown"),
        "nvidia_smi_failure_reason": diag.get("nvidia_smi_failure_reason", ""),
        "adopted_values": diag.get("adopted_values", {}),
        "final_usage": {
            "gpus": usage.get("gpus", []),
            "vram_confidence": usage.get("vram_confidence", "unknown"),
            "vram_source_backend": usage.get("vram_source_backend", usage.get("gpu_backend", "none")),
            "updated_at": usage.get("updated_at"),
        },
    }

def _get_lightweight_health_status() -> dict:
    try:
        res = requests.get(f"http://127.0.0.1:{_model_manager.llm_port}/health", timeout=3)
        llm_ok = res.status_code == 200
    except Exception:
        llm_ok = False

    sandbox_ok = False
    sandbox_status = "docker unavailable"
    if _is_docker_available():
        sandbox_check = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", SANDBOX_CONTAINER],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        sandbox_ok = sandbox_check.returncode == 0 and sandbox_check.stdout.strip() == "true"
        sandbox_status = "running" if sandbox_ok else "not running (fallback: docker run)"

    return {
        "llm": "ok" if llm_ok else "unreachable",
        "sandbox": sandbox_status,
    }

@app.get("/system/summary")
def system_summary():
    model = _model_manager.status_dict()
    usage = get_system_usage_info()
    health = _get_lightweight_health_status()
    return {
        "health": health,
        "model": {
            "status": model.get("status"),
            "current_key": model.get("current_key"),
            "current_name": model.get("current_name"),
            "vram_gb": model.get("vram_gb"),
            "eta_sec": model.get("eta_sec"),
        },
        "usage": {
            "cpu_percent": usage.get("cpu_percent"),
            "ram_used_mb": usage.get("ram_used_mb"),
            "ram_total_mb": usage.get("ram_total_mb"),
            "gpu_backend": usage.get("gpu_backend"),
            "vram_confidence": usage.get("vram_confidence"),
            "vram_source_backend": usage.get("vram_source_backend"),
            "gpus": usage.get("gpus", []),
            "updated_at": usage.get("updated_at"),
        }
    }

@app.get("/debug/model-startup")
def debug_model_startup():
    """
    VRAM未使用・CPUフォールバック時の切り分け用。
    直近の起動コマンドとログ推定ヒントを返す。
    """
    hints = list(_model_manager._last_startup_hints or [])
    if not hints:
        hints = _infer_startup_failure_hints(LLAMA_STARTUP_LOG_PATH)
    log_tail = ""
    if os.path.exists(LLAMA_STARTUP_LOG_PATH):
        try:
            with open(LLAMA_STARTUP_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                log_tail = "".join(f.readlines()[-120:])[-8000:]
        except Exception:
            log_tail = ""
    return {
        "llama_path": _model_manager.llama_path,
        "last_start_cmd": _model_manager._last_start_cmd,
        "hints": hints,
        "log_path": LLAMA_STARTUP_LOG_PATH,
        "log_tail": log_tail,
    }

@app.get("/debug/llama")
def debug_llama():
    """
    llama-server のデバッグ情報を一括表示するエンドポイント。
    VRAM計算、起動コマンド、プロセス状態、ヘルスチェック、ログ末尾を返す。
    """
    # --- モデル情報 ---
    catalog = _model_manager._catalog()
    spec = catalog.get(_model_manager.current_key, {})
    model_path = spec.get("path", "")

    # --- VRAM計算 ---
    free_vram_mb = _get_total_free_vram_mb()
    gpu_cfg = _calc_safe_gpu_layers(spec) if spec else {}
    gguf_meta = _read_gguf_metadata(model_path) if model_path and os.path.exists(model_path) else {}

    # --- プロセス状態 ---
    proc = _model_manager._process
    if proc is not None:
        proc_status = "running" if proc.poll() is None else f"exited (code={proc.returncode})"
        proc_pid = proc.pid
    else:
        proc_status = "not started"
        proc_pid = None

    # --- llama-server ヘルスチェック ---
    llama_health = None
    try:
        import requests as _req
        r = _req.get(f"http://127.0.0.1:{_model_manager.llm_port}/health", timeout=3)
        llama_health = {"status_code": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500]}
    except Exception as e:
        llama_health = {"error": str(e)}

    # --- 起動ログ ---
    hints = list(_model_manager._last_startup_hints or [])
    if not hints:
        hints = _infer_startup_failure_hints(LLAMA_STARTUP_LOG_PATH)
    log_tail = ""
    if os.path.exists(LLAMA_STARTUP_LOG_PATH):
        try:
            with open(LLAMA_STARTUP_LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                log_tail = "".join(f.readlines()[-200:])[-12000:]
        except Exception:
            log_tail = ""

    return {
        "llama_path": _model_manager.llama_path,
        "llm_port": _model_manager.llm_port,
        "process": {"status": proc_status, "pid": proc_pid},
        "health": llama_health,
        "model": {
            "key": _model_manager.current_key,
            "name": spec.get("name", ""),
            "path": model_path,
            "file_size_mb": spec.get("file_size_mb", 0),
            "ctx": spec.get("ctx", 0),
            "gpu_layers_setting": spec.get("gpu_layers", 0),
            "proven_ngl": spec.get("proven_ngl", -1),
            "quantization": spec.get("quantization", ""),
        },
        "vram": {
            "free_vram_mb": free_vram_mb,
            "gpu_vendor": _detect_gpu_vendor(),
            "calc_result": gpu_cfg,
        },
        "gguf_metadata": gguf_meta,
        "startup": {
            "last_start_cmd": _model_manager._last_start_cmd,
            "hints": hints,
            "log_path": LLAMA_STARTUP_LOG_PATH,
            "log_tail": log_tail,
        },
    }

@app.get("/health")
def health():
    return _get_lightweight_health_status()

# =========================
# 静的ファイル配信
# / と /ui/ どちらでもUIにアクセスできる
# =========================

@app.get("/")
def root():
    """ルートアクセスをUIのindex.htmlに直接返す"""
    index = os.path.join(UI_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index, media_type="text/html", headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})
    return RedirectResponse("/ui/")

@app.get("/ui")
def ui_redirect():
    return RedirectResponse("/ui/")

app.mount("/workspace", StaticFiles(directory=WORK_DIR, html=True), name="workspace")
app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR, html=False), name="assets")
