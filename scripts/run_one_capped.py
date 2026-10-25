"""One-run pipeline driver for the owner-capped test: authorize at USD 1.00, then steer the job to done
without ever exceeding the cap. Budget stops are handled by pruning, never by raising the cap."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shera import config, db, pipeline

config.set_data(Path(__file__).resolve().parent.parent / "data")
db.init()
job_id = sys.argv[1]
CAP = 1.00
db.update_job(job_id, authorized_usd=CAP)
pipeline.resume(job_id)
print(f"[runner] authorized at ${CAP:.2f} (hard ledger cap), job resumed", flush=True)

while True:
    job = db.get_job(job_id)
    spent = db.one("SELECT COALESCE(SUM(CASE WHEN state IN ('done','failed') THEN COALESCE(cost_usd,0) "
                   "WHEN state='abandoned' THEN MAX(est_usd, COALESCE(cost_usd,0)) ELSE est_usd END), 0) AS s "
                   "FROM paid_calls WHERE job_id=?", job_id)["s"]
    print(f"[runner] stage={job['stage']:10s} status={job['status']:8s} spent=${spent:.4f}", flush=True)
    if job["status"] == "running" or job["status"] == "waiting":
        time.sleep(15)
        continue
    if job["status"] == "paused" and job["stage"] == "score":
        n = db.one("SELECT COUNT(*) AS n FROM candidates WHERE job_id=? AND score IS NULL", job_id)["n"]
        db.x("DELETE FROM candidates WHERE job_id=? AND score IS NULL", job_id)
        print(f"[runner] budget stop at score: pruned {n} unscored windows, resuming with the scored ones", flush=True)
        pipeline.resume(job_id)
        continue
    if job["status"] == "paused" and job["stage"] == "prepare":
        short = [c for c in db.candidates(job_id) if c["shortlisted"]]
        for c in short:
            rv = db.review(c["id"])
            if not rv["drafts"] or pipeline.drafts_open(rv["drafts"]):
                note = {"facebook": {"title": "(draft skipped: budget)", "description": "", "cta": ""},
                        "youtube": {"title": "(draft skipped: budget)", "description": "", "cta": ""}}
                db.update_review(c["id"], drafts=note)
        print(f"[runner] budget stop at prepare: marked drafts as skipped for {len(short)} clips, resuming", flush=True)
        pipeline.resume(job_id)
        continue
    print(f"[runner] final: stage={job['stage']} status={job['status']} error={job['error']}", flush=True)
    short = [c for c in db.candidates(job_id) if c["shortlisted"]]
    print(f"[runner] shortlist: {len(short)} clips", flush=True)
    for c in sorted(short, key=lambda x: x["rank"]):
        print(f"  #{c['rank']} [{c['start']:.0f}-{c['end']:.0f}s] score={round(c['score'] or 0, 3)} "
              f"cat={c['category']} | {c['text'][:70]!r}", flush=True)
    break
