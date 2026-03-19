from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
import subprocess
import json
import os
import re
import ast
import textwrap
import sqlite3
import uuid
import logging
import asyncio
import sys
from datetime import datetime

# Windows Proactor: SSE切断時のConnectionResetError警告を抑制
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # 起動時: 前回の残骸コンテナをクリーンアップ（後方定義のためglobals経由）
    cleanup = globals().get("_cleanup_server_containers")
    if cleanup: cleanup()
    yield
    # 終了時: サーバーコンテナを全て停止
    cleanup = globals().get("_cleanup_server_containers")
    if cleanup: cleanup()

app = FastAPI(lifespan=lifespan)

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
WORK_DIR = "./workspace"
SANDBOX_CONTAINER = "claude_sandbox"

os.makedirs(WORK_DIR, exist_ok=True)

UI_DIR = "./ui"
os.makedirs(UI_DIR, exist_ok=True)

# =========================
# Web検索 有効/無効フラグ（デフォルトOFF）
# =========================
_search_enabled = False
_search_num_results: int = 5  # デフォルト5件

# =========================
# ModelManager（動的モデル切り替え）
# =========================

import subprocess as _sp
import threading as _mm_thread
import time as _mm_time

MODEL_CATALOG = {
    # ── ベーシック（常時待機・高速） ──────────────────────────
    # 実測: VRAM 11,487 MiB / RAM 639 MiB / gen 154 tok/s / load 6s
    # Qwen9B(86 tok/s)より1.75倍高速。切替後モデルもVRAM13.8GBのため差小さい
    "basic": {
        "name": "GPT-OSS-20B",
        "path": os.environ.get("MODEL_GPT_OSS", ""),
        "ctx": 16384, "gpu_layers": 999, "threads": 8,
        "vram_gb": 11.5, "load_sec": 6, "parser": "gpt_oss",
        "description": "Always-on base. VRAM 11.5GB ctx=16K. 154 tok/s. o3-mini level",
    },
    # ── ルーター（超軽量・分類専用） ─────────────────────────
    # 実測: VRAM 1,630 MiB / RAM 284 MiB / gen 291 tok/s / load 2s
    "router": {
        "name": "LFM2.5-1.2B",
        "path": os.environ.get("MODEL_ROUTER", ""),
        "ctx": 4096, "gpu_layers": 999, "threads": 4,
        "vram_gb": 1.6, "load_sec": 2, "parser": "json",
        "description": "Ultra-fast router only. VRAM 1.6GB. 291 tok/s",
    },
    # ── 汎用・推論（GPT-OSS） ────────────────────────────────
    # 実測: VRAM 11,487 MiB / RAM 639 MiB / gen 154 tok/s / load 6s
    "gpt_oss": {
        "name": "GPT-OSS-20B",
        "path": os.environ.get("MODEL_GPT_OSS", ""),
        "ctx": 16384, "gpu_layers": 999, "threads": 8,
        "vram_gb": 11.8, "load_sec": 6, "parser": "gpt_oss",
        "description": "Best balance: VRAM 11.8GB ctx=16K. 154 tok/s. o3-mini level",
    },
    # ── 汎用バランス（Gemma） ────────────────────────────────
    # 実測: VRAM 8,486 MiB / RAM 944 MiB / gen 60 tok/s / load 4s
    # ctx=16KでKVが1GBと大きいため8Kを推奨
    "gemma": {
        "name": "Gemma-3-12B",
        "path": os.environ.get("MODEL_GEMMA", ""),
        "ctx": 8192, "gpu_layers": 999, "threads": 8,
        "vram_gb": 8.0, "load_sec": 4, "parser": "json",
        "description": "Balanced. VRAM 8GB ctx=8K. 60 tok/s. KV grows fast",
    },
    # ── 検証・JSON安定（Mistral） ────────────────────────────
    # 実測: VRAM 10,778 MiB / RAM 455 MiB / gen 37 tok/s / load 6s
    # ctx=32KでKVが5GB増 → 8K推奨
    "mistral": {
        "name": "Mistral-Small-3.2-24B",
        "path": os.environ.get("MODEL_MISTRAL", ""),
        "ctx": 8192, "gpu_layers": 999, "threads": 8,
        "vram_gb": 11.2, "load_sec": 6, "parser": "json",
        "description": "JSON stable. VRAM 11.2GB ctx=8K. 37 tok/s",
    },
    # ── 高品質コード（Qwen35） ───────────────────────────────
    # 実測: VRAM 13,841 MiB固定 / RAMオフロード 8,320 MiB(ctx=32K) / gen 22 tok/s / load 12s
    # ctx=32Kでも総メモリ21.6GB < RAM空き24.9GB → 32K OK
    "qwen35": {
        "name": "Qwen3.5-35B-A3B",
        "path": os.environ.get("MODEL_QWEN35", ""),
        "ctx": 32768, "gpu_layers": 999, "threads": 12,
        "vram_gb": 19.7, "load_sec": 12, "parser": "qwen_think",
        "parallel": 1, "batch_size": 2048, "ubatch_size": 64,
        "cache_type_k": "q8_0", "cache_type_v": "q8_0",
        "extra_args": ["--jinja", "--log-disable"],
        "description": "Code quality. VRAM 19.7GB ctx=32K. 28 tok/s",
    },
    # ── 最高品質コード（Coder-Next） ─────────────────────────
    # 実測: VRAM 13,849 MiB固定 / RAMオフロード 19,192 MiB(ctx=32K) / gen 13 tok/s / load 20s
    # ctx=32Kで総32.3GB。RAM空き24.9GBをわずかに超えるが実測OKのため採用
    "coder": {
        "name": "Qwen3-Coder-Next",
        "path": os.environ.get("MODEL_CODER", ""),
        "ctx": 32768, "gpu_layers": 42, "threads": 12,
        "vram_gb": 32.2, "load_sec": 20, "parser": "qwen_think",
        "parallel": 1, "batch_size": 2048, "ubatch_size": 64,
        "cache_type_k": "q8_0", "cache_type_v": "q8_0",
        "extra_args": ["--jinja", "--log-disable"],
        "description": "Best code. SWE-bench 70.6%. VRAM 32.2GB ctx=32K. 13 tok/s",
    },
}
TASK_MODEL_MAP = {
    "code":    "qwen35",   # コード実装 → 35B MoE
    "complex": "coder",    # 複雑デバッグ → Coder-Next
    "plan":    "basic",    # プランニング → Qwen9B (高速)
    "chat":    "basic",    # 会話 → Qwen9B
    "search":  "basic",    # 調査 → Qwen9B
    "verify":  "mistral",  # 検証 → Mistral (JSON安定)
    "reason":  "gpt_oss",  # 推論・数学 → GPT-OSS
    "multi":   "gemma",    # バランス → Gemma3
}
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
        self.llama_path      = os.environ.get("LLAMA_SERVER_PATH", r"C:\llama-cpp\llama-server.exe")
        self.llm_port        = int(os.environ.get("LLM_PORT", "8080"))
        self.router_url      = os.environ.get("ROUTER_URL", "")
        self.current_key     = os.environ.get("INITIAL_MODEL", "basic")
        self._process        = None
        self._lock           = _mm_thread.Lock()
        self._status         = "ready"
        self._switch_eta     = 0.0
        self._switch_callbacks = []
        # 起動時に実際に動いているモデルを検出してcurrent_keyを同期
        self._sync_current_model()

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
                    for key, spec in MODEL_CATALOG.items():
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
        return MODEL_CATALOG.get(self.current_key, {}).get("parser", "json")

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
            key = TASK_MODEL_MAP.get(word, "basic")
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
            return "coder"
        elif n >= 3 or any(k in txt for k in code_keywords):
            return "qwen35"
        else:
            return "basic"

    def ensure_model(self, key: str, on_event=None) -> bool:
        """必要なら切り替え、不要なら即return True"""
        if not MODEL_CATALOG.get(key, {}).get("path"):
            key = "basic"
        if key == self.current_key and self._status == "ready":
            return True
        return self._switch(key, on_event)

    def _switch(self, key: str, on_event=None) -> bool:
        def emit(t, msg, pct=0, eta=0):
            if on_event:
                on_event({"type": t, "message": msg, "pct": pct, "eta_sec": eta})

        with self._lock:
            self._status = "switching"
            spec = MODEL_CATALOG[key]
            self._switch_eta = _mm_time.time() + spec["load_sec"]
            prev_name = MODEL_CATALOG.get(self.current_key, {}).get("name", "current")

            emit("model_switching", f"Unloading {prev_name}...", 10, spec["load_sec"])
            self._kill()
            _mm_time.sleep(1)

            emit("model_switching", f"Loading {spec['name']}...", 30,
                 max(0, int(self._switch_eta - _mm_time.time())))

            ok = self._start(spec, on_event, emit)
            if ok:
                self.current_key = key
                self._status = "ready"
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
        cmd = [
            self.llama_path,
            "--model",    spec["path"],
            "--port",     str(self.llm_port),
            "--host",     "0.0.0.0",
            "--ctx-size", str(spec["ctx"]),
            "-ngl",       str(spec["gpu_layers"]),
            "--threads",  str(spec["threads"]),
            "--no-mmap",
        ]
        # モデル別オプション
        if "parallel" in spec:
            cmd += ["--parallel", str(spec["parallel"])]
        if "batch_size" in spec:
            cmd += ["--batch-size", str(spec["batch_size"])]
        if "ubatch_size" in spec:
            cmd += ["--ubatch-size", str(spec["ubatch_size"])]
        if "cache_type_k" in spec:
            cmd += ["--cache-type-k", spec["cache_type_k"]]
        if "cache_type_v" in spec:
            cmd += ["--cache-type-v", spec["cache_type_v"]]
        for arg in spec.get("extra_args", []):
            cmd.append(arg)
        print(f"[ModelManager] starting: {' '.join(cmd[1:3])} parallel={spec.get('parallel','auto')} ubatch={spec.get('ubatch_size','512')}")
        try:
            flags = _sp.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            self._process = _sp.Popen(cmd, stdout=_sp.DEVNULL, stderr=_sp.DEVNULL, creationflags=flags)
        except Exception as e:
            print(f"[ModelManager] Popen error: {e}")
            return False

        import requests as _req
        health = f"http://127.0.0.1:{self.llm_port}/health"
        for i in range(90):
            _mm_time.sleep(2)
            elapsed = i * 2
            remaining = max(0, int(self._switch_eta - _mm_time.time()))
            pct = min(90, 30 + elapsed * 60 // spec["load_sec"])
            emit("model_switching", f"Loading {spec['name']}... {elapsed}s", pct, remaining)
            try:
                if _req.get(health, timeout=2).status_code == 200:
                    return True
            except: pass
            if self._process.poll() is not None:
                print("[ModelManager] process exited during load")
                return False
        return False

    def status_dict(self) -> dict:
        # switching中でない場合は実際のモデルと同期
        if self._status != "switching":
            self._sync_current_model()
        spec = MODEL_CATALOG.get(self.current_key, {})
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
                for k, v in MODEL_CATALOG.items()
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_steps_job_id ON job_steps(job_id, seq)")
    conn.commit()

def get_db(project: str) -> sqlite3.Connection:
    """毎回新しいコネクションを開く。WALモードで読み書き並行OK。"""
    conn = sqlite3.connect(_get_db_path(project), check_same_thread=False)
    _init_db(conn)
    return conn


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


# =========================
# コンテキスト管理
# =========================

def _estimate_tokens(messages: list) -> int:
    """メッセージリストのトークン数を概算（1token≒4文字）"""
    total = sum(len(str(m.get("content", ""))) for m in messages)
    return total // 4

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
        t = len(str(msg.get("content", ""))) // 4
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
        full = os.path.join(WORK_DIR, project, path)
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
        full = os.path.join(WORK_DIR, project, path)
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
        full = os.path.join(WORK_DIR, project, path)
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
        target = os.path.join(WORK_DIR, project, subdir) if subdir else os.path.join(WORK_DIR, project)
        result = []
        for root, dirs, files in os.walk(target):
            rel = os.path.relpath(root, os.path.join(WORK_DIR, project)).replace("\\", "/")
            for f in files:
                path = (rel + "/" + f).lstrip("./").lstrip("/")
                if rel in (".", ""):
                    path = f
                result.append(path)
        # .history.dbは除外
        result = [r for r in result if not r.endswith(".history.db") and not r.endswith("_run.py") and not r.endswith("_venv_run.py")]
        return "\n".join(result) if result else "(empty)"
    except Exception as e:
        return f"ERROR: {e}"

def _server_container_name(port: int) -> str:
    return f"codeagent_server_{port}"

def _cleanup_server_containers():
    """CodeAgentサーバーコンテナを全て停止・削除（起動時・異常時に呼ぶ）"""
    result = _sp.run(
        ["docker", "ps", "-a", "--filter", "name=codeagent_server_",
         "--format", "{{.Names}}"],
        capture_output=True, text=True
    )
    for name in result.stdout.strip().splitlines():
        if name.startswith("codeagent_server_"):
            _sp.run(["docker", "rm", "-f", name], capture_output=True)
            print(f"[run_server] cleaned up: {name}")

def run_server(port: int = 8888, project: str = "default") -> str:
    """
    プロジェクトフォルダをDockerコンテナ内のHTTPサーバーで公開。
    同名コンテナは常に1つだけ。異常時も増殖しない。
    """
    import time, urllib.request
    project_dir = os.path.join(WORK_DIR, project)
    abs_project_dir = os.path.abspath(project_dir)
    if not os.path.exists(abs_project_dir):
        return f"ERROR: project dir not found: {abs_project_dir}"

    container_name = _server_container_name(port)

    # 同名コンテナを問答無用で削除（停止中・起動中・エラー状態問わず）
    _sp.run(["docker", "rm", "-f", container_name], capture_output=True)

    # 新規起動（--rmなし、名前固定で1つだけ保証）
    cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "-p", f"{port}:{port}",
        "-v", f"{abs_project_dir}:/srv:ro",  # :ro で読み取り専用マウント
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



def setup_venv(requirements: list = None, project: str = "default") -> str:
    """
    プロジェクトフォルダに .venv/ を構築し requirements.txt を生成・インストールする。
    Dockerで動作確認済みのパッケージを .venv/ にインストールしておく。
    ユーザーは activate → python app.py で即実行できる状態にする（ローカル自動実行はしない）。
    """
    import sys
    project_dir = os.path.abspath(os.path.join(WORK_DIR, project))
    venv_dir = os.path.join(project_dir, ".venv")
    req_file = os.path.join(project_dir, "requirements.txt")
    python_bin = sys.executable

    # requirements.txt 生成
    reqs = requirements or []
    if reqs:
        with open(req_file, "w", encoding="utf-8") as f:
            f.write("\n".join(reqs) + "\n")

    # .venv 作成
    venv_existed = os.path.isdir(venv_dir)
    if not venv_existed:
        r = _sp.run([python_bin, "-m", "venv", venv_dir], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return (f"ok: requirements.txt generated ({', '.join(reqs)})\n"
                    f"WARNING: .venv creation failed: {r.stderr.strip()[:100]}\n"
                    f"手動: python -m venv .venv && .venv\\Scripts\\activate && pip install -r requirements.txt")

    # pip install（Dockerで確認済みパッケージを.venvに導入）
    pip = os.path.join(venv_dir, "Scripts", "pip.exe") if os.name == "nt" else os.path.join(venv_dir, "bin", "pip")
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
    """Playwrightコンテナが起動中でなければ起動する"""
    check = _sp.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", BROWSER_CONTAINER],
        capture_output=True, text=True
    )
    if check.returncode == 0 and check.stdout.strip() == "true":
        return True
    # 既存のコンテナを削除してから起動
    _sp.run(["docker", "rm", "-f", BROWSER_CONTAINER], capture_output=True)
    result = _sp.run([
        "docker", "run", "-d", "--name", BROWSER_CONTAINER,
        "--memory=1g", "--cpus=2",
        "-v", f"{os.path.abspath(WORK_DIR)}:/app",
        BROWSER_IMAGE,
        "tail", "-f", "/dev/null"  # コンテナを起動したまま待機
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[browser] container start failed: {result.stderr[:200]}")
        return False
    import time; time.sleep(2)  # 起動待ち
    return True

def run_browser(script: str, project: str = "default") -> str:
    """
    Playwright（Python）をDockerコンテナ内で実行してブラウザ自動化を行う。
    script: Playwrightを使ったPythonコード
    - from playwright.sync_api import sync_playwright を使う
    - headless=True でブラウザを起動すること
    - スクリーンショットは /app/{project}/screenshot.png に保存できる
    - ホスト上のrun_serverにアクセスする場合: http://host.docker.internal:8888/
      （Windows/Mac: host.docker.internalが使える。Linux: --add-host=host.docker.internal:host-gateway が必要）
    例:
      from playwright.sync_api import sync_playwright
      with sync_playwright() as p:
          browser = p.chromium.launch(headless=True)
          page = browser.new_page()
          page.goto("http://host.docker.internal:8888/")
          page.screenshot(path="/app/{project}/screenshot.png")
          print(page.title())
          browser.close()
    """
    if not _ensure_browser_container(project):
        # コンテナなしで都度起動
        use_exec = False
    else:
        use_exec = True

    project_dir = os.path.join(WORK_DIR, project)
    os.makedirs(project_dir, exist_ok=True)
    script_path = os.path.join(project_dir, "_browser_run.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

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
            BROWSER_IMAGE,
            "python", f"/app/{project}/_browser_run.py"
        ]

    try:
        result = _sp.run(cmd, capture_output=True, text=True, timeout=60,
                         encoding="utf-8", errors="replace")
        out = (result.stdout + result.stderr).strip()
        # スクリーンショットが保存されたか確認
        ss_path = os.path.join(project_dir, "screenshot.png")
        if os.path.exists(ss_path):
            out += f"\n[screenshot saved: screenshot.png ({os.path.getsize(ss_path)} bytes)]"
        return out[:4000] or "(no output)"
    except _sp.TimeoutExpired:
        return "ERROR: timeout (60s)"
    except Exception as e:
        return f"ERROR: {e}"


# ──────────────────────────────────────────────────
# npm / Node.js 実行環境ツール（Docker内）
# ──────────────────────────────────────────────────

NODE_IMAGE   = "node:20-slim"
NODE_MODULES_VOLUME = "codeagent_node_modules"  # プロジェクト間で共有

def run_npm(command: str, project: str = "default") -> str:
    """
    Node.js/npm コマンドをDockerコンテナ内で実行する。
    command: 実行するnpmコマンド（例: "test", "run build", "install"）
    プロジェクトフォルダをマウントして実行する。
    package.jsonが存在すること。
    例: run_npm("test") → npm test を実行
        run_npm("run build") → npm run build を実行
        run_npm("install") → npm install を実行
    """
    project_dir = os.path.abspath(os.path.join(WORK_DIR, project))
    pkg_json = os.path.join(project_dir, "package.json")

    if not os.path.exists(pkg_json) and not command.startswith("init"):
        return "ERROR: package.json not found. Run npm init or create package.json first."

    cmd = [
        "docker", "run", "--rm",
        "--memory=1g", "--cpus=2",
        "-w", "/app",
        "-v", f"{project_dir}:/app",
        # node_modulesをコンテナ内に閉じ込める（ホストを汚さない）
        "-v", f"{BROWSER_CONTAINER}_node_modules:/app/node_modules",
        NODE_IMAGE,
        "sh", "-c", f"npm {command} 2>&1"
    ]
    # node_modulesボリュームが存在しない場合は作成（初回のみ）
    _sp.run(["docker", "volume", "create", NODE_MODULES_VOLUME],
            capture_output=True)

    try:
        result = _sp.run(cmd, capture_output=True, text=True, timeout=120,
                         encoding="utf-8", errors="replace")
        out = (result.stdout + result.stderr).strip()
        return out[:4000] or "(no output, exit code: " + str(result.returncode) + ")"
    except _sp.TimeoutExpired:
        return "ERROR: timeout (120s)"
    except Exception as e:
        return f"ERROR: {e}"


def run_node(script: str, project: str = "default") -> str:
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

    cmd = [
        "docker", "run", "--rm",
        "--memory=512m", "--cpus=2",
        "-w", "/app",
        "-v", f"{project_dir}:/app",
        "-v", f"{BROWSER_CONTAINER}_node_modules:/app/node_modules",
        NODE_IMAGE,
        "node", "/app/_node_run.js"
    ]
    _sp.run(["docker", "volume", "create", NODE_MODULES_VOLUME],
            capture_output=True)

    try:
        result = _sp.run(cmd, capture_output=True, text=True, timeout=30,
                         encoding="utf-8", errors="replace")
        out = (result.stdout + result.stderr).strip()
        return out[:4000] or "(no output)"
    except _sp.TimeoutExpired:
        return "ERROR: timeout (30s)"
    except Exception as e:
        return f"ERROR: {e}"


def stop_server(port: int = 8888) -> str:
    """run_serverで起動したDockerサーバーを停止・削除する"""
    container_name = _server_container_name(port)
    result = _sp.run(["docker", "rm", "-f", container_name], capture_output=True, text=True)
    if result.returncode == 0:
        return f"ok: stopped server on port {port}"
    return f"already stopped (container not found)"


def write_file(path: str, content: str, project: str = "default") -> str:
    try:
        full = os.path.join(WORK_DIR, project, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        preview = "\n".join(content.splitlines()[:3])
        return f"ok: wrote {len(content)} chars to {path}\npreview:\n{preview}"
    except Exception as e:
        return f"ERROR: {e}"

def patch_function(path: str, function_name: str, new_code: str, project: str = "default") -> str:
    try:
        full = os.path.join(WORK_DIR, project, path)
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

        with open(os.path.join(WORK_DIR, project, path), "w", encoding="utf-8") as f:
            f.write(new_source)

        return f"ok: patched function '{function_name}' in {path} (lines {start+1}-{end})"
    except SyntaxError as e:
        return f"SYNTAX ERROR in new_code: {e}"
    except Exception as e:
        return f"ERROR: {e}"

def run_python(code: str, project: str = "default") -> str:
    """
    Pythonコードをサンドボックス（Docker）で実行する。
    _run.py はプロジェクトフォルダ内に配置し、プロジェクトのファイルにアクセス可能。
    Dockerは WORK_DIR 全体をマウントし /app/{project}/ がプロジェクトフォルダ。
    """
    try:
        project_dir = os.path.join(WORK_DIR, project)
        os.makedirs(project_dir, exist_ok=True)
        run_file_path = os.path.join(project_dir, "_run.py")
        with open(run_file_path, "w", encoding="utf-8") as f:
            f.write(code)

        check = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", SANDBOX_CONTAINER],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        use_exec = check.returncode == 0 and check.stdout.strip() == "true"

        # Docker内でのパス: /app/{project}/_run.py
        container_script = f"/app/{project}/_run.py"
        if use_exec:
            cmd = ["docker", "exec", "-w", f"/app/{project}", SANDBOX_CONTAINER, "python", container_script]
        else:
            cmd = [
                "docker", "run", "--rm",
                "--memory=512m", "--memory-swap=512m", "--cpus=2",
                "-w", f"/app/{project}",
                "-v", f"{os.path.abspath(WORK_DIR)}:/app",
                "python:3.11", "python", container_script
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
        out = result.stdout + result.stderr
        return out[:4000] if len(out) > 4000 else out
    except subprocess.TimeoutExpired:
        return "ERROR: timeout (30s)"
    except Exception as e:
        return f"ERROR: {e}"

def run_file(path: str, project: str = "default") -> str:
    """
    プロジェクト内のPythonファイルをサンドボックスで実行する。
    path は プロジェクトフォルダ内の相対パス（例: "app.py", "tests/test_main.py"）。
    """
    try:
        check = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Running}}", SANDBOX_CONTAINER],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        use_exec = check.returncode == 0 and check.stdout.strip() == "true"

        # pathにプロジェクト名が含まれていない場合は付加
        if not path.startswith(project + "/") and not path.startswith(project + "\\"):
            container_path = f"/app/{project}/{path}"
            work_dir = f"/app/{project}"
        else:
            container_path = f"/app/{path}"
            work_dir = f"/app/{project}"

        if use_exec:
            cmd = ["docker", "exec", "-w", work_dir, SANDBOX_CONTAINER, "python", container_path]
        else:
            cmd = [
                "docker", "run", "--rm",
                "--memory=512m", "--memory-swap=512m", "--cpus=2",
                "-w", work_dir,
                "-v", f"{os.path.abspath(WORK_DIR)}:/app",
                "python:3.11", "python", container_path
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace")
        out = result.stdout + result.stderr
        return out[:4000] if len(out) > 4000 else out
    except subprocess.TimeoutExpired:
        return "ERROR: timeout (30s)"
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

def web_search(query: str, num_results: int = 0) -> str:
    """
    DuckDuckGo で検索する。送信前にクエリを無害化する。
    結果はLLMに渡すのみ、ローカル保存なし。
    """
    global _search_enabled
    if not _search_enabled:
        return "SEARCH_DISABLED: Web search is currently disabled. The user must enable it from the UI."
    try:
        import urllib.request
        import urllib.parse
        import html as html_mod

        # クエリ無害化（機密情報を除去）
        # num_results=0 はグローバル設定を使用
        n = num_results if num_results > 0 else _search_num_results
        safe_query, removed = sanitize_query(query)
        if not safe_query:
            return "SEARCH_BLOCKED: Query contained only sensitive data and was not sent."
        if removed:
            print(f"[SEARCH][SANITIZED] original_len={len(query)} removed={removed}")

        results = []

        # Instant Answer API（サマリーのみ）
        ia_url = "https://api.duckduckgo.com/?q=" + urllib.parse.quote(safe_query) + "&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(ia_url, headers={"User-Agent": "CodeAgent/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode())

        if data.get("AbstractText"):
            # サマリーは200文字に制限
            results.append(f"[Summary] {data['AbstractText'][:200]}")

        # HTML検索（先頭100KBだけ読む）
        search_url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(safe_query)
        req2 = urllib.request.Request(search_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req2, timeout=8) as resp:
            body = resp.read(102400).decode("utf-8", errors="ignore")  # 100KBで打ち切り

        snippets = re.findall(
            r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>.*?'
            r'class="result__snippet"[^>]*>(.*?)</div>',
            body, re.DOTALL
        )
        # 件数を n 件・各150文字に絞る
        for url, title, snippet in snippets[:n]:
            title_clean = html_mod.unescape(re.sub(r"<[^>]+>", "", title)).strip()[:80]
            snippet_clean = html_mod.unescape(re.sub(r"<[^>]+>", "", snippet)).strip()[:150]
            if title_clean and snippet_clean:
                results.append(f"[{title_clean}] {snippet_clean}")

        if not results:
            return f"No results found for: {safe_query}"

        # 合計文字数を件数に応じて調整
        max_chars = 600 + n * 200
        body_text = f"Search: {safe_query}\n" + "\n".join(results)
        return body_text[:max_chars]

    except Exception as e:
        return f"Search error: {e}"



# =========================
# JSON抽出（LLM出力が汚くても壊れない）
# =========================

def _parse_gpt_oss_channel(text: str):
    """
    GPT-OSS-20B の <|channel|>X to=Y <|message|>{...} 形式をエージェント形式に変換。
    通常JSONが取れない場合のフォールバック。
    """
    m = re.search(r'<\|channel\|>(\w+)(?:\s+to=([\w.]+))?(?:\s+\w+)?<\|message\|>(.*)', text, re.DOTALL)
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
        if k == "input" and isinstance(v, dict):
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

    # 3. テキスト中の最初のJSONオブジェクト
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            result = json.loads(m.group(0))
            # actionフィールドがある場合のみ有効なエージェント応答とみなす
            return result
        except Exception:
            pass

    # 4. 途中切れJSONの補完救済（トークン上限で切れた場合）
    repaired = _repair_truncated_json(text)
    if repaired and repaired.get("action"):
        print(f"[extract_json] repaired truncated JSON: action={repaired['action']}")
        return repaired

    # 5. GPT-OSS-20B チャンネル形式フォールバック
    gpt_oss = _parse_gpt_oss_channel(text)
    if gpt_oss:
        return gpt_oss

    return None

# =========================
# LLM呼び出し
# =========================

def call_llm_chat(messages: list, llm_url: str = "") -> tuple:
    """
    chatモード専用: JSON強制なし、通常の会話応答。
    thinking モデル対応: content が空なら reasoning_content を使用。
    llama-server 500 (GPT-OSS-20Bのチャンネル形式) でもボディを読む。
    (content, usage_dict) を返す。
    """
    url = llm_url.strip() or LLM_URL
    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": min(_current_n_ctx - _estimate_tokens(messages) - 64, 32768),
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
            err_msg = data["error"].get("message", "")
            # エラーメッセージにモデル出力が含まれている場合がある
            if "context" in err_msg.lower() and "exceed" in err_msg.lower():
                raise HTTPException(status_code=413, detail=f"Context exceeded: {err_msg[:200]}")
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
        messages = _trim_messages(messages, _current_n_ctx // 2, reserve_output=2048)
        payload["messages"] = messages
        payload["max_tokens"] = min(_current_n_ctx // 2 - _estimate_tokens(messages) - 64, 8192)
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


def call_llm(messages: list, llm_url: str = "") -> tuple:
    """
    (content, usage_dict) を返す。
    usage_dict = {"prompt_tokens":N, "completion_tokens":N, "tps":N}
    エージェントツール用: JSON出力を強制。
    """
    url = llm_url.strip() or LLM_URL
    payload = {
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": min(_current_n_ctx - _estimate_tokens(messages) - 64, 32768),
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
            err_msg = data["error"].get("message", "")
            if "context" in err_msg.lower() and "exceed" in err_msg.lower():
                raise HTTPException(status_code=413, detail=f"Context exceeded: {err_msg[:200]}")
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

SYSTEM_PROMPT = """あなたはコード編集・実行AIです。

【絶対ルール】
- 必ず純粋なJSONオブジェクトのみを出力する。それ以外は一切禁止。
- <|channel|>や<|start|>などの特殊トークンは使わない。
- マークダウン、説明文、コードブロック(```)も禁止。
- 最初の文字は必ず { であること。

【出力形式】（このフォーマット厳守）
{"thought":"考えていること","action":"ツール名","input":{ツールの引数}}

【最終回答】
{"thought":"完了","action":"final","input":{},"output":"ユーザーへの回答"}

【ツール一覧】
- list_files: {"subdir": ""}
- get_outline: {"path": "foo.py"}  ← 大きなファイルの構造把握（関数/クラス/HTML要素と行番号）
- read_file: {"path": "foo.py"}  または {"path": "foo.py", "start_line": 10, "end_line": 50}
- write_file: {"path": "foo.py", "content": "..."}  ← 新規作成・全体上書き専用
- edit_file: {"path": "foo.py", "old_str": "変更前の文字列（一意）", "new_str": "変更後"}  ← 差分修正（推奨）
- patch_function: {"path": "foo.py", "function_name": "bar", "new_code": "def bar(): ..."}
- run_python: {"code": "print('hello')"}  ← project引数不要（自動設定）
- run_file: {"path": "foo.py"}  ← プロジェクト内の相対パス、project引数不要
- run_server: {"port": 8888}  ← 【最終タスクのみ】DockerでHTTPサーバー起動
- stop_server: {"port": 8888}  ← 起動したサーバーを停止
- run_browser: {"script": "from playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n  b=p.chromium.launch(headless=True)\n  pg=b.new_page()\n  pg.goto('http://host.docker.internal:8888/')\n  pg.screenshot(path='/app/{project}/screenshot.png')\n  print(pg.title())\n  b.close()"}  ← Playwright（Python）でブラウザ自動化・スクリーンショット・動作確認
- run_npm: {"command": "test"}  ← npm コマンドをDockerで実行（test/install/run build等）
- run_node: {"script": "console.log(require('./script.js'))"}  ← JSコードをNode.jsで実行・テスト
- setup_venv: {"requirements": ["flask","numpy"]}  ← Pythonプロジェクトで.venv構築＋requirements.txt生成（実行はユーザーが行う）
- web_search: {"query": "検索クエリ", "num_results": 5}
- clarify: {"question": "質問", "options": ["選択肢1", "選択肢2"]}

【戦略】
1. まず list_files でファイル構成を把握
2. 大きなファイル（100行超）は get_outline で構造確認 → read_file(start_line, end_line) で必要箇所だけ読む
3. 既存ファイルの修正は edit_file を使う（write_file は新規作成か全体刷新のみ）
4. edit_file の old_str は一意に特定できる十分な文字列にすること（前後の行を含める）
5. 実行後エラーがあれば必ず自分で修正して再実行
6. HTTPサーバー起動は run_python ではなく run_server を使う（run_pythonはサーバー系タイムアウトする）
7. 要件が曖昧な場合は clarify でユーザーに確認
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
     1. run_python でDockerサンドボックスにて動作確認・ユニットテスト
     2. WebアプリはFlask等: run_server → run_browser でブラウザ確認+スクショ
     3. setup_venv(requirements=["flask","numpy",...]) でローカルvenv構築
        → .venv/ と requirements.txt を生成・pip installまで完了
        → ユーザーが activate → python app.py で即実行できる状態

   ※ 全ファイルはプロジェクトフォルダ直下に配置する
   ※ .venv/ は絶対パスを含むため移動不可・プロジェクト固定"""

def _build_system_prompt(project: str = "") -> str:
    """
    SYSTEM_PROMPTにスキル一覧を注入して返す（OpenClaw互換）。
    スキルは C:\\AI\\skills\\ の SKILL.md から自動ロード。
    """
    # _skills_to_prompt_injectionは後方定義のためglobals()経由で取得
    inject_fn = globals().get("_skills_to_prompt_injection")
    injection = inject_fn() if inject_fn else ""
    if not injection:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + injection


# =========================
# ツールレジストリ
# =========================

TOOLS = {
    "read_file": read_file,
    "list_files": list_files,
    "write_file": write_file,
    "edit_file": edit_file,
    "get_outline": get_outline,
    "patch_function": patch_function,
    "run_python": run_python,
    "run_file": run_file,
    "run_server": run_server,
    "run_browser": run_browser,
    "run_npm": run_npm,
    "run_node": run_node,
    "setup_venv": setup_venv,
    "stop_server": stop_server,
    "web_search": web_search,
}

# =========================
# リクエストモデル
# =========================

class ChatRequest(BaseModel):
    message: str
    max_steps: int = 20
    project: str = "default"
    search_enabled: bool = True
    llm_url: str = ""

class ProjectRequest(BaseModel):
    name: str

class LLMTestRequest(BaseModel):
    url: str

class JobRequest(BaseModel):
    message: str
    project: str = "default"
    mode: str = "task"
    max_steps: int = 20
    search_enabled: bool = False
    llm_url: str = ""
    approved_tasks: list = None
    chat_history: list = []
    recommended_model: str = ""   # planが推奨したモデルキー（空なら自動判断）
    auto_select_option: bool = True  # True: プランナーLLMが対応案を自動選択 / False: ユーザー手動選択

def run_job_background(job_id: str, req: "JobRequest"):
    """
    バックグラウンドスレッドで実行。
    全イベントをDBに書き込み続ける（ブラウザが閉じても継続）。
    """
    project = req.project
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
            # chatモード: 直接LLM呼び出し（エージェントループなし・JSON強制なし）
            exec_url = req.llm_url.strip() or _model_manager.llm_url

            CHAT_SYSTEM = "あなたはCodeAgentです。ユーザーの質問に丁寧に答えてください。コードが必要な場合はmarkdownで記述してください。"
            history_msgs = []
            for h in (req.chat_history or [])[-8:]:
                role = h.get("role", "user")
                text = str(h.get("text", ""))[:800]
                if role in ("user", "assistant") and text:
                    history_msgs.append({"role": role, "content": text})

            messages = [
                {"role": "system", "content": CHAT_SYSTEM},
                *history_msgs,
                {"role": "user", "content": req.message},
            ]
            messages = _trim_messages(messages, _current_n_ctx, reserve_output=2048)
            reply, usage = call_llm_chat(messages, llm_url=exec_url)
            write("done", {"result": reply, "status": "done", "usage": usage})
            save_session(job_id, project, req.message, "chat", {"output": reply, "status": "done"})


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
            if forced_model and forced_model != "auto" and forced_model in MODEL_CATALOG:
                # UIで手動選択されたモデルを使用
                best_key = forced_model
                print(f"[ModelManager] user selected: {best_key}")
            else:
                # Auto or 未指定: 現在のモデルをそのまま使う（切り替えしない）
                best_key = _model_manager.current_key
                print(f"[ModelManager] auto: keeping current model {best_key}")

            if best_key != _model_manager.current_key and MODEL_CATALOG.get(best_key, {}).get("path"):
                write("model_switching", {
                    "from": _model_manager.current_key,
                    "to": best_key,
                    "model_name": MODEL_CATALOG.get(best_key, {}).get("name", best_key),
                    "eta_sec": MODEL_CATALOG.get(best_key, {}).get("load_sec", 60),
                    "message": f"Loading {MODEL_CATALOG.get(best_key,{}).get('name',best_key)}..."
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

            for i, todo in enumerate(todos):
              try:  # ← per-task guard: 1タスクの例外がジョブ全体を止めないよう保護
                write("task_start", {
                    "task_id": todo["id"], "title": todo["title"],
                    "task_index": i, "total": total
                })

                # execute_task_stream を使ってステップごとに書き込む
                task_steps = []
                task_status = "pending"  # done/error/pendingで区別
                task_output = ""

                # req.llm_urlが明示されていればそちら、なければModelManagerのURL
                task_url = req.llm_url.strip() or _model_manager.llm_url
                try:
                    for ev in execute_task_stream(
                        task_detail=todo["detail"], context=context,
                        max_steps=req.max_steps, project=project,
                        search_enabled=req.search_enabled, llm_url=task_url,
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

                def _run_stage(title_prefix, ctx, steps_limit):
                    """execute_task_streamを安全に実行してtask_status/outputを返す"""
                    _steps, _status, _output = [], "pending", ""
                    try:
                        write("task_start", {
                            "task_id": todo["id"], "title": f"{title_prefix}{todo['title']}",
                            "task_index": i, "total": total
                        })
                        for ev in execute_task_stream(
                            task_detail=todo["detail"], context=ctx,
                            max_steps=steps_limit, project=project,
                            search_enabled=req.search_enabled, llm_url=task_url,
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

                # Stage 1: 同じアプローチで再試行
                if task_status in ("error", "pending"):
                    err0 = task_output or "不明なエラー"
                    print(f"[JOB {job_id}] task {i+1}/{total} stage1 same-approach retry")
                    ctx1 = (f"{context}\n\n【前回エラー】{err0[:200]}\n\n"
                            f"【指示】前回と同じタスクをもう一度実行してください。"
                            f"エラーの原因を確認して修正してから再実行してください。")
                    task_steps, task_status, task_output = _run_stage("[再試行] ", ctx1, req.max_steps)

                # Stage 2: 別アプローチで再試行
                if task_status in ("error", "pending"):
                    err1 = task_output or err0
                    print(f"[JOB {job_id}] task {i+1}/{total} stage2 different-approach")
                    ctx2 = (f"{context}\n\n【前回エラー×2】\n1回目: {err0[:100]}\n2回目: {err1[:100]}\n\n"
                            f"【指示】これまでと異なるアプローチで実行してください。\n"
                            f"例: write_file→edit_file / run_python→コード分割 / 大きなファイル→get_outline+部分編集")
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
各案は異なるアプローチで具体的に記述してください。

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
                            {"id": 1, "title": "スキップ", "description": "このタスクをスキップして次に進む", "difficulty": "easy", "detail": "このタスクはスキップします。finalでスキップした旨を返してください。"},
                            {"id": 2, "title": "タスク分割", "description": "タスクをより小さく分割して再実行", "difficulty": "medium", "detail": f"次のタスクを小さなステップに分割して実行してください: {todo['detail'][:200]}"},
                            {"id": 3, "title": "手動実装依頼", "description": "ユーザーへの実装手順を提示して終了", "difficulty": "hard", "detail": "実装できなかった理由と手動実装のための手順をoutputに記載してfinalを返してください。"},
                        ]

                    # ──── 自動選択モード（プランナーLLM） ────
                    auto_select = req.auto_select_option if hasattr(req, 'auto_select_option') else True
                    chosen = None

                    if auto_select:
                        write("model_switching", {
                            "from": prev_model_key,
                            "to": "basic",
                            "model_name": MODEL_CATALOG.get("basic", {}).get("name", "Planner"),
                            "eta_sec": MODEL_CATALOG.get("basic", {}).get("load_sec", 30),
                            "message": "対応案を分析中: プランナーLLMをロード中..."
                        })
                        write("task_start", {
                            "task_id": todo["id"],
                            "title": f"[プランナー分析] {todo['title']}",
                            "task_index": i, "total": total
                        })

                        # コードLLMをアンロードしてプランナーをロード
                        planner_switched = _model_manager.ensure_model(
                            "basic",
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
                        write("model_switching", {
                            "from": "basic",
                            "to": prev_model_key,
                            "model_name": MODEL_CATALOG.get(prev_model_key, {}).get("name", prev_model_key),
                            "eta_sec": MODEL_CATALOG.get(prev_model_key, {}).get("load_sec", 30),
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

                    # 選択案で再実行
                    if chosen:
                        chosen_title = chosen.get("title", "選択案")
                        ctx3 = (f"{context}\n\n【選択された対応案】{chosen_title}\n"
                                f"{chosen.get('description','')}\n\n"
                                f"【実行指示】{chosen.get('detail', todo['detail'])}")
                        task_steps, task_status, task_output = _run_stage(f"[{chosen_title}] ", ctx3, req.max_steps)
                    else:
                        task_status = "done"
                        task_output = f"[skipped by timeout] {todo['title']}"

                print(f"[JOB {job_id}] task {i+1}/{total} '{todo['title'][:30]}' -> {task_status}")
                final_status = task_status if task_status == "done" else "error"
                results.append({"task_id": todo["id"], "title": todo["title"],
                                 "status": final_status, "output": task_output, "steps": task_steps})
                if final_status == "done":
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

            # 検証フェーズ（approved_tasksの場合でも実行）
            if done_count == total:
                requirements = plan_result.get("requirements", ["指示された内容が正しく動作すること"]) if plan_result else ["指示された内容が正しく動作すること"]
                verification = plan_result.get("verification", ["動作確認"]) if plan_result else ["動作確認"]
                # verify_startはverify_and_fix内部で発火するため、ここでは不要
                verify_url = req.llm_url.strip() or _model_manager.llm_url
                verify_result = verify_and_fix(
                    user_message=req.message,
                    requirements=requirements,
                    verification_items=verification,
                    project=project, max_fix_rounds=2,
                    llm_url=verify_url, search_enabled=req.search_enabled,
                    on_event=lambda ev: write(ev.get("type","verify"), ev)
                )
            else:
                verify_result = None

            print(f"[JOB {job_id}] completed: {done_count}/{total} tasks done")
            final = {
                "summary": f"{total}タスク中{done_count}件完了",
                "success": done_count == total,
                "tasks": results,
                "verify": verify_result,
            }
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

        job_update_status(project, job_id, "done")

        # ジョブ完了後にbasicモデルに戻す（次のジョブのため）
        if not req.llm_url.strip() and _model_manager.current_key != "basic":
            _model_manager.ensure_model("basic")

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
    search_enabled: bool = True
    llm_url: str = ""

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
- 単純な指示でも要件・方針・検証は省略しない"""

# GPT-OSS-20B用: チャンネル形式でも確実にパースできるシンプル版
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
    プランナーは常にGPT-OSS-20B（basic/gpt_oss）を使用。
    戻り値: {summary, requirements, approach, verification, tasks}
    """
    # プランナーは常にgpt_ossパーサー（LLM_URL_PLANNERは8080固定 = 起動時のGPT-OSS）
    # モデル切り替え中でも起動時のモデル（GPT-OSS）を呼ぶ
    parser = MODEL_CATALOG.get("basic", {}).get("parser", "gpt_oss")
    prompt = PLANNER_PROMPT  # 常に5フィールド完全版
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_message}
    ]
    # thinkingモデル対応: response_format強制なし
    reply, _usage = call_llm_chat(messages, llm_url=LLM_URL_PLANNER)
    # GPT-OSSパーサーでJSONを抽出
    parsed = extract_json(reply, parser=parser)
    print(f"[PLAN] planner=GPT-OSS parser={parser} parsed={'OK' if parsed and 'tasks' in parsed else 'FAIL'}")
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
    base_prompt = SYSTEM_PROMPT + project_note
    project_prompt = base_prompt + (f"\n\n{past_work}" if past_work else "")
    user_content = task_detail
    if context:
        user_content = f"【前のタスクの結果】\n{context}\n\n【今のタスク】\n{task_detail}"

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
        active_tools.pop("web_search", None)
    # project引数を持つツールに現在のprojectを自動バインド
    _project_tools = ("read_file", "write_file", "edit_file", "get_outline",
                       "patch_function", "list_files",
                       "run_python", "run_file", "run_server", "stop_server", "setup_venv",
                       "run_browser", "run_npm", "run_node")
    for _pt in _project_tools:
        if _pt in active_tools:
            _fn = active_tools[_pt]
            import functools as _ft
            active_tools[_pt] = _ft.partial(_fn, project=project)

    steps = []
    consecutive_errors = 0

    for step in range(max_steps):
        # コンテキスト長チェック: 上限の80%を超えたら古いmessagesをtrim
        messages = _trim_messages(messages, _current_n_ctx, reserve_output=4096)
        reply, _step_usage = call_llm_chat(messages, llm_url=llm_url)
        action_obj = extract_json(reply, parser=_model_manager.current_parser)

        if action_obj is None:
            consecutive_errors += 1
            if consecutive_errors >= 3:
                return {"status": "error", "error": "JSON出力失敗", "steps": steps}
            messages.append({"role": "assistant", "content": reply})
            messages.append({
                "role": "user",
                "content": "エラー: JSON形式で出力してください。説明不要。{\"action\": ..., \"input\": {...}} の形式のみ。"
            })
            steps.append({"step": step, "type": "json_retry", "raw": reply})
            continue
        else:
            consecutive_errors = 0

        action = action_obj.get("action", "")
        thought = action_obj.get("thought", "")
        tool_input = action_obj.get("input", {})

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

            messages.append({"role": "assistant", "content": reply})
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
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"ERROR: 不明なツール '{action}' — 使えるのは {list(active_tools.keys())} のみ"})
            steps.append({"step": step, "type": "unknown_tool", "action": action})
            continue

        try:
            result = active_tools[action](**tool_input)
        except TypeError as e:
            result = f"ERROR: 引数が間違っています - {e}"

        step_info = {
            "step": step,
            "type": "tool_call",
            "action": action,
            "thought": thought,
            "input": tool_input,
            "result_preview": str(result)[:200]
        }
        steps.append(step_info)
        if on_step:
            on_step(step_info)

        messages.append({"role": "assistant", "content": reply})
        result_str = str(result)
        if action in ("write_file", "patch_function"):
            result_str = result_str[:400]
        elif action == "read_file":
            current_tokens = _estimate_tokens(messages)
            remaining = _current_n_ctx - current_tokens - 4096
            max_read_chars = max(4000, min(remaining * 4, 32000))
            if len(result_str) > max_read_chars:
                half = max_read_chars // 2
                result_str = (result_str[:half]
                    + f"\n\n[... {len(result_str) - max_read_chars} chars omitted ...]\n\n"
                    + result_str[-half:])
        else:
            max_result_chars = min(8000, max(2000, _current_n_ctx // 8))
            if len(result_str) > max_result_chars:
                result_str = result_str[:max_result_chars] + f"\n[... {len(result_str)-max_result_chars} chars truncated]"
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

    req_text = "\n".join(f"- {r}" for r in requirements) if requirements else "（要件なし）"
    verify_text = "\n".join(f"- {v}" for v in verification_items) if verification_items else "（検証項目なし）"
    all_issues = []
    phase_results = {}

    # プロジェクト内のPythonファイルを収集
    project_path = os.path.join(WORK_DIR, project)
    py_files = []
    for root, _, files in os.walk(project_path):
        for f in files:
            if f.endswith('.py') and not f.startswith('_') and not f.endswith('_test.py'):
                rel = os.path.relpath(os.path.join(root, f), project_path)
                py_files.append(rel)

    emit({"type": "verify_start", "phase": "Phase 1: 単体テスト", "round": 0})

    # ── Phase 1: 単体テスト ──
    unit_results = []
    for py_file in py_files[:6]:  # 最大6ファイル
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
            for fix_round in range(max_fix_rounds):
                # LLMに失敗原因を分析させてpatch
                fix_prompt = f"""以下のファイルがテストで失敗しました。コードを修正してください。

【ファイル】{py_file}
【現在のコード】
{source[:2000]}

【テスト出力（失敗）】
{output[:1000]}

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
            for fix_round in range(max_fix_rounds):
                fix_prompt = f"""結合テストで以下が失敗しました。実装コードを修正してください。

【失敗シナリオ】
{json.dumps(failed_integ, ensure_ascii=False)}

【テスト出力】
{output[:800]}

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

    for req_item in requirements[:8]:
        # 各要件についてコードで確認するスクリプトを生成・実行
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
    unit_pass_rate = (len(unit_results) - len(unit_failed)) / max(len(unit_results), 1)
    integ_pass_rate = (len(integ_results) - len(failed_integ)) / max(len(integ_results), 1)
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
# エンドポイント: /chat（後方互換）
# =========================

@app.post("/chat")
def chat(req: ChatRequest):
    sid = str(uuid.uuid4())[:8]
    chat_url = req.llm_url.strip() or LLM_URL_CHAT
    result = execute_task(req.message, max_steps=req.max_steps, project=req.project,
                          search_enabled=req.search_enabled, llm_url=chat_url)
    save_session(sid, req.project, req.message, "chat", result)
    if result["status"] == "done":
        return {
            "result": result["output"],
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

@app.post("/plan")
def plan_only(req: ChatRequest):
    """要件定義・タスクリストを返す。モデル推奨情報も含む。"""
    try:
        result = plan(req.message, req.project)
        if not result.get("tasks"):
            result["tasks"] = [{"id": 1, "title": "実行", "detail": req.message}]
    except Exception as e:
        result = {
            "summary": req.message[:80],
            "requirements": [],
            "approach": "",
            "verification": [],
            "tasks": [{"id": 1, "title": "実行", "detail": req.message}]
        }
        print(f"[PLAN] error: {e}")

    # コードエージェント（Taskモード）はqwen35をデフォルト推奨
    # heuristic_classifyの結果がbasicでもqwen35を推奨する
    recommended_key = _model_manager.classify(req.message, plan_result=result)
    # ※ basicのまま推奨（UIでAutoを選べば現在のモデルを使う）
    recommended_spec = MODEL_CATALOG.get(recommended_key, {})
    current_key = _model_manager.current_key

    return {
        **result,
        "message": req.message,
        "project": req.project,
        "recommended_model": recommended_key,
        "recommended_model_name": recommended_spec.get("name", ""),
        "recommended_model_desc": recommended_spec.get("description", ""),
        "current_model": current_key,
        "model_switch_needed": recommended_key != current_key,
        "switch_eta_sec": recommended_spec.get("load_sec", 0) if recommended_key != current_key else 0,
        "catalog": {k: {"name": v["name"], "vram_gb": v["vram_gb"],
                        "available": bool(v["path"])}
                    for k, v in MODEL_CATALOG.items()
                    if k not in ("basic", "router")},  # basicとrouterはUIに不要
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
        # ── planフェーズ ──
        is_task = req.max_steps > 5  # max_steps=1 → chat扱い、デフォルト20 → task扱い
        # modeはクライアントから渡してもらう（max_stepsで判断 or フィールド追加）
        # ここではmessageの複雑さでplannerが1件か複数件かを決める
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
                action_obj = extract_json(reply, parser=_model_manager.current_parser)

                if action_obj is None:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        yield event("tool_call", {
                            "task_id": todo["id"], "step": step,
                            "step_num": step + 1, "max_steps": req.max_steps,
                            "action": "error", "thought": "JSON出力失敗",
                            "progress": step_progress, "tps": 0,
                        })
                        break
                    messages.append({"role": "assistant", "content": reply})
                    messages.append({"role": "user", "content": "JSON形式で出力してください。"})
                    continue
                else:
                    consecutive_errors = 0

                action = action_obj.get("action", "")
                thought = action_obj.get("thought", "")
                tool_input = action_obj.get("input", {})

                if action == "final":
                    task_status = "done"
                    task_output = action_obj.get("output", "")
                    steps.append({"step": step, "type": "final", "thought": thought})
                    yield event("tool_call", {
                        "task_id": todo["id"],
                        "step": step,
                        "step_num": step + 1,
                        "max_steps": req.max_steps,
                        "action": "final",
                        "thought": thought,
                        "progress": int(((task_idx + 1) / total_tasks) * 85),
                        "prompt_tokens": _step_usage.get("prompt_tokens", 0),
                        "completion_tokens": _step_usage.get("completion_tokens", 0),
                        "tps": _step_usage.get("tps", 0),
                    })
                    break

                if action not in TOOLS:
                    messages.append({"role": "assistant", "content": reply})
                    messages.append({"role": "user", "content": f"ERROR: 不明なツール '{action}'"})
                    continue

                try:
                    result = TOOLS[action](**tool_input)
                except TypeError as e:
                    result = f"ERROR: 引数エラー - {e}"

                step_data = {
                    "step": step, "type": "tool_call",
                    "action": action, "thought": thought,
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
                    "thought": thought,
                    "result_preview": str(result)[:200],
                    "progress": step_progress,
                    "prompt_tokens": _step_usage.get("prompt_tokens", 0),
                    "completion_tokens": _step_usage.get("completion_tokens", 0),
                    "tps": _step_usage.get("tps", 0),
                })

                messages.append({"role": "assistant", "content": reply})
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
        if os.path.isdir(path) and not name.startswith("_"):
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
    name = re.sub(r"[^a-zA-Z0-9_\-]", "_", req.name)
    path = os.path.join(WORK_DIR, name)
    os.makedirs(path, exist_ok=True)
    return {"created": name}

@app.delete("/projects/{name}")
def delete_project(name: str):
    """プロジェクトを削除する"""
    import shutil
    path = os.path.join(WORK_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Project not found")
    shutil.rmtree(path)
    return {"deleted": name}

@app.get("/projects/{name}/files")
def project_files(name: str):
    """プロジェクト内ファイル一覧"""
    path = os.path.join(WORK_DIR, name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Project not found")
    files = []
    for root, _, fs in os.walk(path):
        for f in fs:
            rel = os.path.relpath(os.path.join(root, f), path)
            files.append(rel)
    return {"project": name, "files": sorted(files)}


# =========================
# SSE進捗ストリーム用ジェネレータ
# =========================

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

    messages = [
        {"role": "system", "content": project_prompt},
        {"role": "user", "content": user_content}
    ]

    # スキルをTOOLSに動的追加（ホットリロード対応）
    active_tools = dict(TOOLS)
    if not search_enabled:
        active_tools.pop("web_search", None)
    skill_fns = _load_skill_functions()
    active_tools.update(skill_fns)
    # ファイル操作ツールにprojectを自動バインド
    _pt_list = ("read_file", "write_file", "edit_file", "get_outline",
                "patch_function", "list_files",
                "run_python", "run_file", "run_server", "stop_server", "setup_venv")
    import functools as _ft2
    for _pt in _pt_list:
        if _pt in active_tools:
            active_tools[_pt] = _ft2.partial(active_tools[_pt], project=project)
    steps = []
    consecutive_errors = 0

    for step in range(max_steps):
        messages = _trim_messages(messages, _current_n_ctx, reserve_output=4096)
        try:
            reply, usage = call_llm_chat(messages, llm_url=llm_url)
        except HTTPException as _ctx_ex:
            if _ctx_ex.status_code == 413:
                print(f"[execute_task_stream] context exceeded, force trimming...")
                messages = _trim_messages(messages, _current_n_ctx // 2, reserve_output=2048)
                try:
                    reply, usage = call_llm_chat(messages, llm_url=llm_url)
                except Exception as _e2:
                    yield {"type": "task_error", "error": f"Context exceeded after trim: {_e2}", "steps": steps}
                    return
            else:
                yield {"type": "task_error", "error": str(_ctx_ex.detail), "steps": steps}
                return
        action_obj = extract_json(reply)

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
                fb = 'JSON形式のみで出力してください。最初の文字は{であること。例: {"thought":"考え","action":"list_files","input":{"subdir":""}}'
            messages.append({"role": "assistant", "content": reply[:500]})
            messages.append({"role": "user", "content": fb})
            continue
        else:
            consecutive_errors = 0

        action = action_obj.get("action", "")
        thought = action_obj.get("thought", "")
        tool_input = action_obj.get("input", {})

        if action == "final":
            steps.append({"step": step, "type": "final", "thought": thought})
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

        if action not in active_tools:
            # 未知のツール → スキル候補として記録
            yield {"type": "skill_hint", "missing_tool": action, "thought": thought}
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"ERROR: unknown tool '{action}' — 使えるのは {list(active_tools.keys())} のみ。これらのツールで代替する。"})
            continue

        # clarify: ユーザー選択待ち
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
            # ここではanswerをmessagesに注入する責務がないためスキップ
            # → run_job_backgroundがclarify eventを受け取り、waitして回答をDI
            continue

        yield {
            "type": "tool_call",
            "action": action,
            "thought": thought,
            "step_num": step + 1,
            "max_steps": max_steps,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "tps": usage.get("tps", 0),
        }

        try:
            result = active_tools[action](**tool_input)
        except TypeError as e:
            result = f"ERROR: 引数エラー - {e}"

        step_record = {
            "step": step, "type": "tool_call",
            "action": action, "thought": thought,
            "input": tool_input, "result_preview": str(result)[:200]
        }
        steps.append(step_record)
        yield {"type": "tool_result", "action": action, "result_preview": str(result)[:200]}

        # replyをmessagesに追加する際、write_fileのcontentなど巨大フィールドを省略
        compact = _compact_reply(action_obj, max_chars=300)
        messages.append({"role": "assistant", "content": compact or reply[:500]})
        result_str = str(result)
        # write_file/patch_functionは成功メッセージ＋プレビューのみ
        if action in ("write_file", "patch_function"):
            result_str = result_str[:400]
        elif action == "read_file":
            # read_fileはファイル全体を渡す（コンテキスト余裕に応じて）
            # 現在使用トークン数を推定して残り容量を計算
            current_tokens = _estimate_tokens(messages)
            remaining = _current_n_ctx - current_tokens - 4096  # 出力分を確保
            max_read_chars = max(4000, min(remaining * 4, 32000))  # 4文字≒1トークン
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
        messages.append({"role": "user", "content": f"実行結果:\n{result_str}"})

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

            for event in execute_task_stream(
                task_detail=todo["detail"],
                context=context,
                max_steps=req.max_steps,
                project=req.project,
                search_enabled=req.search_enabled,
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
                search_enabled=req.search_enabled,
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
    try:
        res = requests.get("http://localhost:8080/props", timeout=5)
        if res.status_code == 200:
            data = res.json()
            # /propsのn_ctxが信頼できる場合はそれを使用
            # ただし llama-server は /props で default_generation_settings.n_ctx を返す場合がある
            n_ctx = (data.get("default_generation_settings", {}).get("n_ctx")
                     or data.get("n_ctx")
                     or _current_n_ctx)
            return {
                "n_ctx": n_ctx,
                "n_ctx_train": data.get("n_ctx_train", n_ctx),
                "raw": {k: v for k, v in data.items() if k in ("n_ctx","n_ctx_train","model_path","total_slots")}
            }
    except Exception:
        pass
    # フォールバック: サーバー側の_current_n_ctxを返す（スライダーがずれない）
    return {"n_ctx": _current_n_ctx, "note": "using server default"}

# =========================
# コンテキスト長設定
# =========================

_current_n_ctx: int = 32768  # デフォルト
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
    _current_n_ctx = max(512, n)
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
    key = req.get("model", "basic")
    if key not in MODEL_CATALOG:
        raise HTTPException(status_code=400, detail=f"Unknown model: {key}")
    import threading as _t
    def do_switch():
        _model_manager.ensure_model(key)
    _t.Thread(target=do_switch, daemon=True).start()
    return {"switching_to": key, "eta_sec": MODEL_CATALOG[key]["load_sec"]}

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
# スコープ: workspace > global(C:\AI\skills) > bundled(C:\AI\bundled_skills)
# 形式: skills/スキル名/SKILL.md (YAMLフロントマター + Markdownコード)

# スキルフォルダ: C:\AI\skills\ に一本化
# ユーザー追加・CodeAgent提案スキルを共有資産として格納
SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
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
        os_list = meta.get("os", ["win32"])
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
        if os_list and "win32" not in os_list and "windows" not in [x.lower() for x in os_list]:
            skill["_incompatible_os"] = True
        return skill
    except Exception as e:
        print(f"[SKILLS] parse error {path}: {e}")
        return None

def _load_all_skills(force: bool = False) -> dict:
    """
    C:\AI\skills\ からスキルをロード（共有資産）。
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
    skills = _active_skills()
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
    lines.append("スキルのコードはC:\\AI\\skills\\ または /skills APIで確認可能。")
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

def _skill_save_path(name: str, scope: str = "shared") -> str:
    """スキルの保存先: C:\AI\skills\スキル名\SKILL.md"""
    safe = "".join(c for c in name if c.isalnum() or c in "_-")
    d = os.path.join(SKILLS_DIR, safe)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "SKILL.md")

def _write_skill_md(skill: dict, path: str):
    os_list = skill.get("os", ["win32"])
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
    return {"skills": skills, "count": len(skills)}

@app.post("/skills")
def create_skill_api(req: dict):
    name = req.get("name","").strip()
    if not name: raise HTTPException(400, "name required")
    scope = "shared"  # 全スキルをC:\AI\skills\に統一
    path = _skill_save_path(name, scope)
    _write_skill_md(req, path)
    _load_all_skills(force=True)
    return {"ok": True, "path": path}

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

@app.get("/health")
def health():
    try:
        res = requests.get("http://localhost:8080/health", timeout=3)
        llm_ok = res.status_code == 200
    except Exception:
        llm_ok = False

    sandbox_check = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", SANDBOX_CONTAINER],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    sandbox_ok = sandbox_check.returncode == 0 and sandbox_check.stdout.strip() == "true"

    return {
        "llm": "ok" if llm_ok else "unreachable",
        "sandbox": "running" if sandbox_ok else "not running (fallback: docker run)",
        "workspace_files": list_files()
    }

# =========================
# 静的ファイル配信
# / と /ui/ どちらでもUIにアクセスできる
# =========================

@app.get("/")
def root():
    """ルートアクセスをUIのindex.htmlに直接返す"""
    index = os.path.join(UI_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index, media_type="text/html")
    return RedirectResponse("/ui/")

@app.get("/ui")
def ui_redirect():
    return RedirectResponse("/ui/")

app.mount("/workspace", StaticFiles(directory=WORK_DIR, html=True), name="workspace")
app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui")
