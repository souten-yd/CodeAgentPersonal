from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import PurePosixPath
from urllib.parse import parse_qs, quote, urlencode, urlparse

import requests
import websockets
from pydantic import Field

from app.atlas.play.contracts import StrictContractModel
from app.atlas.play.sessions import ACTIVE_SESSION_STATES, PlaySessionError, PlaySessionRecord, PlaySessionRepository
from app.atlas.play.static_preview import StaticPreviewError, validate_preview_request_headers


PROXY_GATEWAY_SCHEMA_VERSION = "atlas.play.proxy_gateway.v1"
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
_TARGET_INJECTION_KEYS = {"target", "url", "proxy_target", "upstream", "upstream_url"}


class ProxyGatewayError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ProxyGatewayDecision(StrictContractModel):
    schema_version: str = PROXY_GATEWAY_SCHEMA_VERSION
    session_id: str
    upstream_url: str
    loopback_only: bool = True
    port_owned_by_session: bool = True
    direct_port_exposed: bool = False
    warnings: list[str] = Field(default_factory=list)


class ProxyGateway:
    def __init__(self, data_root: str) -> None:
        self.repository = PlaySessionRepository(data_root)

    def resolve_upstream(self, session_id: str, relative_path: str, query_string: str = "") -> ProxyGatewayDecision:
        record = self._active_record(session_id)
        safe_path = self._safe_proxy_path(relative_path)
        query = self._safe_query(query_string)
        url = f"http://127.0.0.1:{record.port}/{safe_path}"
        if query:
            url = f"{url}?{query}"
        return ProxyGatewayDecision(session_id=session_id, upstream_url=url)

    def proxy_http(
        self,
        *,
        session_id: str,
        method: str,
        relative_path: str,
        query_string: str,
        headers: dict[str, str],
        body: bytes,
    ) -> requests.Response:
        validate_preview_request_headers(headers)
        decision = self.resolve_upstream(session_id, relative_path, query_string)
        return requests.request(
            method=method,
            url=decision.upstream_url,
            headers=self._forward_headers(headers),
            data=body,
            stream=True,
            timeout=10,
            allow_redirects=False,
        )

    def response_headers(self, response: requests.Response, session_id: str) -> dict[str, str]:
        headers: dict[str, str] = {
            "Cache-Control": "no-store",
            "X-Atlas-Play-Session": session_id,
            "X-Content-Type-Options": "nosniff",
        }
        for key, value in response.headers.items():
            lowered = key.lower()
            if lowered in _HOP_BY_HOP_HEADERS or lowered in {"content-length", "content-encoding"}:
                continue
            if lowered == "location":
                rewritten = self._rewrite_location(value, session_id)
                if rewritten:
                    headers[key] = rewritten
                continue
            if lowered == "set-cookie":
                headers[key] = self._contain_cookie(value, session_id)
                continue
            headers[key] = value
        return headers

    def stream_response(self, response: requests.Response) -> Iterator[bytes]:
        try:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    yield chunk
        finally:
            response.close()

    async def proxy_websocket(self, websocket, session_id: str, relative_path: str, query_string: str) -> None:
        validate_preview_request_headers(dict(websocket.headers))
        decision = self.resolve_upstream(session_id, relative_path, query_string)
        parsed = urlparse(decision.upstream_url)
        upstream_url = parsed._replace(scheme="ws").geturl()
        await websocket.accept()
        async with websockets.connect(upstream_url) as upstream:
            async def client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        await upstream.close()
                        return
                    if "text" in message and message["text"] is not None:
                        await upstream.send(message["text"])
                    elif "bytes" in message and message["bytes"] is not None:
                        await upstream.send(message["bytes"])

            async def upstream_to_client() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            await asyncio.gather(client_to_upstream(), upstream_to_client())

    def _active_record(self, session_id: str) -> PlaySessionRecord:
        try:
            record = self.repository.load(session_id)
        except PlaySessionError as exc:
            raise ProxyGatewayError("session_not_found") from exc
        if record.state not in ACTIVE_SESSION_STATES:
            raise ProxyGatewayError("session_not_active")
        if not record.port:
            raise ProxyGatewayError("session_port_missing")
        return record

    def _safe_proxy_path(self, relative_path: str) -> str:
        text = str(relative_path or "").strip().lstrip("/")
        if not text:
            return ""
        parsed = urlparse(text)
        if parsed.scheme or parsed.netloc:
            raise ProxyGatewayError("proxy_target_injection")
        path = PurePosixPath(text)
        if any(part in {"", ".", ".."} for part in path.parts):
            raise ProxyGatewayError("proxy_path_unsafe")
        return quote(path.as_posix(), safe="/:@=,+-")

    def _safe_query(self, query_string: str) -> str:
        if not query_string:
            return ""
        parsed = parse_qs(query_string, keep_blank_values=True)
        if any(key.lower() in _TARGET_INJECTION_KEYS for key in parsed):
            raise ProxyGatewayError("proxy_target_injection")
        pairs: list[tuple[str, str]] = []
        for key, values in parsed.items():
            for value in values:
                pairs.append((key, value))
        return urlencode(pairs, doseq=True)

    def _forward_headers(self, headers: dict[str, str]) -> dict[str, str]:
        forwarded: dict[str, str] = {}
        for key, value in headers.items():
            lowered = key.lower()
            if lowered in _HOP_BY_HOP_HEADERS or lowered in {"host", "origin", "referer"}:
                continue
            forwarded[key] = value
        forwarded["Host"] = "127.0.0.1"
        return forwarded

    def _rewrite_location(self, value: str, session_id: str) -> str:
        parsed = urlparse(value)
        if not parsed.scheme and not parsed.netloc:
            return f"/api/atlas/play/proxy/{session_id}/{value.lstrip('/')}"
        if parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}:
            path = parsed.path.lstrip("/")
            query = f"?{parsed.query}" if parsed.query else ""
            return f"/api/atlas/play/proxy/{session_id}/{path}{query}"
        return ""

    def _contain_cookie(self, value: str, session_id: str) -> str:
        parts = [part.strip() for part in value.split(";")]
        contained_path = f"Path=/api/atlas/play/proxy/{session_id}"
        replaced = False
        for index, part in enumerate(parts):
            if part.lower().startswith("path="):
                parts[index] = contained_path
                replaced = True
        if not replaced:
            parts.append(contained_path)
        return "; ".join(parts)


def proxy_error_to_static_error(exc: ProxyGatewayError) -> StaticPreviewError:
    return StaticPreviewError(exc.code)
