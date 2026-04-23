from __future__ import annotations

import os
import re
import shutil
import stat
import uuid
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

_STYLE_BERT_VITS2_BASE_DIR = "/workspace/ca_data/tts/style_bert_vits2"
_STYLE_BERT_VITS2_MODELS_DIR = os.path.join(_STYLE_BERT_VITS2_BASE_DIR, "models")
_ALLOWED_EXTENSION = ".zip"
_MAX_EXTRACT_FILES = 4096
_MAX_EXTRACT_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
_REQUIRED_MODEL_FILES = {"config.json", "style_vectors.npy"}
_REQUIRED_WEIGHT_EXTENSIONS = {".safetensors", ".pth", ".pt", ".onnx"}


def _sanitize_model_id(model_id: str) -> str:
    model_id = (model_id or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id required")
    if model_id in {".", ".."}:
        raise HTTPException(status_code=400, detail="invalid model_id")
    if "/" in model_id or "\\" in model_id:
        raise HTTPException(status_code=400, detail="invalid model_id")
    if not re.match(r"^[A-Za-z0-9._-]+$", model_id):
        raise HTTPException(status_code=400, detail="invalid model_id")
    return model_id


def _is_zipinfo_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _validate_archive_entries(zf: zipfile.ZipFile) -> None:
    files = [info for info in zf.infolist() if not info.is_dir()]
    if not files:
        raise HTTPException(status_code=400, detail="empty zip archive")
    if len(files) > _MAX_EXTRACT_FILES:
        raise HTTPException(status_code=413, detail=f"too many files in archive: {len(files)} > {_MAX_EXTRACT_FILES}")

    total_size = 0
    for info in zf.infolist():
        name = info.filename
        if not name:
            continue
        normalized = os.path.normpath(name)
        if normalized.startswith("../") or normalized == ".." or os.path.isabs(name) or os.path.isabs(normalized):
            raise HTTPException(status_code=400, detail=f"unsafe zip entry path: {name}")
        if "\\" in name:
            normalized_backslash = os.path.normpath(name.replace("\\", "/"))
            if normalized_backslash.startswith("../") or normalized_backslash == "..":
                raise HTTPException(status_code=400, detail=f"unsafe zip entry path: {name}")
        if _is_zipinfo_symlink(info):
            raise HTTPException(status_code=400, detail=f"symlink entry is not allowed: {name}")
        if not info.is_dir():
            total_size += max(0, int(info.file_size or 0))
            if total_size > _MAX_EXTRACT_TOTAL_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"archive too large after extraction: {total_size} > {_MAX_EXTRACT_TOTAL_BYTES}",
                )


def _resolve_extracted_root(extract_root: str) -> str:
    entries = [name for name in os.listdir(extract_root) if name not in {"__MACOSX", ".DS_Store"}]
    if not entries:
        raise HTTPException(status_code=400, detail="empty extracted directory")

    if len(entries) == 1:
        one = os.path.join(extract_root, entries[0])
        if os.path.isdir(one):
            return one
    return extract_root


def _validate_model_dir(model_dir: str) -> None:
    file_paths: list[str] = []
    for root, _dirs, files in os.walk(model_dir):
        for filename in files:
            rel = os.path.relpath(os.path.join(root, filename), model_dir)
            file_paths.append(rel)

    if not file_paths:
        raise HTTPException(status_code=400, detail="model directory is empty")

    file_names = {Path(path).name for path in file_paths}
    for required in _REQUIRED_MODEL_FILES:
        if required not in file_names:
            raise HTTPException(status_code=400, detail=f"required asset missing: {required}")

    has_weight = any(Path(path).suffix.lower() in _REQUIRED_WEIGHT_EXTENSIONS for path in file_paths)
    if not has_weight:
        raise HTTPException(
            status_code=400,
            detail=f"required model weight missing: extensions={sorted(_REQUIRED_WEIGHT_EXTENSIONS)}",
        )


async def import_model_zip(upload_file: UploadFile, model_id: str | None = None) -> dict:
    original_name = os.path.basename(upload_file.filename or "")
    ext = os.path.splitext(original_name)[-1].lower()
    if ext != _ALLOWED_EXTENSION:
        raise HTTPException(status_code=400, detail=f"only {_ALLOWED_EXTENSION} is allowed")

    os.makedirs(_STYLE_BERT_VITS2_MODELS_DIR, exist_ok=True)
    temp_dir = os.path.join("/tmp", f"style_bert_vits2_upload_{uuid.uuid4().hex}")
    os.makedirs(temp_dir, exist_ok=False)

    try:
        with zipfile.ZipFile(upload_file.file) as zf:
            _validate_archive_entries(zf)
            zf.extractall(temp_dir)

        model_source_dir = _resolve_extracted_root(temp_dir)
        resolved_model_id = _sanitize_model_id(model_id or os.path.splitext(original_name)[0])
        dest_dir = os.path.join(_STYLE_BERT_VITS2_MODELS_DIR, resolved_model_id)
        if os.path.exists(dest_dir):
            raise HTTPException(status_code=409, detail=f"model already exists: {resolved_model_id}")

        _validate_model_dir(model_source_dir)
        shutil.move(model_source_dir, dest_dir)
        return {"model_id": resolved_model_id, "path": dest_dir}
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="invalid zip file") from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
