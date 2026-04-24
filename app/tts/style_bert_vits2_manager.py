from __future__ import annotations

import os
import re
import shutil
import stat
import traceback
import uuid
import zipfile
import logging
from pathlib import Path

from fastapi import UploadFile
from .style_bert_vits2_paths import resolve_style_bert_vits2_base_dir, resolve_style_bert_vits2_models_dir

_STYLE_BERT_VITS2_BASE_DIR = resolve_style_bert_vits2_base_dir()
_STYLE_BERT_VITS2_MODELS_DIR = resolve_style_bert_vits2_models_dir()
_ALLOWED_EXTENSION = ".zip"
_MAX_EXTRACT_FILES = 4096
_MAX_EXTRACT_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
_REQUIRED_MODEL_FILES = {"config.json", "style_vectors.npy"}
_REQUIRED_WEIGHT_EXTENSIONS = {".safetensors", ".pth", ".pt", ".onnx"}
_logger = logging.getLogger("style_bert_vits2")


class StyleBertVITS2Error(Exception):
    """Style-Bert-VITS2 管理層向けの内部例外。

    user_message: API/フロントで表示してよい文言
    log_detail:   サーバーログ向けの詳細情報
    status_code:  HTTP変換時の推奨ステータス
    """

    def __init__(self, *, user_message: str, log_detail: str, status_code: int = 400):
        super().__init__(user_message)
        self.user_message = user_message
        self.log_detail = log_detail
        self.status_code = status_code


def _sanitize_model_id(model_id: str) -> str:
    model_id = (model_id or "").strip()
    if not model_id:
        raise StyleBertVITS2Error(
            status_code=400,
            user_message="モデルIDが必要です。",
            log_detail="model_id required",
        )
    if model_id in {".", ".."}:
        raise StyleBertVITS2Error(status_code=400, user_message="モデルIDが不正です。", log_detail="invalid model_id")
    if "/" in model_id or "\\" in model_id:
        raise StyleBertVITS2Error(status_code=400, user_message="モデルIDが不正です。", log_detail="invalid model_id")
    if not re.match(r"^[A-Za-z0-9._-]+$", model_id):
        raise StyleBertVITS2Error(status_code=400, user_message="モデルIDが不正です。", log_detail="invalid model_id")
    return model_id


def _is_zipinfo_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _validate_archive_entries(zf: zipfile.ZipFile) -> None:
    files = [info for info in zf.infolist() if not info.is_dir()]
    if not files:
        raise StyleBertVITS2Error(
            status_code=400,
            user_message="無効ZIPです（ファイルが含まれていません）。",
            log_detail="empty zip archive",
        )
    if len(files) > _MAX_EXTRACT_FILES:
        raise StyleBertVITS2Error(
            status_code=413,
            user_message="無効ZIPです（ファイル数が多すぎます）。",
            log_detail=f"too many files in archive: {len(files)} > {_MAX_EXTRACT_FILES}",
        )

    total_size = 0
    for info in zf.infolist():
        name = info.filename
        if not name:
            continue
        normalized = os.path.normpath(name)
        if normalized.startswith("../") or normalized == ".." or os.path.isabs(name) or os.path.isabs(normalized):
            raise StyleBertVITS2Error(
                status_code=400,
                user_message="無効ZIPです（不正なパスが含まれています）。",
                log_detail=f"unsafe zip entry path: {name}",
            )
        if "\\" in name:
            normalized_backslash = os.path.normpath(name.replace("\\", "/"))
            if normalized_backslash.startswith("../") or normalized_backslash == "..":
                raise StyleBertVITS2Error(
                    status_code=400,
                    user_message="無効ZIPです（不正なパスが含まれています）。",
                    log_detail=f"unsafe zip entry path(backslash): {name}",
                )
        if _is_zipinfo_symlink(info):
            raise StyleBertVITS2Error(
                status_code=400,
                user_message="無効ZIPです（シンボリックリンクは使用できません）。",
                log_detail=f"symlink entry is not allowed: {name}",
            )
        if not info.is_dir():
            total_size += max(0, int(info.file_size or 0))
            if total_size > _MAX_EXTRACT_TOTAL_BYTES:
                raise StyleBertVITS2Error(
                    status_code=413,
                    user_message="無効ZIPです（展開サイズが上限を超えています）。",
                    log_detail=f"archive too large after extraction: {total_size} > {_MAX_EXTRACT_TOTAL_BYTES}",
                )


def _resolve_extracted_root(extract_root: str) -> str:
    entries = [name for name in os.listdir(extract_root) if name not in {"__MACOSX", ".DS_Store"}]
    if not entries:
        raise StyleBertVITS2Error(
            status_code=400,
            user_message="無効ZIPです（展開結果が空です）。",
            log_detail="empty extracted directory",
        )

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
        raise StyleBertVITS2Error(
            status_code=400,
            user_message="空モデルフォルダです。必要なファイルを含めてください。",
            log_detail=f"model directory is empty: {model_dir}",
        )

    file_names = {Path(path).name for path in file_paths}
    for required in _REQUIRED_MODEL_FILES:
        if required not in file_names:
            raise StyleBertVITS2Error(
                status_code=400,
                user_message=f"モデルファイルが不足しています（{required}）。",
                log_detail=f"required asset missing: {required}",
            )

    has_weight = any(Path(path).suffix.lower() in _REQUIRED_WEIGHT_EXTENSIONS for path in file_paths)
    if not has_weight:
        raise StyleBertVITS2Error(
            status_code=400,
            user_message="モデル重みファイルが見つかりません。",
            log_detail=f"required model weight missing: extensions={sorted(_REQUIRED_WEIGHT_EXTENSIONS)}",
        )


def ensure_model_exists(model_id: str, models_dir: str = _STYLE_BERT_VITS2_MODELS_DIR) -> str:
    resolved_model_id = _sanitize_model_id(model_id)
    model_dir = os.path.join(models_dir, resolved_model_id)
    if not os.path.isdir(model_dir):
        raise StyleBertVITS2Error(
            status_code=404,
            user_message=f"モデル未存在です: {resolved_model_id}",
            log_detail=f"model not found: {model_dir}",
        )
    return model_dir


async def import_model_zip(upload_file: UploadFile, model_id: str | None = None) -> dict:
    original_name = os.path.basename(upload_file.filename or "")
    ext = os.path.splitext(original_name)[-1].lower()
    if ext != _ALLOWED_EXTENSION:
        raise StyleBertVITS2Error(
            status_code=400,
            user_message=f"無効ZIPです（{_ALLOWED_EXTENSION} のみ対応）。",
            log_detail=f"only {_ALLOWED_EXTENSION} is allowed",
        )

    _logger.info("[Style-Bert-VITS2][models/upload] using models_dir=%s", _STYLE_BERT_VITS2_MODELS_DIR)
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
            raise StyleBertVITS2Error(
                status_code=409,
                user_message=f"同名モデルが既に存在します: {resolved_model_id}",
                log_detail=f"model already exists: {resolved_model_id}",
            )

        _validate_model_dir(model_source_dir)
        shutil.move(model_source_dir, dest_dir)
        _logger.info(
            "[Style-Bert-VITS2][models/upload] imported model_id=%s path=%s models_dir=%s",
            resolved_model_id,
            dest_dir,
            _STYLE_BERT_VITS2_MODELS_DIR,
        )
        return {"model_id": resolved_model_id, "path": dest_dir}
    except zipfile.BadZipFile as exc:
        raise StyleBertVITS2Error(
            status_code=400,
            user_message="無効ZIPです。ZIPファイルを確認してください。",
            log_detail=f"bad zip file: {exc}\n{traceback.format_exc()}",
        ) from exc
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
