"""Render infographic videos for a job's shortlisted clips — the production render path, without the
approval gate, for the owner's one-run test. Scene plans go through the same ledger (so a later
in-app generate replays them for free); if the cap is reached the offline planner takes over.
Audio is the clip's own from media.mp4, stream-copied untouched.

Run:  python scripts/render_shortlist_test.py <job_id> [max_clips]
"""
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shera import candidates as cand
from shera import config, db, infographics, ledger, media, pipeline, providers

MAX_CLIPS = int(sys.argv[2]) if len(sys.argv) > 2 else 10


def plan_for(job_id, cid, lines, title, category, intent):
    """Model scene plan under the job's cap; offline planner when the cap or the provider says no."""
    key = f"info:{cid}:{infographics.plan_key(lines, title, category, intent)}"

    def call():
        raw, cost = providers.scene_plan(lines, title=title, category=category, intent=intent)
        return infographics.normalize_plan(raw, len(lines), lines), cost

    try:
        try:
            planned = ledger.call(job_id, key, "infographic", config.INFO_EST_USD, call)
        except ledger.ProviderError:  # the model ignored the contract once; one clean retry
            planned = ledger.call(job_id, key, "infographic", config.INFO_EST_USD, call)
        return planned, "model"
    except (ledger.ProviderError, ledger.BudgetStop, ledger.Indeterminate) as e:
        print(f"  [plan] {key}: model plan unavailable ({str(e)[:80]}); using the offline planner", flush=True)
        return infographics.normalize_plan(infographics.local_plan(lines, title), len(lines), lines), "local"


def render(job_id, c, k):
    rv = db.review(c["id"])
    units = pipeline._units(job_id)
    lines = infographics.clip_units(units, rv["start"], rv["end"])
    if not lines:
        print(f"  [skip] clip {c['id']}: no transcript lines", flush=True)
        return None
    dur = rv["end"] - rv["start"]
    profile = pipeline.job_profile(job_id)
    planned, planner = plan_for(job_id, c["id"], lines, rv["title"] or "", rv["category"] or "",
                                profile["intent"])
    times = infographics.scene_times(planned["scenes"], lines, dur)
    idx = [i for i, u in enumerate(units) if u["end"] > rv["start"] and u["start"] < rv["end"]]
    caps = cand.caption_lines(units, idx[0], idx[-1], rv["start"], rv["end"])

    root = config.DATA / "exports" / job_id / "infographics-test"
    final = root / f"{k:02d}-{c['id']}"
    tmp = final.with_name(final.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "slides").mkdir(parents=True)
    htmls = [infographics.slide_html(sc, n, len(times), headline=planned["headline"],
                                     title=rv["title"] or "", category=rv["category"] or "")
             for n, sc in enumerate(times, 1)]
    t0 = time.time()
    pngs = infographics.render_slides(htmls, tmp / "slides")
    video = tmp / "video.mp4"
    infographics.build_video(pngs, times, caps, pipeline.media_path(job_id), rv["start"], dur,
                             video, preset="veryfast")
    problems, extra = infographics.qc(video, dur)
    media.thumbnail(video, tmp / "poster.jpg", 0.5)
    spent = ledger.spent(job_id)
    report = {"folder": final.name, "candidate_id": c["id"], "rank": c["rank"], "title": rv["title"] or "",
              "headline": planned["headline"], "category": rv["category"] or "", "duration": round(dur, 3),
              "scenes": len(times), "planner": planner, "job_spent_usd": round(spent, 4), **extra,
              "status": "ok" if not problems else "failed", "problems": problems,
              "render_s": round(time.time() - t0, 1)}
    (tmp / "plan.json").write_text(json.dumps({"headline": planned["headline"], "scenes": times},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
    infographics.finalize(tmp, final, report)
    print(f"[done] {final.name}: {len(times)} scenes, planner={planner}, "
          f"qc={'ok' if not problems else problems}, {report['render_s']}s, job spent ${spent:.4f}", flush=True)
    return final


def main():
    config.set_data(Path(__file__).resolve().parent.parent / "data")
    db.init()
    job_id = sys.argv[1]
    job = db.get_job(job_id)
    if job["status"] != "done":
        print(f"job {job_id} is {job['status']}, not done yet", flush=True)
        return
    short = sorted((c for c in db.candidates(job_id) if c["shortlisted"]), key=lambda c: c["rank"])[:MAX_CLIPS]
    print(f"[job] {job_id}: rendering {len(short)} shortlisted clips (original audio, no approval changes)",
          flush=True)
    made = 0
    for c in short:
        if ledger.spent(job_id) >= 0.995:
            print("[stop] at the $1.00 cap before clip", c["rank"], flush=True)
            break
        if render(job_id, c, made + 1):
            made += 1
    print(f"[job] finished: {made} videos in data/exports/{job_id}/infographics-test/", flush=True)


if __name__ == "__main__":
    main()
