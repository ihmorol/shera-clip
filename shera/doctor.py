"""Setup doctor (D34): one command that tells the operator exactly what is missing.

Checks the three surfaces (web, CLI, desktop) against one local server: Python and
FFmpeg are required, the desktop extra and WebView2 are needed only for the desktop
window, and OpenRouter/Zoom credentials unlock their features. Every gap names its fix.
Prints a human checklist by default; --json emits the same rows for machines.
"""
import json
import shutil
import sys

from shera import config, zoom


def _fix_ffmpeg():
    if sys.platform == "win32":
        return "run: winget install Gyan.FFmpeg  (then reopen the terminal)"
    if sys.platform == "darwin":
        return "run: brew install ffmpeg"
    return "run: sudo apt-get install -y ffmpeg"


def _font_missing():
    if sys.platform != "win32":
        return False  # non-Windows picks a Bangla-capable fallback via the font stack
    from pathlib import Path
    return not Path("C:/Windows/Fonts/nirmala.ttf").exists()


NEXT = [
    ("desktop", "shera desktop", "native window; needs the Desktop extra above"),
    ("web", "python -m shera", "opens http://127.0.0.1:8765 in your browser"),
    ("cli", "shera --help", "machine stages with JSON output"),
]


def checks():
    """-> (rows, ok) where rows are (state, name, detail) with state in ok/fix/optional."""
    rows = []

    v = sys.version_info
    if (v.major, v.minor) >= (3, 12):
        rows.append(("ok", "Python", f"{v.major}.{v.minor}.{v.micro}"))
    else:
        rows.append(("fix", "Python", f"{v.major}.{v.minor} found; Shera Clip needs 3.12 or later"))

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool):
            rows.append(("ok", tool, "on PATH"))
        else:
            rows.append(("fix", tool, f"not on PATH — {_fix_ffmpeg()}"))

    if _font_missing():
        rows.append(("fix", "Bangla font", "Nirmala UI not found in C:/Windows/Fonts — captions may not render; "
                                           "install a Bangla-capable font"))
    else:
        rows.append(("ok", "Bangla font", "Nirmala UI available" if sys.platform == "win32" else "system font stack"))

    try:
        import webview  # noqa: F401
        rows.append(("ok", "Desktop extra", "pywebview installed"))
        if sys.platform == "win32":
            try:
                from shera import desktop
                desktop.check_webview2()
                rows.append(("ok", "WebView2", "runtime present"))
            except ValueError as e:
                rows.append(("optional", "WebView2", str(e).split(". Install it from")[0]))
    except ImportError:
        rows.append(("optional", "Desktop extra", "pywebview not installed — the desktop window needs it. "
                                                  "Run: pip install -e .[desktop]"))
    rows.append(("ok", "Web and CLI", f"always available on this install; server binds to {config.HOST}:{config.PORT}"))

    if config.openrouter_key():
        rows.append(("ok", "OpenRouter", "key configured (ranking, drafts, transcription)"))
    else:
        rows.append(("optional", "OpenRouter", "no key in .env — add OPENROUTER_API_KEY to unlock paid ranking, "
                                               "posting drafts, and transcription"))
    if zoom.configured():
        rows.append(("ok", "Zoom", "cloud-recording import configured"))
    else:
        rows.append(("optional", "Zoom", "not configured — optional; see docs/zoom-setup.md"))

    ok = all(state != "fix" for state, _, _ in rows)
    return rows, ok


def run(json_mode=False):
    """Print the checklist; -> exit code (1 when a required piece is missing)."""
    rows, ok = checks()
    if json_mode:
        print(json.dumps({"ok": ok, "checks": [{"state": s, "name": n, "detail": d} for s, n, d in rows],
                          "next": [{"surface": a, "command": b, "note": c} for a, b, c in NEXT]},
                         ensure_ascii=False, indent=2))
    else:
        marks = {"ok": "ok  ", "fix": "MISS", "optional": "opt "}
        for state, name, detail in rows:
            print(f"[{marks[state]}] {name}: {detail}")
        print()
        if ok:
            print("Ready. Three ways in — all on the same server and data:")
            for _, command, note in NEXT:
                print(f"  {command.ljust(18)} {note}")
        else:
            print("Fix the MISS items above, then run `shera doctor` again.")
    return 0 if ok else 1
