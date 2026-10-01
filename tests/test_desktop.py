"""Desktop shell tests (D30): server lifecycle headlessly; no window is ever opened."""
import httpx
import json
import socket
import sys
import time

from shera import cli, config, db, desktop


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
    server = desktop._start_server()
    assert server is not None and server.started
    assert desktop._live_server()
    assert httpx.get(url, timeout=3).status_code == 200
    server.should_exit = True
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
        assert desktop._start_server() is None
    finally:
        blocker.close()


def test_desktop_needs_pywebview(tmp_path, capsys, monkeypatch):
    env(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "webview", None)  # `import webview` now raises ImportError
    rc = cli.main(["desktop"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "pywebview" in out["error"]
