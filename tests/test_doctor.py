"""Doctor tests (D34): the checklist reports required gaps and names their fixes."""
import json
import sys
from pathlib import Path

import pytest

from shera import cli, config, doctor


@pytest.fixture
def env(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    for k in ("OPENROUTER_API_KEY", "ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(doctor, "_font_missing", lambda: False)


def test_ready_install_passes_with_optional_notes(env, capsys):
    rc = doctor.run()
    out = capsys.readouterr().out
    assert rc == 0
    assert "[ok  ] ffmpeg: on PATH" in out
    assert "[ok  ] ffprobe: on PATH" in out
    assert "[opt ] OpenRouter" in out and "no key in .env" in out
    assert "[opt ] Zoom" in out
    assert "Three ways in" in out and "shera desktop" in out


def test_missing_ffmpeg_is_a_required_fix(env, capsys, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    rc = doctor.run()
    out = capsys.readouterr().out
    assert rc == 1
    assert "[MISS] ffmpeg: not on PATH" in out
    assert "winget install Gyan.FFmpeg" in out  # the fix names the command for this platform
    assert "Fix the MISS items" in out


def test_desktop_extra_reported_as_optional(env, capsys, monkeypatch):
    real_import = __import__

    def fake_import(name, *a, **k):
        if name == "webview":
            raise ImportError("no pywebview")
        return real_import(name, *a, **k)

    monkeypatch.setattr("builtins.__import__", fake_import)
    rc = doctor.run()
    out = capsys.readouterr().out
    assert rc == 0  # web and CLI still work; the desktop gap is optional
    assert "[opt ] Desktop extra" in out and "pip install -e .[desktop]" in out


def test_openrouter_key_is_acknowledged_without_printing_it(env, capsys, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-value-123")
    doctor.run()
    out = capsys.readouterr().out
    assert "[ok  ] OpenRouter" in out
    assert "sk-secret-value-123" not in out  # the secret itself never prints


def test_json_mode_matches_the_cli_contract(env, capsys):
    rc = cli.main(["doctor", "--json"])
    assert rc == 0
    d = json.loads(capsys.readouterr().out)
    assert d["ok"] is True
    names = {c["name"] for c in d["checks"]}
    assert {"ffmpeg", "ffprobe", "OpenRouter", "Zoom"} <= names
    assert {n["surface"] for n in d["next"]} == {"desktop", "web", "cli"}


def test_python_dash_m_dispatch(tmp_path):
    """python -m shera with arguments goes through the CLI (the Start-menu shortcuts depend on it)."""
    import os
    import subprocess
    root = Path(__file__).resolve().parent.parent
    env = {**os.environ, "SHERA_DATA": str(tmp_path / "data")}
    r = subprocess.run([sys.executable, "-m", "shera", "doctor", "--json"], capture_output=True,
                       text=True, cwd=root, env=env, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout)["ok"] is True
    h = subprocess.run([sys.executable, "-m", "shera", "--help"], capture_output=True,
                       text=True, cwd=root, env=env, timeout=120)
    assert h.returncode == 0 and "usage" in (h.stdout + h.stderr).lower()
