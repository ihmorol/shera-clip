import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env(path):
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


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
# Speech-to-text through OpenRouter; whisper-1 is the fallback when a provider rejects timestamps.
STT_MODEL = os.environ.get("SHERA_STT_MODEL") or "openai/whisper-large-v3"
STT_FALLBACK_MODEL = "openai/whisper-1"
JEV_EST_USD = float(os.environ.get("SHERA_JEV_EST_USD", 0.002))
DRAFT_EST_USD = float(os.environ.get("SHERA_DRAFT_EST_USD", 0.002))
DRAFT_MODEL = os.environ.get("SHERA_DRAFT_MODEL") or "openai/gpt-4o-mini"
HOST = "127.0.0.1"
PORT = int(os.environ.get("SHERA_PORT") or 8765)
