"""Resumable job runner: import -> transcript -> authorize -> transcribe -> candidates -> score -> prepare -> review."""
import contextlib
import hashlib
import json
import shutil
import threading
import time
import uuid
from pathlib import Path

from shera import candidates as cand
from shera import config, db, ledger, media, providers, transcript

_running = set()
_lock = threading.Lock()


def job_dir(job_id):
    return config.JOBS / job_id


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, data):
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def start_job(src_mp4, vtt=None):
    job_id = uuid.uuid4().hex[:12]
    db.x("INSERT INTO jobs(id, created, title, source_path, vtt_path, stage, status, progress, flags) "
         "VALUES (?, ?, ?, ?, ?, 'import', 'running', 0, '[]')",
         job_id, time.time(), Path(src_mp4).stem, str(src_mp4), str(vtt) if vtt else None)
    _spawn(job_id)
    return job_id


def _spawn(job_id):
    threading.Thread(target=run, args=(job_id,), daemon=True).start()


def resume(job_id):
    db.update_job(job_id, status="running", error=None)
    _spawn(job_id)


def authorize(job_id):
    """The operator saw the estimate and authorizes paid calls up to the hard cap."""
    db.update_job(job_id, authorized_usd=config.CAP_USD)
    resume(job_id)


def on_start():
    db.init()
    ledger.recover_on_start()
    for job in db.list_jobs():
        if job["status"] == "running":
            _spawn(job["id"])


def run(job_id):
    with _lock:
        if job_id in _running:
            return
        _running.add(job_id)
    try:
        db.update_job(job_id, status="running", error=None)
        for stage in (_import, _transcript, _authorize, _transcribe, _candidates, _score, _prepare):
            if stage(job_id) is False:
                return  # waiting for the operator
        db.update_job(job_id, stage="review", status="done", progress=1.0)
    except (ledger.BudgetStop, ledger.Indeterminate) as e:
        db.update_job(job_id, status="paused", error=str(e))
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e) or type(e).__name__)
    finally:
        with _lock:
            _running.discard(job_id)


def _import(job_id):
    job, d = db.get_job(job_id), job_dir(job_id)
    d.mkdir(parents=True, exist_ok=True)
    src = d / "source.mp4"
    db.update_job(job_id, stage="import")
    if not job["source_sha256"] or not src.exists():
        sha, n = media.copy_with_hash(Path(job["source_path"]), src, lambda f: db.update_job(job_id, progress=f))
        db.update_job(job_id, source_sha256=sha, source_bytes=n)
    if job["vtt_path"] and not (d / "source.vtt").exists():
        shutil.copyfile(job["vtt_path"], d / "source.vtt")
    if job["duration"] is None:
        p = media.probe(src)
        if not p.get("vcodec") or not p.get("width"):
            raise ValueError("The file has no readable video stream. Pick the Zoom MP4 recording.")
        if not p.get("has_audio"):
            raise ValueError("The recording has no audio track. Pick the MP4 that includes the class audio.")
        db.update_job(job_id, duration=p["duration"], width=p["width"], height=p["height"])


def _speech(job_id):
    path = job_dir(job_id) / "speech.json"
    if not path.exists():
        _write(path, media.speech_intervals(job_dir(job_id) / "source.mp4"))
    return [tuple(x) for x in _read(path)]


def _transcript(job_id):
    d, job = job_dir(job_id), db.get_job(job_id)
    if (d / "transcript.json").exists():
        return
    db.update_job(job_id, stage="transcript")
    if not (d / "source.vtt").exists():
        db.update_job(job_id, flags=["no VTT transcript; paid transcription needed"])
        return
    units = transcript.parse_vtt((d / "source.vtt").read_text(encoding="utf-8-sig"))
    flags = transcript.check_alignment(units, _speech(job_id), job["duration"])
    if flags:
        db.update_job(job_id, flags=flags + ["VTT unusable; paid transcription needed"])
        return
    _write(d / "transcript.json", {"source": "local_vtt", "units": units, "flags": []})
    db.update_job(job_id, transcript_source="local_vtt", flags=[])


def _units(job_id):
    return _read(job_dir(job_id) / "transcript.json")["units"]


def estimate(job_id):
    """Estimate breakdown shown before authorization: USD per paid step plus the window count."""
    job = db.get_job(job_id)
    has_t = (job_dir(job_id) / "transcript.json").exists()
    windows = len(cand.build_windows(_units(job_id))) if has_t else int(job["duration"] // 20) + 1
    return {"transcription": 0.0 if has_t else job["duration"] / 60 * config.WHISPER_USD_PER_MIN,
            "ranking": config.JEV_EST_USD * windows, "drafts": config.DRAFT_EST_USD * 10, "windows": windows}


def _authorize(job_id):
    job = db.get_job(job_id)
    if job["authorized_usd"] is not None:
        return
    e = estimate(job_id)
    est = e["transcription"] + e["ranking"] + e["drafts"]
    db.update_job(job_id, stage="authorize", status="waiting", estimate_usd=round(est, 4))
    return False


def _transcribe(job_id):
    d, job = job_dir(job_id), db.get_job(job_id)
    if (d / "transcript.json").exists():
        return
    db.update_job(job_id, stage="transcribe", progress=0)
    chunks = media.audio_chunks(d / "source.mp4", d / "audio", _speech(job_id))
    results = []
    for i, (path, offset) in enumerate(chunks):
        end = chunks[i + 1][1] if i + 1 < len(chunks) else job["duration"]
        est = (end - offset) / 60 * config.WHISPER_USD_PER_MIN
        results.append((offset, ledger.call(job_id, f"whisper:{i}", "whisper", est,
                                            lambda p=path: providers.whisper(p))))
        db.update_job(job_id, progress=(i + 1) / len(chunks))
    units, flags = transcript.units_from_whisper(results)
    _write(d / "transcript.json", {"source": "whisper-1", "units": units, "flags": flags})
    db.update_job(job_id, transcript_source="whisper-1", flags=job["flags"] + flags)


def _candidates(job_id):
    if db.candidates(job_id):
        return
    db.update_job(job_id, stage="candidates")
    units = _units(job_id)
    rows = [(job_id, u0, u1, units[u0]["start"], units[u1]["end"], " ".join(u["text"] for u in units[u0:u1 + 1]))
            for u0, u1 in cand.build_windows(units)]
    with db.LOCK:  # all rows or none
        c = db.connect()
        c.execute("BEGIN")
        c.executemany('INSERT INTO candidates(job_id, u0, u1, start, "end", text) VALUES (?, ?, ?, ?, ?, ?)', rows)
        c.execute("COMMIT")


def _score(job_id):
    db.update_job(job_id, stage="score", progress=0)
    cands = db.candidates(job_id)
    for n, c in enumerate(cands):
        if c["score"] is None:
            r = ledger.call(job_id, f"jev:{c['id']}", "jev", config.JEV_EST_USD,
                            lambda c=c: providers.jev_score(c["text"]))
            db.x("UPDATE candidates SET value=?, clarity=?, opening=?, category=?, score=? WHERE id=?",
                 r["value"], r["clarity"], r["opening"], r["category"],
                 cand.rank_score(r["value"], r["clarity"], r["opening"]), c["id"])
        db.update_job(job_id, progress=(n + 1) / len(cands))
    ids = cand.shortlist(db.candidates(job_id))
    db.x("UPDATE candidates SET shortlisted=0, rank=NULL WHERE job_id=?", job_id)
    for rank, cid in enumerate(ids, 1):
        db.x("UPDATE candidates SET shortlisted=1, rank=? WHERE id=?", rank, cid)


def ensure_review(cid):
    """Review row with default captions and full-frame layout filled in."""
    rv, c = db.review(cid), db.candidate(cid)
    if rv["category"] is None and c["category"]:  # review opened before scoring
        db.update_review(cid, category=c["category"])
        rv = db.review(cid)
    if rv["captions"] is None:
        caps = cand.caption_lines(_units(c["job_id"]), c["u0"], c["u1"], rv["start"], rv["end"])
        db.update_review(cid, captions=caps, layout=rv["layout"] or {"mode": "full"})
        rv = db.review(cid)
    return rv


def drafts_open(d):
    """True when drafts may be (re)filled: nothing stored, a provider error, or only empty fields."""
    return not d or "error" in d or not any(v for p in ("facebook", "youtube") for v in (d.get(p) or {}).values())


def draft(cid):
    """Paid posting draft for one candidate; a provider failure is stored, never replaced by made-up text.
    Text the operator typed meanwhile is never overwritten."""
    c = db.candidate(cid)
    try:
        d = ledger.call(c["job_id"], f"draft:{cid}", "draft", config.DRAFT_EST_USD,
                        lambda: providers.draft_post(c["text"], c["category"]))
    except ledger.ProviderError as e:
        d = {"error": str(e)}
    with db.LOCK:
        current = db.review(cid)["drafts"]
        if not drafts_open(current):
            return current
        db.update_review(cid, drafts=d)
    return d


def _prepare(job_id):
    db.update_job(job_id, stage="prepare", progress=0)
    short = sorted((c for c in db.candidates(job_id) if c["shortlisted"]), key=lambda c: c["rank"])
    for n, c in enumerate(short):
        rv = ensure_review(c["id"])
        in_flight = db.one("SELECT id FROM paid_calls WHERE job_id=? AND key=? AND state='sent'", job_id, f"draft:{c['id']}")
        if drafts_open(rv["drafts"]) and not in_flight:  # an in-flight web draft task owns that call
            draft(c["id"])
        db.update_job(job_id, progress=(n + 1) / len(short))


def delete_job(job_id):
    with _lock:
        if job_id in _running:
            raise ValueError("The job is still running; wait for it to pause or finish.")
    db.x("DELETE FROM reviews WHERE candidate_id IN (SELECT id FROM candidates WHERE job_id=?)", job_id)
    db.x("DELETE FROM candidates WHERE job_id=?", job_id)
    db.x("DELETE FROM paid_calls WHERE job_id=?", job_id)
    db.x("DELETE FROM jobs WHERE id=?", job_id)
    shutil.rmtree(job_dir(job_id), ignore_errors=True)
    shutil.rmtree(config.DATA / "exports" / job_id, ignore_errors=True)
    shutil.rmtree(config.DATA / "exports" / (job_id + ".part"), ignore_errors=True)


def state_hash(rv):
    """Fingerprint of everything that changes the rendered video; the preview file name carries it."""
    vals = [rv["start"], rv["end"], rv["layout"] or {"mode": "full"}, rv["captions"] or [], rv["title"] or ""]
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode()).hexdigest()[:12]


def preview_current(rv):
    """True when the saved preview was rendered from the review's current saved state."""
    p = rv["preview_path"] and Path(rv["preview_path"])
    return bool(p) and p.name == f"{rv['candidate_id']}-{state_hash(rv)}.mp4" and p.exists()


def render_preview(cid):
    rv, c = ensure_review(cid), db.candidate(cid)
    out = job_dir(c["job_id"]) / "previews" / f"{cid}-{state_hash(rv)}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    media.render(job_dir(c["job_id"]) / "source.mp4", rv["start"], rv["end"], rv["layout"], rv["captions"],
                 rv["title"] or "", out)
    db.update_review(cid, preview_path=str(out))
    for old in out.parent.glob(f"{cid}-*.mp4"):
        if old != out:
            with contextlib.suppress(OSError):  # a browser may still hold the old file open
                old.unlink()
    return out


def _srt_time(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def srt(captions):
    return "\n".join(f"{i}\n{_srt_time(c['start'])} --> {_srt_time(c['end'])}\n{c['text']}\n"
                     for i, c in enumerate(captions, 1))


def export(job_id):
    """Package approved reviews into DATA/exports/<job_id>/; returns that folder.
    Builds in a .part folder and swaps it in on success, so a failed export keeps the previous package.
    Approved clips whose preview no longer matches the saved edits are skipped and listed in skipped.json."""
    job, root = db.get_job(job_id), config.DATA / "exports" / job_id
    tmp = root.with_name(job_id + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    index, skipped = [], []
    for c in db.candidates(job_id):
        rv = db.one("SELECT * FROM reviews WHERE candidate_id=? AND status='approved'", c["id"])
        if not rv:
            continue
        if not preview_current(rv):
            skipped.append({"candidate_id": c["id"], "rank": c["rank"],
                            "reason": "approved, but its preview does not match the saved edits; render and approve again"})
            continue
        folder = tmp / f"{c['rank'] or 0:02d}-{c['id']}"
        folder.mkdir(parents=True)
        video = folder / "video.mp4"
        media.render(job_dir(job_id) / "source.mp4", rv["start"], rv["end"], rv["layout"], rv["captions"],
                     rv["title"] or "", video, preset="medium")
        (folder / "captions.srt").write_text(srt(rv["captions"] or []), encoding="utf-8")
        media.thumbnail(video, folder / "thumbnail.jpg", (rv["end"] - rv["start"]) / 2)
        drafts = rv["drafts"] or {}
        post = {"job_id": job_id, "candidate_id": c["id"], "rank": c["rank"], "category": rv["category"],
                "tags": rv["tags"] or [], "facebook": drafts.get("facebook"), "youtube": drafts.get("youtube"),
                "source_sha256": job["source_sha256"], "source_start": rv["start"], "source_end": rv["end"],
                "problems": media.verify(video, rv["end"] - rv["start"])}
        (folder / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"folder": folder.name, "candidate_id": c["id"], "rank": c["rank"], "problems": post["problems"]})
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp / "skipped.json").write_text(json.dumps(skipped, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(root, ignore_errors=True)
    tmp.rename(root)
    return root
