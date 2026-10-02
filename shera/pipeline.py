"""Resumable job runner: import -> transcript -> authorize -> transcribe -> candidates -> score -> prepare -> review."""
import contextlib
import hashlib
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from shera import candidates as cand
from shera import config, db, ledger, media, providers, transcript, zoom

_running = set()
_lock = threading.Lock()
inline = False  # CLI mode: run jobs in the calling thread so the process waits for them


def job_dir(job_id):
    return config.JOBS / job_id


def media_path(job_id):
    """What every later step reads: the video with the Zoom audio lined up (media.mp4), else the copied source."""
    d = job_dir(job_id)
    return d / "media.mp4" if (d / "media.mp4").exists() else d / "source.mp4"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path, data):
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def start_job(src_mp4, vtt=None, audio=None, title=None):
    """audio: optional separate recording of the class sound (Zoom M4A); it replaces the video's own audio."""
    job_id = uuid.uuid4().hex[:12]
    db.x("INSERT INTO jobs(id, created, title, source_path, vtt_path, audio_path, stage, status, progress, flags) "
         "VALUES (?, ?, ?, ?, ?, ?, 'import', 'running', 0, '[]')",
         job_id, time.time(), title or Path(src_mp4).stem, str(src_mp4),
         str(vtt) if vtt else None, str(audio) if audio else None)
    _spawn(job_id)
    return job_id


def start_zoom_job(meeting_uuid, title, mp4, vtt=None, m4a=None):
    """A Zoom cloud recording: the chosen files (Zoom file ids) are downloaded into the job folder by _import,
    after which the job reads them exactly like a local import."""
    job_id = uuid.uuid4().hex[:12]
    d = job_dir(job_id)
    db.x("INSERT INTO jobs(id, created, title, source_path, vtt_path, audio_path, stage, status, progress, flags, zoom) "
         "VALUES (?, ?, ?, ?, ?, ?, 'import', 'running', 0, '[]', ?)",
         job_id, time.time(), title, str(d / "source.mp4"), str(d / "source.vtt") if vtt else None,
         str(d / "zoom.m4a") if m4a else None, json.dumps({"uuid": meeting_uuid, "mp4": mp4, "vtt": vtt, "m4a": m4a}))
    _spawn(job_id)
    return job_id


def _spawn(job_id):
    if inline:
        run(job_id)
    else:
        threading.Thread(target=run, args=(job_id,), daemon=True).start()


def resume(job_id):
    db.update_job(job_id, status="running", error=None)
    _spawn(job_id)


def authorize(job_id):
    """The operator saw the estimate and authorizes paid calls up to the hard cap."""
    db.update_job(job_id, authorized_usd=config.CAP_USD)
    resume(job_id)


def recover():
    """CLI-side recovery: DB init plus reaping in-flight calls that no runner can own.
    The server's on_start instead runs the full recover_on_start: at a process start the
    previous runner is gone, so every 'sent' row becomes resolvable."""
    db.init()
    ledger.reap_orphans()


def on_start():
    """Server startup: DB init, then every 'sent' call becomes resolvable and running jobs re-spawn.
    The global reap is safe here because the previous runner process is presumed gone; the CLI
    instead reaps conservatively (recover/reap_orphans) since another process may be live."""
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
        for stage in (_import, _transcript, _authorize, _transcribe, _translate, _candidates, _score, _prepare):
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
    if job["zoom"]:
        _download(job_id, job, d)
        job = db.get_job(job_id)
    if not job["source_sha256"] or not src.exists():
        need = Path(job["source_path"]).stat().st_size  # the copy and its transcript/audio extras together
        for extra in (job["vtt_path"], job["audio_path"]):
            if extra:
                need += Path(extra).stat().st_size
        media.ensure_free(need)
        sha, n = media.copy_with_hash(Path(job["source_path"]), src, lambda f: db.update_job(job_id, progress=f))
        db.update_job(job_id, source_sha256=sha, source_bytes=n)
    if job["vtt_path"] and not (d / "source.vtt").exists():
        shutil.copyfile(job["vtt_path"], d / "source.vtt")
    if job["duration"] is None:
        p = media.probe(src)
        if not p.get("vcodec") or not p.get("width"):
            raise ValueError("The file has no readable video stream. Pick the Zoom MP4 recording.")
        if not p.get("has_audio") and not job["audio_path"]:
            raise ValueError("The recording has no audio track. Pick the MP4 that includes the class audio, "
                             "or add the class's Zoom audio (.m4a).")
        db.update_job(job_id, duration=p["duration"], width=p["width"], height=p["height"])
        job = db.get_job(job_id)
    if job["audio_path"] and not (d / "media.mp4").exists():
        _attach_audio(job_id, job, d)


def _download(job_id, job, d):
    """Fetch the chosen Zoom files; each lands under its final name only when complete, so a resume skips it."""
    z = job["zoom"]
    if not job["source_sha256"] or not (d / "source.mp4").exists():
        sha, n = zoom.download(z["uuid"], z["mp4"], d / "source.mp4", lambda f: db.update_job(job_id, progress=f))
        db.update_job(job_id, source_sha256=sha, source_bytes=n)
    for kind, name in (("vtt", "source.vtt"), ("m4a", "zoom.m4a")):
        if z.get(kind) and not (d / name).exists():
            zoom.download(z["uuid"], z[kind], d / name)


def _attach_audio(job_id, job, d):
    """Line the Zoom M4A up with the video and stream-copy both into media.mp4 (audio samples untouched)."""
    zoom = d / "zoom.m4a"
    if not zoom.exists():
        shutil.copyfile(job["audio_path"], zoom)
    a = media.probe(zoom)
    if not a.get("has_audio"):
        raise ValueError("The .m4a file has no audio stream. Pick the Zoom audio recording of this class.")
    offset, how = media.sync_offset(d / "source.mp4", zoom)
    covered = min(job["duration"], a["duration"] - offset) - max(0.0, -offset)
    if covered < 0.5 * job["duration"]:
        raise ValueError(f"The Zoom audio covers only {max(covered, 0) / 60:.0f} of {job['duration'] / 60:.0f} min "
                         "of this video. Check that the .m4a is from the same class.")
    media.mux_audio(d / "source.mp4", zoom, offset, d / "media.mp4")
    note = {"sound": f"Zoom audio lined up by matching sound ({offset:+.2f} s)",
            "clock": f"Zoom audio lined up by recording clocks ({offset:+.0f} s, about 1 s accuracy): check lip sync",
            "none": "Zoom audio could not be lined up automatically; assumed it starts with the video: check sync"}[how]
    flags = job["flags"] + [note] + ([f"Zoom audio covers {covered / 60:.0f} of {job['duration'] / 60:.0f} min"]
                                     if covered < job["duration"] - 1 else [])
    db.update_job(job_id, audio_offset=offset, flags=flags)


def _speech(job_id):
    path = job_dir(job_id) / "speech.json"
    if not path.exists():
        _write(path, media.speech_intervals(media_path(job_id)))
    _peaks(job_id)
    return [tuple(x) for x in _read(path)]


def _peaks(job_id):
    """Cache the review waveform's peaks once per job, only when the media has an audio stream."""
    d = job_dir(job_id)
    if (d / "peaks.json").exists() or not media.probe(media_path(job_id))["has_audio"]:
        return
    _write(d / "peaks.json", media.peaks(media_path(job_id)))


def peaks_cached(job_id):
    """The job's cached waveform peaks, or [] when none were computed (no audio stream, or pre-waveform job)."""
    p = job_dir(job_id) / "peaks.json"
    return _read(p) if p.exists() else []


def check_audible(speech, duration):
    """Stop before any paid step when the recording is (nearly) silent: transcribing silence
    bills for nothing and makes Whisper invent text."""
    heard = sum(e - s for s, e in speech)
    if heard < min(60, 0.05 * duration):
        raise ValueError(f"The recording's audio is silent ({heard:.0f} s of sound in {duration / 60:.0f} min), "
                         "so there is nothing to transcribe. Import it again with the class's Zoom audio (.m4a), "
                         "or pick the MP4 that has the sound. No paid call was made.")


def _transcript(job_id):
    d, job = job_dir(job_id), db.get_job(job_id)
    if (d / "transcript.json").exists():
        return
    db.update_job(job_id, stage="transcript")
    check_audible(_speech(job_id), job["duration"])
    keep = [f for f in job["flags"] if f.startswith("Zoom audio")]  # import notes outlive transcript checks
    if not (d / "source.vtt").exists():
        db.update_job(job_id, flags=keep + ["no VTT transcript; paid transcription needed"])
        return
    units = transcript.parse_vtt((d / "source.vtt").read_text(encoding="utf-8-sig"))
    flags = transcript.check_alignment(units, _speech(job_id), job["duration"])
    if flags:
        db.update_job(job_id, flags=keep + flags + ["VTT unusable; paid transcription needed"])
        return
    _write(d / "transcript.json", {"source": "local_vtt", "units": units, "flags": []})
    db.update_job(job_id, transcript_source="local_vtt", flags=keep)


def _units(job_id):
    return _read(job_dir(job_id) / "transcript.json")["units"]


def estimate(job_id):
    """Estimate breakdown shown before authorization: USD per paid step plus the window count."""
    job = db.get_job(job_id)
    has_t = (job_dir(job_id) / "transcript.json").exists()
    windows = len(cand.build_windows(_units(job_id))) if has_t else int(job["duration"] // 30) + 1
    return {"transcription": 0.0 if has_t else job["duration"] / 60 * config.STT_USD_PER_MIN,
            "translation": job["duration"] / 60 * config.TRANSLATE_USD_PER_MIN,
            "ranking": config.JEV_EST_USD * windows, "drafts": config.DRAFT_EST_USD * 10, "windows": windows}  # nominal ten: the shortlist size is unknown before scoring (D33 uncapped)


def _authorize(job_id):
    job = db.get_job(job_id)
    if job["authorized_usd"] is not None:
        return
    e = estimate(job_id)
    est = e["transcription"] + e["translation"] + e["ranking"] + e["drafts"]
    db.update_job(job_id, stage="authorize", status="waiting", estimate_usd=round(est, 4))
    return False


def _transcribe(job_id):
    d, job = job_dir(job_id), db.get_job(job_id)
    if (d / "transcript.json").exists():
        return
    db.update_job(job_id, stage="transcribe", progress=0)
    chunks = media.audio_chunks(media_path(job_id), d / "audio", _speech(job_id))
    results = []
    for i, (path, offset) in enumerate(chunks):
        end = chunks[i + 1][1] if i + 1 < len(chunks) else job["duration"]
        est = (end - offset) / 60 * config.STT_USD_PER_MIN
        # the key names model and start, so a new model or chunking after "find clips again" is a new call
        results.append((offset, ledger.call(job_id, f"stt:{config.STT_MODEL}:{offset:.1f}", "stt", est,
                                            lambda p=path: providers.transcribe(p))))
        db.update_job(job_id, progress=(i + 1) / len(chunks))
    units, flags = transcript.units_from_whisper(results)
    source = results[0][1].get("model", config.STT_MODEL) if results else config.STT_MODEL
    _write(d / "transcript.json", {"source": source, "units": units, "flags": flags})
    db.update_job(job_id, transcript_source=source, flags=job["flags"] + flags)


BANGLA = re.compile("[ঀ-৿]")
TRANSLATE_BATCH = 50


def _translate(job_id):
    """Paid English translation of every line that is not already English; the words as spoken stay in `text`."""
    d = job_dir(job_id)
    data = _read(d / "transcript.json")
    units = data["units"]
    for u in units:
        if "en" not in u and not BANGLA.search(u["text"]):
            u["en"] = u["text"]
    for attempt in range(2):  # a line the model skips is asked again once, in a new batch
        todo = [i for i, u in enumerate(units) if "en" not in u]
        if not todo:
            break
        db.update_job(job_id, stage="translate", progress=0)
        batches = [todo[k:k + TRANSLATE_BATCH] for k in range(0, len(todo), TRANSLATE_BATCH)]
        for n, batch in enumerate(batches):
            lines = [units[i]["text"] for i in batch]
            key = "tr2:" + hashlib.sha1("\n".join(lines).encode()).hexdigest()[:16]
            est = sum(units[i]["end"] - units[i]["start"] for i in batch) / 60 * config.TRANSLATE_USD_PER_MIN * 3
            r = ledger.call(job_id, key, "translate", est, lambda lines=lines: providers.translate(lines))
            for i, en in zip(batch, r["en"]):
                if en:
                    units[i]["en"] = en
            _write(d / "transcript.json", data)  # keep finished batches if a later one stops
            db.update_job(job_id, progress=(n + 1) / len(batches))
    left = [u for u in units if "en" not in u]
    for u in left:  # still unanswered after two asks: keep the words as spoken rather than stall the class
        u["en"] = u["text"]
    _write(d / "transcript.json", data)
    if left:
        job = db.get_job(job_id)
        db.update_job(job_id, flags=job["flags"] + [f"{len(left)} lines left untranslated (the translator skipped them twice)"])


def _join(units, key):
    return " ".join(u.get(key) or u["text"] for u in units)


def _candidates(job_id):
    if db.candidates(job_id):
        return
    db.update_job(job_id, stage="candidates")
    units = _units(job_id)
    rows = [(job_id, u0, u1, units[u0]["start"], units[u1]["end"], _join(units[u0:u1 + 1], "text"),
             _join(units[u0:u1 + 1], "en")) for u0, u1 in cand.build_windows(units)]
    with db.LOCK:  # all rows or none
        c = db.connect()
        c.execute("BEGIN")
        c.executemany('INSERT INTO candidates(job_id, u0, u1, start, "end", text, text_en) VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
        c.execute("COMMIT")


def _score(job_id):
    db.update_job(job_id, stage="score", progress=0)
    cands = db.candidates(job_id)
    for n, c in enumerate(cands):
        if c["score"] is None:
            r = ledger.call(job_id, f"jev2:{c['id']}", "jev", config.JEV_EST_USD,
                            lambda c=c: providers.jev_score(c["text_en"] or c["text"], c["text"]))
            db.x("UPDATE candidates SET value=?, clarity=?, opening=?, category=?, score=?, teacher=?, complete=?, "
                 "jev=? WHERE id=?", r["value"], r["clarity"], r["opening"], r["category"],
                 cand.rank_score(r["value"], r["clarity"], r["opening"], r.get("postable")), r["teacher"], r["complete"],
                 json.dumps(r["raw"], ensure_ascii=False), c["id"])
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
    skill = ((c["jev"] or {}).get("skill") or {}).get("choice")
    if not rv["tags"] and skill and skill != "general":  # Jev's IELTS part is a sensible first tag
        db.update_review(cid, tags=["IELTS", skill.capitalize()])
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
                        lambda: providers.draft_post(c["text"], c["category"], c["text_en"]))
    except ledger.ProviderError as e:
        d = {"error": str(e)}
    with db.LOCK:
        rv = db.review(cid)
        if not drafts_open(rv["drafts"]):
            return rv["drafts"]
        fields = {"drafts": d}
        if "error" not in d and not rv["title"] and rv["status"] == "pending":  # a clip needs a title to make sense
            fields["title"] = (d["youtube"]["title"] or d["facebook"]["title"]).strip()
        db.update_review(cid, **fields)
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
    _stills(job_id)


def make_frame(job_id, c):
    """The candidate's contact-sheet still (a few seconds in, 480 px wide), made once and then cached;
    the review-page frame endpoint serves exactly this file as its on-demand fallback."""
    out = job_dir(job_id) / "frames" / f"{c['id']}-{c['start']:.1f}.jpg"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        media.thumbnail(media_path(job_id), out, c["start"] + min(6.0, (c["end"] - c["start"]) / 3), width=480)
    return out


def _stills(job_id):
    """Pre-generate every candidate's still so the class page never runs ffmpeg inside a request thread."""
    for c in db.candidates(job_id):
        try:
            make_frame(job_id, c)
        except RuntimeError:  # unreadable media: the endpoint reports "No frame" per clip instead
            pass


def redo(job_id):
    """Find clips again from the recording with the current transcription, translation, and clip rules.
    Keeps the imported media and the paid-call record (earlier spend still counts toward the cap);
    drops the transcript, candidates, reviews, previews, and exports, then asks for cost approval again."""
    with _lock:
        if job_id in _running:
            raise ValueError("The job is still running; wait for it to pause or finish.")
    d = job_dir(job_id)
    db.x("DELETE FROM reviews WHERE candidate_id IN (SELECT id FROM candidates WHERE job_id=?)", job_id)
    db.x("DELETE FROM candidates WHERE job_id=?", job_id)
    (d / "transcript.json").unlink(missing_ok=True)
    for sub in (d / "audio", d / "previews", d / "frames", config.DATA / "exports" / job_id):
        shutil.rmtree(sub, ignore_errors=True)
    keep = [f for f in db.get_job(job_id)["flags"] if f.startswith("Zoom audio")]
    db.update_job(job_id, authorized_usd=None, estimate_usd=None, transcript_source=None,
                  flags=keep, stage="transcript")
    resume(job_id)


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


def landscape_path(portrait):
    """The landscape preview/export sits next to its portrait file."""
    return Path(portrait).with_name(Path(portrait).stem + "-landscape.mp4")


def preview_current(rv):
    """True when both saved previews were rendered from the review's current saved state."""
    p = rv["preview_path"] and Path(rv["preview_path"])
    return (bool(p) and p.name == f"{rv['candidate_id']}-{state_hash(rv)}.mp4" and p.exists()
            and landscape_path(p).exists())


def _render_both(src, rv, portrait, landscape, preset="veryfast"):
    args = (src, rv["start"], rv["end"], rv["layout"], rv["captions"], rv["title"] or "")
    media.render(*args, portrait, preset=preset)
    media.render(*args, landscape, preset=preset, landscape=True)


def render_preview(cid):
    rv, c = ensure_review(cid), db.candidate(cid)
    out = job_dir(c["job_id"]) / "previews" / f"{cid}-{state_hash(rv)}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    _render_both(media_path(c["job_id"]), rv, out, landscape_path(out))
    db.update_review(cid, preview_path=str(out))
    keep = {out, landscape_path(out)}
    for old in out.parent.glob(f"{cid}-*.mp4"):
        if old not in keep:
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
        video = folder / "portrait.mp4"
        _render_both(media_path(job_id), rv, video, folder / "landscape.mp4", preset="medium")
        (folder / "captions.srt").write_text(srt(rv["captions"] or []), encoding="utf-8")
        media.thumbnail(video, folder / "thumbnail.jpg", (rv["end"] - rv["start"]) / 2)
        dur = rv["end"] - rv["start"]
        problems = ([f"portrait: {x}" for x in media.verify(video, dur)] +
                    [f"landscape: {x}" for x in media.verify(folder / "landscape.mp4", dur, (media.H, media.W))])
        drafts = rv["drafts"] or {}
        post = {"job_id": job_id, "candidate_id": c["id"], "rank": c["rank"], "category": rv["category"],
                "tags": rv["tags"] or [], "facebook": drafts.get("facebook"), "youtube": drafts.get("youtube"),
                "source_sha256": job["source_sha256"], "source_start": rv["start"], "source_end": rv["end"],
                "problems": problems}
        (folder / "post.json").write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"folder": folder.name, "candidate_id": c["id"], "rank": c["rank"], "problems": post["problems"]})
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp / "skipped.json").write_text(json.dumps(skipped, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.rmtree(root, ignore_errors=True)
    tmp.rename(root)
    return root
