"""Pipeline state tests with fake media and providers (fakes live only here, never in app code)."""
import json
import shutil

import pytest

from shera import config, db, ledger, media, pipeline, providers

DUR = 300.0
SENTENCE = "In Task 2 always answer the exact question and give one clear example"  # 14 words


class Crash(BaseException):
    """The process dies mid-call."""


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
    calls = {"jev": [], "draft": [], "stt": [], "render": []}

    def copy(s, d, on_progress=None):
        shutil.copyfile(s, d)
        on_progress and on_progress(1.0)
        return "sha-fake", d.stat().st_size

    monkeypatch.setattr(pipeline, "_spawn", pipeline.run)  # run synchronously
    monkeypatch.setattr(media, "copy_with_hash", copy)
    monkeypatch.setattr(media, "probe", lambda p: {"duration": DUR, "width": 1920, "height": 1080, "vcodec": "h264",
                                                   "acodec": "aac", "v_start": 0, "a_start": 0, "has_audio": True})
    monkeypatch.setattr(media, "speech_intervals", lambda p: [(0.0, DUR)])
    monkeypatch.setattr(media, "peaks", lambda p, buckets=2000: [10] * buckets)
    monkeypatch.setattr(media, "render", lambda *a, **k: (calls["render"].append(a), a[6].write_bytes(b"mp4")))
    monkeypatch.setattr(media, "thumbnail", lambda v, out, at, width=None: out.write_bytes(b"jpg"))
    monkeypatch.setattr(media, "verify", lambda p, d, size=None: [])

    def jev(text, original=None):
        calls["jev"].append(text)
        n = int(text.split()[-1])  # last cue number in the window
        return {"value": 2 + n % 3, "clarity": 3, "opening": n % 5, "teacher": 0.9, "complete": 0.8,
                "category": "exam_tip", "raw": {"value": {"type": "score", "score": 2 + n % 3}}}, 0.001

    def draft(text, category, english=None):
        calls["draft"].append(text)
        t = {"title": "Task 2", "description": "d", "cta": "Follow for more"}
        return {"facebook": t, "youtube": t}, 0.001

    monkeypatch.setattr(providers, "jev_score", jev)
    monkeypatch.setattr(providers, "draft_post", draft)
    return src, vtt, calls


def test_good_vtt_waits_for_authorization_then_runs_to_done(env):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    job = db.get_job(jid)
    assert (job["stage"], job["status"], job["transcript_source"]) == ("authorize", "waiting", "local_vtt")
    assert 0 < job["estimate_usd"] < config.CAP_USD and job["source_sha256"] == "sha-fake"
    assert calls["jev"] == [] and ledger.calls(jid) == []

    pipeline.authorize(jid)
    job = db.get_job(jid)
    assert (job["stage"], job["status"], job["error"]) == ("review", "done", None)
    cands = db.candidates(jid)
    short = [c for c in cands if c["shortlisted"]]
    assert cands and all(60 <= c["end"] - c["start"] <= 90 for c in cands)
    assert 0 < len(short) <= 10 and sorted(c["rank"] for c in short) == list(range(1, len(short) + 1))
    assert len(calls["jev"]) == len(cands) and len(calls["draft"]) == len(short)
    rv = db.review(short[0]["id"])
    assert rv["layout"] == {"mode": "full"} and rv["captions"] and rv["drafts"]["youtube"]["cta"]
    assert rv["captions"][0]["start"] == 0.0
    assert ledger.spent(jid) == pytest.approx(0.001 * (len(cands) + len(short)))


def test_budget_stop_pauses_and_keeps_partial_work(env, monkeypatch):
    src, vtt, calls = env
    monkeypatch.setattr(providers, "jev_score", lambda t, o=None: (calls["jev"].append(t) or
                                                                   {"value": 3, "clarity": 3, "opening": 3, "teacher": 1,
                                                                    "complete": 1, "category": "other", "raw": {}}, 0.4))
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    job = db.get_job(jid)
    assert job["status"] == "paused" and "Budget stop" in job["error"]
    scored = [c for c in db.candidates(jid) if c["score"] is not None]
    assert len(scored) == 3 == len(calls["jev"])  # 3 x 0.40; a 4th would cross 1.50
    assert ledger.spent(jid) <= config.CAP_USD


def test_draft_provider_error_does_not_fail_job(env, monkeypatch):
    src, vtt, _ = env

    def boom(text, category, english=None):
        raise ledger.ProviderError("OPENROUTER_API_KEY not set")

    monkeypatch.setattr(providers, "draft_post", boom)
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    assert db.get_job(jid)["status"] == "done"
    short = [c for c in db.candidates(jid) if c["shortlisted"]]
    assert all(db.review(c["id"])["drafts"] == {"error": "OPENROUTER_API_KEY not set"} for c in short)


def test_resume_after_restart_never_recalls_done_work(env, monkeypatch):
    src, vtt, calls = env
    real = providers.jev_score

    def crash_on_third(text, original=None):
        if len(calls["jev"]) == 2:
            calls["jev"].append(text)
            raise Crash()
        return real(text, original)

    monkeypatch.setattr(providers, "jev_score", crash_on_third)
    jid = pipeline.start_job(src, vtt)
    with pytest.raises(Crash):
        pipeline.authorize(jid)
    assert db.get_job(jid)["status"] == "running"

    monkeypatch.setattr(providers, "jev_score", real)
    pipeline.on_start()  # restart: the sent call becomes indeterminate and the job pauses on it
    job = db.get_job(jid)
    assert job["status"] == "paused" and "may have been sent" in job["error"]
    stuck = [c for c in ledger.calls(jid) if c["state"] == "indeterminate"]
    assert len(stuck) == 1 and len(calls["jev"]) == 3

    ledger.resolve(stuck[0]["id"])  # operator chooses retry
    pipeline.resume(jid)
    assert db.get_job(jid)["status"] == "done"
    n = len(db.candidates(jid))
    assert len(calls["jev"]) == n + 1  # only the uncertain call was repeated
    assert len(set(calls["jev"][:2]) & set(calls["jev"][3:])) == 0


def test_missing_vtt_uses_authorized_whisper_with_absolute_times(env, monkeypatch, tmp_path):
    src, _, calls = env
    chunk = {"segments": [{"start": i * 5.0, "end": i * 5 + 5.0, "text": f"{SENTENCE} {i}"} for i in range(30)],
             "duration": 150.0}
    monkeypatch.setattr(media, "audio_chunks", lambda p, out, speech: [(tmp_path / "a0.mp3", 0.0),
                                                                        (tmp_path / "a1.mp3", 150.0)])
    monkeypatch.setattr(providers, "transcribe", lambda p: (calls["stt"].append(p) or dict(chunk, model="openai/whisper-large-v3"), 0.015))
    jid = pipeline.start_job(src, None)
    job = db.get_job(jid)
    assert job["status"] == "waiting" and job["estimate_usd"] >= DUR / 60 * config.STT_USD_PER_MIN
    pipeline.authorize(jid)
    job = db.get_job(jid)
    assert job["status"] == "done" and job["transcript_source"] == "openai/whisper-large-v3"
    assert len(calls["stt"]) == 2
    assert max(c["end"] for c in db.candidates(jid)) > 150  # second chunk offsets were applied


def test_export_packages_only_approved(env):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    short = sorted((c for c in db.candidates(jid) if c["shortlisted"]), key=lambda c: c["rank"])
    pipeline.render_preview(short[0]["id"])
    db.update_review(short[0]["id"], status="approved", tags=["writing"])
    db.update_review(short[1]["id"], status="rejected")
    db.update_review(short[2]["id"], status="approved")  # approved without a current preview: skipped, reported
    root = pipeline.export(jid)
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    assert [i["candidate_id"] for i in index] == [short[0]["id"]]
    skipped = json.loads((root / "skipped.json").read_text(encoding="utf-8"))
    assert [s["candidate_id"] for s in skipped] == [short[2]["id"]]
    folder = root / index[0]["folder"]
    post = json.loads((folder / "post.json").read_text(encoding="utf-8"))
    assert post["source_sha256"] == "sha-fake" and post["tags"] == ["writing"] and post["problems"] == []
    assert all((folder / f).exists() for f in ("portrait.mp4", "landscape.mp4", "thumbnail.jpg"))
    assert calls["render"][-1][6].name == "landscape.mp4"
    assert (folder / "captions.srt").read_text(encoding="utf-8").startswith("1\n00:00:00,000 --> ")


def test_failed_export_keeps_previous_package(env, monkeypatch):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    cid = next(c["id"] for c in db.candidates(jid) if c["rank"] == 1)
    pipeline.render_preview(cid)
    db.update_review(cid, status="approved")
    root = pipeline.export(jid)
    monkeypatch.setattr(media, "thumbnail", lambda *a: (_ for _ in ()).throw(RuntimeError("disk full")))
    with pytest.raises(RuntimeError):
        pipeline.export(jid)
    assert json.loads((root / "index.json").read_text(encoding="utf-8"))[0]["candidate_id"] == cid


def test_prepare_pre_generates_every_contact_sheet_still(env):
    """The class page's thumbnails exist before any page request, named exactly as the frame endpoint serves them."""
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    frames = pipeline.job_dir(jid) / "frames"
    cands = db.candidates(jid)
    assert len(list(frames.glob("*.jpg"))) == len(cands)  # every candidate, not only the shortlist
    assert all((frames / f"{c['id']}-{c['start']:.1f}.jpg").stat().st_size > 0 for c in cands)


def test_redo_clears_stale_contact_sheet_stills(env):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    frames = pipeline.job_dir(jid) / "frames"
    assert list(frames.glob("*.jpg"))
    pipeline.redo(jid)  # new candidates get new starts: the old stills must not survive
    assert not frames.exists()


def test_prepare_leaves_in_flight_web_draft_alone(env):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    db.update_job(jid, authorized_usd=config.CAP_USD)
    pipeline._candidates(jid)
    pipeline._score(jid)
    top = next(c for c in db.candidates(jid) if c["rank"] == 1)
    db.x("INSERT INTO paid_calls(job_id, key, kind, state, est_usd, created, updated) "
         "VALUES (?, ?, 'draft', 'sent', 0.002, 0, 0)", jid, f"draft:{top['id']}")
    pipeline._prepare(jid)  # would raise Indeterminate on the shared key without the skip
    assert db.review(top["id"])["drafts"] is None


def test_draft_never_overwrites_operator_text(env, monkeypatch):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    db.update_job(jid, authorized_usd=config.CAP_USD)
    pipeline._candidates(jid)
    cid = db.candidates(jid)[0]["id"]
    typed = {"facebook": {"title": "mine", "description": "", "cta": ""}, "youtube": {}}

    def slow_draft(text, category, english=None):  # the operator saves while the paid call is out
        db.update_review(cid, drafts=typed)
        return {"facebook": {"title": "model", "description": "d", "cta": "c"}, "youtube": {}}, 0.001

    monkeypatch.setattr(providers, "draft_post", slow_draft)
    db.review(cid)
    pipeline.draft(cid)
    assert db.review(cid)["drafts"] == typed


def test_ensure_review_fills_category_after_scoring(env):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    db.update_job(jid, authorized_usd=config.CAP_USD)
    pipeline._candidates(jid)
    cid = db.candidates(jid)[0]["id"]
    assert pipeline.ensure_review(cid)["category"] is None  # opened before scoring
    pipeline._score(jid)
    assert pipeline.ensure_review(cid)["category"] == "exam_tip"


def test_state_hash_treats_missing_title_as_empty():
    rv = {"start": 1, "end": 2, "layout": {"mode": "full"}, "captions": [], "title": None}
    assert pipeline.state_hash(rv) == pipeline.state_hash({**rv, "title": ""})


def test_silent_recording_stops_before_any_paid_call(env, monkeypatch):
    src, vtt, calls = env
    monkeypatch.setattr(media, "speech_intervals", lambda p: [(DUR - 4, DUR)])  # a few seconds of noise
    jid = pipeline.start_job(src)
    job = db.get_job(jid)
    assert job["status"] == "failed" and "silent" in job["error"] and job["authorized_usd"] is None
    assert not ledger.calls(jid)


def test_check_audible_threshold():
    pipeline.check_audible([(0, 10)], 20)  # a short clip that is half speech is fine
    with pytest.raises(ValueError):
        pipeline.check_audible([(0, 4)], 2212)


def test_zoom_audio_replaces_video_audio_everywhere(env, monkeypatch, tmp_path):
    src, vtt, calls = env
    zoom = tmp_path / "audio1803441616.m4a"
    zoom.write_bytes(b"m4a")
    video_only = {"duration": DUR, "width": 1920, "height": 1080, "vcodec": "h264", "acodec": None,
                  "v_start": 0, "a_start": 0, "has_audio": False}
    monkeypatch.setattr(media, "probe", lambda p: {**video_only, "has_audio": True, "acodec": "aac"} if str(p).endswith("m4a") else video_only)
    monkeypatch.setattr(media, "sync_offset", lambda v, a: (1.25, "sound"))
    muxed = []
    monkeypatch.setattr(media, "mux_audio", lambda v, a, off, out: (muxed.append((a.name, off)), shutil.copyfile(v, out)))
    heard = []
    monkeypatch.setattr(media, "speech_intervals", lambda p: (heard.append(p.name), [(0.0, DUR)])[1])
    jid = pipeline.start_job(src, vtt, zoom)  # a video with no audio track is fine when the Zoom audio comes with it
    pipeline.authorize(jid)
    job = db.get_job(jid)
    assert job["status"] == "done", job["error"]
    assert muxed == [("zoom.m4a", 1.25)] and job["audio_offset"] == 1.25
    assert any(f.startswith("Zoom audio lined up by matching sound") for f in job["flags"])
    assert heard == ["media.mp4"] and pipeline.media_path(jid).name == "media.mp4"
    cid = next(c["id"] for c in db.candidates(jid) if c["rank"] == 1)
    pipeline.render_preview(cid)
    assert calls["render"][-1][0].name == "media.mp4"  # clips carry the Zoom sound


def test_zoom_audio_from_another_class_is_refused(env, monkeypatch, tmp_path):
    src, vtt, calls = env
    zoom = tmp_path / "other.m4a"
    zoom.write_bytes(b"m4a")
    real = media.probe
    monkeypatch.setattr(media, "probe", lambda p: {**real(p), "duration": 30.0} if str(p).endswith("m4a") else real(p))
    monkeypatch.setattr(media, "sync_offset", lambda v, a: (0.0, "none"))
    jid = pipeline.start_job(src, vtt, zoom)
    job = db.get_job(jid)
    assert job["status"] == "failed" and "covers only" in job["error"] and not ledger.calls(jid)


def test_ai_draft_fills_an_empty_on_video_title(env):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    top = next(c for c in db.candidates(jid) if c["rank"] == 1)
    assert db.review(top["id"])["title"] == "Task 2"


def test_bangla_lines_get_an_english_translation_that_jev_reads(env, monkeypatch):
    src, vtt, calls = env
    bn = "আজকে আমরা Task 2 নিয়ে কথা বলব"
    vtt.write_text(vtt_text().replace("Rimon Ahmed: In Task 2", f"Rimon Ahmed: {bn} In Task 2", 30), encoding="utf-8")
    sent = []
    monkeypatch.setattr(providers, "translate", lambda lines: (sent.append(lines), {"en": [f"EN {i}" for i in range(len(lines))]})[1:] + (0.001,))
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    assert db.get_job(jid)["status"] == "done", db.get_job(jid)["error"]
    units = json.loads((pipeline.job_dir(jid) / "transcript.json").read_text(encoding="utf-8"))["units"]
    assert len(sent) == 1 and len(sent[0]) == 30 and all(bn in line for line in sent[0])  # only Bangla lines are paid for
    assert units[0]["en"] == "EN 0" and units[0]["text"].startswith(bn)  # as spoken stays in text
    assert units[40]["en"] == units[40]["text"]  # English lines are their own translation
    assert any(t.startswith("EN ") for t in calls["jev"])  # Jev reads the English


def test_find_clips_again_starts_over_and_asks_for_cost_again(env):
    src, vtt, calls = env
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    cid = next(c["id"] for c in db.candidates(jid) if c["rank"] == 1)
    pipeline.render_preview(cid)
    pipeline.redo(jid)
    job = db.get_job(jid)
    assert (job["stage"], job["status"], job["authorized_usd"]) == ("authorize", "waiting", None)
    assert not db.q("SELECT candidate_id FROM reviews WHERE candidate_id=?", cid) and not db.candidates(jid)
    assert not (pipeline.job_dir(jid) / "previews").exists() and ledger.spent(jid) > 0  # earlier spend still counts


def test_skipped_translation_lines_are_asked_again_then_kept_as_spoken(env, monkeypatch):
    src, vtt, calls = env
    bn = "আজকে আমরা Task 2 নিয়ে কথা বলব"
    vtt.write_text(vtt_text().replace("Rimon Ahmed: In Task 2", f"Rimon Ahmed: {bn} In Task 2", 3), encoding="utf-8")
    asked = []

    def skips_the_last(lines):
        asked.append(len(lines))
        return {"en": [f"EN {n}" for n in range(len(lines) - 1)] + [None]}, 0.001
    monkeypatch.setattr(providers, "translate", skips_the_last)
    jid = pipeline.start_job(src, vtt)
    pipeline.authorize(jid)
    job = db.get_job(jid)
    assert job["status"] == "done", job["error"]
    assert asked == [3, 1]  # the skipped line is asked again once, alone
    units = json.loads((pipeline.job_dir(jid) / "transcript.json").read_text(encoding="utf-8"))["units"]
    assert units[2]["en"] == units[2]["text"] and "1 lines left untranslated" in " ".join(job["flags"])
