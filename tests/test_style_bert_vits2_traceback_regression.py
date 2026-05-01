import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
import importlib

from app.tts import style_bert_vits2_runtime as runtime


def test_runtime_module_importable():
    module = importlib.import_module("app.tts.style_bert_vits2_runtime")
    assert module is not None


def test_runtime_error_path_uses_traceback_without_nameerror(monkeypatch):
    rt = runtime.StyleBertVITS2Runtime()
    monkeypatch.setattr(rt, "_build_payload", lambda *args, **kwargs: {
        "request_id": "r1",
        "model_name": "m",
        "model_path": "m.pth",
        "text": "hello",
        "raw_text": "hello",
    })
    monkeypatch.setattr(rt, "_send_to_worker", lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(runtime, "write_tts_debug_entry", lambda *_a, **_k: None)

    try:
        rt.synthesize({"text": "hello", "model": "m"})
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "boom" in str(exc)
        assert "NameError" not in str(exc)


def test_worker_no_output_returncode_139_does_not_raise_secondary_nameerror(monkeypatch):
    rt = runtime.StyleBertVITS2Runtime()

    class DummyStdout:
        def readline(self):
            return ""

    class DummyStdin:
        def write(self, _s):
            return None

        def flush(self):
            return None

    class DummyProc:
        stdin = DummyStdin()
        stdout = DummyStdout()

        def poll(self):
            return 139

    rt._workers = 1
    rt._worker_procs = [DummyProc()]
    rt._worker_stderr_tails = [["Segmentation fault in torch.jit modeling_deberta_v2"]]
    monkeypatch.setattr(rt, "_ensure_worker_started", lambda: None)

    try:
        rt._send_once_to_worker({"x": 1})
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        msg = str(exc)
        assert "returned no output" in msg
        assert "returncode=139" in msg
        assert "likely_reason=deberta_v2_torch_jit_segfault" in msg
        assert "NameError" not in msg
