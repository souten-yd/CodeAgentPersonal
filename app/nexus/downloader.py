from __future__ import annotations

import ipaddress
import socket
from urllib import error as urllib_error
from urllib import request
from urllib.parse import urlparse


DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SEC = 8
MAX_REDIRECTS = 3


def _is_private_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True

    for info in infos:
        ip_raw = info[4][0]
        ip_addr = ipaddress.ip_address(ip_raw)
        if ip_addr.is_private or ip_addr.is_loopback or ip_addr.is_link_local:
            return True
    return False


def safe_download(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    allowed_content_types: tuple[str, ...] = ("text/", "application/pdf"),
) -> dict:
    """サイズ/timeout/redirect/content-type/private IP を検証しつつ取得する。"""
    current_url = url

    for _ in range(MAX_REDIRECTS + 1):
        parsed = urlparse(current_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("unsupported or malformed url")
        if _is_private_host(parsed.hostname):
            raise ValueError("private or local network target is blocked")

        req = request.Request(current_url, headers={"User-Agent": "nexus-downloader/1.0"}, method="GET")
        try:
            with request.urlopen(req, timeout=timeout_sec) as resp:
                status_code = int(getattr(resp, "status", 200))
                content_type = str(resp.headers.get("Content-Type") or "")
                location = str(resp.headers.get("Location") or "")

                if 300 <= status_code < 400 and location:
                    current_url = location
                    continue

                if allowed_content_types and not any(content_type.lower().startswith(prefix) for prefix in allowed_content_types):
                    raise ValueError(f"disallowed content-type: {content_type}")

                content_length = int(resp.headers.get("Content-Length") or 0)
                if content_length and content_length > max_bytes:
                    raise ValueError("content too large")

                data = resp.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ValueError("content too large")

                return {
                    "url": url,
                    "final_url": str(resp.geturl()),
                    "status_code": status_code,
                    "content_type": content_type,
                    "bytes": data,
                    "size": len(data),
                }
        except urllib_error.HTTPError as exc:
            raise ValueError(f"download failed: http {exc.code}") from exc
        except urllib_error.URLError as exc:
            raise ValueError(f"download failed: {exc.reason}") from exc

    raise ValueError("too many redirects")
