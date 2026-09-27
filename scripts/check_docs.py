from pathlib import Path
from subprocess import check_output
import re
import sys
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SUFFIXES = {".mp4", ".mov", ".m4a", ".wav", ".mp3", ".vtt", ".srt", ".zip", ".sqlite", ".sqlite3", ".db"}


def main() -> int:
    tracked = [Path(line) for line in check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()]
    failures = []
    for path in tracked:
        if path.suffix.lower() in PRIVATE_SUFFIXES or (path.name == ".env" or path.name.startswith(".env.")) and path.name != ".env.example":
            failures.append(f"private artifact tracked: {path}")
        if path.suffix.lower() != ".md":
            continue
        body = (ROOT / path).read_text(encoding="utf-8-sig")
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", body):
            target = unquote(target.split("#", 1)[0].strip("<>"))
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (ROOT / path.parent / target).exists():
                failures.append(f"broken link: {path} -> {target}")
    print("\n".join(failures) if failures else f"Checked {len(tracked)} tracked files; document links and artifact policy pass.")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
