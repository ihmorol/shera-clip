"""Infographic videos (D35–D38): plan contract, scene timing, slide HTML, ffmpeg assembly, pipeline, routes.

Pure-logic tests run everywhere. The assembly test uses real ffmpeg (like test_media.py); the browser
screenshot test skips when no Chromium-family browser is installed.
"""
import json
import pathlib
import shutil
import subprocess
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from shera import app as web
from shera import app as app_module
from shera import config, db, infographics, ledger, media, pipeline, providers

BASE = f"http://127.0.0.1:{config.PORT}"


def units(n=12, span=5.0):
    return [{"start": i * span, "end": (i + 1) * span, "text": f"লাইন {i} says the point {i}",
             "speaker": None, "en": f"line {i}"} for i in range(n)]


def plan(n=12, size=4):
    scenes = [{"u0": k * size, "u1": (k + 1) * size - 1, "kind": "point", "heading": f"Scene {k}",
               "bullets": ["one", "two"], "emphasis": "", "note": ""} for k in range(n // size)]
    return {"headline": "The lesson", "scenes": scenes}


# ---------- transcript slicing ----------

def test_clip_units_indexes_and_clamps():
    got = infographics.clip_units(units(6), 7.5, 22.5)
    assert [g["i"] for g in got] == [0, 1, 2, 3]  # lines 1–4 overlap the span, renumbered from 0
    assert (got[0]["start"], got[0]["end"]) == (0.0, pytest.approx(2.5))  # cut mid-line at the start
    assert (got[-1]["start"], got[-1]["end"]) == (pytest.approx(12.5), pytest.approx(15.0))


# ---------- plan contract ----------

def test_normalize_plan_keeps_a_valid_plan():
    got = infographics.normalize_plan(plan(8, 4), 8, units(8))
    assert got["headline"] == "The lesson"
    assert [s["u0"] for s in got["scenes"]] == [0, 4] and [s["u1"] for s in got["scenes"]] == [3, 7]


def test_normalize_plan_repairs_numbering_slips_without_dropping_speech():
    p = plan(6, 2)
    p["scenes"][0]["u0"] = 1          # first scene starts late
    p["scenes"][1]["u0"] = 3          # gap: line 2 was never claimed
    p["scenes"][2]["u1"] = 4          # last scene ends early
    got = infographics.normalize_plan(p, 6, units(6))
    assert [(s["u0"], s["u1"]) for s in got["scenes"]] == [(0, 2), (3, 3), (4, 5)]


def test_normalize_plan_rejects_overlap_and_garbage():
    p = plan(8, 4)
    p["scenes"][1]["u0"] = 3          # overlaps scene 0's span
    with pytest.raises(ledger.ProviderError) as e:
        infographics.normalize_plan(p, 8, units(8))
    assert e.value.billed
    p2 = plan(8, 4)
    p2["scenes"][0]["kind"] = "chart"
    with pytest.raises(ledger.ProviderError):
        infographics.normalize_plan(p2, 8, units(8))
    with pytest.raises(ledger.ProviderError):
        infographics.normalize_plan({"headline": "x", "scenes": []}, 8, units(8))


def test_normalize_plan_clamps_long_text_and_fills_headline():
    p = plan(4, 4)
    p["headline"] = ""
    p["scenes"][0]["heading"] = "x" * 300
    p["scenes"][0]["bullets"] = ["b" * 300] + [""] * 9
    got = infographics.normalize_plan(p, 4, units(4))
    assert len(got["headline"]) <= 120 and got["headline"] == "লাইন 0 says the point 0"[:120]
    assert got["scenes"][0]["heading"].endswith("…") and len(got["scenes"][0]["heading"]) <= 110
    assert got["scenes"][0]["bullets"] == ["b" * 139 + "…"]


def test_plan_key_tracks_boundaries_and_title():
    lines = infographics.clip_units(units(6), 0, 30)
    assert infographics.plan_key(lines, "t") == infographics.plan_key(lines, "t")
    assert infographics.plan_key(lines, "t") != infographics.plan_key(lines, "other")
    assert infographics.plan_key(lines, "t") != infographics.plan_key(lines[:5], "t")


# ---------- timing ----------

def test_scene_times_cover_the_audio_exactly():
    lines = infographics.clip_units(units(6), 0, 30)
    times = infographics.scene_times(plan(6, 2)["scenes"], lines, 30.0)
    assert (times[0]["start"], times[-1]["end"]) == (0.0, 30.0)
    assert all(a["end"] == b["start"] for a, b in zip(times, times[1:]))


def test_scene_times_hold_short_scenes_and_end_at_the_audio():
    lines = [{"i": 0, "start": 0.0, "end": 0.4, "text": "a", "en": ""},   # far shorter than MIN_SCENE_S
             {"i": 1, "start": 0.4, "end": 2.0, "text": "b", "en": ""},
             {"i": 2, "start": 2.0, "end": 3.5, "text": "c", "en": ""}]
    scenes = [{"u0": 0, "u1": 0, "kind": "point"}, {"u0": 1, "u1": 1, "kind": "point"},
              {"u0": 2, "u1": 2, "kind": "point"}]
    times = infographics.scene_times(scenes, lines, 60.0)
    assert times[0]["dur"] >= infographics.MIN_SCENE_S
    assert times[-1]["end"] == 60.0  # trailing silence belongs to the last scene


# ---------- slide HTML ----------

def test_slide_html_shows_scene_text_escaped():
    sc = {"u0": 0, "u1": 1, "kind": "point", "heading": "<b>নেটওয়ার্ক</b>", "bullets": ["A & B"],
          "emphasis": "42%", "note": ""}
    html = infographics.slide_html(sc, 2, 5, headline="The lesson", title="T", category="Exam tip")
    assert "নেটওয়ার্ক" in html and "&lt;b&gt;" in html and "A &amp; B" in html and "42%" in html
    assert "40.0" in html  # progress fill at scene 2 of 5
    assert "The lesson" in html and "Exam tip" in html


def test_slide_html_renders_each_kind():
    for kind in providers.SCENE_KINDS:
        sc = {"u0": 0, "u1": 1, "kind": kind, "heading": "H", "bullets": ["x", "y"], "emphasis": "e", "note": "n"}
        html = infographics.slide_html(sc, 1, 1)
        assert "H" in html and "x" in html


# ---------- ffmpeg assembly ----------

def test_ffmpeg_command_structure():
    times = [{"dur": 4.0}, {"dur": 3.0}]
    cmd = infographics.ffmpeg_command(["a.png", "b.png"], times, [], "src.mp4", 10.0, 7.0, acodec="aac")
    assert cmd["inputs"].count("-i") == 3 and cmd["inputs"][cmd["inputs"].index("-ss") + 1] == "10.000"
    assert "concat=n=2:v=1:a=0" in cmd["graph"][2]
    assert any("zoompan" in g and "min(1+0.000500*on,1.0600)" in g for g in cmd["graph"])  # zoom in
    assert any("zoompan" in g and "max(1.0600-0.000667*on,1)" in g for g in cmd["graph"])  # zoom out
    assert cmd["out_args"][cmd["out_args"].index("-t") + 1] == "7.000"
    assert cmd["audio_args"] == ["-c:a", "copy"]  # aac is copied untouched (D21 rule)
    other = infographics.ffmpeg_command(["a.png"], [{"dur": 2.0}], [], "s.mp4", 0, 2.0, acodec="pcm_s16le")
    assert other["audio_args"] == ["-c:a", "aac", "-b:a", "192k"]
    with_ass = infographics.ffmpeg_command(["a.png"], [{"dur": 2.0}], [], "s.mp4", 0, 2.0, ass_name="x.ass")
    assert "ass=x.ass:fontsdir=C\\\\:/Windows/Fonts" in with_ass["graph"][-1]  # same escape media.render uses


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_build_video_and_qc_with_real_ffmpeg(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=10",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(src)], check=True)
    pngs = []
    for k, color in enumerate(("red", "green")):
        png = tmp_path / f"s{k}.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=1920x1080",
                        "-frames:v", "1", str(png)], check=True)
        pngs.append(png)
    times = [{"u0": 0, "u1": 0, "kind": "point", "heading": "A", "bullets": [], "emphasis": "", "note": "",
              "start": 0.0, "end": 5.0, "dur": 5.0},
             {"u0": 1, "u1": 1, "kind": "list", "heading": "B", "bullets": ["x"], "emphasis": "", "note": "",
              "start": 5.0, "end": 8.0, "dur": 3.0}]
    out = tmp_path / "video.mp4"
    infographics.build_video(pngs, times, [{"start": 0.0, "end": 2.0, "text": "hello"}],
                             src, 1.0, 8.0, out, preset="veryfast")
    problems, extra = infographics.qc(out, 8.0)
    assert problems == [], problems
    assert extra["audio_peak"] > 10
    p = media.probe(out)
    assert (p["width"], p["height"]) == (1920, 1080) and p["vcodec"] == "h264" and p["acodec"] == "aac"


def test_render_slides_with_the_local_browser(tmp_path):
    pytest.importorskip("playwright")
    htmls = [infographics.slide_html({"u0": 0, "u1": 1, "kind": "point", "heading": "টেস্ট শিরোনাম",
                                      "bullets": ["প্রথম পয়েন্ট"], "emphasis": "", "note": ""}, 1, 2,
                                     headline="H")]
    try:
        paths = infographics.render_slides(htmls, tmp_path)
    except RuntimeError as e:  # no Edge/Chrome/Chromium installed on this machine
        pytest.skip(str(e))
    assert paths[0].stat().st_size > 5000


# ---------- provider contract ----------

def _openrouter(monkeypatch, content, cost=0.001):
    def fake_post(url, **kw):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}],
                                         "usage": {"cost": cost}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)


def test_scene_plan_provider_sends_lines_and_parses(monkeypatch):
    seen = {}

    def fake_post(url, **kw):
        seen.update(body=kw["json"])
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(plan(4, 2))}}],
                                         "usage": {"cost": 0.001}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    lines = units(4)
    out, cost = providers.scene_plan(lines, title="T", category="exam_tip", intent="goal")
    assert cost == 0.001 and out["headline"] == "The lesson" and len(out["scenes"]) == 2
    assert seen["body"]["model"] == config.INFOGRAPHIC_MODEL
    sent = json.loads(seen["body"]["messages"][1]["content"])
    assert sent["lines"] == lines and sent["title"] == "T" and sent["goal"] == "goal"


def test_scene_plan_provider_rejects_bad_shapes(monkeypatch):
    for bad in ({"scenes": []}, {"headline": "x", "scenes": [{"u0": 0, "u1": 1, "kind": "chart"}]},
                {"headline": "x"}, {}):
        _openrouter(monkeypatch, bad)
        with pytest.raises(ledger.ProviderError) as e:
            providers.scene_plan(units(4))
        assert e.value.billed


# ---------- pipeline ----------

@pytest.fixture
def job_env(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    jid = "job1"
    db.x("INSERT INTO jobs(id, created, title, source_path, stage, status, progress, duration, authorized_usd) "
         "VALUES (?, 0, 'Class', 'x.mp4', 'review', 'done', 1, 300, 1.5)", jid)
    d = pipeline.job_dir(jid)
    d.mkdir(parents=True)
    (d / "transcript.json").write_text(json.dumps({"source": "local_vtt", "units": units(12), "flags": []}),
                                       encoding="utf-8")
    (d / "source.mp4").write_bytes(b"x")
    cid = db.x('INSERT INTO candidates(job_id, u0, u1, start, "end", text, text_en, value, clarity, opening, '
               "category, score, shortlisted, rank) VALUES (?, 0, 11, 0, 60, 'text', 'en', 3, 3, 3, "
               "'exam_tip', 0.8, 1, 1)", jid)
    db.x("INSERT INTO reviews(candidate_id, status, start, \"end\", captions, layout) "
         "VALUES (?, 'approved', 0, 60, ?, ?)", cid,
         json.dumps([{"start": 0, "end": 4, "text": "hello"}]), json.dumps({"mode": "full"}))
    calls = {"plan": []}

    def fake_plan(lines, title="", category="", intent=""):
        calls["plan"].append(len(lines))
        return plan(len(lines)), 0.001

    def fake_slides(htmls, out_dir):
        out = []
        for k in range(len(htmls)):
            png = pathlib.Path(out_dir) / f"scene-{k + 1:02d}.png"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                            "-i", f"color=c=teal:s=1920x1080", "-frames:v", "1", str(png)], check=True)
            out.append(png)
        return out

    monkeypatch.setattr(providers, "scene_plan", fake_plan)
    monkeypatch.setattr(infographics, "render_slides", fake_slides)
    monkeypatch.setattr(infographics, "build_video",
                        lambda pngs, times, caps, src, cs, dur, out, preset="medium": out.write_bytes(b"mp4"))
    monkeypatch.setattr(infographics, "qc", lambda v, d: ([], {"audio_peak": 900.0}))
    monkeypatch.setattr(media, "thumbnail", lambda v, out, at, width=None: out.write_bytes(b"jpg"))
    return jid, cid, calls


def test_infographic_builds_folder_report_and_replays_the_plan(job_env):
    jid, cid, calls = job_env
    report = pipeline.infographic(cid)
    assert report["status"] == "ok" and report["problems"] == [] and report["scenes"] == 3
    assert report["cost_usd"] == 0.001
    folder = config.DATA / "exports" / jid / "infographics" / f"01-{cid}"
    assert (folder / "video.mp4").exists() and (folder / "poster.jpg").exists()
    assert (folder / "plan.json").exists() and (folder / "report.json").exists()
    assert (folder / "slides" / "scene-01.png").exists()
    index = json.loads((folder.parent / "index.json").read_text(encoding="utf-8"))
    assert [i["candidate_id"] for i in index] == [cid] and index[0]["status"] == "ok"
    assert [c["kind"] for c in ledger.calls(jid)] == ["infographic"]
    pipeline.infographic(cid)  # again: the journaled plan is replayed, not re-billed
    assert calls["plan"] == [12]


def test_infographic_needs_an_approved_clip(job_env):
    jid, cid, _ = job_env
    db.update_review(cid, status="pending")
    with pytest.raises(ValueError):
        pipeline.infographic(cid)


def test_infographic_retries_a_bad_plan_once(job_env, monkeypatch):
    jid, cid, calls = job_env
    state = {"n": 0}

    def flaky(lines, title="", category="", intent=""):
        state["n"] += 1
        if state["n"] == 1:
            raise ledger.ProviderError("scene plan: no scenes", billed=True)
        return plan(len(lines)), 0.001

    monkeypatch.setattr(providers, "scene_plan", flaky)
    report = pipeline.infographic(cid)
    assert report["status"] == "ok" and state["n"] == 2
    states = [c["state"] for c in ledger.calls(jid)]
    assert states.count("done") == 1  # the billed failure stays recorded, the retry finished


def test_infographic_reports_failed_qc_instead_of_ok(job_env, monkeypatch):
    jid, cid, _ = job_env
    monkeypatch.setattr(infographics, "qc",
                        lambda v, d: (["duration 6.00s, expected 60.00s"], {"audio_peak": 900.0}))
    report = pipeline.infographic(cid)
    assert report["status"] == "failed" and report["problems"]
    folder = config.DATA / "exports" / jid / "infographics" / f"01-{cid}"
    assert json.loads((folder / "report.json").read_text(encoding="utf-8"))["status"] == "failed"


def test_render_previews_ranks_through_the_shortlist(job_env, monkeypatch):
    jid, cid, _ = job_env
    done = []

    def fake_preview(cid):
        done.append(cid)

    monkeypatch.setattr(pipeline, "render_preview", fake_preview)
    monkeypatch.setattr(pipeline, "preview_current", lambda rv: False)
    assert pipeline.render_previews(jid) == []
    assert done == [cid]
    monkeypatch.setattr(pipeline, "preview_current", lambda rv: True)
    assert pipeline.render_previews(jid) == [] and done == [cid]  # current previews are not re-rendered
    done.clear()
    monkeypatch.setattr(pipeline, "preview_current", lambda rv: False)
    monkeypatch.setattr(pipeline, "render_preview",
                        lambda cid: (_ for _ in ()).throw(RuntimeError("ffmpeg died")))
    assert pipeline.render_previews(jid) == [cid]  # the failure is reported, the rest carry on


# ---------- web ----------

@pytest.fixture
def client(tmp_path, job_env):
    web.TASKS.clear()
    return TestClient(web.app, base_url=BASE), job_env


def _wait(key, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        t = web.TASKS.get(key)
        if t and t["state"] != "running":
            return t
        time.sleep(0.05)
    raise AssertionError(f"task {key} did not finish")


def _fake_render(jid, status="ok"):
    """A pipeline.infographic stand-in that writes the folder and report the real one would."""

    def fake(cid, preset="medium"):
        folder = config.DATA / "exports" / jid / "infographics" / f"01-{cid}"
        (folder / "slides").mkdir(parents=True, exist_ok=True)
        report = {"folder": folder.name, "candidate_id": cid, "status": status, "problems": [],
                  "headline": "The lesson", "scenes": 3, "duration": 60.0, "audio_peak": 900.0,
                  "cost_usd": 0.001}
        (folder / "video.mp4").write_bytes(b"mp4")
        (folder / "poster.jpg").write_bytes(b"jpg")
        (folder / "report.json").write_text(json.dumps(report), encoding="utf-8")
        infographics.write_index(folder.parent)
        return report

    return fake


def test_infographics_page_lists_only_approved(client):
    web, (jid, cid, _) = client
    html = web.get(f"/jobs/{jid}/infographics").text
    assert "Infographic videos" in html and "Not generated" in html and "Generate 1 video" in html
    db.update_review(cid, status="pending")
    html = web.get(f"/jobs/{jid}/infographics").text
    assert "No approved clips yet" in html


def test_generate_all_renders_then_shows_ready(client, monkeypatch):
    web, (jid, cid, _) = client
    monkeypatch.setattr(pipeline, "infographic", _fake_render(jid))
    r = web.post(f"/jobs/{jid}/infographics/generate", follow_redirects=False)
    assert r.status_code == 303
    _wait(f"infographics:{jid}")
    html = web.get(f"/jobs/{jid}/infographics").text
    assert "Ready" in html and "The lesson" in html
    # a second run has nothing to do: the finished clip is skipped
    calls = {"n": 0}
    monkeypatch.setattr(pipeline, "infographic", lambda cid, preset="medium": calls.__setitem__("n", calls["n"] + 1))
    web.post(f"/jobs/{jid}/infographics/generate")
    _wait(f"infographics:{jid}")
    assert calls["n"] == 0


def test_generate_all_reports_a_failed_clip_as_failed(client, monkeypatch):
    web, (jid, cid, _) = client
    monkeypatch.setattr(pipeline, "infographic", _fake_render(jid, status="failed"))
    web.post(f"/jobs/{jid}/infographics/generate")
    _wait(f"infographics:{jid}")
    assert "Failed checks" in web.get(f"/jobs/{jid}/infographics").text
    state = web.get(f"/jobs/{jid}/infographics/state").json()
    assert state["clips"][str(cid)]["state"] == "done"  # the work finished; the file itself is marked failed


def test_generate_needs_an_approved_clip(client):
    web, (jid, cid, _) = client
    db.update_review(cid, status="pending")
    r = web.post(f"/jobs/{jid}/infographics/generate", follow_redirects=False)
    assert r.status_code == 409 and "Approve" in r.text


def test_single_clip_route_and_error_state(client, monkeypatch):
    web, (jid, cid, _) = client

    def boom(cid, preset="medium"):
        raise RuntimeError("the browser is missing")

    monkeypatch.setattr(pipeline, "infographic", boom)
    assert web.post(f"/jobs/{jid}/clips/{cid}/infographic", follow_redirects=False).status_code == 303
    _wait(f"info:{cid}")
    state = web.get(f"/jobs/{jid}/infographics/state").json()
    assert state["clips"][str(cid)]["state"] == "error" and "browser" in state["clips"][str(cid)]["error"]
    html = web.get(f"/jobs/{jid}/infographics").text
    assert "Failed" in html and "the browser is missing" in html
    db.update_review(cid, status="pending")
    r = web.post(f"/jobs/{jid}/clips/{cid}/infographic")
    assert r.status_code == 409  # only approved clips get videos


def test_approve_selected_bulk_action(client, monkeypatch):
    web, (jid, cid, _) = client
    monkeypatch.setattr(app_module, "_start_infographics", lambda j: False)  # covered by the dedicated test below
    db.update_review(cid, status="pending")  # the fixture seeds it approved; the bulk action needs it pending
    cid2 = db.x('INSERT INTO candidates(job_id, u0, u1, start, "end", text, value, clarity, opening, category, '
                "score, shortlisted, rank) VALUES (?, 8, 11, 40, 60, 'more text', 3, 3, 3, 'exam_tip', 0.6, 1, 2)", jid)
    cid3 = db.x('INSERT INTO candidates(job_id, u0, u1, start, "end", text, value, clarity, opening, category, '
                "score, shortlisted, rank) VALUES (?, 12, 15, 60, 80, 'third text', 3, 3, 3, 'exam_tip', 0.5, 1, 3)", jid)
    for c in (cid, cid2):  # previews rendered for two of the three
        rv = pipeline.ensure_review(c)
        p = pipeline.job_dir(jid) / "previews" / f"{c}-{pipeline.state_hash(rv)}.mp4"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        pipeline.landscape_path(p).write_bytes(b"x")
        db.update_review(c, preview_path=str(p))
    html = web.post(f"/jobs/{jid}/approve-selected").text
    assert "Approved 2 selected clips" in html and "1 still waiting" in html
    assert [db.review(c)["status"] for c in (cid, cid2, cid3)] == ["approved", "approved", "pending"]


def test_approve_selected_starts_rendering_the_videos(client, monkeypatch):
    web, (jid, cid, _) = client
    started = []
    monkeypatch.setattr(app_module, "_start_infographics", lambda j: started.append(j) or True)
    db.update_review(cid, status="pending")
    rv = pipeline.ensure_review(cid)
    p = pipeline.job_dir(jid) / "previews" / f"{cid}-{pipeline.state_hash(rv)}.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    pipeline.landscape_path(p).write_bytes(b"x")
    db.update_review(cid, preview_path=str(p))
    html = web.post(f"/jobs/{jid}/approve-selected").text
    assert started == [jid] and "infographic videos are rendering" in html


def test_render_previews_route_runs_in_background(client, monkeypatch):
    web, (jid, cid, _) = client
    seen = []
    monkeypatch.setattr(pipeline, "render_previews", lambda j: seen.append(j))
    r = web.post(f"/jobs/{jid}/render-previews", follow_redirects=False)
    assert r.status_code == 303
    _wait(f"autorender:{jid}")
    assert seen == [jid]


def test_job_page_shows_bulk_actions_when_ready(client):
    web, (jid, cid, _) = client
    db.update_review(cid, status="pending")  # the fixture seeds it approved
    rv = pipeline.ensure_review(cid)
    p = pipeline.job_dir(jid) / "previews" / f"{cid}-{pipeline.state_hash(rv)}.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    pipeline.landscape_path(p).write_bytes(b"x")
    db.update_review(cid, preview_path=str(p))
    html = web.get(f"/jobs/{jid}").text
    assert "Approve the 1 ready clip" in html and "Infographic videos" not in html
    db.update_review(cid, status="approved")
    html = web.get(f"/jobs/{jid}").text
    assert "Infographic videos" in html  # the extension appears once something is approved
