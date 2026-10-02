#!/usr/bin/env bash
# Shera Clip one-command installer (D34) for macOS and Linux.
#   ./scripts/install.sh [--add-path]
# Sets up Python 3.12+, the virtualenv, the package with the desktop extra, and
# FFmpeg (with your consent), then runs `shera doctor` for the final checklist.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== Shera Clip installer =="

PY=""
for candidate in python3.13 python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        v=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
        major=${v%%.*}; minor=${v#*.}
        if [ "$major" -eq 3 ] && [ "$minor" -ge 12 ]; then PY="$candidate"; break; fi
    fi
done
if [ -z "$PY" ]; then
    echo "Python 3.12+ was not found."
    if command -v brew >/dev/null 2>&1; then echo "Install it with: brew install python@3.13"; fi
    if command -v apt-get >/dev/null 2>&1; then echo "Or: sudo apt-get install -y python3.12 python3.12-venv (Ubuntu 24.04+ has 3.12)"; fi
    exit 1
fi
echo "Python: $($PY --version)"

[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e ".[desktop]"
echo "Package installed (with the desktop extra)."

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    echo "FFmpeg was not found (needed to cut and caption the clips)."
    read -r -p "Install FFmpeg now? [y/N] " answer || answer=""
    case "$answer" in
        y|Y|yes|Yes)
            if command -v apt-get >/dev/null 2>&1; then
                sudo apt-get update && sudo apt-get install -y ffmpeg || echo "FFmpeg install failed; install it manually, then run .venv/bin/shera doctor."
            elif command -v brew >/dev/null 2>&1; then
                brew install ffmpeg || echo "FFmpeg install failed; install it manually, then run .venv/bin/shera doctor."
            elif command -v dnf >/dev/null 2>&1; then
                sudo dnf install -y ffmpeg || echo "FFmpeg install failed; install it manually, then run .venv/bin/shera doctor."
            else
                echo "No supported package manager (apt/brew/dnf) found. Install FFmpeg manually, then run .venv/bin/shera doctor."
            fi ;;
        *) echo "No problem — install it later, then run .venv/bin/shera doctor." ;;
    esac
else
    echo "FFmpeg: found."
fi

if [ "${1:-}" = "--add-path" ]; then
    dir="$(pwd)/.venv/bin"
    case ":$PATH:" in *":$dir:"*) ;; *) echo "Add this to your shell profile to use \`shera\` anywhere:  export PATH=\"$dir:\$PATH\"" ;; esac
fi

rc=0
.venv/bin/shera doctor || rc=$?
echo
echo "Done. Everything (web, CLI, desktop) drives the same local server and data."
echo "Desktop:  .venv/bin/shera desktop    Web:  .venv/bin/python -m shera    CLI:  .venv/bin/shera --help"
exit $rc
