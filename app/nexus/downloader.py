from __future__ import annotations

import html
import ipaddress
import json
import mimetypes
import re
import ssl
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib import error as urllib_error
from urllib import request
from urllib.parse import urljoin, urlparse

from app.nexus.config import NEXUS_PATHS
from app.nexus.extractors import build_artifacts, extract_pages

DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT_SEC = 5
DEFAULT_READ_TIMEOUT_SEC = 8
MAX_REDIRECTS = 3

DOWNLOAD_ROOT = NEXUS_PATHS.nexus_dir / "research_jobs"

ALLOWED_CONTENT_TYPES: dict[str, tuple[str, ...]] = {
    "text/html": (".html", ".htm"),
    "text/plain": (".txt",),
    "application/pdf": (".pdf",),
    "application/json": (".json",),
    "text/markdown": (".md",),
}


class _ContentTooLargeError(ValueError):
    pass


class _ScriptStyleStrippingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def get_text(self) -> str:
        return "\n".join(self._chunks)


def _is_blocked_ip(ip_raw: str) -> bool:
    ip_addr = ipaddress.ip_address(ip_raw)
    return (
        ip_addr.is_private
        or ip_addr.is_loopback
        or ip_addr.is_link_local
        or ip_addr.is_multicast
        or ip_addr.is_reserved
    )


def _validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("unsupported or malformed url")

    lowered_host = parsed.hostname.lower()
    if lowered_host in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("localhost targets are blocked")

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ValueError("target hostname cannot be resolved") from exc

    for info in infos:
        ip_raw = info[4][0]
        if _is_blocked_ip(ip_raw):
            raise ValueError("private or local network target is blocked")


def _sanitize_filename(name: str) -> str:
    basename = Path(name).name
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", basename).strip("._")
    if not cleaned:
        return "downloaded"
    return cleaned[:120]


def _guess_extension_from_content_type(content_type: str) -> str:
    mime = content_type.split(";", 1)[0].strip().lower()
    ext = mimetypes.guess_extension(mime) or ""
    return ext.lower()


def _validate_content_type_and_extension(content_type: str, filename: str) -> str:
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"disallowed content-type: {content_type}")

    ext = Path(filename).suffix.lower()
    allowed_exts = ALLOWED_CONTENT_TYPES[mime]

    if ext and ext not in allowed_exts:
        raise ValueError(f"extension mismatch for content-type: {mime} vs {ext}")

    if not ext:
        guessed = _guess_extension_from_content_type(mime)
        if guessed and guessed in allowed_exts:
            ext = guessed
        else:
            ext = allowed_exts[0]

    return ext


def _read_with_limit(resp, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = resp.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise _ContentTooLargeError("content too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_text_for_analysis(content_type: str, raw_bytes: bytes) -> tuple[str, str]:
    mime = content_type.split(";", 1)[0].strip().lower()

    if mime == "application/pdf":
        return "", ""

    if mime == "text/html":
        decoded = raw_bytes.decode("utf-8", errors="replace")
        parser = _ScriptStyleStrippingParser()
        parser.feed(decoded)
        parser.close()
        text = html.unescape(parser.get_text())
        markdown = text
        return text, markdown

    decoded = raw_bytes.decode("utf-8", errors="replace")
    return decoded, decoded


def _resolve_redirect_location(current_url: str, location: str) -> str:
    resolved = urljoin(current_url, location)
    _validate_public_http_url(resolved)
    return resolved


def _build_ssl_context() -> ssl.SSLContext:
    certifi_path = ""
    try:
        import certifi  # type: ignore

        certifi_path = str(certifi.where() or "").strip()
    except Exception:  # noqa: BLE001
        certifi_path = ""

    if certifi_path:
        return ssl.create_default_context(cafile=certifi_path)
    return ssl.create_default_context()


def _build_opener_no_auto_redirect(*, ssl_context: ssl.SSLContext) -> request.OpenerDirector:
    class _NoRedirect(request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return request.build_opener(_NoRedirect, request.HTTPSHandler(context=ssl_context))


def safe_download(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    connect_timeout_sec: int = DEFAULT_CONNECT_TIMEOUT_SEC,
    read_timeout_sec: int = DEFAULT_READ_TIMEOUT_SEC,
    max_redirects: int = MAX_REDIRECTS,
) -> dict:
    """安全制約を適用して URL を取得する。"""
    current_url = url
    opener = _build_opener_no_auto_redirect(ssl_context=_build_ssl_context())

    for _ in range(max_redirects + 1):
        _validate_public_http_url(current_url)
        req = request.Request(
            current_url,
            headers={
                "User-Agent": "nexus-downloader/1.0",
                "Accept": "text/html,text/plain,application/pdf,application/json,text/markdown,*/*;q=0.1",
                "Connection": "close",
            },
            method="GET",
        )
        try:
            with opener.open(req, timeout=connect_timeout_sec) as resp:
                resp.fp.raw._sock.settimeout(read_timeout_sec)  # type: ignore[attr-defined]
                status_code = int(getattr(resp, "status", 200))
                content_type = str(resp.headers.get("Content-Type") or "")
                location = str(resp.headers.get("Location") or "")

                if 300 <= status_code < 400 and location:
                    current_url = _resolve_redirect_location(current_url, location)
                    continue

                candidate_name = _sanitize_filename(Path(urlparse(resp.geturl()).path).name or "downloaded")
                extension = _validate_content_type_and_extension(content_type, candidate_name)

                content_length = int(resp.headers.get("Content-Length") or 0)
                if content_length and content_length > max_bytes:
                    raise ValueError("content too large")

                data = _read_with_limit(resp, max_bytes)
                return {
                    "url": url,
                    "final_url": str(resp.geturl()),
                    "status_code": status_code,
                    "content_type": content_type,
                    "filename": candidate_name,
                    "extension": extension,
                    "bytes": data,
                    "size": len(data),
                }
        except urllib_error.HTTPError as exc:
            if 300 <= exc.code < 400 and exc.headers.get("Location"):
                current_url = _resolve_redirect_location(current_url, str(exc.headers.get("Location")))
                continue
            raise ValueError(f"download failed: http {exc.code}") from exc
        except _ContentTooLargeError as exc:
            raise ValueError(str(exc)) from exc
        except TimeoutError as exc:
            raise ValueError("download failed: timeout") from exc
        except urllib_error.URLError as exc:
            raise ValueError(f"download failed: {exc.reason}") from exc

    raise ValueError("too many redirects")


def save_download_artifacts(job_id: str, source_id: str, download_result: dict) -> dict[str, str]:
    """固定パスに original/extracted/metadata を保存する。"""
    safe_job = _sanitize_filename(job_id)
    safe_source = _sanitize_filename(source_id)

    base_dir = DOWNLOAD_ROOT / safe_job / "downloads" / f"source_{safe_source}"
    base_dir.mkdir(parents=True, exist_ok=True)

    ext = str(download_result.get("extension") or "")
    original_path = base_dir / f"original{ext}"
    text_path = base_dir / "text.txt"
    markdown_path = base_dir / "document.md"
    metadata_path = base_dir / "metadata.json"

    raw = bytes(download_result.get("bytes") or b"")
    content_type = str(download_result.get("content_type") or "")
    extracted_text = ""
    extracted_markdown = ""
    status = "downloaded"
    error = ""
    original_path.write_bytes(raw)
    try:
        mime = content_type.split(";", 1)[0].strip().lower()
        if mime == "application/pdf":
            pages = extract_pages(original_path)
            artifacts = build_artifacts(pages)
            extracted_text = artifacts.text
            extracted_markdown = artifacts.markdown
        else:
            extracted_text, extracted_markdown = _extract_text_for_analysis(content_type, raw)
    except Exception as exc:  # noqa: BLE001
        status = "degraded"
        error = str(exc)

    text_path.write_text(extracted_text, encoding="utf-8")
    markdown_path.write_text(extracted_markdown, encoding="utf-8")

    metadata = {
        "url": download_result.get("url"),
        "final_url": download_result.get("final_url"),
        "status_code": download_result.get("status_code"),
        "content_type": content_type,
        "size": int(download_result.get("size") or len(raw)),
        "filename": download_result.get("filename"),
        "status": status,
        "error": error,
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "base_dir": str(base_dir),
        "original": str(original_path),
        "extracted_txt": str(text_path),
        "extracted_md": str(markdown_path),
        "metadata": str(metadata_path),
        "status": status,
        "error": error,
    }
