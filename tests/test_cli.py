"""CLI contract tests (D29): JSON on stdout, exit codes, and the human-approval boundary."""
import json
import shutil
from pathlib import Path

import pytest

from shera import cli, config, db, media, pipeline, providers

DUR = 300.0
SENTENCE = "In Task 2 always answer the exact question and give one clear example"  # 14 words


def vtt_text(n=60):
    cues = [f"{i + 1}\n00:{i * 5 // 60:02d}:{i * 5 % 60:02d}.000 --> 00:{(i * 5 + 5) // 60:02d}:"
            f"{(i * 5 + 5) % 60:02d}.000\nRimon Ahmed: {SENTENCE} {i}" for i in range(n)]
    return "WEBVTT\n\n" + "\n\n".join(cues) + "\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    src = tmp_path / "class.mp4"
    src.write_bytes(b"not really a video")
    vtt = tmp_path / "class.vtt"
    vtt.write_text(vtt_text(), encoding="utf-8")

    def copy(s, d, on_progress=None):
        shutil.copyfile(s, d)
        on_progress and on_progress(1.0)
        return "sha-fake", d.stat().st_size

    monkeypatch.setattr(media, "copy_with_hash", copy)
    monkeypatch.setattr(media, "probe", lambda p: {"duration": DUR, "width": 1920, "height": 1080, "vcodec": "h264",
                                                   "acodec": "aac", "v_start": 0, "a_start": 0, "has_audio": True})
    monkeypatch.setattr(media, "speech_intervals", lambda p: [(0.0, DUR)])
    monkeypatch.setattr(media, "render", lambda *a, **k: a[6].write_bytes(b"mp4"))
    monkeypatch.setattr(media, "thumbnail", lambda v, out, at: out.write_bytes(b"jpg"))
    monkeypatch.setattr(media, "verify", lambda p, d, size=None: [])

    def jev(text, original=None):
        n = int(text.split()[-1])
        return {"value": 2 + n % 3, "clarity": 3, "opening": n % 5, "teacher": 0.9, "complete": 0.8,
                "category": "exam_tip", "raw": {"value": {"type": "score", "score": 2 + n % 3}}}, 0.001

    def draft(text, category, english=None):
        t = {"title": "Task 2", "description": "d", "cta": "Follow for more"}
        return {"facebook": t, "youtube": t}, 0.001

    monkeypatch.setattr(providers, "jev_score", jev)
    monkeypatch.setattr(providers, "draft_post", draft)
    return src, vtt


def run(capsys, *argv):
    rc = cli.main(list(argv))
    out = json.loads(capsys.readouterr().out)
    return rc, out


def test_import_stops_at_authorization(env, capsys):
    src, vtt = env
    rc, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    assert rc == 0
    job = out["job"]
    assert job["stage"] == "authorize" and job["status"] == "waiting"
    assert job["authorized_usd"] is None
    assert job["estimate"]["transcription"] == 0.0  # the VTT is usable; no paid transcription needed


def test_authorize_without_yes_changes_nothing(env, capsys):
    src, vtt = env
    _, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    jid = out["job"]["id"]
    rc, out = run(capsys, "authorize", jid)
    assert rc == 0 and out["already_authorized"] is False and out["cap_usd"] == 1.5
    job = db.get_job(jid)
    assert job["authorized_usd"] is None and job["status"] == "waiting"
    assert ledger_never_billed(jid)


def ledger_never_billed(job_id):
    return db.one("SELECT COUNT(*) AS n FROM paid_calls WHERE job_id=?", job_id)["n"] == 0


def test_full_run_candidates_and_export(env, capsys, monkeypatch):
    src, vtt = env

    def jev_with_one_weak(text, original=None):  # the first window (last cue 14) is not worth reviewing
        n = int(text.split()[-1])
        value = 1 if n == 14 else 2 + n % 3
        return {"value": value, "clarity": 3, "opening": n % 5, "teacher": 0.9, "complete": 0.8,
                "category": "exam_tip", "raw": {"value": {"type": "score", "score": value}}}, 0.001

    monkeypatch.setattr(providers, "jev_score", jev_with_one_weak)
    _, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    jid = out["job"]["id"]
    rc, out = run(capsys, "authorize", jid, "--yes")
    assert rc == 0 and out["job"]["stage"] == "review" and out["job"]["status"] == "done"
    assert out["job"]["summary"]["shortlisted"] > 0

    rc, out = run(capsys, "candidates", jid)
    short = out["candidates"]
    assert short and all(c["shortlisted"] and c["blocker"] is None for c in short)
    rc, out = run(capsys, "candidates", jid, "--all")
    weak = [c for c in out["candidates"] if not c["shortlisted"]]
    # weak candidates stay visible outside the shortlist with their reason; others were
    # dropped for overlapping a higher-ranked kept candidate, not for quality
    assert any(c["blocker"] == "low" for c in weak)
    assert all(c["score"] is not None for c in weak)
    assert any(c["review_status"] == "pending" for c in out["candidates"])

    top = short[0]["id"]  # approve the way the review UI does, then the CLI can export it
    pipeline.render_preview(top)
    db.update_review(top, status="approved")
    rc, out = run(capsys, "export", jid)
    assert rc == 0 and [c["candidate_id"] for c in out["clips"]] == [top]
    assert (Path(out["folder"]) / out["clips"][0]["folder"] / "post.json").is_file()

    second = short[1]["id"]
    db.update_review(second, status="approved")  # approved but never previewed at this state
    rc, out = run(capsys, "export", jid)
    assert rc == 0 and [s["candidate_id"] for s in out["skipped"]] == [second]
    assert "render and approve again" in out["skipped"][0]["reason"]


def test_errors_are_json_with_exit_1(env, capsys):
    rc, out = run(capsys, "job", "nope")
    assert rc == 1 and out["ok"] is False and "nope" in out["error"]
    src, vtt = env
    rc, out = run(capsys, "import", str(src.parent / "missing.mp4"))
    assert rc == 1 and out["ok"] is False and "video" in out["error"]


def test_delete_requires_yes(env, capsys):
    src, vtt = env
    _, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    jid = out["job"]["id"]
    rc, _ = run(capsys, "delete", jid)
    assert rc == 0 and db.get_job(jid) is not None
    rc, out = run(capsys, "delete", jid, "--yes")
    assert rc == 0 and out["deleted"] == jid and db.get_job(jid) is None


def test_data_flag_points_elsewhere(env, capsys, tmp_path):
    rc, out = run(capsys, "--data", str(tmp_path / "other"), "jobs")
    assert rc == 0 and out["jobs"] == []
    assert (tmp_path / "other" / "shera.sqlite3").exists()


def test_zoom_list_requires_setup(env, capsys, monkeypatch):
    for k in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER"):
        monkeypatch.delenv(k, raising=False)
    rc, out = run(capsys, "zoom", "list")
    assert rc == 1 and out["ok"] is False and "ZOOM_ACCOUNT_ID" in out["error"]
