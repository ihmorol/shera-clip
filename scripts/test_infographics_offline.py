"""Render test infographic videos from existing local jobs without any paid API call.

Picks speech-dense ~80 s windows from each job's recording (skipping the class edges, where the
intro and the goodbye live), transcribes them with local faster-whisper (no provider, no key),
plans scenes with the offline planner, and renders into data/exports/<job>/infographics-test/.
Nothing in the database is touched: no candidates, no reviews, no paid calls.

Run:  python scripts/test_infographics_offline.py [model_size]
"""
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shera import candidates as cand
from shera import config, db, infographics, media, pipeline, transcript

WINDOW_S = 80.0      # one clip's worth of class
STEP_S = 30.0
SKIP_EDGE_S = 120.0  # keep the class intro and ending out of the test windows
PER_JOB = 2          # videos kept per job
AUDITION = 6         # windows tried, best speech first, until PER_JOB pass the transcript check

_model = None


def whisper_model(size):
    global _model
    if _model is None:
        import os
        from faster_whisper import WhisperModel
        print(f"[whisper] loading {size} on CPU (int8, greedy); first run downloads the weights", flush=True)
        _model = WhisperModel(size, device="cpu", compute_type="int8",
                              cpu_threads=max(2, os.cpu_count() or 4))
    return _model


def pick_windows(job_id):
    """Speech-dense, mutually non-overlapping windows away from the class edges. Windows must hold at
    least a minute of detected speech, so a recording whose audio track is dead (an OBS capture that
    needs its Zoom M4A) is skipped instead of transcribed into nothing."""
    speech = pipeline._speech(job_id)
    dur = db.get_job(job_id)["duration"]
    scored = []
    t = SKIP_EDGE_S
    while t + WINDOW_S <= dur - SKIP_EDGE_S:
        coverage = sum(max(0.0, min(e, t + WINDOW_S) - max(s, t)) for s, e in speech)
        if coverage >= 0.4 * WINDOW_S:  # real talk, not just background hiss
            scored.append((coverage, t))
        t += STEP_S
    scored.sort(key=lambda x: -x[0])
    chosen = []
    for coverage, start in scored:
        if all(abs(start - u) >= WINDOW_S for _, u in chosen):
            chosen.append((coverage, start))
        if len(chosen) == AUDITION:
            break
    return sorted(s for _, s in chosen)


def transcribe_window(wav, offset):
    segments, info = whisper_model("base" if len(sys.argv) < 2 else sys.argv[1]).transcribe(
        str(wav), word_timestamps=True, vad_filter=True, beam_size=1,
        condition_on_previous_text=False,  # a noise loop must not feed on itself
        no_speech_threshold=0.6)
    words = [{"start": offset + w.start, "end": offset + w.end, "word": w.word}
             for seg in segments for w in (seg.words or [])]
    print(f"[whisper] language={info.language} p={info.language_probability:.2f} words={len(words)}", flush=True)
    return transcript._lines(words)


def render_one(job_id, win_start, k):
    src = pipeline.media_path(job_id)
    if media._envelope(src, win_start, WINDOW_S).max() < 100:  # ≈ under -50 dBFS: no voice here
        print(f"[skip] window {win_start:.0f}s: the audio is silent", flush=True)
        return None
    wav = config.DATA / f"test-window-{job_id}-{int(win_start)}.wav"
    media._run(["ffmpeg", "-y", "-v", "error", "-ss", f"{win_start:.3f}", "-t", f"{WINDOW_S:.3f}",
                "-i", src, "-map", "0:a:0", "-ac", "1", "-ar", "16000", wav])
    try:
        units = transcribe_window(wav, win_start)  # window-relative times + offset = absolute
    finally:
        wav.unlink(missing_ok=True)
    text = " ".join(u["text"] for u in units)
    alpha = sum(1 for ch in text if "\u0980" <= ch <= "\u09FF" or (ch.isascii() and ch.isalpha()))
    if len(units) < 3 or len(text.split()) < 40 or alpha < 100:
        print(f"[skip] window {win_start:.0f}s: {len(text.split())} words is not real speech", flush=True)
        return None
    end = win_start + WINDOW_S
    lines = infographics.clip_units(units, win_start, end)
    plan = infographics.normalize_plan(infographics.local_plan(lines), len(lines), lines)
    times = infographics.scene_times(plan["scenes"], lines, WINDOW_S)
    idx = [i for i, u in enumerate(units) if u["end"] > win_start and u["start"] < end]
    caps = cand.caption_lines(units, idx[0], idx[-1], win_start, end)

    root = config.DATA / "exports" / job_id / "infographics-test"
    final = root / f"{k:02d}-{int(win_start)}s"
    tmp = final.with_name(final.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "slides").mkdir(parents=True)
    htmls = [infographics.slide_html(sc, n, len(times), headline=plan["headline"],
                                     title=f"Window {int(win_start)}s", category="Test render")
             for n, sc in enumerate(times, 1)]
    t0 = time.time()
    pngs = infographics.render_slides(htmls, tmp / "slides")
    video = tmp / "video.mp4"
    infographics.build_video(pngs, times, caps, src, win_start, WINDOW_S, video, preset="veryfast")
    problems, extra = infographics.qc(video, WINDOW_S)
    media.thumbnail(video, tmp / "poster.jpg", 0.5)
    report = {"folder": final.name, "job_id": job_id, "window": [round(win_start, 1), round(end, 1)],
              "headline": plan["headline"], "duration": WINDOW_S, "scenes": len(times),
              "planner": "local", "transcript": "faster-whisper (local, no API)", **extra,
              "status": "ok" if not problems else "failed", "problems": problems,
              "render_s": round(time.time() - t0, 1)}
    (tmp / "plan.json").write_text(json.dumps({"headline": plan["headline"], "scenes": times},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
    infographics.finalize(tmp, final, report)
    print(f"[done] {final} scenes={len(times)} qc={'ok' if not problems else problems} "
          f"in {report['render_s']}s", flush=True)
    return final


def main():
    config.set_data(Path(__file__).resolve().parent.parent / "data")
    db.init()
    for job in db.list_jobs():
        src = pipeline.media_path(job["id"])
        if not src.exists():
            continue
        cands = pick_windows(job["id"])
        if not cands:
            print(f"[job] {job['id']} {job['title']} -> no window with enough detected speech", flush=True)
            continue
        root = config.DATA / "exports" / job["id"] / "infographics-test"
        shutil.rmtree(root, ignore_errors=True)  # a rerun replaces the last test set
        print(f"[job] {job['id']} {job['title']} -> auditioning {['%ds' % w for w in cands]}", flush=True)
        made = 0
        for win in cands:
            if made >= PER_JOB:
                break
            if render_one(job["id"], win, made + 1):
                made += 1
        if not made:
            print(f"[job] {job['id']} -> no window produced a usable transcript", flush=True)


if __name__ == "__main__":
    main()
