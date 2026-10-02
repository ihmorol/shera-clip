"""Zoom cloud-recording import (phase 2, D15) against a fake Zoom: token, listing, download, job, pages."""
import base64
import hashlib
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from shera import app as web
from shera import config, db, media, pipeline, zoom

BASE = f"http://127.0.0.1:{config.PORT}"
UUID = "/ab//cd=="  # starts with / and contains //: Zoom requires double encoding
VIDEO = b"v" * 5000


def rec(fid, file_type, recording_type, size, status="completed"):
    return {"id": fid, "file_type": file_type, "recording_type": recording_type, "file_size": size,
            "status": status, "download_url": f"https://zoom.us/rec/download/{fid}"}


MEETING = {"uuid": UUID, "id": 111, "topic": "IELTS Writing", "start_time": "2026-09-20T10:00:00Z", "duration": 150,
           "recording_files": [rec("g", "MP4", "gallery_view", 4000), rec("s", "MP4", "shared_screen_with_speaker_view", 5000),
                               rec("a", "M4A", "audio_only", 3), rec("t", "TRANSCRIPT", "audio_transcript", 7),
                               rec("c", "CHAT", "chat_file", 2)]}


class FakeZoom:
    """Serves the token, list, meeting and download endpoints; records what arrived."""

    def __init__(self):
        self.seen, self.tokens, self.reject, self.body = [], 0, 0, {"s": VIDEO, "g": b"g" * 4000, "a": b"m4a", "t": b"WEBVTT\n"}

    def __call__(self, req):
        self.seen.append(req)
        url, auth = req.url, req.headers.get("authorization", "")
        if url.host == "zoom.us" and url.path == "/oauth/token":
            self.tokens += 1
            return httpx.Response(200, json={"access_token": f"tok{self.tokens}", "expires_in": 3600})
        if url.host == "cdn.example":  # the signed redirect target: must never receive the Zoom token
            assert "authorization" not in req.headers
            return httpx.Response(200, content=self.body[url.path.rsplit("/", 1)[1]])
        if self.reject:
            self.reject -= 1
            return httpx.Response(401, json={"code": 124, "message": "Invalid access token."})
        assert auth.startswith("Bearer tok")
        if url.path.startswith("/rec/download/"):
            return httpx.Response(302, headers={"location": f"https://cdn.example/f/{url.path.rsplit('/', 1)[1]}"})
        if url.path == "/v2/users/teacher@example.com/recordings":
            if url.params.get("next_page_token") != "p2":
                return httpx.Response(200, json={"meetings": [MEETING], "next_page_token": "p2"})
            older = {**MEETING, "uuid": "u2", "start_time": "2026-09-10T10:00:00Z",
                     "recording_files": [rec("x", "MP4", "active_speaker", 9, status="processing")]}
            return httpx.Response(200, json={"meetings": [older], "next_page_token": ""})
        if url.raw_path.decode() == "/v2/meetings/%252Fab%252F%252Fcd%253D%253D/recordings":
            return httpx.Response(200, json=MEETING)
        return httpx.Response(404, json={"code": 3301, "message": "This recording does not exist."})


@pytest.fixture
def fake(monkeypatch):
    for k, v in {"ZOOM_ACCOUNT_ID": "acc", "ZOOM_CLIENT_ID": "cid", "ZOOM_CLIENT_SECRET": "sec",
                 "ZOOM_USER": "teacher@example.com"}.items():
        monkeypatch.setenv(k, v)
    f = FakeZoom()
    monkeypatch.setattr(zoom, "TRANSPORT", httpx.MockTransport(f))
    monkeypatch.setattr(zoom, "_token_cache", {})
    return f


def test_account_token_is_requested_once_and_used_as_bearer(fake):
    zoom.meeting(UUID)
    zoom.meeting(UUID)
    tok = fake.seen[0]
    assert tok.method == "POST" and tok.url.params["grant_type"] == "account_credentials"
    assert tok.url.params["account_id"] == "acc"
    assert tok.headers["authorization"] == "Basic " + base64.b64encode(b"cid:sec").decode()
    assert fake.tokens == 1 and fake.seen[-1].headers["authorization"] == "Bearer tok1"


def test_expired_token_is_refreshed_once_then_lost_authorization_is_explained(fake):
    fake.reject = 1
    assert zoom.meeting(UUID)["topic"] == "IELTS Writing" and fake.tokens == 2
    fake.reject = 2
    with pytest.raises(zoom.ZoomError, match="authorization"):
        zoom.meeting(UUID)


def test_bad_credentials_give_an_actionable_error(fake, monkeypatch):
    monkeypatch.setattr(zoom, "TRANSPORT", httpx.MockTransport(
        lambda r: httpx.Response(400, json={"reason": "Invalid client_id or client_secret", "error": "invalid_client"})))
    with pytest.raises(zoom.ZoomError, match="Invalid client_id or client_secret.*ZOOM_CLIENT_SECRET"):
        zoom.meeting(UUID)


def test_unconfigured_is_reported_without_network(monkeypatch):
    for k in ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER"):
        monkeypatch.delenv(k, raising=False)
    assert not zoom.configured()
    with pytest.raises(zoom.ZoomError, match="ZOOM_ACCOUNT_ID"):
        zoom.recordings(date(2026, 9, 27))


def test_listing_pages_through_a_month_and_prefers_screen_with_speaker(fake):
    start, occ = zoom.recordings(date(2026, 9, 27))
    lists = [r for r in fake.seen if r.url.path.endswith("/recordings") and "users" in r.url.path]
    assert start == date(2026, 8, 28) and lists[0].url.params["from"] == "2026-08-28"
    assert lists[0].url.params["to"] == "2026-09-27" and len(lists) == 2
    first, older = occ  # newest first
    assert first["uuid"] == UUID and first["minutes"] == 150
    assert [v["id"] for v in first["videos"]] == ["s", "g"] and first["vtt"]["id"] == "t" and first["m4a"]["id"] == "a"
    assert older["videos"] == [] and older["processing"] == 1


def test_download_follows_redirect_without_leaking_token_and_verifies_size(fake, tmp_path):
    sha, n = zoom.download(UUID, "s", tmp_path / "source.mp4")
    assert (tmp_path / "source.mp4").read_bytes() == VIDEO
    assert n == 5000 and sha == hashlib.sha256(VIDEO).hexdigest()
    fake.body["s"] = VIDEO[:100]  # connection dropped early
    with pytest.raises(zoom.ZoomError, match="incomplete: 100 of 5000"):
        zoom.download(UUID, "s", tmp_path / "again.mp4")
    assert not (tmp_path / "again.mp4").exists() and not (tmp_path / "again.mp4.part").exists()
    with pytest.raises(zoom.ZoomError, match="no longer"):
        zoom.download(UUID, "gone", tmp_path / "x.mp4")


# ---------- job ----------

def test_zoom_job_downloads_selected_files_into_the_job(fake, tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    monkeypatch.setattr(pipeline, "_spawn", lambda jid: None)
    monkeypatch.setattr(media, "probe", lambda p: {"duration": 9000.0, "width": 1920, "height": 1080,
                                                   "vcodec": "h264", "has_audio": True})
    jid = pipeline.start_zoom_job(UUID, "IELTS Writing · 20 Sep 2026", "s", vtt="t")
    pipeline._import(jid)
    job, d = db.get_job(jid), pipeline.job_dir(jid)
    assert job["zoom"] == {"uuid": UUID, "mp4": "s", "vtt": "t", "m4a": None}
    assert (d / "source.mp4").read_bytes() == VIDEO and (d / "source.vtt").read_bytes() == b"WEBVTT\n"
    assert job["source_sha256"] == hashlib.sha256(VIDEO).hexdigest() and job["source_bytes"] == 5000
    assert job["vtt_path"] == str(d / "source.vtt") and job["audio_path"] is None and job["duration"] == 9000.0
    n = len(fake.seen)
    pipeline._import(jid)  # resuming never downloads finished files again
    assert len(fake.seen) == n


# ---------- pages ----------

@pytest.fixture
def client(tmp_path):
    config.set_data(tmp_path / "data")
    db.init()
    return TestClient(web.app, base_url=BASE)


def test_zoom_page_explains_setup_when_unconfigured(client, monkeypatch):
    monkeypatch.setattr(zoom, "configured", lambda: False)
    r = client.get("/zoom")
    assert r.status_code == 200 and "ZOOM_CLIENT_SECRET" in r.text and "docs/zoom-setup.md" in r.text


def test_zoom_page_lists_occurrences_and_shows_errors(client, fake):
    r = client.get("/zoom", params={"to": "2026-09-27"})
    assert "IELTS Writing" in r.text and "Shared screen with speaker" in r.text and "still processing" in r.text
    assert "Needs about 4.9 KB free" in r.text  # the preferred video plus the transcript (5000 + 7); the .m4a is unticked by default
    assert 'href="/zoom?to=2026-08-27"' in r.text  # earlier month
    fake.reject = 5
    assert "authorization" in client.get("/zoom", params={"to": "2026-09-27"}).text


def test_zoom_import_checks_file_ids_against_zoom_then_starts_the_job(client, fake, monkeypatch):
    started = []
    monkeypatch.setattr(pipeline, "start_zoom_job", lambda *a, **k: started.append((a, k)) or "j7")
    r = client.post("/zoom/import", data={"uuid": UUID, "mp4": "a", "vtt": "", "m4a": ""})
    assert r.status_code == 400 and "no longer" in r.text and not started
    r = client.post("/zoom/import", data={"uuid": UUID, "mp4": "g", "vtt": "t", "m4a": "a"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/jobs/j7"
    (uuid, title, mp4), kw = started[0]
    assert uuid == UUID and mp4 == "g" and kw == {"vtt": "t", "m4a": "a"} and title.startswith("IELTS Writing · ")
