"""Web layer: security guards, pages, review round-trip, approve gating, media ranges."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shera import app as web
from shera import config, db, pipeline

BASE = f"http://127.0.0.1:{config.PORT}"


@pytest.fixture
def client(tmp_path):
    config.set_data(tmp_path / "data")
    db.init()
    web.TASKS.clear()
    return TestClient(web.app, base_url=BASE)


def make_job(job_id="j1", status="done", stage="review"):
    db.x("INSERT INTO jobs(id, created, title, source_path, stage, status, progress, duration, flags, "
         "authorized_usd, transcript_source) VALUES (?, ?, 'Writing Task 2', 'x.mp4', ?, ?, 1, 300, '[]', 1.5, 'local_vtt')",
         job_id, time.time(), stage, status)
    d = pipeline.job_dir(job_id)
    d.mkdir(parents=True)
    units = [{"start": i * 5.0, "end": i * 5.0 + 5, "text": f"sentence number {i}", "speaker": None} for i in range(60)]
    (d / "transcript.json").write_text(json.dumps({"source": "local_vtt", "units": units, "flags": []}))
    (d / "source.mp4").write_bytes(bytes(range(256)) * 40)
    cid = db.x('INSERT INTO candidates(job_id, u0, u1, start, "end", text, value, clarity, opening, category, score, '
               "shortlisted, rank) VALUES (?, 2, 8, 10, 45, 'sentence text', 3, 3, 2, 'exam_tip', 0.7, 1, 1)", job_id)
    return job_id, cid


def test_foreign_host_is_rejected(client):
    assert client.get("/", headers={"host": "evil.example:8765"}).status_code == 403
    assert client.get("/").status_code == 200
    assert client.get("/", headers={"host": f"localhost:{config.PORT}"}).status_code == 200


def test_cross_origin_post_is_rejected(client):
    r = client.post("/import", data={"mp4": "x.mp4"}, headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    r = client.post("/import", data={"mp4": "x.mp4"}, headers={"referer": "http://evil.example/page"})
    assert r.status_code == 403
    r = client.post("/import", data={"mp4": "x.mp4"}, headers={"origin": BASE})
    assert r.status_code == 400  # passed the guard; failed validation


def test_home_shows_key_status_without_leaking_value(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-SECRET-123456")
    html = client.get("/").text
    assert "sk-or-SECRET-123456" not in html
    assert "Finish setup" not in html and "OpenAI" not in html
    monkeypatch.delenv("OPENROUTER_API_KEY")
    html = client.get("/").text
    assert "<strong>OpenRouter key</strong> is missing" in html and "OPENROUTER_API_KEY</span> to <span class=\"mono\">.env" in html


def test_import_validation_errors(client, tmp_path):
    assert "Enter the path" in client.post("/import", data={"mp4": ""}).text
    r = client.post("/import", data={"mp4": str(tmp_path / "class.mov")})
    assert r.status_code == 400 and "must be a .mp4 file" in r.text
    r = client.post("/import", data={"mp4": str(tmp_path / "missing.mp4")})
    assert r.status_code == 400 and "not found" in r.text
    mp4 = tmp_path / "c.mp4"
    mp4.write_bytes(b"x")
    r = client.post("/import", data={"mp4": str(mp4), "vtt": str(tmp_path / "c.srt")})
    assert r.status_code == 400 and "must be a .vtt file" in r.text


def test_browse_lists_folders_and_mp4_only(client, tmp_path):
    root = tmp_path / "classes"
    (root / "sub").mkdir(parents=True)
    (root / "a.mp4").write_bytes(b"x")
    (root / "notes.txt").write_bytes(b"x")
    data = client.get("/browse", params={"path": str(root)}).json()
    assert data["path"] == str(root) and data["parent"] == str(tmp_path)
    assert [f["name"] for f in data["files"]] == ["a.mp4"]  # non-MP4 files are not offered
    assert [d["name"] for d in data["dirs"]] == ["sub"]


def test_browse_defaults_to_starting_places(client):
    config.INBOX.mkdir(parents=True, exist_ok=True)
    data = client.get("/browse").json()
    assert data["path"] == "" and data["parent"] is None and data["files"] == []
    assert any(d["name"] == "Inbox" for d in data["dirs"])


def test_browse_missing_path_404_and_guard_still_applies(client, tmp_path):
    assert client.get("/browse", params={"path": str(tmp_path / "nope")}).status_code == 404
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    assert client.get("/browse", params={"path": str(f)}).status_code == 404  # a file is not a folder
    assert client.get("/browse", headers={"host": "evil.example:8765"}).status_code == 403


def test_job_page_renders_shortlist_and_waiting_state(client):
    job_id, cid = make_job()
    html = client.get(f"/jobs/{job_id}").text
    assert "Writing Task 2" in html and f"/clips/{cid}" in html and "Exam tip" in html
    make_job("j2", status="waiting", stage="authorize")
    db.update_job("j2", authorized_usd=None, estimate_usd=0.1)
    html = client.get("/jobs/j2").text
    assert "Approve up to $1.50 and continue" in html


def test_empty_shortlist_state(client):
    job_id, cid = make_job()
    db.x("UPDATE candidates SET shortlisted=0, rank=NULL")
    html = client.get(f"/jobs/{job_id}").text
    assert "No postable moments in this class" in html and "Other moments (1)" in html


def test_review_save_round_trip_persists(client):
    job_id, cid = make_job()
    assert client.get(f"/jobs/{job_id}/clips/{cid}").status_code == 200
    body = {"start": 12.5, "end": 44, "title": "Answer the exact question", "category": "common_mistake",
            "tags": "Writing, Task 2", "layout": {"mode": "crop", "crop": [0, 0, 0.75, 1], "inset": None},
            "captions": [{"start": 3, "end": 5, "text": "প্রশ্নটা ঠিকমতো পড়ো"}],
            "drafts": {"facebook": {"title": "t", "description": "d", "cta": "c"}, "youtube": {}}}
    assert client.post(f"/jobs/{job_id}/clips/{cid}", json=body).status_code == 200
    rv = db.review(cid)
    assert (rv["start"], rv["end"], rv["category"], rv["tags"]) == (12.5, 44, "common_mistake", ["Writing", "Task 2"])
    assert rv["layout"]["crop"] == [0, 0, 0.75, 1] and rv["captions"][0]["text"] == "প্রশ্নটা ঠিকমতো পড়ো"
    assert (rv["captions"][0]["start"], rv["captions"][0]["end"]) == (0.5, 2.5)  # re-timed to the new start
    assert rv["drafts"]["facebook"]["title"] == "t"
    bad = client.post(f"/jobs/{job_id}/clips/{cid}", json={"layout": {"mode": "crop", "crop": [0.5, 0, 0.8, 1]}})
    assert bad.status_code == 422


def test_approve_requires_preview_of_current_state(client, monkeypatch):
    job_id, cid = make_job()
    url = f"/jobs/{job_id}/clips/{cid}"
    client.get(url)
    assert client.post(url + "/decision", json={"decision": "approve"}).status_code == 409
    monkeypatch.setattr(pipeline.media, "render", lambda *a, **k: a[6].write_bytes(b"mp4"))
    pipeline.render_preview(cid)
    r = client.post(url + "/decision", json={"decision": "approve"})
    assert r.status_code == 200 and db.review(cid)["status"] == "approved"
    client.post(url, json={"title": "changed"})  # an edit after approval invalidates preview and approval
    assert db.review(cid)["status"] == "pending"
    assert client.post(url + "/decision", json={"decision": "approve"}).status_code == 409


def test_media_range_request_returns_206_and_stays_in_data(client):
    job_id, _ = make_job()
    r = client.get(f"/media/jobs/{job_id}/source.mp4", headers={"range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    assert client.get("/media/../pyproject.toml").status_code == 404
    assert client.get("/media/%2e%2e/%2e%2e/pyproject.toml").status_code == 404


def test_peaks_endpoint_serves_the_cache_and_404s_cleanly(client):
    job_id, _ = make_job()
    r = client.get(f"/jobs/{job_id}/peaks.json")
    assert r.status_code == 404 and "waveform" in r.json()["detail"]  # the review page hides the strip
    (pipeline.job_dir(job_id) / "peaks.json").write_text(json.dumps([0, 100, 32768]), encoding="utf-8")
    r = client.get(f"/jobs/{job_id}/peaks.json")
    assert r.status_code == 200 and r.json() == [0, 100, 32768]
    assert client.get("/jobs/nope/peaks.json").status_code == 404
    assert client.get("/jobs/../peaks.json").status_code == 404  # only real job ids reach the folder


def test_waveform_strip_is_reachable_and_usable_from_the_keyboard(client):
    """The strip seeks, so it must be focusable and labelled as a control, not a picture."""
    job_id, cid = make_job()
    r = client.get(f"/jobs/{job_id}/clips/{cid}")
    assert 'id="waveform"' in r.text
    assert 'role="slider"' in r.text      # it is an interactive control
    assert 'tabindex="0"' in r.text       # so it can actually take focus
    assert "aria-valuetext" in r.text     # the position is announced, not only drawn
    assert "aria-label" in r.text
    assert 'role="img"' not in r.text     # a seek control is not a static image
    js = (Path(web.HERE) / "static" / "review.js").read_text(encoding="utf-8")
    assert 'wave.addEventListener("keydown"' in js  # arrows/PageUp/Home/End move the playhead
    assert "#waveform" in js              # J/K must not fire while the strip has focus


def test_indeterminate_call_retry_resolves_then_resumes(client, monkeypatch):
    job_id, _ = make_job(status="paused", stage="score")
    call_id = db.x("INSERT INTO paid_calls(job_id, key, kind, state, est_usd, created, updated) "
                   "VALUES (?, 'jev:1', 'jev', 'indeterminate', 0.002, 0, 0)", job_id)
    assert "Retry (may charge again)" in client.get(f"/jobs/{job_id}").text
    resumed = []
    monkeypatch.setattr(pipeline, "resume", resumed.append)
    client.post(f"/jobs/{job_id}/calls/{call_id}/retry")
    assert db.one("SELECT state FROM paid_calls WHERE id=?", call_id)["state"] == "abandoned"
    assert resumed == [job_id]


def _approved_with_preview(cid, monkeypatch):
    monkeypatch.setattr(pipeline.media, "render", lambda *a, **k: a[6].write_bytes(b"mp4"))
    pipeline.render_preview(cid)
    db.update_review(cid, status="approved")


def test_caption_rebuild_withdraws_approval(client, monkeypatch):
    job_id, cid = make_job()
    client.get(f"/jobs/{job_id}/clips/{cid}")
    db.update_review(cid, captions=[{"start": 0, "end": 1, "text": "edited"}])
    _approved_with_preview(cid, monkeypatch)
    client.post(f"/jobs/{job_id}/clips/{cid}/captions/reset")
    assert db.review(cid)["status"] == "pending"


def test_saves_without_draft_edits_keep_paid_drafts(client):
    job_id, cid = make_job()
    client.get(f"/jobs/{job_id}/clips/{cid}")
    paid = {"facebook": {"title": "paid", "description": "d", "cta": "c"}, "youtube": {"title": "y"}}
    db.update_review(cid, drafts=paid)
    client.post(f"/jobs/{job_id}/clips/{cid}", json={"title": "x"})
    empty = {p: {"title": "", "description": "", "cta": ""} for p in ("facebook", "youtube")}
    client.post(f"/jobs/{job_id}/clips/{cid}", json={"drafts": empty})  # a stale page
    assert db.review(cid)["drafts"] == paid


def test_posting_text_save_keeps_approval_of_untitled_clip(client, monkeypatch):
    job_id, cid = make_job()
    client.get(f"/jobs/{job_id}/clips/{cid}")
    assert db.review(cid)["title"] is None
    _approved_with_preview(cid, monkeypatch)
    rv = db.review(cid)
    body = {"start": rv["start"], "end": rv["end"], "title": "", "layout": rv["layout"], "captions": rv["captions"],
            "drafts": {"facebook": {"title": "t"}, "youtube": {}}}
    client.post(f"/jobs/{job_id}/clips/{cid}", json=body)
    assert db.review(cid)["status"] == "approved"


def test_moving_start_retimes_captions(client):
    job_id, cid = make_job()  # review span 10..45
    client.get(f"/jobs/{job_id}/clips/{cid}")
    caps = [{"start": 0, "end": 2, "text": "a"}, {"start": 3, "end": 6, "text": "b"}, {"start": 33, "end": 35, "text": "c"}]
    r = client.post(f"/jobs/{job_id}/clips/{cid}", json={"start": 14, "end": 40, "captions": caps}).json()
    # shift by -4 into a 26 s clip: "a" ends before the new start, "b" is clamped to 0..2, "c" starts after the end
    assert [c["text"] for c in r["captions"]] == ["b"]
    assert r["captions"][0]["start"] == 0 and r["captions"][0]["end"] == 2
    assert db.review(cid)["captions"] == r["captions"]


def test_orphan_sent_call_shows_and_draft_refused_while_preparing(client):
    job_id, cid = make_job(status="paused", stage="prepare")
    db.x("INSERT INTO paid_calls(job_id, key, kind, state, est_usd, created, updated) "
         "VALUES (?, 'draft:99', 'draft', 'sent', 0.002, 0, 0)", job_id)
    html = client.get(f"/jobs/{job_id}").text
    assert "without an answer being saved" in html and "draft:99" in html
    db.update_job(job_id, status="running")
    assert client.post(f"/jobs/{job_id}/clips/{cid}/draft").status_code == 409
    assert "disabled" in client.get(f"/jobs/{job_id}/clips/{cid}").text.split('id="draft-run"')[1][:20]


def test_unscored_category_shows_choose_option(client):
    job_id, cid = make_job()
    db.x("UPDATE candidates SET category=NULL, score=NULL")
    html = client.get(f"/jobs/{job_id}/clips/{cid}").text
    assert '<option value="" selected>Choose…</option>' in html
    client.post(f"/jobs/{job_id}/clips/{cid}", json={"category": "", "title": "t"})
    assert db.review(cid)["category"] is None


def test_clip_list_and_bench_explain_why_each_clip_was_picked(client):
    job_id, cid = make_job()
    db.x('INSERT INTO candidates(job_id, u0, u1, start, "end", text, value, clarity, opening, category, score, '
         "shortlisted, rank) VALUES (?, 3, 9, 20, 50, 'Overlapping moment. More.', 3, 1, 2, 'vocabulary', 0.5, 0, NULL)", job_id)
    html = client.get(f"/jobs/{job_id}").text
    assert "Exam tip · a clear teaching point · mostly stands alone · plain start" in html
    assert "Left out: leans on earlier context" in html
    review = client.get(f"/jobs/{job_id}/clips/{cid}").text
    assert "Why the AI picked it" in review and "Clear value: a specific, correct, useful teaching point." in review
    assert "Check before approving" in review and "Scores (0–4)" not in review


def test_import_takes_zoom_audio_and_browse_lists_by_type(client, tmp_path, monkeypatch):
    mp4, m4a = tmp_path / "class.mp4", tmp_path / "audio1.m4a"
    mp4.write_bytes(b"x")
    m4a.write_bytes(b"x")
    started = []
    monkeypatch.setattr(pipeline, "start_job", lambda *a: started.append(a) or "j9")
    r = client.post("/import", data={"mp4": str(mp4), "m4a": str(tmp_path / "nope.m4a")})
    assert r.status_code == 400 and "Zoom audio not found" in r.text
    r = client.post("/import", data={"mp4": str(mp4), "m4a": str(m4a)}, follow_redirects=False)
    assert r.status_code == 303 and started == [(mp4, None, m4a)]
    names = [f["name"] for f in client.get("/browse", params={"path": str(tmp_path), "ext": ".m4a"}).json()["files"]]
    assert names == ["audio1.m4a"]
    assert client.get("/browse", params={"path": str(tmp_path), "ext": ".exe"}).status_code == 422


def test_static_revalidates_on_every_request(client):
    r = client.get("/static/app.css")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"  # upgrades show on the next reload, not after a heuristic-cache delay


def _posting_record(cid):
    pipeline.ensure_review(cid)  # make_job leaves the review row for the pipeline to create
    return db.one("SELECT posted FROM reviews WHERE candidate_id=?", cid)["posted"] or {}


def test_posting_record_stores_links_and_allows_blanks(client):
    """Story 34/D12: a real link is kept, and leaving one empty is normal, not an error."""
    job_id, cid = make_job()
    r = client.post(f"/jobs/{job_id}/clips/{cid}/posted", data={
        "facebook_url": "https://facebook.com/rimonsielts/posts/123", "youtube_url": "",
        "notes": "reached 4k"}, follow_redirects=False)
    assert r.status_code == 303
    assert _posting_record(cid) == {"facebook_url": "https://facebook.com/rimonsielts/posts/123",
                                    "youtube_url": "", "notes": "reached 4k"}


def test_posting_record_unwraps_a_link_pasted_inside_shared_text(client):
    job_id, cid = make_job()
    client.post(f"/jobs/{job_id}/clips/{cid}/posted", data={
        "facebook_url": "Check this out! https://facebook.com/rimonsielts/posts/9", "notes": ""})
    assert _posting_record(cid)["facebook_url"] == "https://facebook.com/rimonsielts/posts/9"


def test_posting_record_refuses_a_link_that_is_not_a_web_address(client):
    """A typo must not be stored as if it were a real post; the page explains and keeps the record."""
    job_id, cid = make_job()
    r = client.post(f"/jobs/{job_id}/clips/{cid}/posted", data={"facebook_url": "not a url at all", "notes": ""})
    assert r.status_code == 200
    assert "not a web address" in r.text
    assert _posting_record(cid) == {}   # nothing half-saved


def test_posting_record_refuses_a_non_http_scheme(client):
    job_id, cid = make_job()
    r = client.post(f"/jobs/{job_id}/clips/{cid}/posted", data={"youtube_url": "javascript:alert(1)"})
    assert "not a web address" in r.text
    assert _posting_record(cid) == {}


def test_posting_record_refuses_a_link_broken_by_a_space(client):
    """A pasted address with a stray space must not be silently cut into a different, valid host."""
    job_id, cid = make_job()
    r = client.post(f"/jobs/{job_id}/clips/{cid}/posted", data={"youtube_url": "http://exa mple.com"})
    assert "space in it" in r.text
    assert _posting_record(cid) == {}


def test_a_bad_second_link_does_not_wipe_the_saved_first(client):
    job_id, cid = make_job()
    client.post(f"/jobs/{job_id}/clips/{cid}/posted", data={"facebook_url": "https://facebook.com/x/posts/1"})
    r = client.post(f"/jobs/{job_id}/clips/{cid}/posted", data={
        "facebook_url": "https://facebook.com/x/posts/1", "youtube_url": "nope", "notes": "later"})
    assert "not a web address" in r.text
    kept = _posting_record(cid)
    assert kept["facebook_url"] == "https://facebook.com/x/posts/1"  # the good link survived the typo
