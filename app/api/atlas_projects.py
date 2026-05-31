from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.atlas_root import resolve_atlas_ca_data_root
from agent.atlas_conversation_store import AtlasConversationStore

router = APIRouter(prefix="/api/atlas/projects", tags=["atlas-projects"])

_NAME_MAX_LEN = 40
# Keep unicode word characters (so Japanese instructions yield identifiable
# names) while collapsing everything else — including path separators and
# ``..`` — into a hyphen. Combined with the resolve()-based containment guards
# below, this is traversal-safe.
_SLUG_RE = re.compile(r"[^\w-]+", re.UNICODE)


# ── name handling ──
def _normalize_name(raw: str) -> str:
    """Normalize a project name into a filesystem/workspace-safe identifier.

    Lowercased, non word/``-`` characters collapsed to ``-``, trimmed,
    length-capped. Unicode letters/digits are preserved. Returns "" when
    nothing usable remains (caller decides the fallback).
    """
    text = str(raw or "").strip().lower()
    text = _SLUG_RE.sub("-", text)
    text = re.sub(r"_{2,}", "_", text)
    text = re.sub(r"-{2,}", "-", text).strip("-_")
    if len(text) > _NAME_MAX_LEN:
        text = text[:_NAME_MAX_LEN].strip("-_")
    return text


def _provisional_name() -> str:
    # base36 of the current millisecond clock keeps it short and sortable.
    stamp = int(time.time() * 1000)
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while stamp:
        stamp, rem = divmod(stamp, 36)
        out = digits[rem] + out
    return f"untitled-{out or '0'}"


def _is_provisional(name: str) -> bool:
    return name.startswith("untitled-")


# ── path helpers (with containment guards) ──
def _projects_dir(root: Path) -> Path:
    return root / "atlas" / "projects"


def _project_dir(root: Path, name: str) -> Path:
    base = _projects_dir(root).resolve()
    target = (base / name).resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": "invalid_project_name"})
    return target


def _work_dir(root: Path, name: str) -> Path:
    # The working directory Atlas dev/repair operates on; sent as project_path.
    return _project_dir(root, name) / "work"


def _workspace_dir(root: Path, name: str) -> Path:
    base = (root / "atlas" / "workspaces").resolve()
    target = (base / name).resolve()
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": "invalid_project_name"})
    return target


def _require_name(raw: str) -> str:
    name = _normalize_name(raw)
    if not name:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "reason": "invalid_project_name"})
    return name


def _file_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    for _base, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        count += len(files)
    return count


def _project_payload(root: Path, name: str) -> dict:
    store = AtlasConversationStore(root, name)
    meta = store.read_meta()
    work = _work_dir(root, name)
    display_name = str(meta.get("display_name") or name)
    return {
        "name": name,
        "display_name": display_name,
        "project_path": str(work),
        "workspace_id": name,
        "file_count": _file_count(work),
        "provisional": bool(meta.get("provisional", _is_provisional(name))),
        "active_pool_id": meta.get("active_pool_id", ""),
        "updated_at": meta.get("updated_at", ""),
    }


# ── request models ──
class CreateProjectRequest(BaseModel):
    name: str = ""
    overwrite: bool = False


class RenameProjectRequest(BaseModel):
    new_name: str


class ConversationMessageRequest(BaseModel):
    role: str = "system"
    text: str = ""
    meta: dict | None = None


# ── endpoints ──
@router.get("")
@router.get("/")
def list_projects(request: Request):
    root = resolve_atlas_ca_data_root(request)
    base = _projects_dir(root)
    projects = []
    if base.exists():
        for entry in sorted(base.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                projects.append(_project_payload(root, entry.name))
    return {"projects": projects}


@router.post("")
@router.post("/")
def create_project(payload: CreateProjectRequest, request: Request):
    root = resolve_atlas_ca_data_root(request)
    name = _normalize_name(payload.name) if payload.name else _provisional_name()
    if not name:
        name = _provisional_name()
    work = _work_dir(root, name)
    existed = work.exists()
    if existed and payload.overwrite:
        shutil.rmtree(_project_dir(root, name), ignore_errors=True)
        existed = False
    work.mkdir(parents=True, exist_ok=True)
    _workspace_dir(root, name).mkdir(parents=True, exist_ok=True)
    store = AtlasConversationStore(root, name)
    store.write_meta({"provisional": _is_provisional(name), "display_name": name})
    return {"created": name, "existed": existed, **_project_payload(root, name)}


@router.post("/{name}/rename")
def rename_project(name: str, payload: RenameProjectRequest, request: Request):
    """Rename only the user-facing project title.

    The project ``name`` is the stable storage id for both
    ``atlas/projects/<name>/work`` and ``atlas/workspaces/<name>``. Moving those
    directories after planning has started can split artifacts: older in-flight
    calls keep the previous project_path/workspace_id while new UI calls switch
    to the renamed id. Keep storage immutable and store the friendly title in
    conversation meta instead.
    """
    root = resolve_atlas_ca_data_root(request)
    storage_id = _require_name(name)
    display_name = _require_name(payload.new_name)
    proj_dir = _project_dir(root, storage_id)
    if not proj_dir.exists():
        raise HTTPException(status_code=404, detail={"error": "not_found", "reason": "project_not_found"})
    store = AtlasConversationStore(root, storage_id)
    store.write_meta({"provisional": False, "display_name": display_name})
    return _project_payload(root, storage_id)


@router.delete("/{name}")
def delete_project(name: str, request: Request):
    root = resolve_atlas_ca_data_root(request)
    safe = _require_name(name)
    proj = _project_dir(root, safe)
    if not proj.exists():
        raise HTTPException(status_code=404, detail={"error": "not_found", "reason": "project_not_found"})
    shutil.rmtree(proj, ignore_errors=True)
    shutil.rmtree(_workspace_dir(root, safe), ignore_errors=True)
    return {"deleted": safe}


@router.get("/{name}/conversation")
def get_conversation(name: str, request: Request, limit: int | None = None):
    root = resolve_atlas_ca_data_root(request)
    safe = _require_name(name)
    store = AtlasConversationStore(root, safe)
    return {"project": safe, "messages": store.list(limit=limit), "meta": store.read_meta()}


@router.post("/{name}/conversation")
def append_conversation(name: str, payload: ConversationMessageRequest, request: Request):
    root = resolve_atlas_ca_data_root(request)
    safe = _require_name(name)
    store = AtlasConversationStore(root, safe)
    record = store.append(payload.role, payload.text, meta=payload.meta)
    return {"project": safe, "message": record}


@router.get("/{name}/download")
def download_project(name: str, request: Request, background_tasks: BackgroundTasks):
    """Zip the project working dir AND its Atlas workspace artifacts (logs,
    plan pools, pipeline runs, conversation) so the download is a full archive."""
    root = resolve_atlas_ca_data_root(request)
    safe = _require_name(name)
    work = _work_dir(root, safe)
    workspace = _workspace_dir(root, safe)
    if not _project_dir(root, safe).exists():
        raise HTTPException(status_code=404, detail={"error": "not_found", "reason": "project_not_found"})

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp.close()
    zip_path = tmp.name
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for src, prefix in ((work, "work"), (workspace, "atlas_workspace")):
                if not src.exists():
                    continue
                for base, dirs, files in os.walk(src):
                    dirs[:] = [d for d in dirs if d != ".git"]
                    for fname in files:
                        abs_path = os.path.join(base, fname)
                        rel_path = os.path.relpath(abs_path, src).replace("\\", "/")
                        zf.write(abs_path, arcname=f"{safe}/{prefix}/{rel_path}")
    except Exception as exc:
        try:
            os.remove(zip_path)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"zip creation failed: {exc}")

    background_tasks.add_task(lambda p=zip_path: os.path.exists(p) and os.remove(p))
    return FileResponse(path=zip_path, media_type="application/zip", filename=f"{safe}.zip")
