"""CLI contract tests (D29): JSON on stdout, exit codes, and the human-approval boundary."""
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from shera import cli, config, db, ledger, media, pipeline, providers

DUR = 300.0
SENTENCE = "In Task 2 always answer the exact question and give one clear example"  # 14 words


def vtt_text(n=60):
    # mostly per-cue vocabulary, so windows are not "the same passage played again"
    # (D26 repeat suppression would otherwise collapse the shortlist — by design)
    skills = ("listening", "reading", "writing", "speaking")
    cues = [f"{i + 1}\n00:{i * 5 // 60:02d}:{i * 5 % 60:02d}.000 --> 00:{(i * 5 + 5) // 60:02d}:"
            f"{(i * 5 + 5) % 60:02d}.000\n"
            f"Rimon Ahmed: idea{i} shows method{i} using sheet{i} part{i} where band{i} improves "
            f"when students {skills[i % 4]} daily {i}" for i in range(n)]
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


def test_data_flag_after_subcommand(env, capsys, tmp_path):
    rc, out = run(capsys, "jobs", "--data", str(tmp_path / "after"))
    assert rc == 0 and out["jobs"] == []
    assert (tmp_path / "after" / "shera.sqlite3").exists()


def test_wont_touch_a_job_marked_running(env, capsys):
    src, vtt = env
    _, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    jid = out["job"]["id"]
    db.update_job(jid, status="running")  # as the app's runner threads would mark it
    for argv in (("run", jid), ("authorize", jid, "--yes"), ("delete", jid, "--yes")):
        rc, out = run(capsys, *argv)
        assert rc == 1 and "marked running" in out["error"], argv
    assert db.get_job(jid) is not None
    rc, out = run(capsys, "run", jid, "--force")  # explicit takeover of a stuck job
    assert rc == 0 and out["job"]["status"] == "waiting"
    rc, out = run(capsys, "delete", jid, "--yes", "--force")
    assert rc == 0 and db.get_job(jid) is None


def test_failed_job_is_reported_not_crashed(env, capsys, monkeypatch):
    """A job that dies mid-score leaves unscored candidates (NULL shortlisted/rank/score);
    the CLI must still report the job instead of crashing on them."""
    src, vtt = env
    _, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    jid = out["job"]["id"]

    def no_key(text, original=None):  # what providers do before any spend
        raise ledger.ProviderError("OPENROUTER_API_KEY not set")

    monkeypatch.setattr(providers, "jev_score", no_key)
    rc, out = run(capsys, "authorize", jid, "--yes")
    assert rc == 1
    job = out["job"]  # the job record still comes back, with the failure inside it
    assert job["status"] == "failed" and "OPENROUTER_API_KEY not set" in job["error"]
    assert job["summary"]["candidates"] > 0 and job["summary"]["shortlisted"] == 0
    rc, out = run(capsys, "job", jid)  # reading a failed job works
    assert rc == 0 and "OPENROUTER_API_KEY not set" in out["job"]["error"]
    rc, out = run(capsys, "candidates", jid, "--all")
    assert rc == 0 and all(c["score"] is None for c in out["candidates"])
    assert ledger.spent(jid) == 0  # the key check fires before any spend; the failed attempt costs nothing


def test_usage_errors_stay_json(env, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["job"])  # missing argument
    assert e.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and "usage" in out["error"]
    with pytest.raises(SystemExit) as e:
        cli.main(["nope"])  # unknown command
    assert e.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False


def test_export_refuses_running_job(env, capsys):
    src, vtt = env
    _, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    jid = out["job"]["id"]
    db.update_job(jid, status="running")
    rc, out = run(capsys, "export", jid)
    assert rc == 1 and "marked running" in out["error"]
    rc, out = run(capsys, "export", jid, "--force")  # takeover; nothing approved yet
    assert rc == 0 and out["clips"] == [] and out["skipped"] == []


def test_import_title_and_zoom_audio(env, capsys, monkeypatch, tmp_path):
    src, vtt = env
    monkeypatch.setattr(media, "sync_offset", lambda v, a: (0.25, "sound"))
    monkeypatch.setattr(media, "mux_audio", lambda v, a, off, out_path: Path(out_path).write_bytes(b"muxed"))
    m4a = tmp_path / "zoom.m4a"
    m4a.write_bytes(b"not really audio")
    rc, out = run(capsys, "import", str(src), "--vtt", str(vtt), "--audio", str(m4a), "--title", "Week 3 class")
    assert rc == 0
    job = out["job"]
    assert job["title"] == "Week 3 class"
    assert Path(config.JOBS, job["id"], "media.mp4").is_file()
    assert any("lined up by matching sound" in f for f in job["flags"])
    rc, out = run(capsys, "import", str(src), "--audio", str(tmp_path / "missing.m4a"))
    assert rc == 1 and "audio" in out["error"]


def test_sent_call_recovery_loop(env, capsys):
    """A runner died mid-call: the CLI reaps the orphaned 'sent' row, pauses, lets the
    operator resolve it, and then finishes the job."""
    src, vtt = env
    _, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    jid = out["job"]["id"]
    now = time.time()
    cid = db.x("INSERT INTO paid_calls(job_id, key, kind, state, est_usd, created, updated) "
               "VALUES (?, 'jev2:1', 'jev', 'sent', 0.002, ?, ?)", jid, now, now)
    rc, out = run(capsys, "resolve", str(cid))  # a live runner may own it: refused
    assert rc == 1 and "'sent'" in out["error"]
    rc, out = run(capsys, "authorize", jid, "--yes")  # recover() reaps the orphan, the PENDING check pauses
    assert rc == 0 and out["job"]["status"] == "paused"
    assert "resolve stuck calls" in out["next"]
    rc, out = run(capsys, "resolve", str(cid))
    assert rc == 0 and "abandoned" in out["note"]
    rc, out = run(capsys, "run", jid)  # retried in place; the good fake finishes the job
    assert rc == 0 and out["job"]["status"] == "done"
    rc, out = run(capsys, "calls", jid)
    assert rc == 0 and len(out["calls"]) >= 1


def test_recover_leaves_web_draft_calls_alone(env, capsys):
    """A 'draft' call can belong to a live web task even on a non-running job, so CLI
    recovery must never reap it (only a --force takeover may)."""
    src, vtt = env
    _, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    jid = out["job"]["id"]
    now = time.time()
    draft_id = db.x("INSERT INTO paid_calls(job_id, key, kind, state, est_usd, created, updated) "
                    "VALUES (?, 'draft:x', 'draft', 'sent', 0.002, ?, ?)", jid, now, now)
    rc, out = run(capsys, "authorize", jid, "--yes")  # runs CLI recovery; job is not running
    assert rc == 0 and out["job"]["status"] == "done"
    assert db.one("SELECT state FROM paid_calls WHERE id=?", draft_id)["state"] == "sent"


def test_zoom_list_requires_setup(env, capsys, monkeypatch):
    for k in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER"):
        monkeypatch.delenv(k, raising=False)
    rc, out = run(capsys, "zoom", "list")
    assert rc == 1 and out["ok"] is False and "ZOOM_ACCOUNT_ID" in out["error"]


# ---------- real FFmpeg media: only the paid providers are faked ----------

@pytest.fixture(scope="module")
def real_class(tmp_path_factory):
    """A real 200 s recording: test pattern video, continuous tone audio, VTT aligned to it."""
    d = tmp_path_factory.mktemp("real")
    src = d / "class.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25:d=200",
         "-f", "lavfi", "-i", "aevalsrc='0.4*sin(2*PI*440*t)':s=48000:d=200",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(src)],
        check=True)
    vtt = d / "class.vtt"
    vtt.write_text(vtt_text(40), encoding="utf-8")
    return src, vtt


@pytest.fixture
def real_env(real_class, tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    # product clip length is 60-90 s (D24); a few short windows keep the real renders quick
    monkeypatch.setattr(config, "CLIP_MIN_S", 4)
    monkeypatch.setattr(config, "CLIP_TARGET_S", 6)
    monkeypatch.setattr(config, "CLIP_MAX_S", 10)

    def jev(text, original=None):
        n = int(text.split()[-1])
        return {"value": 2 + n % 3, "clarity": 3, "opening": n % 5, "teacher": 0.9, "complete": 0.8,
                "category": "exam_tip", "postable": 3,
                "raw": {"value": {"type": "score", "score": 2 + n % 3}}}, 0.001

    def draft(text, category, english=None):
        t = {"title": "Task 2", "description": "d", "cta": "Follow for more"}
        return {"facebook": t, "youtube": t}, 0.001

    monkeypatch.setattr(providers, "jev_score", jev)
    monkeypatch.setattr(providers, "draft_post", draft)
    return real_class


def test_real_media_end_to_end(real_env, capsys):
    """Real probe, copy, silence detection, VTT alignment, windows, render, verify, export."""
    src, vtt = real_env
    rc, out = run(capsys, "import", str(src), "--vtt", str(vtt))
    assert rc == 0
    job = out["job"]
    assert job["stage"] == "authorize" and job["status"] == "waiting"
    assert job["duration"] == pytest.approx(200, abs=1)
    assert job["source_sha256"] and len(job["source_sha256"]) == 64
    assert job["estimate"]["transcription"] == 0.0  # the real VTT aligned, so no paid transcription
    jid = job["id"]

    rc, out = run(capsys, "authorize", jid, "--yes")
    assert rc == 0 and out["job"]["status"] == "done" and out["job"]["stage"] == "review"

    rc, out = run(capsys, "candidates", jid)
    short = out["candidates"]
    # 40 cues over 200 s: windows start every 30 s (stride), each 4-10 s, and all seven
    # survive the shortlist because this fixture's cues do not repeat or overlap
    assert len(out["candidates"]) == 7 and len(short) == 7
    assert sorted(c["rank"] for c in short) == [1, 2, 3, 4, 5, 6, 7]  # the list is start order, rank is score order
    top = next(c["id"] for c in short if c["rank"] == 1)

    pipeline.render_preview(top)  # real portrait + landscape renders
    db.update_review(top, status="approved")  # the one thing only a human may do
    rc, out = run(capsys, "export", jid)
    assert rc == 0 and len(out["clips"]) == 1 and out["clips"][0]["candidate_id"] == top
    assert out["clips"][0]["problems"] == []  # real ffprobe verify: codecs, size, duration all hold
    pkg = Path(out["folder"]) / out["clips"][0]["folder"]
    assert (pkg / "portrait.mp4").stat().st_size > 10_000
    assert (pkg / "captions.srt").read_text(encoding="utf-8").startswith("1\n")
