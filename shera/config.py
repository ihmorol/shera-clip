import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env(path):
    """A filled .env entry is authoritative over a stale variable inherited from the shell,
    so editing .env always takes effect after a restart (setdefault let an old export win)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip("\"'")
            if v:  # a blank .env line never clobbers a real environment value
                os.environ[k.strip()] = v


_load_env(ROOT / ".env")


def set_data(path):
    """Point all data paths at `path` (tests call this with tmp_path)."""
    global DATA, INBOX, JOBS, DB_PATH
    DATA = Path(path)
    INBOX = DATA / "inbox"
    JOBS = DATA / "jobs"
    DB_PATH = DATA / "shera.sqlite3"


set_data(os.environ.get("SHERA_DATA", ROOT / "data"))


def openrouter_key():
    return os.environ.get("OPENROUTER_API_KEY") or None


CAP_USD = 1.50
WEIGHTS = (0.45, 0.35, 0.20)
# Estimates only; the ledger records actual provider cost when the response reports it.
STT_USD_PER_MIN = float(os.environ.get("SHERA_STT_USD_PER_MIN", 0.006))
# Speech-to-text through OpenRouter (D25). MAI-Transcribe-2 lists Bengali, detects the language itself and
# follows Bangla/English switching mid-sentence; Whisper large-v3 came last of 8 on a 2026 Bangla benchmark and
# translated this class's Bangla into English. Deepgram Nova-3 (3rd on that benchmark) is the fallback when a
# provider rejects timestamps (HTTP 400).
STT_MODEL = os.environ.get("SHERA_STT_MODEL") or "microsoft/mai-transcribe-2"
STT_FALLBACK_MODEL = os.environ.get("SHERA_STT_FALLBACK_MODEL") or "deepgram/nova-3"
# English translation of the as-spoken transcript, so Jev (and the reviewer) read proper English.
TRANSLATE_MODEL = os.environ.get("SHERA_TRANSLATE_MODEL") or "google/gemini-3.1-flash-lite"
TRANSLATE_USD_PER_MIN = float(os.environ.get("SHERA_TRANSLATE_USD_PER_MIN", 0.001))
# Clip length (D24): long enough to hold one complete teaching point.
CLIP_MIN_S, CLIP_TARGET_S, CLIP_MAX_S = 60, 75, 90
JEV_EST_USD = float(os.environ.get("SHERA_JEV_EST_USD", 0.002))
DRAFT_EST_USD = float(os.environ.get("SHERA_DRAFT_EST_USD", 0.002))
DRAFT_MODEL = os.environ.get("SHERA_DRAFT_MODEL") or "openai/gpt-4o-mini"
HOST = "127.0.0.1"
PORT = int(os.environ.get("SHERA_PORT") or 8765)
