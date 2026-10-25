import socket
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shera import companion, config, db


@pytest.fixture
def client(tmp_path):
    config.set_data(tmp_path / "data")
    db.init()
    app = FastAPI()
    app.middleware("http")(companion.guard)
    app.include_router(companion.router)
    return TestClient(app, base_url=f"http://127.0.0.1:{config.PORT}")


def headers():
    return {"Authorization": f"Bearer {companion.TOKEN}", "Origin": "http://127.0.0.1:8877"}


def test_pairing_origin_and_host(client):
    assert client.get("/companion/health").status_code == 401
    response = client.get("/companion/health", headers=headers())
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8877"
    assert "token" not in response.json()
    assert client.get("/companion/jobs", headers={**headers(), "Origin": "https://evil.example"}).status_code == 403
    assert client.get("/companion/jobs", headers={**headers(), "Host": "evil.example"}).status_code == 403
    assert client.get("/companion/jobs", headers={**headers(), "Authorization": "Bearer wrong"}).status_code == 401


def test_private_network_preflight(client):
    request_headers = {"Origin": "http://127.0.0.1:8877", "Access-Control-Request-Method": "POST",
                       "Access-Control-Request-Headers": "authorization,content-type",
                       "Access-Control-Request-Private-Network": "true"}
    response = client.options("/companion/import", headers=request_headers)
    assert response.status_code == 204
    assert response.headers["access-control-allow-private-network"] == "true"
    assert client.options("/companion/import", headers={**request_headers, "Origin": "https://evil.example"}).status_code == 403
    assert client.options("/companion/import", headers={**request_headers, "Access-Control-Request-Headers": "x-evil"}).status_code == 403


def test_media_stays_in_data_and_hides_database(client, tmp_path):
    (config.DATA / "video.mp4").write_bytes(b"video")
    (tmp_path / "outside.mp4").write_bytes(b"secret")
    assert client.get("/companion/media/video.mp4", headers=headers()).content == b"video"
    assert client.get("/companion/media/%2e%2e/outside.mp4", headers=headers()).status_code == 404
    assert client.get("/companion/media/shera.sqlite3", headers=headers()).status_code == 404


def test_media_ticket_is_bound_to_path_and_supports_range(client):
    (config.DATA / "video.mp4").write_bytes(b"0123456789")
    (config.DATA / "other.mp4").write_bytes(b"other")
    response = client.post("/companion/media-ticket", headers=headers(), json={"path": "/companion/media/video.mp4"})
    url = response.json()["url"]
    result = client.get(url, headers={"Range": "bytes=2-4"})
    assert result.status_code == 206
    assert result.content == b"234"
    assert client.get(url.replace("video.mp4", "other.mp4")).status_code == 401
    assert client.get(url.replace("expires=", "expires=0")).status_code == 401
    assert client.post("/companion/media-ticket", headers=headers(), json={"path": "/companion/media/../secret.mp4"}).status_code == 404


def test_json_media_is_limited_to_exports(client):
    exports = config.DATA / "exports"
    exports.mkdir()
    (exports / "post.json").write_text('{"title":"clip"}')
    (config.DATA / "private.json").write_text('{"secret":true}')
    assert client.get("/companion/media/exports/post.json", headers=headers()).status_code == 200
    assert client.get("/companion/media/private.json", headers=headers()).status_code == 404
    assert client.get("/companion/media/exports/%2e%2e/private.json", headers=headers()).status_code == 404


def test_upload_streams_and_normalizes_profile(client, monkeypatch):
    captured = {}
    def start(video, vtt, audio, profile):
        captured.update(video=video.read_bytes(), vtt=vtt.read_bytes(), profile=profile)
        return "job1"
    monkeypatch.setattr(companion.pipeline, "start_job", start)
    monkeypatch.setattr(companion.db, "update_job", lambda job_id, **fields: captured.update(fields))
    response = client.post("/companion/import", headers=headers(), files={
        "video": ("../../bad.mp4", b"video", "video/mp4"), "vtt": ("captions.vtt", b"WEBVTT", "text/vtt")})
    assert response.json() == {"job_id": "job1"}
    assert captured["video"] == b"video"
    assert captured["profile"]["preset"] == "general"
    assert captured["title"] == "bad"


def test_url_import_uses_filename_without_query(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(companion, "_download", lambda url, path: path.write_bytes(b"video"))
    monkeypatch.setattr(companion.pipeline, "start_job", lambda *args, **kwargs: "job1")
    monkeypatch.setattr(companion.db, "update_job", lambda job_id, **fields: captured.update(fields))
    response = client.post("/companion/import-url", headers=headers(), json={"url": "https://example.com/My%20Talk.mp4?token=secret"})
    assert response.json() == {"job_id": "job1"}
    assert captured["title"] == "My Talk"
    assert companion._title("", "Downloaded video") == "Downloaded video"


def test_failed_upload_cleans_partial_files(client, monkeypatch):
    monkeypatch.setattr(companion, "MAX_BYTES", 3)
    response = client.post("/companion/import", headers=headers(), files={"video": ("video.mp4", b"oversize")})
    assert response.status_code == 413
    assert list(config.INBOX.iterdir()) == []


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "192.168.1.1", "169.254.169.254", "100.64.0.1"])
def test_download_rejects_private_destinations(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))])
    with pytest.raises(ValueError):
        companion._destination("https://example.com/video.mp4")


@pytest.mark.parametrize("url", ["http://example.com/video", "https://user:pass@example.com/video", "https://example.com:8765/video"])
def test_download_rejects_unsafe_url_forms(url):
    with pytest.raises(ValueError):
        companion._destination(url)


def test_redirect_revalidates_destination(monkeypatch, tmp_path):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1" if host == "localhost" else "8.8.8.8", 443))])
    class Connection:
        def __init__(self, host, address):
            assert address == "8.8.8.8"
        def request(self, *args):
            pass
        def getresponse(self):
            return self
        status = 302
        def getheader(self, key):
            return "https://localhost/private"
        def close(self):
            pass
    monkeypatch.setattr(companion, "_PinnedHTTPS", Connection)
    with pytest.raises(ValueError):
        companion._download("https://example.com/video", tmp_path / "video.mp4")


def test_download_rejects_truncated_body(monkeypatch, tmp_path):
    monkeypatch.setattr(companion, "_destination", lambda url: (urlsplit(url), "8.8.8.8"))
    class Connection:
        def __init__(self, *args):
            self.chunks = iter([b"short", b""])
        def request(self, *args):
            pass
        def getresponse(self):
            return self
        status = 200
        def getheader(self, key):
            return "100"
        def read(self, size):
            return next(self.chunks)
        def close(self):
            pass
    monkeypatch.setattr(companion, "_PinnedHTTPS", Connection)
    with pytest.raises(ValueError, match="incomplete"):
        companion._download("https://example.com/video", tmp_path / "video.mp4")
