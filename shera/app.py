"""Local web UI: server-rendered pages over the pipeline. Binds to loopback only."""
import json
import os
import shutil
import threading
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shera import candidates as cand
from shera import config, db, ledger, pipeline

HERE = Path(__file__).parent
STAGES = ("import", "transcript", "authorize", "transcribe", "candidates", "score", "prepare", "review")
CATEGORIES = {"exam_tip": "Exam tip", "worked_example": "Worked example",
              "common_mistake": "Common mistake and correction", "vocabulary": "Vocabulary/phrase",
              "practice_exercise": "Practice exercise", "other": "Other"}
PLATFORMS = ("facebook", "youtube")
FIELDS = ("title", "description", "cta")

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

# Background work keyed like "render:12" -> {"state": "running"|"done"|"error", "error": str|None}
TASKS = {}
_tasks_lock = threading.Lock()


def _bg(key, fn):
    with _tasks_lock:
        if TASKS.get(key, {}).get("state") == "running":
            return
        TASKS[key] = {"state": "running", "error": None}

    def work():
        try:
            fn()
            TASKS[key] = {"state": "done", "error": None}
        except Exception as e:
            TASKS[key] = {"state": "error", "error": str(e) or type(e).__name__}

    threading.Thread(target=work, daemon=True).start()


# ---------- security: DNS rebinding + CSRF ----------

def _allowed_hosts():
    return {f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}"}


@app.middleware("http")
async def guard(request: Request, call_next):
    if request.headers.get("host", "") not in _allowed_hosts():
        return PlainTextResponse("Forbidden host", status_code=403)
    if request.method not in ("GET", "HEAD"):
        origin = request.headers.get("origin")
        src = origin if origin is not None else request.headers.get("referer")
        if src is not None and urlsplit(src).netloc not in _allowed_hosts():
            return PlainTextResponse("Cross-origin request refused", status_code=403)
    return await call_next(request)


# ---------- helpers ----------

def _dir_bytes(path):
    return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file()) if Path(path).exists() else 0


def _media_url(path):
    rel = Path(path).resolve().relative_to(config.DATA.resolve())
    return "/media/" + rel.as_posix()


def _job_or_404(job_id):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "No such job")
    return job


def _clip_or_404(job_id, cid):
    c = db.candidate(cid)
    if not c or c["job_id"] != job_id:
        raise HTTPException(404, "No such clip")
    return c


def _units(job_id):
    p = pipeline.job_dir(job_id) / "transcript.json"
    return json.loads(p.read_text(encoding="utf-8"))["units"] if p.exists() else []


def _ordered(job_id):
    """Shortlist by rank, then everything else by source time."""
    cs = db.candidates(job_id)
    short = sorted((c for c in cs if c["shortlisted"]), key=lambda c: c["rank"])
    return short, [c for c in cs if not c["shortlisted"]]


def _reviews(job_id):
    return {r["candidate_id"]: r for r in db.q(
        "SELECT r.* FROM reviews r JOIN candidates c ON c.id=r.candidate_id WHERE c.job_id=?", job_id)}


def fmt_time(s):
    if s is None:
        return "–"
    s = float(s)
    return f"{int(s // 3600)}:{int(s // 60 % 60):02d}:{s % 60:04.1f}"


def fmt_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


templates.env.filters.update(t=fmt_time, bytes=fmt_bytes, usd=lambda v: f"${float(v or 0):.4f}")
templates.env.globals.update(CATEGORIES=CATEGORIES, CAP=config.CAP_USD, STAGES=STAGES)


def page(request, name, status_code=200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


# ---------- home + import ----------

def _home(request, error=None, form=None, status_code=200):
    inbox = []
    if config.INBOX.is_dir():
        for f in sorted(config.INBOX.iterdir()):
            if f.is_file() and f.suffix.lower() == ".mp4":
                vtt = f.with_suffix(".vtt")
                inbox.append({"path": f, "size": f.stat().st_size, "vtt": vtt if vtt.exists() else None})
    jobs = [{**j, "spent": ledger.spent(j["id"]),
             "disk": _dir_bytes(pipeline.job_dir(j["id"])) + _dir_bytes(config.DATA / "exports" / j["id"])}
            for j in db.list_jobs()]
    setup = {"FFmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
             "OpenRouter key": bool(config.openrouter_key())}
    return page(request, "home.html", status_code, setup=setup, inbox=inbox, inbox_dir=config.INBOX, jobs=jobs,
                error=error, form=form or {})


@app.get("/")
def home(request: Request):
    return _home(request)


def _check_file(raw, ext, label):
    path = Path(raw.strip().strip('"'))
    if path.suffix.lower() != ext:
        return None, f"{label} must be a {ext} file: {path}"
    if not path.is_file():
        return None, f"{label} not found: {path}. Check the path, or copy the file into {config.INBOX}."
    return path, None


@app.post("/import")
def import_(request: Request, mp4: str = Form(""), vtt: str = Form("")):
    form = {"mp4": mp4, "vtt": vtt}
    if not mp4.strip():
        return _home(request, "Enter the path to the class MP4.", form, 400)
    src, err = _check_file(mp4, ".mp4", "Recording")
    if not err and vtt.strip():
        vtt_path, err = _check_file(vtt, ".vtt", "Transcript")
    else:
        vtt_path = None
    if err:
        return _home(request, err, form, 400)
    job_id = pipeline.start_job(src, vtt_path)
    return RedirectResponse(f"/jobs/{job_id}", 303)


# ---------- job ----------

def _live(call):
    """A 'sent' paid call still owned by a running pipeline thread or web task."""
    with pipeline._lock:
        if call["job_id"] in pipeline._running:
            return True
    return call["key"].startswith("draft:") and TASKS.get(call["key"], {}).get("state") == "running"


def _job_page(request, job_id, error=None, status_code=200):
    job = _job_or_404(job_id)
    short, other = _ordered(job_id)
    reviews = _reviews(job_id)
    calls = ledger.calls(job_id)
    est = pipeline.estimate(job_id) if job["stage"] == "authorize" and job["status"] == "waiting" else None
    return page(request, "job.html", status_code, job=job, short=short, other=other, reviews=reviews,
                spent=ledger.spent(job_id), est=est, error=error, stt_model=config.STT_MODEL,
                stuck=[c for c in calls if c["state"] == "indeterminate" or (c["state"] == "sent" and not _live(c))],
                inflight=[c for c in calls if c["state"] == "sent" and _live(c)],
                approved=sum(r["status"] == "approved" for r in reviews.values()))


@app.get("/jobs/{job_id}")
def job_page(request: Request, job_id: str):
    return _job_page(request, job_id)


@app.post("/jobs/{job_id}/authorize")
def authorize(job_id: str):
    job = _job_or_404(job_id)
    if job["stage"] == "authorize" and job["status"] == "waiting":
        pipeline.authorize(job_id)
    return RedirectResponse(f"/jobs/{job_id}", 303)


@app.post("/jobs/{job_id}/resume")
def resume(job_id: str):
    if _job_or_404(job_id)["status"] in ("failed", "paused"):
        pipeline.resume(job_id)
    return RedirectResponse(f"/jobs/{job_id}", 303)


@app.post("/jobs/{job_id}/calls/{call_id}/retry")
def retry_call(job_id: str, call_id: int):
    _job_or_404(job_id)
    if not db.one("SELECT id FROM paid_calls WHERE id=? AND job_id=?", call_id, job_id):
        raise HTTPException(404, "No such paid call")
    call = db.one("SELECT * FROM paid_calls WHERE id=?", call_id)
    if call["state"] == "sent" and not _live(call):  # orphaned: same as what a restart would record
        db.x("UPDATE paid_calls SET state='indeterminate' WHERE id=?", call_id)
    ledger.resolve(call_id)
    if not any(c["state"] == "indeterminate" or (c["state"] == "sent" and not _live(c)) for c in ledger.calls(job_id)):
        pipeline.resume(job_id)
    return RedirectResponse(f"/jobs/{job_id}", 303)


@app.post("/jobs/{job_id}/delete")
def delete(request: Request, job_id: str):
    _job_or_404(job_id)
    try:
        pipeline.delete_job(job_id)
    except ValueError as e:
        return _job_page(request, job_id, str(e), 409)
    return RedirectResponse("/", 303)


# ---------- review ----------

def _drafting(job):
    return job["stage"] == "prepare" and job["status"] == "running"


def _state(rv):
    task = TASKS.get(f"render:{rv['candidate_id']}", {})
    return {"status": rv["status"], "preview_ok": pipeline.preview_current(rv),
            "preview_url": _media_url(rv["preview_path"]) if pipeline.preview_current(rv) else None,
            "render": task.get("state"), "render_error": task.get("error"),
            "draft": TASKS.get(f"draft:{rv['candidate_id']}", {}).get("state"),
            "draft_error": TASKS.get(f"draft:{rv['candidate_id']}", {}).get("error")}


@app.get("/jobs/{job_id}/clips/{cid}")
def review_page(request: Request, job_id: str, cid: int):
    job, c = _job_or_404(job_id), _clip_or_404(job_id, cid)
    rv = pipeline.ensure_review(cid)
    units = _units(job_id)
    lo, hi = min(rv["start"], c["start"]) - 30, max(rv["end"], c["end"]) + 30
    near = [u for u in units if u["end"] > lo and u["start"] < hi]
    short, other = _ordered(job_id)
    order = [x["id"] for x in short + other]
    i = order.index(cid)
    return page(request, "review.html", job=job, c=c, rv=rv, near=near, state=_state(rv), drafting=_drafting(job),
                source_url=f"/media/jobs/{job_id}/source.mp4",
                prev=order[i - 1] if i > 0 else None, next=order[i + 1] if i + 1 < len(order) else None,
                bounds={"starts": [u["start"] for u in units], "ends": [u["end"] for u in units]})


def _num(v, lo, hi, label):
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise HTTPException(422, f"{label} must be a number")
    if not lo <= v <= hi:
        raise HTTPException(422, f"{label} must be between {lo:g} and {hi:g}")
    return v


def _box(b, label):
    if not isinstance(b, list) or len(b) != 4:
        raise HTTPException(422, f"{label} needs 4 numbers (x, y, w, h)")
    x, y, w, h = (_num(v, 0, 1, label) for v in b)
    if w <= 0 or h <= 0 or x + w > 1.0001 or y + h > 1.0001:
        raise HTTPException(422, f"{label} must fit inside the frame (x+w ≤ 1, y+h ≤ 1, w and h > 0)")
    return [x, y, w, h]


def _retime(caps, shift, duration):
    """Captions are relative to clip start: shift them when the start moves, drop those outside, clamp the rest."""
    out = []
    for c in caps:
        s, e = c["start"] + shift, c["end"] + shift
        if e > 0 and s < duration:
            out.append({**c, "start": max(s, 0.0), "end": min(e, duration)})
    return out


def _clean(body, job, rv):
    """Validate a review save from the browser into update_review fields."""
    f = {}
    caps = rv["captions"] or []
    if "captions" in body:
        caps = []
        for n, row in enumerate(body["captions"] or [], 1):
            s, e = _num(row.get("start"), 0, 1e6, f"Caption {n} start"), _num(row.get("end"), 0, 1e6, f"Caption {n} end")
            if e <= s:
                raise HTTPException(422, f"Caption {n} must end after it starts")
            caps.append({"start": s, "end": e, "text": str(row.get("text", "")).strip()})
        f["captions"] = caps
    if "start" in body or "end" in body:
        start = _num(body.get("start", rv["start"]), 0, job["duration"] or 1e9, "Start")
        end = _num(body.get("end", rv["end"]), 0, job["duration"] or 1e9, "End")
        if end - start < 1:
            raise HTTPException(422, "End must be at least 1 s after start")
        f["start"], f["end"] = round(start, 3), round(end, 3)
        if f["start"] != rv["start"] or f["end"] != rv["end"] or "captions" in f:
            f["captions"] = _retime(caps, rv["start"] - f["start"], f["end"] - f["start"])
    if "layout" in body:
        lay = body["layout"] or {}
        if lay.get("mode") == "crop":
            f["layout"] = {"mode": "crop", "crop": _box(lay.get("crop"), "Crop"),
                           "inset": _box(lay["inset"], "Inset") if lay.get("inset") else None}
        else:
            f["layout"] = {"mode": "full"}
    if "title" in body:
        f["title"] = str(body["title"]).strip()
    if body.get("category"):  # "" = still unchosen; leave it null
        if body["category"] not in CATEGORIES:
            raise HTTPException(422, "Unknown category")
        f["category"] = body["category"]
    if "tags" in body:
        f["tags"] = [t.strip() for t in str(body["tags"]).split(",") if t.strip()]
    if "drafts" in body:
        typed = {p: {k: str((body["drafts"].get(p) or {}).get(k, "")).strip() for k in FIELDS} for p in PLATFORMS}
        # All-empty fields never replace stored drafts (a paid draft or a visible provider error).
        if any(v for p in typed.values() for v in p.values()) or not rv["drafts"]:
            f["drafts"] = typed
    return f


@app.post("/jobs/{job_id}/clips/{cid}")
async def save_review(request: Request, job_id: str, cid: int):
    job, _ = _job_or_404(job_id), _clip_or_404(job_id, cid)
    rv = pipeline.ensure_review(cid)
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "Expected JSON")
    _save(rv, _clean(body, job, rv))
    rv = db.review(cid)
    return {**_state(rv), "captions": rv["captions"], "start": rv["start"], "end": rv["end"]}


def _save(rv, fields):
    """Persist review fields; a change to the rendered video withdraws an approval."""
    if rv["status"] == "approved" and pipeline.state_hash({**rv, **fields}) != pipeline.state_hash(rv):
        fields["status"] = "pending"
    db.update_review(rv["candidate_id"], **fields)


@app.post("/jobs/{job_id}/clips/{cid}/captions/reset")
def reset_captions(job_id: str, cid: int):
    """Rebuild captions from the transcript for the current saved boundaries."""
    _job_or_404(job_id), _clip_or_404(job_id, cid)
    rv, units = pipeline.ensure_review(cid), _units(job_id)
    idx = [i for i, u in enumerate(units) if u["end"] > rv["start"] and u["start"] < rv["end"]]
    caps = cand.caption_lines(units, idx[0], idx[-1], rv["start"], rv["end"]) if idx else []
    _save(rv, {"captions": caps})
    return {"captions": caps, **_state(db.review(cid))}


@app.get("/jobs/{job_id}/clips/{cid}/state")
def clip_state(job_id: str, cid: int):
    _job_or_404(job_id), _clip_or_404(job_id, cid)
    rv = db.review(cid)
    return {**_state(rv), "drafts": rv["drafts"]}


@app.post("/jobs/{job_id}/clips/{cid}/preview")
def preview(job_id: str, cid: int):
    _job_or_404(job_id), _clip_or_404(job_id, cid)
    _bg(f"render:{cid}", lambda: pipeline.render_preview(cid))
    return _state(db.review(cid))


@app.post("/jobs/{job_id}/clips/{cid}/draft")
def redraft(job_id: str, cid: int):
    """Paid posting draft for this clip (the job's authorization and cap apply)."""
    job, _ = _job_or_404(job_id), _clip_or_404(job_id, cid)
    if _drafting(job):
        raise HTTPException(409, "The job is drafting posting text now; wait for it to finish.")
    _bg(f"draft:{cid}", lambda: pipeline.draft(cid))
    return _state(db.review(cid))


@app.post("/jobs/{job_id}/clips/{cid}/decision")
async def decide(request: Request, job_id: str, cid: int):
    _job_or_404(job_id), _clip_or_404(job_id, cid)
    decision = (await request.json()).get("decision")
    rv = pipeline.ensure_review(cid)
    if decision == "approve":
        if not pipeline.preview_current(rv):
            return JSONResponse({"error": "Render a phone preview of the current saved edits before approving."}, 409)
        db.update_review(cid, status="approved")
    elif decision in ("reject", "pending"):
        db.update_review(cid, status="rejected" if decision == "reject" else "pending")
    else:
        raise HTTPException(422, "decision must be approve, reject, or pending")
    return _state(db.review(cid))


# ---------- export ----------

def _export_root(job_id):
    return config.DATA / "exports" / job_id


@app.get("/jobs/{job_id}/export")
def export_page(request: Request, job_id: str, error: str = ""):
    job = _job_or_404(job_id)
    root = _export_root(job_id)
    packages = []
    if (root / "index.json").exists():
        for entry in json.loads((root / "index.json").read_text(encoding="utf-8")):
            folder = root / entry["folder"]
            rv = db.one("SELECT * FROM reviews WHERE candidate_id=?", entry["candidate_id"])
            packages.append({**entry, "path": folder, "files": sorted(p.name for p in folder.iterdir()),
                             "posted": (rv or {}).get("posted") or {},
                             "video_url": _media_url(folder / "video.mp4") if (folder / "video.mp4").exists() else None})
    skipped = json.loads((root / "skipped.json").read_text(encoding="utf-8")) if (root / "skipped.json").exists() else []
    approved = db.one("SELECT COUNT(*) AS n FROM reviews r JOIN candidates c ON c.id=r.candidate_id "
                      "WHERE c.job_id=? AND r.status='approved'", job_id)["n"]
    return page(request, "export.html", job=job, root=root, packages=packages, approved=approved, skipped=skipped,
                task=TASKS.get(f"export:{job_id}", {}), error=error, can_open=hasattr(os, "startfile"))


@app.post("/jobs/{job_id}/export")
def run_export(job_id: str):
    _job_or_404(job_id)
    n = db.one("SELECT COUNT(*) AS n FROM reviews r JOIN candidates c ON c.id=r.candidate_id "
               "WHERE c.job_id=? AND r.status='approved'", job_id)["n"]
    if not n:
        return RedirectResponse(f"/jobs/{job_id}/export?error=Approve+at+least+one+clip+first.", 303)
    _bg(f"export:{job_id}", lambda: pipeline.export(job_id))
    return RedirectResponse(f"/jobs/{job_id}/export", 303)


@app.post("/jobs/{job_id}/export/open")
def open_folder(job_id: str):
    _job_or_404(job_id)
    root = _export_root(job_id)
    if root.exists() and hasattr(os, "startfile"):
        os.startfile(root)
    return RedirectResponse(f"/jobs/{job_id}/export", 303)


@app.post("/jobs/{job_id}/clips/{cid}/posted")
def posted(job_id: str, cid: int, facebook_url: str = Form(""), youtube_url: str = Form(""), notes: str = Form("")):
    _job_or_404(job_id), _clip_or_404(job_id, cid)
    db.update_review(cid, posted={"facebook_url": facebook_url.strip(), "youtube_url": youtube_url.strip(),
                                  "notes": notes.strip()})
    return RedirectResponse(f"/jobs/{job_id}/export", 303)


# ---------- media (Range-capable, confined to DATA) ----------

@app.get("/media/{rel:path}")
def media_file(rel: str):
    root = config.DATA.resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Not found")
    return FileResponse(path)
