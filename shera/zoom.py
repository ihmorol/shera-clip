"""Read-only Zoom cloud-recording access through an internal Server-to-Server OAuth app (D04, D15).
Never logs tokens or download URLs; errors name the fix, not the request."""
import hashlib
import os
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx

from shera import config, media  # noqa: F401  (config loads .env)

API = "https://api.zoom.us/v2"
TOKEN_URL = "https://zoom.us/oauth/token"
KEYS = ("ZOOM_ACCOUNT_ID", "ZOOM_CLIENT_ID", "ZOOM_CLIENT_SECRET", "ZOOM_USER")
TRANSPORT = None  # tests swap in httpx.MockTransport
# Preferred first (docs/zoom-setup.md): the slide stays readable and the teacher is visible.
LAYOUTS = {"shared_screen_with_speaker_view": "Shared screen with speaker (recommended)",
           "shared_screen_with_speaker_view(CC)": "Shared screen with speaker, Zoom captions burned in",
           "shared_screen": "Shared screen only",
           "shared_screen_with_gallery_view": "Shared screen with gallery",
           "active_speaker": "Active speaker",
           "gallery_view": "Gallery view"}
_token_cache = {}
_token_lock = threading.Lock()


class ZoomError(Exception):
    pass


def configured():
    return all(os.environ.get(k) for k in KEYS)


def _client():
    return httpx.Client(transport=TRANSPORT, timeout=httpx.Timeout(60.0))


def _why(r):
    try:
        body = r.json()
    except ValueError:
        return f"HTTP {r.status_code}"
    return f"HTTP {r.status_code}: {body.get('reason') or body.get('message') or body.get('error') or 'no reason given'}"


def _token(fresh=False):
    if not configured():
        raise ZoomError("Zoom is not set up: add ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET and ZOOM_USER "
                        "to .env (see docs/zoom-setup.md), then restart Shera Clip.")
    with _token_lock:
        if fresh or _token_cache.get("exp", 0) < time.time():
            try:
                with _client() as c:
                    r = c.post(TOKEN_URL, params={"grant_type": "account_credentials",
                                                  "account_id": os.environ["ZOOM_ACCOUNT_ID"]},
                               auth=(os.environ["ZOOM_CLIENT_ID"], os.environ["ZOOM_CLIENT_SECRET"]))
            except httpx.HTTPError as e:
                raise ZoomError(f"Could not reach Zoom ({type(e).__name__}). Check the internet connection.") from None
            if r.is_error:
                raise ZoomError(f"Zoom refused the app credentials ({_why(r)}). Check ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID "
                                "and ZOOM_CLIENT_SECRET in .env and that the Server-to-Server app is activated.")
            body = r.json()
            _token_cache.update(value=body["access_token"], exp=time.time() + body.get("expires_in", 3600) - 300)
        return _token_cache["value"]


def _fail(r):
    if r.status_code == 401:
        raise ZoomError(f"Zoom authorization was lost ({_why(r)}). Check that the Server-to-Server app is still "
                        "activated and its credentials in .env are current, then try again.")
    raise ZoomError(f"Zoom refused the request ({_why(r)}). Check ZOOM_USER and that the app has the recording "
                    "read scopes listed in docs/zoom-setup.md.")


def _get(path, params=None):
    try:
        with _client() as c:
            for fresh in (False, True):  # one retry with a new token if Zoom says the old one expired
                r = c.get(API + path, params=params, headers={"Authorization": f"Bearer {_token(fresh)}"})
                if r.status_code != 401:
                    break
    except httpx.HTTPError as e:
        raise ZoomError(f"Could not reach Zoom ({type(e).__name__}). Check the internet connection.") from None
    if r.is_error:
        _fail(r)
    return r.json()


def _uuid_path(uuid):
    once = quote(uuid, safe="")
    return quote(once, safe="") if uuid.startswith("/") or "//" in uuid else once  # Zoom's double-encoding rule


def meeting(uuid):
    """One occurrence with fresh download URLs."""
    return _get(f"/meetings/{_uuid_path(uuid)}/recordings")


def occurrence(m):
    """What the chooser shows: completed videos (preferred layout first), transcript, Zoom audio."""
    done = [f for f in m.get("recording_files", []) if f.get("status", "completed") == "completed"]
    order = list(LAYOUTS)
    videos = sorted((f for f in done if f.get("file_type") == "MP4"),
                    key=lambda f: order.index(f.get("recording_type")) if f.get("recording_type") in order else len(order))

    def pick(*types):
        return next(({"id": f["id"], "size": f.get("file_size")} for t in types for f in done if f.get("file_type") == t), None)

    vtt, m4a = pick("TRANSCRIPT", "CC"), pick("M4A")
    # one import fetches the preferred video plus the chosen extras: what "needs about X" on the page estimates
    need = sum((f.get("file_size") or f.get("size") or 0) for f in videos[:1] + [vtt, m4a] if f)
    return {"uuid": m["uuid"], "topic": m.get("topic") or "Zoom meeting", "start": m.get("start_time", ""),
            "minutes": m.get("duration"),
            "videos": [{"id": f["id"], "size": f.get("file_size"),
                        "label": LAYOUTS.get(f.get("recording_type"), (f.get("recording_type") or "Video").replace("_", " ").capitalize())}
                       for f in videos],
            "vtt": vtt, "m4a": m4a,
            "processing": sum(f.get("status", "completed") != "completed" for f in m.get("recording_files", [])),
            "need": need}


def recordings(to):
    """Occurrences recorded in the month ending `to` (Zoom's longest range per request), newest first."""
    start = to - timedelta(days=30)
    params = {"from": start.isoformat(), "to": to.isoformat(), "page_size": 300}
    user = quote(os.environ.get("ZOOM_USER", ""), safe="@")
    out = []
    while True:
        body = _get(f"/users/{user}/recordings", params)
        out += [occurrence(m) for m in body.get("meetings", [])]
        if not body.get("next_page_token"):
            break
        params = {**params, "next_page_token": body["next_page_token"]}
    out.sort(key=lambda o: o["start"], reverse=True)
    return start, out


def local_time(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def checked_occurrence(uuid, mp4, vtt="", m4a=""):
    """Fetch the occurrence and check the chosen file ids against it (D27). Returns (occurrence, title)."""
    occ = occurrence(meeting(uuid))
    if (mp4 not in {v["id"] for v in occ["videos"]} or vtt not in ("", (occ["vtt"] or {}).get("id"))
            or m4a not in ("", (occ["m4a"] or {}).get("id"))):
        raise ZoomError("That recording file is no longer in Zoom or not ready yet. "
                        "Refresh the list and choose again.")
    when = local_time(occ["start"])
    return occ, occ["topic"] + (when.strftime(" · %d %b %Y") if when else "")


def download(uuid, file_id, dst, on_progress=None):
    """Stream one recording file to dst via dst.part, hashing on the way; the byte count must match Zoom's.
    -> (sha256, bytes)."""
    f = next((f for f in meeting(uuid).get("recording_files", []) if f.get("id") == file_id), None)
    if f is None:
        raise ZoomError("That recording file is no longer in Zoom (deleted, trashed or expired). Import the class again.")
    if f.get("status", "completed") != "completed":
        raise ZoomError("Zoom is still processing that recording file. Resume in a few minutes.")
    expected = f.get("file_size")
    if expected:  # the free-space guard runs here, before every caller's download (pipeline._download included)
        media.ensure_free(expected * 1.1)
    part = dst.with_name(dst.name + ".part")
    h, n = hashlib.sha256(), 0
    try:
        with _client() as c:
            for fresh in (False, True):
                # httpx drops the Authorization header when Zoom redirects to its storage host.
                with c.stream("GET", f["download_url"], follow_redirects=True,
                              headers={"Authorization": f"Bearer {_token(fresh)}"}) as r:
                    if r.status_code == 401 and not fresh:
                        continue
                    if r.is_error:
                        r.read()
                        _fail(r)
                    # ponytail: a broken download restarts from zero on resume; add HTTP Range resume if that hurts
                    with open(part, "wb") as fo:
                        for chunk in r.iter_bytes(8 << 20):
                            fo.write(chunk)
                            h.update(chunk)
                            n += len(chunk)
                            if on_progress and expected:
                                on_progress(min(n / expected, 1.0))
                    break
    except httpx.HTTPError as e:
        part.unlink(missing_ok=True)
        raise ZoomError(f"The Zoom download broke off ({type(e).__name__}). Resume to download it again.") from None
    if expected is not None and n != expected:
        part.unlink(missing_ok=True)
        raise ZoomError(f"The Zoom download is incomplete: {n} of {expected} bytes arrived. Resume to download it again.")
    os.replace(part, dst)
    return h.hexdigest(), n
