import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_play import router as atlas_play_router
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlaySessionManager


def _project(tmp_path: Path, project_id: str = "demo") -> Path:
    work = tmp_path / "atlas" / "projects" / project_id / "work"
    work.mkdir(parents=True)
    return work


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_play_router)
    return TestClient(app)


def _adapter(work: Path, entrypoint: str):
    return build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id=Path(entrypoint).stem, name="Server", kind=LaunchKind.PYTHON_SCRIPT, entrypoint=entrypoint),
    )


def _write_http_server(path: Path, label: str) -> None:
    path.write_text(
        f"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/redirect'):
            self.send_response(302)
            self.send_header('Location', f"http://127.0.0.1:{{os.environ['ATLAS_PLAY_PORT']}}/hello")
            self.end_headers()
            return
        if self.path.startswith('/cookie'):
            self.send_response(200)
            self.send_header('Set-Cookie', 'sid=1; Path=/; HttpOnly')
            self.end_headers()
            self.wfile.write(b'cookie')
            return
        if self.path.startswith('/events'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            self.wfile.write(b'data: one\\\\n\\\\n')
            self.wfile.flush()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write({label!r}.encode('utf-8') + b':' + self.path.encode('utf-8'))

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or '0')
        body = self.rfile.read(length)
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'post:' + body)

    def log_message(self, *args):
        return

server = ThreadingHTTPServer(('127.0.0.1', int(os.environ['ATLAS_PLAY_PORT'])), Handler)
print('ready', flush=True)
server.serve_forever()
""".lstrip(),
        encoding="utf-8",
    )


def _write_websocket_server(path: Path) -> None:
    path.write_text(
        """
import asyncio
import os
import websockets

async def handler(websocket):
    async for message in websocket:
        await websocket.send('echo:' + message)

async def main():
    async with websockets.serve(handler, '127.0.0.1', int(os.environ['ATLAS_PLAY_PORT'])):
        print('ready', flush=True)
        await asyncio.Future()

asyncio.run(main())
""".lstrip(),
        encoding="utf-8",
    )


def _start_session(tmp_path: Path, work: Path, entrypoint: str, project_id: str = "demo"):
    return PlaySessionManager(tmp_path).start_session(
        project_id=project_id,
        project_root=work,
        adapter=_adapter(work, entrypoint),
    )


def _wait_get(client: TestClient, url: str):
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        last = client.get(url)
        if last.status_code < 500:
            return last
        time.sleep(0.05)
    return last


def test_proxy_forwards_http_methods_to_session_owned_loopback_port(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_http_server(work / "server.py", "A")
    session = _start_session(tmp_path, work, "server.py")
    client = _client(tmp_path)

    get = _wait_get(client, f"/api/atlas/play/proxy/{session.session_id}/hello?x=1")
    post = client.post(f"/api/atlas/play/proxy/{session.session_id}/submit", content=b"payload")
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert get.status_code == 200
    assert get.text == "A:/hello?x=1"
    assert post.status_code == 200
    assert post.text == "post:payload"
    assert get.headers["x-atlas-play-session"] == session.session_id


def test_proxy_rejects_target_injection_and_non_local_hosts(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_http_server(work / "server.py", "A")
    session = _start_session(tmp_path, work, "server.py")
    client = _client(tmp_path)

    injected = client.get(f"/api/atlas/play/proxy/{session.session_id}/hello?target=http://127.0.0.1:{session.port}/cookie")
    bad_host = client.get(f"/api/atlas/play/proxy/{session.session_id}/hello", headers={"host": "evil.example"})
    bad_origin = client.get(f"/api/atlas/play/proxy/{session.session_id}/hello", headers={"origin": "https://evil.example"})
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert injected.status_code == 403
    assert injected.json()["detail"]["error"] == "proxy_target_injection"
    assert bad_host.status_code == 403
    assert bad_origin.status_code == 403


def test_proxy_rewrites_redirects_and_contains_cookie_paths(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_http_server(work / "server.py", "A")
    session = _start_session(tmp_path, work, "server.py")
    client = _client(tmp_path)

    redirect = client.get(f"/api/atlas/play/proxy/{session.session_id}/redirect", follow_redirects=False)
    cookie = client.get(f"/api/atlas/play/proxy/{session.session_id}/cookie")
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert redirect.status_code == 302
    assert redirect.headers["location"] == f"/api/atlas/play/proxy/{session.session_id}/hello"
    assert cookie.status_code == 200
    assert f"Path=/api/atlas/play/proxy/{session.session_id}" in cookie.headers["set-cookie"]


def test_proxy_does_not_allow_cross_session_port_access(tmp_path: Path) -> None:
    work_a = _project(tmp_path, "a")
    work_b = _project(tmp_path, "b")
    _write_http_server(work_a / "server.py", "A")
    _write_http_server(work_b / "server.py", "B")
    session_a = _start_session(tmp_path, work_a, "server.py", "a")
    session_b = _start_session(tmp_path, work_b, "server.py", "b")
    client = _client(tmp_path)

    own = _wait_get(client, f"/api/atlas/play/proxy/{session_a.session_id}/hello")
    injected = client.get(f"/api/atlas/play/proxy/{session_a.session_id}/hello?proxy_target=http://127.0.0.1:{session_b.port}/hello")
    manager = PlaySessionManager(tmp_path)
    manager.stop_session(session_a.session_id)
    manager.stop_session(session_b.session_id)

    assert own.text == "A:/hello"
    assert injected.status_code == 403
    assert injected.json()["detail"]["error"] == "proxy_target_injection"


def test_proxy_forwards_sse_stream(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _write_http_server(work / "server.py", "A")
    session = _start_session(tmp_path, work, "server.py")
    client = _client(tmp_path)

    response = _wait_get(client, f"/api/atlas/play/proxy/{session.session_id}/events")
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "data: one" in response.text


def test_proxy_forwards_websocket_messages(tmp_path: Path) -> None:
    work = _project(tmp_path, "ws")
    _write_websocket_server(work / "ws.py")
    session = _start_session(tmp_path, work, "ws.py", "ws")
    client = _client(tmp_path)

    with client.websocket_connect(f"/api/atlas/play/proxy/{session.session_id}/ws/echo") as websocket:
        websocket.send_text("hello")
        received = websocket.receive_text()
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert received == "echo:hello"
