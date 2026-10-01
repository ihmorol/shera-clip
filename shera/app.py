"""Local web UI: server-rendered pages over the pipeline. Binds to loopback only."""
import json
import os
import re
import shutil
import string
import threading
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shera import candidates as cand
from shera import config, db, ledger, media, pipeline, providers, zoom

HERE = Path(__file__).parent
STAGES = ("import", "transcript", "authorize", "transcribe", "translate", "candidates", "score", "prepare", "review")
CATEGORIES = {"exam_tip": "Exam tip", "worked_example": "Worked example",
              "common_mistake": "Common mistake and correction", "vocabulary": "Vocabulary/phrase",
              "practice_exercise": "Practice exercise", "other": "Other"}
STAGE_LABELS = {"import": "Copy recording", "transcript": "Check transcript", "authorize": "Approve cost",
                "transcribe": "Transcribe", "translate": "Translate", "candidates": "Find moments", "score": "Score moments",
                "prepare": "Draft posts", "review": "Review clips"}
STATUS_LABELS = {"running": "Working", "waiting": "Needs you", "paused": "Paused", "failed": "Failed",
                 "done": "Ready", "pending": "To review", "approved": "Approved", "rejected": "Rejected"}
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
    """Shortlist by rank, then everything else by the decision-model score, best first
    (unscored last), so the operator scans left-out moments in the same order of promise."""
    cs = db.candidates(job_id)
    short = sorted((c for c in cs if c["shortlisted"]), key=lambda c: c["rank"])
    other = sorted((c for c in cs if not c["shortlisted"]),
                   key=lambda c: (-(c["score"] if c["score"] is not None else -1.0), c["start"]))
    return short, other


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
templates.env.globals.update(CATEGORIES=CATEGORIES, CAP=config.CAP_USD, STAGES=STAGES,
                             STAGE_LABELS=STAGE_LABELS, STATUS_LABELS=STATUS_LABELS, zoom_time=zoom.local_time)


# ---------- plain-words reasons, from the same rubric Jev scored against ----------

SHORT = {"value": ("no teaching value", "little teaching value", "some teaching value", "a clear teaching point",
                   "a strong teaching point"),
         "clarity": ("needs missing context", "leans on earlier context", "some unclear references",
                     "mostly stands alone", "fully stands alone"),
         "opening": ("starts mid-thought", "weak start", "plain start", "good start", "strong hook")}
LABELS = {"value": "Teaching value", "clarity": "Stands alone", "opening": "Opening"}
SENTENCE = re.compile(r"(.+?[.?!।])(\s|$)")


def _level(v):
    return min(4, max(0, int(float(v) + 0.5)))


def opening_line(text, limit=110):
    """The clip's first sentence, as spoken."""
    m = SENTENCE.match(text.strip())
    first = (m.group(1) if m else text).strip()
    return first if len(first) <= limit else first[:limit - 1].rsplit(" ", 1)[0] + "…"


def explain(c, drafts=None):
    """Why a candidate was suggested, in the scorer's own terms, plus what it teaches."""
    d = drafts if drafts and "error" not in drafts else {}
    post = d.get("youtube") or d.get("facebook") or {}
    opens, opens_en = opening_line(c["text"] or ""), opening_line(c.get("text_en") or "")
    out = {"what": post.get("title") or "", "summary": post.get("description") or "", "opens": opens,
           "opens_en": opens_en if opens_en and opens_en != opens else "", "why": "", "reasons": []}
    if c["score"] is None:
        return out
    cat = c["category"] or "other"
    speaker = [] if c.get("teacher") is None else ["teacher talking" if c["teacher"] >= 0.5 else "played recording"]
    out["why"] = " · ".join([CATEGORIES.get(cat, cat)] + speaker +
                            [SHORT[q][_level(c[q])] for q in ("value", "clarity", "opening")])
    out["reasons"] = [{"label": LABELS[q], "score": f"{c[q]:.1f}/4", "text": providers.JEV_QUESTIONS[q]["criteria"][_level(c[q])]}
                      for q in ("value", "clarity", "opening")]
    for q, label in (("teacher", "Who is speaking"), ("complete", "Finishes its point")):
        if c.get(q) is not None:
            yes = c[q] >= 0.5
            out["reasons"].append({"label": label, "score": f"{c[q] * 100:.0f}%",
                                   "text": providers.JEV_QUESTIONS[q]["criteria"]["true" if yes else "false"]})
    out["category"] = f"{CATEGORIES.get(cat, cat)}: {providers.CATEGORIES.get(cat, '')}"
    return out


def left_out(c, short):
    """Why a scored candidate is not on the shortlist (mirrors candidates.shortlist, D33: no count cap)."""
    if c["score"] is None:
        return "Not scored"
    low = [SHORT[q][_level(c[q])] for q in ("value", "clarity") if (c[q] or 0) < 2]
    if low:
        return "Left out: " + " and ".join(low)
    if not cand.is_teacher(c):
        return f"Left out: a played recording, not the teacher (Jev: {c['teacher'] * 100:.0f}% teacher)"
    off, private_ = cand.jev(c, "offtopic"), cand.jev(c, "private")
    if (off or 0) >= 0.5:
        return "Left out: off-topic chatter, not teaching"
    if (private_ or 0) >= 0.5:
        return "Left out: a student's private details"
    if cand.jev(c, "postable") is not None and cand.jev(c, "postable") < 2:
        return "Left out: too thin to post on its own"
    over = next((k for k in short if min(c["end"], k["end"]) - max(c["start"], k["start"]) > 0), None)
    if over:
        return f"Left out: overlaps clip {over['rank']}, which scored higher"
    again = cand.repeat_of(c, short)
    return f"Left out: repeats clip {again['rank']}" if again else "Left out: below the shortlist cut for this class"


QUESTION_LABELS = {"value": "Teaching value", "clarity": "Stands alone", "opening": "Opening hook",
                   "teacher": "Teacher talking (not a played recording)", "complete": "Finishes its point",
                   "category": "Category"}


def jev_answers(c):
    """Jev's full reply for a clip, question by question, for the reviewer to read."""
    raw = c.get("jev") or {}
    rows = []
    for q, spec in providers.JEV_QUESTIONS.items():
        a = raw.get(q)
        if not a:
            continue
        row = {"label": QUESTION_LABELS.get(q, q), "asked": spec["instructions"], "confidence": a.get("confidence"),
               "options": []}
        if spec["type"] == "score":
            row["answer"] = f"{float(a['score']):.2f} of {len(spec['criteria']) - 1}"
            legend = a.get("legend") or {str(i): t for i, t in enumerate(spec["criteria"])}
            row["options"] = [(f"{k} · {legend.get(k, '')}", p) for k, p in (a.get("probabilities") or {}).items()]
        elif spec["type"] == "noul":
            row["answer"] = f"{float(a['noul']) * 100:.0f}% yes"
            row["options"] = [("yes · " + spec["criteria"]["true"], float(a["noul"])),
                              ("no · " + spec["criteria"]["false"], 1 - float(a["noul"]))]
        else:
            row["answer"] = CATEGORIES.get(a.get("choice"), a.get("choice"))
            row["options"] = [(CATEGORIES.get(k, k), p) for k, p in (a.get("probabilities") or {}).items()]
        row["options"] = sorted(((t, float(p)) for t, p in row["options"]), key=lambda x: -x[1])
        rows.append(row)
    return rows


templates.env.globals.update(explain=explain, left_out=left_out, jev_answers=jev_answers)


def page(request, name, status_code=200, **ctx):
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


# ---------- home + import ----------

def _home(request, error=None, form=None, status_code=200):
    inbox = []
    if config.INBOX.is_dir():
        for f in sorted(config.INBOX.iterdir()):
            if f.is_file() and f.suffix.lower() == ".mp4":
                vtt, m4a = f.with_suffix(".vtt"), f.with_suffix(".m4a")
                inbox.append({"path": f, "size": f.stat().st_size, "vtt": vtt if vtt.exists() else None,
                              "m4a": m4a if m4a.exists() else None})
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


def _drive_roots():
    """Starting places for the chooser: drive letters on Windows, else root, plus common folders."""
    roots = []
    if os.name == "nt":
        roots += [{"name": f"{letter}:\\", "path": f"{letter}:\\"}
                  for letter in string.ascii_uppercase if Path(f"{letter}:\\").exists()]
    else:
        roots.append({"name": "/", "path": "/"})
    seen = {r["path"] for r in roots}
    home = Path.home()
    for label, p in (("Inbox", config.INBOX), ("Videos", home / "Videos"), ("Zoom recordings", home / "Documents" / "Zoom"),
                     ("Desktop", home / "Desktop"), ("Downloads", home / "Downloads"), ("Home", home)):
        try:
            if str(p) not in seen and p.is_dir():
                seen.add(str(p))
                roots.append({"name": label, "path": str(p)})
        except OSError:  # an unreadable profile folder is simply not offered
            pass
    return roots


PICKABLE = (".mp4", ".m4a", ".vtt")


def _enumerate(path, ext):
    dirs, files = [], []
    with os.scandir(path) as it:
        for e in it:
            if e.name.startswith((".", "$")):  # hidden and system folders only add noise
                continue
            if e.is_dir():
                dirs.append({"name": e.name, "path": e.path})
            elif e.is_file() and e.name.lower().endswith(ext):
                files.append({"name": e.name, "path": e.path})
    dirs.sort(key=lambda d: d["name"].casefold())
    files.sort(key=lambda f: f["name"].casefold())
    return dirs, files


@app.get("/browse")
def browse(path: str = "", ext: str = ".mp4"):
    """Read-only folder listing for the import chooser: folders to open, plus the files of one type to pick."""
    if ext not in PICKABLE:
        raise HTTPException(422, f"ext must be one of {', '.join(PICKABLE)}")
    path = path.strip().strip('"')
    if not path:
        return {"path": "", "parent": None, "dirs": _drive_roots(), "files": []}
    p = Path(path)
    if not p.is_dir():
        raise HTTPException(404, "That folder does not exist or cannot be read")
    try:
        dirs, files = _enumerate(p, ext)
    except OSError as e:
        raise HTTPException(403, f"Cannot read that folder: {e.strerror or e}")
    parent = str(p.parent)
    return {"path": str(p), "parent": parent if parent != str(p) else None, "dirs": dirs, "files": files}


@app.post("/import")
def import_(request: Request, mp4: str = Form(""), vtt: str = Form(""), m4a: str = Form("")):
    form = {"mp4": mp4, "vtt": vtt, "m4a": m4a}
    if not mp4.strip():
        return _home(request, "Enter the path to the class MP4.", form, 400)
    src, err = _check_file(mp4, ".mp4", "Recording")
    if not err and vtt.strip():
        vtt_path, err = _check_file(vtt, ".vtt", "Transcript")
    else:
        vtt_path = None
    m4a_path = None
    if not err and m4a.strip():
        m4a_path, err = _check_file(m4a, ".m4a", "Zoom audio")
    if err:
        return _home(request, err, form, 400)
    job_id = pipeline.start_job(src, vtt_path, m4a_path)
    return RedirectResponse(f"/jobs/{job_id}", 303)


# ---------- Zoom cloud recordings (phase 2, D15) ----------

def _zoom_page(request, to=None, error=None, status_code=200):
    """Lists the account's cloud recordings on open and on Refresh; no webhook (local-only MVP)."""
    to = to or date.today()
    ctx = {"configured": zoom.configured(), "to": to, "start": to - timedelta(days=30), "occ": [], "error": error}
    if ctx["configured"]:
        try:
            ctx["start"], ctx["occ"] = zoom.recordings(to)
        except zoom.ZoomError as e:
            ctx["error"] = error or str(e)
    return page(request, "zoom.html", status_code, earlier=ctx["start"] - timedelta(days=1), **ctx)


@app.get("/zoom")
def zoom_list(request: Request, to: str = ""):
    try:
        day = date.fromisoformat(to) if to else None
    except ValueError:
        raise HTTPException(422, "to must be a date like 2026-09-27")
    return _zoom_page(request, day)


@app.post("/zoom/import")
def zoom_import(request: Request, uuid: str = Form(...), mp4: str = Form(...), vtt: str = Form(""), m4a: str = Form("")):
    try:
        _, title = zoom.checked_occurrence(uuid, mp4, vtt, m4a)  # the form's file ids must still be completed files
    except zoom.ZoomError as e:
        return _zoom_page(request, error=str(e), status_code=400)
    job_id = pipeline.start_zoom_job(uuid, title, mp4, vtt=vtt or None, m4a=m4a or None)
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
                translate_model=config.TRANSLATE_MODEL,
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


@app.post("/jobs/{job_id}/redo")
def redo(request: Request, job_id: str):
    _job_or_404(job_id)
    try:
        pipeline.redo(job_id)
    except ValueError as e:
        return _job_page(request, job_id, str(e), 409)
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
    ok = pipeline.preview_current(rv)
    return {"status": rv["status"], "preview_ok": ok,
            "preview_url": _media_url(rv["preview_path"]) if ok else None,
            "landscape_url": _media_url(pipeline.landscape_path(rv["preview_path"])) if ok else None,
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
                about=explain(c, rv["drafts"]), n_short=len(short), not_chosen=None if c["shortlisted"] else left_out(c, short),
                source_url=_media_url(pipeline.media_path(job_id)),
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


@app.get("/jobs/{job_id}/clips/{cid}/frame.jpg")
def clip_frame(job_id: str, cid: int):
    """A small still from a few seconds into the clip, for the contact sheet (made once, then cached)."""
    _job_or_404(job_id)
    c = _clip_or_404(job_id, cid)
    out = pipeline.job_dir(job_id) / "frames" / f"{cid}-{c['start']:.1f}.jpg"
    if not out.exists():
        try:
            media.thumbnail(pipeline.media_path(job_id), out, c["start"] + min(6.0, (c["end"] - c["start"]) / 3), width=480)
        except RuntimeError:
            raise HTTPException(404, "No frame")
    return FileResponse(out, headers={"Cache-Control": "max-age=86400"})


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
                             "video_url": _media_url(folder / "portrait.mp4") if (folder / "portrait.mp4").exists() else None,
                             "landscape_url": _media_url(folder / "landscape.mp4") if (folder / "landscape.mp4").exists() else None})
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
