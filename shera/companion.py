import http.client
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import shutil
import time
import socket
import ssl
import uuid
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from shera import config, db, pipeline

TOKEN = secrets.token_urlsafe(32)
TICKET_KEY = secrets.token_bytes(32)
MAX_BYTES = 4 * 1024 ** 3
CHUNK = 1024 * 1024
router = APIRouter(prefix="/companion")


def origins():
    return {os.environ.get("SHERA_SITE_ORIGIN", "https://shera-video-desk.imoral223489.chatgpt.site"),
            "http://127.0.0.1:8877"}


async def guard(request, call_next):
    if request.url.path != "/companion" and not request.url.path.startswith("/companion/"):
        return await call_next(request)
    origin = request.headers.get("origin")
    if request.headers.get("host") not in {f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}"}:
        return JSONResponse({"detail": "Forbidden host"}, status_code=403)
    if origin is not None and origin not in origins():
        return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
    headers = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"} if origin else {}
    if request.method == "OPTIONS":
        if not origin or request.headers.get("access-control-request-method") not in {"GET", "POST"}:
            return JSONResponse({"detail": "Forbidden preflight"}, status_code=403)
        requested = {h.strip().lower() for h in request.headers.get("access-control-request-headers", "").split(",") if h.strip()}
        if requested - {"authorization", "content-type"}:
            return JSONResponse({"detail": "Forbidden headers"}, status_code=403)
        headers.update({"Access-Control-Allow-Methods": "GET, POST", "Access-Control-Allow-Headers": "Authorization, Content-Type",
                        "Access-Control-Allow-Private-Network": "true"})
        return Response(status_code=204, headers=headers)
    ticket = False
    if request.method == "GET" and request.url.path.startswith("/companion/media/"):
        expires = request.query_params.get("expires", "")
        signature = request.query_params.get("ticket", "")
        try:
            ticket = time.time() <= int(expires) <= time.time() + 300 and hmac.compare_digest(
                signature, _signature(request.url.path, expires))
        except ValueError:
            pass
    if not ticket and not secrets.compare_digest(request.headers.get("authorization", ""), f"Bearer {TOKEN}"):
        return JSONResponse({"detail": "Pairing token required"}, status_code=401, headers=headers)
    response = await call_next(request)
    response.headers.update(headers)
    return response


@router.get("/health")
def health():
    from shera import profiles
    return {"status": "ok", "version": "1", "local": True, "profiles": profiles.PRESETS,
            "setup": {"ffmpeg": bool(shutil.which("ffmpeg")), "provider_key": bool(config.openrouter_key())},
            "cap_usd": config.CAP_USD}


def _signature(path, expires):
    return hmac.new(TICKET_KEY, f"{path}\n{expires}".encode(), hashlib.sha256).hexdigest()


@router.post("/media-ticket")
def media_ticket(body: dict):
    from urllib.parse import quote
    path = body.get("path", "")
    if not isinstance(path, str) or not path.startswith("/companion/media/"):
        raise HTTPException(422, "A companion media path is required")
    relative = path.removeprefix("/companion/media/")
    media(relative)
    canonical = "/companion/media/" + relative
    expires = str(int(time.time()) + 299)
    return {"url": f"{quote(canonical, safe='/')}?expires={expires}&ticket={_signature(canonical, expires)}"}


@router.get("/jobs")
def jobs():
    return {"jobs": db.list_jobs()}


@router.get("/jobs/{job_id}")
def job(job_id: str):
    value = db.get_job(job_id)
    if not value:
        raise HTTPException(404, "No such job")
    path = pipeline.job_dir(job_id) / "transcript.json"
    transcript = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"units": []}
    media = pipeline.media_path(job_id)
    relative = Path(media).resolve().relative_to(config.DATA.resolve()) if media else None
    return {"job": value, "candidates": db.candidates(job_id),
            "reviews": db.q("SELECT r.* FROM reviews r JOIN candidates c ON c.id=r.candidate_id WHERE c.job_id=?", job_id),
            "transcript": transcript, "media_url": f"/companion/media/{relative.as_posix()}" if relative else None}


def _profile(value):
    from shera import profiles
    try:
        return profiles.resolve(json.loads(value) if isinstance(value, str) else value)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


async def _save(upload, path):
    size = 0
    with path.open("wb") as out:
        while chunk := await upload.read(CHUNK):
            size += len(chunk)
            if size > MAX_BYTES:
                raise HTTPException(413, "File exceeds 4 GiB")
            out.write(chunk)
    if not size:
        raise HTTPException(422, "Empty file")


def _title(filename, fallback):
    name = Path(filename.replace("\\", "/")).stem
    return "".join(c for c in name if c.isprintable()).strip()[:200] or fallback


@router.post("/import")
async def import_video(video: UploadFile = File(...), vtt: UploadFile | None = File(None),
                       audio: UploadFile | None = File(None), profile: str = Form("{}")):
    normalized = _profile(profile)
    folder = config.INBOX / uuid.uuid4().hex
    folder.mkdir(parents=True)
    try:
        await _save(video, folder / "source.mp4")
        if vtt:
            await _save(vtt, folder / "source.vtt")
        if audio:
            await _save(audio, folder / "source.m4a")
        job_id = pipeline.start_job(folder / "source.mp4", folder / "source.vtt" if vtt else None,
                                    folder / "source.m4a" if audio else None, profile=normalized)
        db.update_job(job_id, title=_title(video.filename or "", "Imported video"))
        return {"job_id": job_id}
    except BaseException:
        shutil.rmtree(folder)
        raise
    finally:
        for upload in (video, vtt, audio):
            if upload:
                await upload.close()


def _destination(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Use a direct public HTTPS video URL on port 443")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("URL must resolve only to public addresses")
    return parsed, addresses[0][4][0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname, address):
        super().__init__(hostname, timeout=30, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def _download(url, path):
    for _ in range(6):
        parsed, address = _destination(url)
        connection = _PinnedHTTPS(parsed.hostname, address)
        try:
            connection.request("GET", (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else ""))
            response = connection.getresponse()
            if response.status in {301, 302, 303, 307, 308}:
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Redirect has no destination")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError(f"Video download returned HTTP {response.status}")
            length = response.getheader("Content-Length")
            if length and int(length) > MAX_BYTES:
                raise ValueError("Video exceeds 4 GiB")
            size = 0
            with path.open("wb") as out:
                while chunk := response.read(CHUNK):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("Video exceeds 4 GiB")
                    out.write(chunk)
            if not size:
                raise ValueError("Empty video")
            if length is not None and size != int(length):
                raise ValueError("Video download was incomplete")
            return
        finally:
            connection.close()
    raise ValueError("Too many redirects")


@router.post("/import-url")
def import_url(body: dict):
    profile = _profile(body.get("profile", {}))
    folder = config.INBOX / uuid.uuid4().hex
    folder.mkdir(parents=True)
    try:
        _download(body.get("url", ""), folder / "source.mp4")
        job_id = pipeline.start_job(folder / "source.mp4", profile=profile)
        db.update_job(job_id, title=_title(unquote(urlsplit(body.get("url", "")).path), "Downloaded video"))
        return {"job_id": job_id}
    except (ValueError, OSError, http.client.HTTPException) as exc:
        shutil.rmtree(folder)
        raise HTTPException(422, "Unable to download a public video URL") from exc
    except BaseException:
        shutil.rmtree(folder)
        raise


@router.get("/media/{rel:path}")
def media(rel: str):
    root = config.DATA.resolve()
    path = (root / rel).resolve()
    allowed = path.suffix.lower() in {".mp4", ".m4a", ".mp3", ".wav", ".vtt", ".srt", ".jpg", ".jpeg", ".png", ".zip"}
    allowed = allowed or (path.suffix.lower() == ".json" and path.is_relative_to(root / "exports"))
    if not path.is_relative_to(root) or not allowed or not path.is_file():
        raise HTTPException(404, "No such media")
    return FileResponse(path)
