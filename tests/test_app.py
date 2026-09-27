"""Web layer: security guards, pages, review round-trip, approve gating, media ranges."""
import json
import time

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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    html = client.get("/").text
    assert "sk-or-SECRET-123456" not in html
    assert "OpenRouter key" in html and "missing" in html and "add to .env" in html


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


def test_job_page_renders_shortlist_and_waiting_state(client):
    job_id, cid = make_job()
    html = client.get(f"/jobs/{job_id}").text
    assert "Writing Task 2" in html and f"/clips/{cid}" in html and "Exam tip" in html
    make_job("j2", status="waiting", stage="authorize")
    db.update_job("j2", authorized_usd=None, estimate_usd=0.1)
    html = client.get("/jobs/j2").text
    assert "Authorize paid work (hard cap $1.50)" in html


def test_empty_shortlist_state(client):
    job_id, cid = make_job()
    db.x("UPDATE candidates SET shortlisted=0, rank=NULL")
    html = client.get(f"/jobs/{job_id}").text
    assert "No strong moments in this class" in html and "Other candidates (1)" in html


def test_review_save_round_trip_persists(client):
    job_id, cid = make_job()
    assert client.get(f"/jobs/{job_id}/clips/{cid}").status_code == 200
    body = {"start": 12.5, "end": 44, "title": "Answer the exact question", "category": "common_mistake",
            "tags": "Writing, Task 2", "layout": {"mode": "crop", "crop": [0, 0, 0.75, 1], "inset": None},
            "captions": [{"start": 0, "end": 2, "text": "প্রশ্নটা ঠিকমতো পড়ো"}],
            "drafts": {"facebook": {"title": "t", "description": "d", "cta": "c"}, "youtube": {}}}
    assert client.post(f"/jobs/{job_id}/clips/{cid}", json=body).status_code == 200
    rv = db.review(cid)
    assert (rv["start"], rv["end"], rv["category"], rv["tags"]) == (12.5, 44, "common_mistake", ["Writing", "Task 2"])
    assert rv["layout"]["crop"] == [0, 0, 0.75, 1] and rv["captions"][0]["text"] == "প্রশ্নটা ঠিকমতো পড়ো"
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


def test_indeterminate_call_retry_resolves_then_resumes(client, monkeypatch):
    job_id, _ = make_job(status="paused", stage="score")
    call_id = db.x("INSERT INTO paid_calls(job_id, key, kind, state, est_usd, created, updated) "
                   "VALUES (?, 'jev:1', 'jev', 'indeterminate', 0.002, 0, 0)", job_id)
    assert "Retry (may bill again)" in client.get(f"/jobs/{job_id}").text
    resumed = []
    monkeypatch.setattr(pipeline, "resume", resumed.append)
    client.post(f"/jobs/{job_id}/calls/{call_id}/retry")
    assert db.one("SELECT state FROM paid_calls WHERE id=?", call_id)["state"] == "abandoned"
    assert resumed == [job_id]
