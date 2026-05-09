from __future__ import annotations

import base64
import io
import json
import os
import tempfile
import time
import traceback
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping


AUDIO_RUNTIME_ENDPOINT_OWNERSHIP: dict[str, dict[str, str]] = {
    "GET /voice/status": {
        "owner": "app/api/audio.py",
        "domain": "ASR runtime status",
        "risk": "low-risk read/status",
        "next_step": "Moved to app/api/audio.py in PR4.56; production behavior remains provider-backed from main.py",
    },
    "GET /asr/config": {
        "owner": "app/api/audio.py",
        "domain": "ASR runtime config",
        "risk": "low-risk read/status",
        "next_step": "Moved to app/api/audio.py in PR4.56; production behavior remains provider-backed from main.py",
    },
    "POST /voice/load": {
        "owner": "main.py",
        "domain": "ASR runtime load",
        "risk": "medium-risk write/runtime-load",
        "next_step": "Keep in main.py until ASR runtime helpers are extracted",
    },
    "POST /voice/transcribe": {
        "owner": "main.py",
        "domain": "ASR execution",
        "risk": "high-risk execution",
        "next_step": "Do not move before PR4.55 service extraction validates helpers",
    },
    "WebSocket /echo/stream": {
        "owner": "main.py",
        "domain": "Echo streaming ASR/TTS session execution",
        "risk": "high-risk execution/websocket",
        "next_step": "PR4.58+ last; keep session/write behavior frozen",
    },
    "DELETE /echo/sessions/{filename:path}": {
        "owner": "main.py",
        "domain": "Echo session filesystem write/delete",
        "risk": "medium-risk write/filesystem",
        "next_step": "Move only after provider write seam is explicit",
    },
    "POST /api/tts/style-bert-vits2/prepare": {
        "owner": "main.py",
        "domain": "SBV2 runtime prepare/load",
        "risk": "medium-risk write/runtime-load",
        "next_step": "Keep in main.py until SBV2 runtime seam is explicit",
    },
    "GET /api/tts/style-bert-vits2/models": {
        "owner": "app/api/audio.py",
        "domain": "SBV2 model inventory",
        "risk": "low-risk read/status",
        "next_step": "Moved to app/api/audio.py in PR4.56 with side-effect-free create_app fallback",
    },
    "POST /api/tts/style-bert-vits2/preview-normalization": {
        "owner": "app/api/audio.py",
        "domain": "SBV2 normalization / katakana fallback / dictionary cache",
        "risk": "low/medium-risk read-preview with LLM fallback caution",
        "next_step": "Moved to app/api/audio.py in PR4.56; LLM fallback remains provider-only in production",
    },
    "POST /tts/synthesize": {
        "owner": "main.py",
        "domain": "TTS/SBV2 execution",
        "risk": "high-risk execution",
        "next_step": "PR4.57 extracted the non-streaming service body; keep route owner in main.py",
    },
    "POST /tts/synthesize-batch": {
        "owner": "main.py",
        "domain": "TTS/SBV2 batch execution",
        "risk": "high-risk execution",
        "next_step": "PR4.58 extracted the batch service body; keep route owner in main.py",
    },
}


class AudioRuntimeHttpError(Exception):
    """Route-neutral HTTP error raised by audio service-body helpers."""

    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = int(status_code)
        self.detail = detail


@dataclass(frozen=True)
class TtsSynthesizeServiceDependencies:
    """Injected production seams for POST /tts/synthesize without importing main.py."""

    engine_registry: Any
    logger: Any
    write_tts_debug_entry: Callable[[Mapping[str, Any]], Any]
    ensure_model_exists: Callable[[str, str], Any]
    read_model_version: Callable[[str], str]
    apply_tts_language_routing: Callable[..., Any]
    style_bert_vits2_models_dir: str
    request_id_factory: Callable[[], str]
    utcnow_factory: Callable[[], datetime] = datetime.utcnow


@dataclass(frozen=True)
class TtsSynthesizeBatchServiceDependencies:
    """Injected production seams for POST /tts/synthesize-batch without importing main.py."""

    engine_registry: Any
    logger: Any
    ensure_model_exists: Callable[[str, str], Any]
    style_bert_vits2_models_dir: str
    request_id_factory: Callable[[], str]
    job_create: Callable[..., str]
    job_update_status: Callable[[str, str, str], Any]
    job_append_step: Callable[[str, str, int, str, Mapping[str, Any]], Any]
    sample_rate_from_wav_bytes: Callable[[bytes], int]
    merge_wav_bytes: Callable[[list[bytes]], bytes]
    perf_counter: Callable[[], float] = time.perf_counter


@dataclass(frozen=True)
class AudioRuntimeStatus:
    """Route-neutral status shape for future Echo/ASR/TTS service seams."""

    asr_loaded: bool = False
    tts_loaded: bool = False
    sbv2_available: bool = False
    echo_active_sessions: int = 0
    selected_asr_device: str = ""
    selected_tts_device: str = ""
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AudioRuntimeDiagnostics:
    """Debug-only metadata that must not trigger CUDA probes or model loads."""

    baseline: str = "KasaneCore_v2.8"
    route_owner: str = "main.py"
    endpoint_count: int = field(default_factory=lambda: len(AUDIO_RUNTIME_ENDPOINT_OWNERSHIP))
    import_time_cuda_probe_allowed: bool = False
    model_load_allowed: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["details"] = dict(self.details)
        return data


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "loaded", "available"}
    return bool(value)


def normalize_audio_runtime_status_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Normalize existing route payloads without importing or touching runtimes."""

    source = dict(payload or {})
    status = AudioRuntimeStatus(
        asr_loaded=_coerce_bool(source.get("asr_loaded", source.get("loaded", False))),
        tts_loaded=_coerce_bool(source.get("tts_loaded", source.get("tts_ready", False))),
        sbv2_available=_coerce_bool(source.get("sbv2_available", source.get("style_bert_vits2", False))),
        echo_active_sessions=int(source.get("echo_active_sessions", source.get("active_sessions_count", 0)) or 0),
        selected_asr_device=str(source.get("selected_asr_device", source.get("asr_device", "")) or ""),
        selected_tts_device=str(source.get("selected_tts_device", source.get("tts_device", "")) or ""),
        notes=tuple(str(item) for item in source.get("notes", ()) or ()),
    )
    return status.to_dict()


def normalize_audio_runtime_error(value: Any) -> dict[str, str]:
    """Normalize route-collected audio runtime errors without touching runtimes."""

    if not value:
        return {"error": "", "reason": ""}
    if isinstance(value, Mapping):
        error = str(value.get("error") or value.get("message") or "")
        reason = str(value.get("reason") or value.get("code") or "")
        if not error and value:
            error = str(dict(value))
        return {"error": error, "reason": reason}
    return {"error": str(value), "reason": ""}


def _clean_text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text if text else default


def classify_audio_runtime_degraded(
    *,
    asr_state: Mapping[str, Any] | None = None,
    tts_state: Mapping[str, Any] | None = None,
    sbv2_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify degraded ASR/TTS/SBV2 status from already-collected state."""

    reasons: list[str] = []
    for prefix, state in (("asr", asr_state), ("tts", tts_state), ("sbv2", sbv2_state)):
        source = dict(state or {})
        error_info = normalize_audio_runtime_error(
            source.get("error") or source.get("last_cuda_error") or source.get("last_worker_error")
        )
        reason = _clean_text(source.get("reason") or error_info.get("reason"))
        if reason:
            reasons.append(f"{prefix}:{reason}")
        elif error_info.get("error"):
            reasons.append(f"{prefix}:error")
        if source.get("available") is False or (
            source.get("loaded") is False and source.get("required") is True
        ):
            reasons.append(f"{prefix}:unavailable")
    return {"degraded": bool(reasons), "reasons": reasons}


def summarize_asr_runtime_state(
    asr_config: Mapping[str, Any] | None = None,
    voice_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Shape ASR device/backend display from values collected by the route owner."""

    cfg = dict(asr_config or {})
    voice = dict(voice_status or {})
    return {
        "device": cfg.get("asr_device") or voice.get("device"),
        "compute_type": cfg.get("asr_compute_type") or voice.get("compute_type"),
        "effective_engine": cfg.get("effective_engine"),
        "effective_backend": cfg.get("effective_backend"),
        "loaded": voice.get("loaded"),
    }


def summarize_tts_runtime_state(
    tts_status: Mapping[str, Any] | None = None,
    runtime_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Shape TTS device display from route-collected runtime status."""

    status = dict(tts_status or {})
    runtime = dict(runtime_config or {})
    runtime_tts_device = runtime.get("tts_device")
    return {
        "device": status.get("selected_device") or status.get("effective_device") or runtime_tts_device,
        "requested_device": status.get("requested_device") or status.get("device_env") or "auto",
        "effective_device": status.get("effective_device") or runtime_tts_device,
    }


def summarize_sbv2_runtime_state(tts_status: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Shape SBV2 model/runtime status from already-collected TTS status."""

    status = dict(tts_status or {})
    error_info = normalize_audio_runtime_error(status.get("error") or status.get("last_worker_error"))
    return {
        "available": _coerce_bool(status.get("available", status.get("loaded", False))),
        "loaded": _coerce_bool(status.get("loaded", status.get("available", False))),
        "engine_key": _clean_text(status.get("engine_key"), "style_bert_vits2"),
        "model_ready": _coerce_bool(status.get("koharune_ami_ready", False)),
        "reason": _clean_text(status.get("reason") or error_info.get("reason")),
        "error": _clean_text(error_info.get("error")),
    }


def build_voice_status_payload(
    status: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Build the GET /voice/status payload while preserving existing keys."""

    source = dict(status or {})
    source.update(overrides)
    return {
        "loaded": _coerce_bool(source.get("loaded", False)),
        "model": str(source.get("model") or ""),
        "device": str(source.get("device") or ""),
        "compute_type": str(source.get("compute_type") or ""),
        "last_cuda_error": str(source.get("last_cuda_error") or ""),
        "last_cuda_error_at": str(source.get("last_cuda_error_at") or ""),
        "lock_locked": _coerce_bool(source.get("lock_locked", False)),
        "candidates": source.get("candidates") or [],
    }


def build_asr_config_payload(config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return the ASR config response shape from route-collected settings."""

    return dict(config or {})


def build_tts_status_payload(
    *,
    jtalk_exists: Any,
    tts_startup_health: Mapping[str, Any] | None,
    engine_registry: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build GET /tts/status payload without querying any TTS runtime."""

    return {
        "jtalk_exists": _coerce_bool(jtalk_exists),
        "tts_startup_health": dict(tts_startup_health or {}),
        "engine_registry": dict(engine_registry or {}),
    }


def run_tts_synthesize_service_body(
    req: Mapping[str, Any] | None,
    deps: TtsSynthesizeServiceDependencies,
) -> dict[str, Any]:
    """Run the POST /tts/synthesize body while keeping the FastAPI route in main.py."""

    source_req = dict(req or {})
    request_id = str(source_req.get("request_id") or deps.request_id_factory())
    route_req = dict(source_req)
    engine = "style_bert_vits2"
    route_req["engine"] = engine
    route_req["engine_key"] = engine
    text = str(route_req.get("text", "")).strip()
    if not text:
        raise AudioRuntimeHttpError(status_code=400, detail="text required")

    try:
        deps.write_tts_debug_entry(
            {
                "timestamp": deps.utcnow_factory().isoformat() + "Z",
                "stage": "route_enter",
                "route": "/tts/synthesize",
                "request_id": request_id,
                "engine": engine,
                "model": str(route_req.get("model", "")).strip(),
                "text_preview": text[:100],
            }
        )
    except Exception:
        deps.logger.warning("[TTS][synthesize:%s] route_enter debug write failed", request_id, exc_info=True)

    deps.logger.info(
        "[TTS][synthesize:%s] request engine=%s text_len=%d model=%s speaker=%s",
        request_id,
        engine,
        len(text),
        str(route_req.get("model", "")).strip(),
        str(route_req.get("speaker_name", "")).strip() or str(route_req.get("speaker", "")).strip(),
    )
    route_req["request_id"] = request_id
    normalized_key = deps.engine_registry.resolve_engine_key(engine, route_req.get("engine_key"))
    if normalized_key == "style_bert_vits2":
        model = str(route_req.get("model", "")).strip() or "koharune-ami"
        route_req["model"] = model
        deps.ensure_model_exists(model, deps.style_bert_vits2_models_dir)
        model_config_path = os.path.join(deps.style_bert_vits2_models_dir, model, "config.json")
        model_version = deps.read_model_version(model_config_path)
        route = deps.apply_tts_language_routing(route_req, model_version=model_version)
        deps.logger.info(
            "[TTS][synthesize:%s] original_text=%r translated_text=%r final_text=%r route=%s needs_translation=%s translation_target_language=%s",
            request_id,
            route_req.get("original_text", ""),
            route_req.get("translated_text", ""),
            route_req.get("final_text", ""),
            route,
            route_req.get("needs_translation"),
            route_req.get("translation_target_language"),
        )
    try:
        runtime = deps.engine_registry.get(raw_engine_key="style_bert_vits2")
    except KeyError:
        raise AudioRuntimeHttpError(status_code=400, detail=f"不明なエンジン: {engine}")

    try:
        audio_bytes, media_type = runtime.synthesize(route_req)
        deps.logger.info(
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
            deps.logger.warning("[TTS][synthesize:%s] unprocessable_entity: %s", request_id, err_payload.get("error"))
            raise AudioRuntimeHttpError(
                status_code=422,
                detail={
                    "error": err_payload.get("error") or "Unprocessable TTS input",
                    "text_preview": err_payload.get("text_preview") or "",
                    "effective_language": err_payload.get("effective_language") or "JP",
                    "model_version": err_payload.get("model_version") or "",
                },
            )
        if "worker protocol error" in error_message.lower():
            deps.logger.error("[TTS][synthesize:%s] worker_protocol_error: %s", request_id, e)
            raise AudioRuntimeHttpError(status_code=500, detail=error_message)
        deps.logger.warning("[TTS][synthesize:%s] validation_error: %s", request_id, e)
        raise AudioRuntimeHttpError(status_code=400, detail=error_message)
    except Exception as e:
        try:
            deps.write_tts_debug_entry(
                {
                    "timestamp": deps.utcnow_factory().isoformat() + "Z",
                    "stage": "route_error",
                    "route": "/tts/synthesize",
                    "request_id": request_id,
                    "engine": normalized_key,
                    "model": str(route_req.get("model", "")).strip(),
                    "text": text,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
        except Exception:
            deps.logger.warning("[TTS][synthesize:%s] route_error debug write failed", request_id, exc_info=True)
        deps.logger.error(
            "[TTS][synthesize:%s] failed engine=%s error=%s",
            request_id,
            normalized_key,
            e,
            exc_info=True,
        )
        raise AudioRuntimeHttpError(status_code=500, detail=str(e))

    return {
        "audio_bytes": audio_bytes,
        "media_type": media_type,
        "request_id": request_id,
        "engine": normalized_key,
    }


def run_tts_synthesize_batch_service_body(
    req: Mapping[str, Any] | None,
    deps: TtsSynthesizeBatchServiceDependencies,
) -> dict[str, Any]:
    """Run the POST /tts/synthesize-batch body while keeping the FastAPI route in main.py."""

    route_req = dict(req or {})
    engine = "style_bert_vits2"
    route_req["engine"] = engine
    route_req["engine_key"] = engine
    model = str(route_req.get("model", "")).strip()
    device = str(route_req.get("device", "")).strip()
    output_format = str(route_req.get("output", "json") or "json").strip().lower()
    items = route_req.get("items")
    request_id = str(route_req.get("request_id") or deps.request_id_factory())

    if output_format not in {"json", "zip", "wav"}:
        raise AudioRuntimeHttpError(status_code=400, detail='output must be "json", "zip", or "wav"')
    if not isinstance(items, list) or not items:
        raise AudioRuntimeHttpError(status_code=400, detail="items must be a non-empty list")

    normalized_key = deps.engine_registry.resolve_engine_key(engine, route_req.get("engine_key"))
    if normalized_key == "style_bert_vits2" and not model:
        model = "koharune-ami"
    if normalized_key == "style_bert_vits2":
        deps.ensure_model_exists(model, deps.style_bert_vits2_models_dir)

    try:
        runtime = deps.engine_registry.get(raw_engine=engine, raw_engine_key=route_req.get("engine_key"))
    except KeyError:
        raise AudioRuntimeHttpError(status_code=400, detail=f"不明なエンジン: {engine}")

    if normalized_key == "style_bert_vits2" and hasattr(runtime, "prepare"):
        try:
            runtime.prepare({"model": model, "device": device})
        except Exception as e:
            raise AudioRuntimeHttpError(status_code=500, detail=f"prepare failed: {e}")

    common_payload = dict(route_req)
    common_payload["engine"] = engine
    common_payload["request_id"] = request_id
    common_payload["model"] = model
    common_payload["device"] = device

    project = str(route_req.get("project", "default") or "default")
    job_id = deps.job_create(
        project=project,
        message=f"tts_synthesize_batch request_id={request_id}",
        mode="tts_batch",
    )
    deps.job_update_status(project, job_id, "running")
    seq = 0
    batch_started_at = deps.perf_counter()
    item_elapsed_history_ms: list[int] = []
    current_item_id: str | None = None
    current_item_index = 0

    def _batch_progress_data(
        *,
        total: int,
        current: int,
        current_id: str | None,
        error: str | None = None,
    ) -> dict[str, Any]:
        elapsed_ms = int((deps.perf_counter() - batch_started_at) * 1000)
        if current <= 0:
            estimated_remaining_ms = None
        elif current >= total:
            estimated_remaining_ms = 0
        elif item_elapsed_history_ms:
            estimated_remaining_ms = int(sum(item_elapsed_history_ms) / len(item_elapsed_history_ms) * (total - current))
        else:
            estimated_remaining_ms = None
        data: dict[str, Any] = {
            "total": total,
            "current": current,
            "current_id": current_id,
            "elapsed_ms": elapsed_ms,
            "estimated_remaining_ms": estimated_remaining_ms,
        }
        if error:
            data["error"] = error
        return data

    def _append_batch_step(event_type: str, data: Mapping[str, Any]) -> None:
        nonlocal seq
        deps.job_append_step(project, job_id, seq, event_type, data)
        seq += 1

    manifest: list[dict[str, Any]] = []
    json_items: list[dict[str, Any]] = []
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
                raise AudioRuntimeHttpError(status_code=400, detail=f"items[{index}] must be object")
            text = str(raw_item.get("text", "")).strip()
            if not text:
                raise AudioRuntimeHttpError(status_code=400, detail=f"items[{index}].text required")

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
            item_payload["model"] = model
            item_payload["device"] = device
            item_payload["request_id"] = f"{request_id}-{index+1:03d}"

            item_infer_ms: int | None = None
            item_total_ms: int | None = None
            batch_route_mode = "legacy_b64"
            audio_bytes = b""
            sample_rate = 0
            output_bytes = 0
            started = deps.perf_counter()
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
                    raise AudioRuntimeHttpError(status_code=500, detail=f"batch output file missing: {audio_path}")
            else:
                audio_bytes, _media_type = runtime.synthesize(item_payload)
                sample_rate = deps.sample_rate_from_wav_bytes(audio_bytes)
                output_bytes = len(audio_bytes)
            if output_format == "wav":
                if batch_route_mode == "raw_file":
                    with open(audio_path, "rb") as f:
                        wav_chunks.append(f.read())
                else:
                    wav_chunks.append(audio_bytes)
            elapsed_ms = int((deps.perf_counter() - started) * 1000)
            item_elapsed_history_ms.append(elapsed_ms)
            filename = f"{index+1:03d}_{item_id}.wav"

            row: dict[str, Any] = {
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
            deps.logger.info(
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
        deps.job_update_status(project, job_id, "done")

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
            merged_wav = deps.merge_wav_bytes(wav_chunks)
            if not merged_wav:
                raise AudioRuntimeHttpError(status_code=500, detail="batch synthesis returned empty audio")
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
            deps.logger.warning(
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
            deps.job_update_status(project, job_id, "error")
            raise AudioRuntimeHttpError(status_code=422, detail=detail_payload)
        _append_batch_step(
            "tts_batch_failed",
            _batch_progress_data(
                total=len(items),
                current=current_item_index,
                current_id=current_item_id,
                error=error_message,
            ),
        )
        deps.job_update_status(project, job_id, "error")
        raise AudioRuntimeHttpError(status_code=400, detail=error_message)
    except AudioRuntimeHttpError as e:
        _append_batch_step(
            "tts_batch_failed",
            _batch_progress_data(
                total=len(items),
                current=current_item_index,
                current_id=current_item_id,
                error="http_exception",
            ),
        )
        deps.job_update_status(project, job_id, "error")
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
        deps.job_update_status(project, job_id, "error")
        raise AudioRuntimeHttpError(status_code=500, detail=str(e))
    finally:
        if zip_file is not None:
            zip_file.close()
        if zip_tempdir_ctx is not None:
            zip_tempdir_ctx.cleanup()

def classify_audio_endpoint_risk(method_and_path: str) -> str:
    """Return the inventory risk label for a route-neutral method/path key."""

    normalized = " ".join(str(method_and_path or "").strip().split())
    entry = AUDIO_RUNTIME_ENDPOINT_OWNERSHIP.get(normalized)
    if entry:
        return entry["risk"]
    return "unknown"


def build_audio_runtime_debug_payload(
    extra: Mapping[str, Any] | None = None,
    *,
    runtime_config: Mapping[str, Any] | None = None,
    main_venv_cuda: Mapping[str, Any] | None = None,
    ctranslate2_cuda_available: Any = None,
    sbv2_venv_cuda_probe: Mapping[str, Any] | None = None,
    asr_config: Mapping[str, Any] | None = None,
    voice_status: Mapping[str, Any] | None = None,
    tts_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build audio runtime diagnostics from values collected by route owners."""

    if (
        runtime_config is None
        and main_venv_cuda is None
        and sbv2_venv_cuda_probe is None
        and asr_config is None
        and voice_status is None
        and tts_status is None
    ):
        diagnostics = AudioRuntimeDiagnostics(details=dict(extra or {})).to_dict()
        diagnostics["endpoints"] = {key: dict(value) for key, value in AUDIO_RUNTIME_ENDPOINT_OWNERSHIP.items()}
        return diagnostics

    runtime = dict(runtime_config or {})
    voice = dict(voice_status or {})
    tts = dict(tts_status or {})
    ctranslate2_available = ctranslate2_cuda_available
    if ctranslate2_available is None:
        ctranslate2_available = runtime.get("ctranslate2_cuda_available", False)
    return {
        "audio_runtime": runtime,
        "main_venv_cuda": dict(main_venv_cuda or {}),
        "ctranslate2_cuda": {
            "available": _coerce_bool(ctranslate2_available),
        },
        "sbv2_venv_cuda_probe": dict(sbv2_venv_cuda_probe or {}),
        "asr_selected": summarize_asr_runtime_state(asr_config, voice),
        "tts_selected": summarize_tts_runtime_state(tts, runtime),
        "last_asr_cuda_error": {
            "error": str(voice.get("last_cuda_error") or ""),
            "at": str(voice.get("last_cuda_error_at") or ""),
        },
        "last_tts_worker_error": tts.get("last_worker_error") or {},
        "audio_cuda_serialize_lock": {
            "asr_lock_locked": _coerce_bool(voice.get("lock_locked", False)),
        },
    }
