"""Headless CLI over the pipeline (D29): the machine stages, driven with JSON and exit codes.

Every valid command prints one JSON object on stdout; exit 0 means the command did its part,
1 means an error the JSON names (usage errors included). The review UI stays the only place
a clip is approved: there is no approve command, and paid calls need an explicit
`authorize --yes` inside the same hard USD 1.50 cap as the web app (D11).
"""
import argparse
import contextlib
import json
import sys
from datetime import date
from pathlib import Path

from shera import candidates as cand
from shera import config, db, ledger, pipeline, zoom


def _out(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


class CmdError(Exception):
    """An expected failure: JSON on stdout and exit 1 instead of a traceback."""


def _job_or_fail(job_id):
    job = db.get_job(job_id)
    if job is None:
        raise CmdError(f"No job {job_id}. Run 'shera jobs' to list jobs.")
    return job


def _not_running(a, job):
    """pipeline._running only sees this process; the app's runner threads live in another one.
    A 'running' row is therefore either the app working (wait) or a killed process's leftover.
    Returns True when the caller is taking a stuck job over (--force) — the caller then reaps
    that job's in-flight calls at the point where it actually mutates state."""

    if job["status"] == "running":
        if not getattr(a, "force", False):
            raise CmdError(f"Job {job['id']} is marked running, probably in the app. Wait for it to pause or finish. "
                           "If the app is closed and the job is stuck from a killed process, re-run with --force.")
        return True
    return False


def _detail(job):
    cands = db.candidates(job["id"])
    out = dict(job)
    # candidates of a failed or partial job are unscored: shortlisted/rank/score can all be NULL
    out["summary"] = {"candidates": len(cands), "shortlisted": sum(1 for c in cands if c["shortlisted"]),
                      "approved": db.one("SELECT COUNT(*) AS n FROM reviews WHERE status='approved' AND "
                                         "candidate_id IN (SELECT id FROM candidates WHERE job_id=?)",
                                         job["id"])["n"],
                      "spent_usd": round(ledger.spent(job["id"]), 4)}
    if job["stage"] == "authorize" and job["status"] == "waiting":
        out["estimate"] = pipeline.estimate(job["id"])
    return out


def _report(job_id):
    """Print the job after an inline run; a job that failed is a command error (exit 1)."""
    job = db.get_job(job_id)
    out = {"ok": job["status"] != "failed", "job": _detail(job)}
    if job["status"] == "waiting" and job["stage"] == "authorize":
        out["next"] = f"review the estimate with 'shera authorize {job_id}', then authorize it with --yes"
    elif job["status"] == "paused":
        out["next"] = f"check 'shera calls {job_id}' and resolve stuck calls, then 'shera run {job_id}'"
    _out(out)
    return 0 if job["status"] != "failed" else 1


def _checked_path(kind, path, ext):
    p = Path(path)
    if not p.is_file():
        raise CmdError(f"The {kind} file does not exist: {p}")
    if p.suffix.lower() != ext:
        raise CmdError(f"The {kind} file must be a {ext} file: {p}")
    return p


def cmd_jobs(_):
    keys = ("id", "title", "created", "stage", "status", "progress", "authorized_usd", "estimate_usd", "error")
    _out({"ok": True, "jobs": [{k: j[k] for k in keys} for j in db.list_jobs()]})
    return 0


def cmd_job(a):
    _out({"ok": True, "job": _detail(_job_or_fail(a.job_id))})
    return 0


def cmd_import(a):
    src = _checked_path("video", a.mp4, ".mp4")
    vtt = _checked_path("transcript", a.vtt, ".vtt") if a.vtt else None
    audio = _checked_path("audio", a.audio, ".m4a") if a.audio else None
    pipeline.recover()
    jid = pipeline.start_job(src, vtt, audio, title=a.title)
    return _report(jid)


def cmd_run(a):
    job = _job_or_fail(a.job_id)
    takeover = _not_running(a, job)
    if takeover:
        ledger.reap_stale(a.job_id)
    pipeline.recover()
    pipeline.resume(a.job_id)
    return _report(a.job_id)


def cmd_authorize(a):
    job = _job_or_fail(a.job_id)
    _not_running(a, job)
    if job["authorized_usd"] is None and not (job["stage"] == "authorize" and job["status"] == "waiting"):
        raise CmdError(f"Job {a.job_id} is not waiting for authorization "
                       f"(stage {job['stage']}, status {job['status']}).")
    if not a.yes:
        _out({"ok": True, "job_id": a.job_id, "already_authorized": job["authorized_usd"] is not None,
              "estimate": pipeline.estimate(a.job_id), "cap_usd": config.CAP_USD,
              "next": "re-run with --yes to authorize paid calls up to the hard cap"})
        return 0
    if _not_running(a, job):
        ledger.reap_stale(a.job_id)
    pipeline.recover()
    pipeline.authorize(a.job_id)
    return _report(a.job_id)


def cmd_candidates(a):
    _job_or_fail(a.job_id)
    cands = db.candidates(a.job_id)
    if not a.all:
        cands = [c for c in cands if c["shortlisted"]]
    status = {r["candidate_id"]: r["status"] for r in
              db.q("SELECT rc.candidate_id, rc.status FROM reviews rc "
                   "JOIN candidates c ON c.id=rc.candidate_id WHERE c.job_id=?", a.job_id)}
    rows = [{"id": c["id"], "rank": c["rank"], "shortlisted": bool(c["shortlisted"]),
             "review_status": status.get(c["id"], "pending"),
             "start": round(c["start"], 2), "end": round(c["end"], 2),
             "seconds": round(c["end"] - c["start"], 1),
             "category": c["category"], "value": c["value"], "clarity": c["clarity"], "opening": c["opening"],
             "postable": cand.jev(c, "postable"),
             "score": round(c["score"], 3) if c["score"] is not None else None,
             "blocker": cand.blocker(c) if c["score"] is not None else None,
             "text": c["text"], "text_en": c["text_en"],
             **({"jev": c["jev"]} if a.jev else {})}
            for c in cands]
    _out({"ok": True, "candidates": rows})
    return 0


def cmd_calls(a):
    _job_or_fail(a.job_id)
    keys = ("id", "key", "kind", "state", "est_usd", "cost_usd", "error")
    _out({"ok": True, "calls": [{k: c[k] for k in keys} for c in ledger.calls(a.job_id)]})
    return 0


def cmd_resolve(a):
    call = db.one("SELECT * FROM paid_calls WHERE id=?", a.call_id)
    if call is None:
        raise CmdError(f"No paid call {a.call_id}. Run 'shera calls <job>' to list them.")
    if call["state"] == "sent":
        raise CmdError(f"Call {a.call_id} is 'sent' — a runner may still own it. Wait for the job to pause or "
                       "finish; if the app is closed, restarting the app frees stuck calls (the app's Retry does "
                       "the same). A stuck 'running' job can also be taken over with 'shera run <job> --force'.")
    if call["state"] != "indeterminate":
        raise CmdError(f"Call {a.call_id} is {call['state']}, not indeterminate; nothing to resolve.")
    ledger.resolve(a.call_id)
    _out({"ok": True, "call_id": a.call_id, "job_id": call["job_id"],
          "note": "marked abandoned (still counted as possibly spent); re-run 'shera run' on the job to retry it"})
    return 0


def cmd_export(a):
    job = _job_or_fail(a.job_id)
    _not_running(a, job)
    root = pipeline.export(a.job_id)
    _out({"ok": True, "folder": str(root),
          "clips": json.loads((root / "index.json").read_text(encoding="utf-8")),
          "skipped": json.loads((root / "skipped.json").read_text(encoding="utf-8"))})
    return 0


def cmd_delete(a):
    job = _job_or_fail(a.job_id)
    _not_running(a, job)
    if not a.yes:
        _out({"ok": True, "job_id": a.job_id, "title": job["title"],
              "next": "re-run with --yes to permanently delete the job, its media and its exports"})
        return 0
    pipeline.delete_job(a.job_id)
    _out({"ok": True, "deleted": a.job_id})
    return 0


def _zoom_ready():
    if not zoom.configured():
        raise CmdError("Zoom is not set up: add ZOOM_ACCOUNT_ID, ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET and "
                       "ZOOM_USER to .env (see docs/zoom-setup.md).")


def cmd_zoom_list(a):
    _zoom_ready()
    to = date.fromisoformat(a.to) if a.to else date.today()
    start, occs = zoom.recordings(to)
    _out({"ok": True, "from": start.isoformat(), "to": to.isoformat(), "recordings": occs})
    return 0


def cmd_zoom_import(a):
    _zoom_ready()
    pipeline.recover()
    _, title = zoom.checked_occurrence(a.uuid, a.video, a.vtt or "", a.audio or "")
    jid = pipeline.start_zoom_job(a.uuid, title, a.video, vtt=a.vtt or None, m4a=a.audio or None)
    return _report(jid)


class _Parser(argparse.ArgumentParser):
    """Usage errors keep the D29 contract: JSON on stdout, exit 1 — the first failure an
    agent hits is a typo, and that is exactly where machine-readable errors matter."""

    def error(self, message):
        _out({"ok": False, "error": f"usage: {message}"})
        raise SystemExit(1)


def cmd_desktop(a):
    """D30: the same loopback review UI in a native window. A desktop session is a long-lived
    server with background runner threads, so it opts out of the CLI's inline-run mode."""
    pipeline.inline = False
    try:
        import webview  # noqa: F401
    except ImportError:
        raise CmdError("The desktop window needs pywebview. Install it with: pip install -e .[desktop]")
    from shera import desktop
    desktop.check_webview2()
    how = desktop.run_window()
    _out({"ok": True, "window": "closed", "server": how, "port": config.PORT})
    return 0


def build_parser():
    p = _Parser(prog="shera", description="Shera Clip CLI: the machine stages with JSON output. "
                                           "Clip approval stays in the review UI (D29).")
    p.add_argument("--data", help="data directory (default: $SHERA_DATA or ./data beside the app)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("jobs", help="list jobs").set_defaults(func=cmd_jobs)

    j = sub.add_parser("job", help="one job's full record")
    j.add_argument("job_id")
    j.set_defaults(func=cmd_job)

    i = sub.add_parser("import", help="import a local recording and run it until it waits for a human")
    i.add_argument("mp4")
    i.add_argument("--vtt", help="the class's VTT transcript, when Zoom made one")
    i.add_argument("--audio", help="the class's Zoom audio (.m4a); replaces the video's own sound")
    i.add_argument("--title")
    i.set_defaults(func=cmd_import)

    r = sub.add_parser("run", help="resume a paused or failed job and wait for it")
    r.add_argument("job_id")
    r.add_argument("--force", action="store_true", help="run even when the job is marked running elsewhere")
    r.set_defaults(func=cmd_run)

    az = sub.add_parser("authorize", help="show the cost estimate; --yes authorizes paid calls up to the hard cap")
    az.add_argument("job_id")
    az.add_argument("--yes", action="store_true")
    az.add_argument("--force", action="store_true", help="authorize even when the job is marked running elsewhere")
    az.set_defaults(func=cmd_authorize)

    c = sub.add_parser("candidates", help="list the ranked candidates (the shortlist unless --all)")
    c.add_argument("job_id")
    c.add_argument("--all", action="store_true", help="include candidates outside the shortlist")
    c.add_argument("--jev", action="store_true", help="attach Jev's full answer for each candidate")
    c.set_defaults(func=cmd_candidates)

    cl = sub.add_parser("calls", help="list the job's paid provider calls")
    cl.add_argument("job_id")
    cl.set_defaults(func=cmd_calls)

    rs = sub.add_parser("resolve", help="after checking the provider dashboard, free an indeterminate paid call")
    rs.add_argument("call_id", type=int)
    rs.set_defaults(func=cmd_resolve)

    e = sub.add_parser("export", help="package approved clips into data/exports/<job>/")
    e.add_argument("job_id")
    e.add_argument("--force", action="store_true", help="export even when the job is marked running elsewhere")
    e.set_defaults(func=cmd_export)

    dsk = sub.add_parser("desktop", help="open the review UI in a desktop window (needs the [desktop] extra)")
    dsk.set_defaults(func=cmd_desktop)

    d = sub.add_parser("delete", help="delete a job, its media and its exports; --yes required")
    d.add_argument("job_id")
    d.add_argument("--yes", action="store_true")
    d.add_argument("--force", action="store_true", help="delete even when the job is marked running elsewhere")
    d.set_defaults(func=cmd_delete)

    z = sub.add_parser("zoom", help="Zoom cloud recordings (read-only)")
    zsub = z.add_subparsers(dest="zoom_command", required=True)
    zl = zsub.add_parser("list", help="list the host's recordings, newest first")
    zl.add_argument("--to", help="month ending at this date, YYYY-MM-DD (default: today)")
    zl.add_argument("--data", default=argparse.SUPPRESS,
                    help="data directory (default: $SHERA_DATA or ./data beside the app)")
    zl.set_defaults(func=cmd_zoom_list)
    zi = zsub.add_parser("import", help="import one cloud recording by file ids from 'zoom list'")
    zi.add_argument("uuid")
    zi.add_argument("--video", required=True, help="the MP4 file id")
    zi.add_argument("--vtt", help="the transcript file id, when Zoom has one")
    zi.add_argument("--audio", help="the separate Zoom audio (.m4a) file id")
    zi.add_argument("--data", default=argparse.SUPPRESS,
                    help="data directory (default: $SHERA_DATA or ./data beside the app)")
    zi.set_defaults(func=cmd_zoom_import)

    for sp in sub.choices.values():  # a global flag must also work after the subcommand
        sp.add_argument("--data", default=argparse.SUPPRESS,  # absent beats None, so it never
                        help="data directory (default: $SHERA_DATA or ./data beside the app)")  # clobbers the global one
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    if a.data:
        config.set_data(a.data)
    # Bangla clip text must survive pipes and redirection, which Windows does not default to UTF-8
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError):
            stream.reconfigure(encoding="utf-8")
    db.init()
    pipeline.inline = True
    try:
        return a.func(a)
    except (CmdError, ValueError, KeyError, ledger.BudgetStop, ledger.Indeterminate,
            ledger.ProviderError, zoom.ZoomError) as e:
        _out({"ok": False, "error": str(e) or type(e).__name__, "exception": type(e).__name__})
        return 1
    except Exception as e:  # never print a fake success; the type name keeps it debuggable
        _out({"ok": False, "error": str(e) or type(e).__name__, "exception": type(e).__name__})
        return 1
    finally:
        pipeline.inline = False


if __name__ == "__main__":
    raise SystemExit(main())
