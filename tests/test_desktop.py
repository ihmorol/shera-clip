"""Desktop shell tests (D30): server lifecycle headlessly; no window is ever opened."""
import httpx
import json
import socket
import sys
import time
import types

from shera import cli, config, db, desktop, pipeline


def _free_port():
    s = socket.socket()
    s.bind((config.HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


def env(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    port = _free_port()
    monkeypatch.setattr(config, "PORT", port)
    return f"http://{config.HOST}:{port}/"


def test_server_lifecycle(tmp_path, monkeypatch):
    url = env(tmp_path, monkeypatch)
    server, thread = desktop._start_server()
    assert server is not None and server.started
    assert desktop._live_server()
    assert httpx.get(url, timeout=3).status_code == 200
    server.should_exit = True
    thread.join(timeout=10)
    deadline = time.time() + 5
    while desktop._live_server() and time.time() < deadline:
        time.sleep(0.05)
    assert not desktop._live_server()


def test_port_taken_by_another_program(tmp_path, monkeypatch):
    env(tmp_path, monkeypatch)
    blocker = socket.socket()
    blocker.bind((config.HOST, config.PORT))
    blocker.listen(1)
    try:
        assert desktop._start_server() == (None, None)
    finally:
        blocker.close()


def test_reuse_requires_shera_branding(tmp_path, monkeypatch):
    """A foreign program answering 200 on the port must not be mistaken for Shera Clip."""
    env(tmp_path, monkeypatch)

    def fake_get(url, timeout=None):
        class R:
            status_code = 200
            content = b"<html>totally unrelated service</html>"
        return R()

    monkeypatch.setattr(desktop.httpx, "get", fake_get)
    assert desktop._live_server() is False  # not ours -> do not reuse

    def fake_get_ours(url, timeout=None):
        class R:
            status_code = 200
            content = b"<title>Shera Clip</title>"
        return R()

    monkeypatch.setattr(desktop.httpx, "get", fake_get_ours)
    assert desktop._live_server() is True


def test_desktop_needs_pywebview(tmp_path, capsys, monkeypatch):
    env(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "webview", None)  # `import webview` now raises ImportError
    rc = cli.main(["desktop"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "pywebview" in out["error"]
    assert pipeline.inline is False


def test_desktop_runs_with_background_threads(tmp_path, capsys, monkeypatch):
    """A desktop session opts out of the CLI's inline-run mode, and reports like any command."""
    env(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "webview", types.ModuleType("webview"))
    seen = {}
    monkeypatch.setattr(desktop, "check_webview2", lambda: None)

    def fake_run():
        seen["inline"] = pipeline.inline
        return "started"

    monkeypatch.setattr(desktop, "run_window", fake_run)
    rc = cli.main(["desktop"])
    assert rc == 0 and seen["inline"] is False
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["server"] == "started" and out["window"] == "closed"


class _FakeWinreg:
    def __init__(self, present):
        self.present = present
        self.HKEY_LOCAL_MACHINE = 1
        self.HKEY_CURRENT_USER = 2
        self.tried = []

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, sub):
        self.tried.append(sub)
        if self.present:
            return self._Key()
        raise OSError("not found")


def _with_windows(monkeypatch, fake):
    monkeypatch.setitem(sys.modules, "winreg", fake)
    monkeypatch.setattr(sys, "platform", "win32")


def test_check_webview2_missing_raises_with_fix(tmp_path, monkeypatch):
    fake = _FakeWinreg(present=False)
    _with_windows(monkeypatch, fake)
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: False)  # no fallback folder either
    with __import__("pytest").raises(ValueError) as e:
        desktop.check_webview2()
    assert "WebView2" in str(e.value)
    assert any("WOW6432Node" in s for s in fake.tried)  # both registry layouts were tried


def test_check_webview2_present_passes(tmp_path, monkeypatch):
    fake = _FakeWinreg(present=True)
    _with_windows(monkeypatch, fake)
    assert desktop.check_webview2() is None


def test_check_webview2_folder_fallback(tmp_path, monkeypatch):
    fake = _FakeWinreg(present=False)
    _with_windows(monkeypatch, fake)
    monkeypatch.setattr("pathlib.Path.is_dir", lambda self: True)  # runtime installed, key absent
    assert desktop.check_webview2() is None
