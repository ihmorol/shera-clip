"""Infographic videos from approved clips (D35–D38).

The audio is the clip's own and no model touches it: the video track is assembled to the audio's exact
length, scenes are cut on transcript-line boundaries, and on-screen text may only compress what the
transcript says. Rendering is local — the browser screenshots one designed slide per scene, then ffmpeg
adds slow Ken Burns motion, burns the spoken-line captions, and muxes the original audio.
"""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from shera import media
from shera.ledger import ProviderError

W, H, FPS = 1920, 1080, 30
MIN_SCENE_S = 0.8    # a scene never flashes by faster than this
ZOOM = 0.06          # total Ken Burns travel over one scene
FADE_S = 0.5

_env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
                   autoescape=select_autoescape(["html"]))


# ---------- transcript slicing ----------

def clip_units(units, start, end):
    """The transcript lines inside [start, end) of the source, with times relative to the clip start
    and 0-based indexes the scene plan refers to."""
    out = []
    for u in units:
        s, e = max(start, u["start"]), min(end, u["end"])
        if e - s <= 0.01:
            continue
        out.append({"i": len(out), "start": round(s - start, 3), "end": round(e - start, 3),
                    "text": u["text"], "en": u.get("en") or ""})
    return out


# ---------- scene plan ----------

def _clean(text, limit):
    text = " ".join(str(text or "").split())
    return text[:limit - 1].rstrip() + "…" if len(text) > limit else text


def normalize_plan(plan, n, lines):
    """Validate the model's plan against the clip's lines and fill safe defaults.
    Scenes must be ordered and non-overlapping; small numbering slips are repaired by holding the
    previous slide longer (never by dropping speech). Anything ambiguous raises ProviderError."""
    scenes, prev = [], -1
    for s in plan.get("scenes") or []:
        try:
            u0, u1 = int(s["u0"]), int(s["u1"])
        except (KeyError, TypeError, ValueError) as e:
            raise ProviderError("scene plan: a scene is missing integer u0/u1", billed=True) from e
        if not 0 <= u0 <= u1 < n:
            raise ProviderError(f"scene plan: scene {u0}–{u1} is outside the clip's {n} lines", billed=True)
        if u0 <= prev:
            raise ProviderError("scene plan: scenes overlap or are out of order", billed=True)
        kind = s.get("kind")
        if kind not in ("point", "list", "steps", "example", "mistake", "definition",
                        "quote", "comparison", "chatter"):
            raise ProviderError(f"scene plan: unknown scene kind {kind!r}", billed=True)
        if scenes and u0 > prev + 1:  # a numbering slip: the previous slide holds through the gap
            scenes[-1]["u1"] = u0 - 1
        heading = _clean(s.get("heading"), 110)
        raw_bullets = s.get("bullets")
        bullets = [_clean(b, 140) for b in (raw_bullets if isinstance(raw_bullets, list) else [])
                   if isinstance(b, str) and _clean(b, 140)][:5]
        if not heading:
            heading = _clean(lines[u0]["text"], 110)
        if not heading and not bullets and kind != "chatter":
            raise ProviderError(f"scene plan: scene {u0}–{u1} has no text", billed=True)
        scenes.append({"u0": u0, "u1": u1, "kind": kind, "heading": heading, "bullets": bullets,
                       "emphasis": _clean(s.get("emphasis"), 80), "note": _clean(s.get("note"), 160)})
        prev = u1
    if not scenes:
        raise ProviderError("scene plan: no scenes", billed=True)
    scenes[0]["u0"] = 0          # leading silence belongs to the first scene
    if scenes[-1]["u1"] != n - 1:  # trailing lines keep the last scene on screen
        scenes[-1]["u1"] = n - 1
    return {"headline": _clean(plan.get("headline"), 120) or _clean(lines[0]["text"], 120),
            "scenes": scenes}


def plan_key(lines, title, category="", intent=""):
    """Fingerprint of everything the paid plan call depends on; the ledger key carries it."""
    raw = json.dumps({"t": title, "c": category, "i": intent,
                      "lines": [(u["text"], u["start"], u["end"]) for u in lines]},
                     ensure_ascii=False)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def local_plan(lines, title=""):
    """Deterministic offline scene plan (no provider, no cost): consecutive lines are grouped into
    ~15 s scenes; each scene is headed by its first spoken line with the rest as bullets. Every word
    on screen comes from the transcript. Used when no OpenRouter key is configured or the operator
    asks for the offline planner."""
    groups, cur = [], []
    for ln in lines:
        cur.append(ln)
        if ln["end"] - cur[0]["start"] >= 15.0 or len(cur) >= 4:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    scenes = [{"u0": g[0]["i"], "u1": g[-1]["i"], "kind": "list" if len(g) > 2 else "point",
               "heading": g[0]["text"], "bullets": [x["text"] for x in g[1:6]],
               "emphasis": "", "note": ""} for g in groups]
    if not scenes:
        raise ValueError("no transcript lines to plan scenes from")
    return {"headline": _clean(title, 120) or scenes[0]["heading"], "scenes": scenes}


def scene_times(scenes, lines, duration):
    """Clip-relative [start, end) per scene: hard cuts with full coverage. A scene ends when its last
    line ends (short scenes are held for MIN_SCENE_S); the first starts at 0 and the last runs to the
    audio's end, so the visuals always span exactly the audio. A scene with no room left on the clock
    merges into the previous slide rather than failing the render."""
    out, t = [], 0.0
    for k, sc in enumerate(scenes):
        e = duration if k == len(scenes) - 1 else min(duration, max(t + MIN_SCENE_S, lines[sc["u1"]]["end"]))
        if e <= t:
            if not out:
                raise ValueError("scene timing collapsed; the clip is too short for its scenes")
            out[-1]["u1"] = sc["u1"]  # the previous slide holds through these lines too
            continue
        out.append({**sc, "start": round(t, 3), "end": round(e, 3), "dur": round(e - t, 3)})
        t = e
    if not out:
        raise ValueError("scene timing collapsed; the clip is too short for its scenes")
    return out


def slide_html(scene, k, n, headline="", title="", category=""):
    return _env.get_template("slide.html").render(
        scene=scene, k=k, n=n, headline=headline, title=title, category=category)


# ---------- slide rendering ----------

def _launch(pw):
    """The installed Edge (always present on Windows) first, then Chrome, then a downloaded Chromium."""
    last = None
    for channel in ("msedge", "chrome", None):
        try:
            return pw.chromium.launch(channel=channel) if channel else pw.chromium.launch()
        except Exception as e:  # a channel that is not installed simply is not there
            last = e
    raise RuntimeError("No Chromium-family browser found for slide rendering. Microsoft Edge is used "
                       "when present, or run: python -m playwright install chromium") from last


def render_slides(htmls, out_dir):
    """One 1920x1080 PNG per scene, screenshot by the local browser."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("Slide rendering needs Playwright: python -m pip install playwright") from e
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as pw:
        browser = _launch(pw)
        try:
            page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            for k, html in enumerate(htmls, 1):
                f = out_dir / f"scene-{k:02d}.html"
                f.write_text(html, encoding="utf-8")
                page.goto(f.as_uri())
                page.evaluate("document.fonts.ready")
                png = out_dir / f"scene-{k:02d}.png"
                page.screenshot(path=str(png))
                paths.append(png)
        finally:
            browser.close()
    return paths


# ---------- video assembly ----------

def ffmpeg_command(pngs, times, captions, src, clip_start, dur, acodec="aac", preset="medium",
                   ass_name=None):
    """The whole assembly as pure data (tests assert on this): one ffmpeg invocation that Ken Burns each
    slide, concats the scenes, optionally burns the spoken-line captions via `ass_name` (a bare file name
    resolved next to the output), and muxes the original audio."""
    inputs, graph = [], []
    for k, png in enumerate(pngs):
        inputs += ["-i", str(png)]
        frames = max(1, int(round(times[k]["dur"] * FPS)))
        rate = ZOOM / frames
        z = (f"min(1+{rate:.6f}*on,{1 + ZOOM:.4f})" if k % 2 == 0
             else f"max({1 + ZOOM:.4f}-{rate:.6f}*on,1)")
        graph.append(f"[{k}:v]scale=3840:-2,zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':"
                     f"y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},setsar=1[v{k}]")
    a = len(pngs)
    inputs += ["-ss", f"{clip_start:.3f}", "-i", str(src)]
    graph.append("".join(f"[v{k}]" for k in range(a)) + f"concat=n={a}:v=1:a=0[vc]")
    tail = (f"ass={ass_name}:fontsdir={media.FONTS_DIR.replace(':', '\\\\:')}," if ass_name else "")
    graph.append(f"[vc]fade=t=in:st=0:d={FADE_S},fade=t=out:st={max(0.0, dur - FADE_S):.3f}:d={FADE_S},"
                 f"{tail}format=yuv420p[vout]")
    audio = ["-c:a", "copy"] if acodec == "aac" else ["-c:a", "aac", "-b:a", "192k"]
    return {
        "inputs": inputs,
        "graph": graph,
        "out_args": ["-map", "[vout]", "-map", f"{a}:a:0", "-t", f"{dur:.3f}",
                     "-c:v", "libx264", "-preset", preset, "-crf", "20", "-r", str(FPS),
                     *audio, "-movflags", "+faststart", "-f", "mp4"],
        "audio_args": audio,
    }


def build_video(pngs, times, captions, src, clip_start, dur, out, preset="medium"):
    """Run the assembly into `out` (a .part file is used and renamed on success)."""
    src, out = Path(src).resolve(), Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    p = media.probe(src)
    if not p.get("has_audio"):
        raise ValueError("The clip's source has no audio track, so there is nothing to keep.")
    fd, ass = tempfile.mkstemp(suffix=".ass", prefix="shera_", dir=out.parent)
    os.close(fd)
    ass = Path(ass)
    ass.write_text(media.captions_ass(captions, dur, W, H, 180), encoding="utf-8")  # above the slide footer
    part = out.with_name(out.name + ".part")
    try:
        cmd = ffmpeg_command(pngs, times, captions, src, clip_start, dur,
                             acodec=p.get("acodec") or "aac", preset=preset, ass_name=ass.name)
        media._run(["ffmpeg", "-y", "-v", "error", *cmd["inputs"], "-filter_complex", ";".join(cmd["graph"]),
                    *cmd["out_args"], part.name], cwd=out.parent)
        os.replace(part, out)
    finally:
        ass.unlink(missing_ok=True)
        part.unlink(missing_ok=True)
    return out


# ---------- quality gates (A8) ----------

def qc(video, expected_dur):
    """-> (problems, report). An empty problems list is the only path to 'done'."""
    problems = media.verify(video, expected_dur, (W, H))
    peak = media.audio_peak(video, min(expected_dur, 120.0))
    if peak < 10:
        problems.append("the audio track is silent; the mux must have failed")
    return problems, {"audio_peak": round(peak, 1)}


def index_entries(root):
    """One summary row per finished clip folder, for infographics/index.json."""
    entries = []
    for folder in sorted(Path(root).iterdir()) if Path(root).is_dir() else []:
        report = folder / "report.json"
        if folder.is_dir() and report.exists():
            try:
                entries.append(json.loads(report.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
    return entries


def write_index(root):
    root = Path(root)
    tmp = root.with_name(root.name + ".index.part")
    tmp.write_text(json.dumps(index_entries(root), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(root / "index.json")


def finalize(tmp, final, report):
    """Swap the finished clip folder in; a failed QC still lands (marked failed) so the evidence stays,
    but the UI never shows it as done. The previous folder is renamed aside first, so a player holding
    one of its files open cannot destroy the old deliverable before the new one is in place."""
    (tmp / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    old = final.with_name(final.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    moved = False
    if final.exists():
        final.rename(old)
        moved = True
    try:
        tmp.rename(final)
    except OSError:
        if moved and not final.exists():
            old.rename(final)  # put the previous deliverable back
        raise
    shutil.rmtree(old, ignore_errors=True)
    write_index(final.parent)
