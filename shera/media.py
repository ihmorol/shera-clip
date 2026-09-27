"""All ffmpeg/ffprobe work: probe, import copy, speech detection, audio chunks, portrait render, verify.

Times are zero-based seconds on the source's presentation timeline. ffmpeg (without -copyts)
already shifts timestamps so the file's start_time is 0, and an input -ss is relative to it.
"""
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

W, H, FPS = 1080, 1920, 30
TITLE_H = 200            # top band reserved for the title in crop mode
CAP_TOP = 1500           # content never extends below this; the caption band is underneath
MAX_CONTENT_H = CAP_TOP - TITLE_H   # 1300
INSET_W, INSET_PAD = 360, 24
BG = "0x111111"
FONT = "Nirmala UI"
FONTS_DIR = "C:/Windows/Fonts"
MAX_CHUNK_BYTES = 24 * 1024 * 1024


def _run(args, cwd=None):
    r = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=cwd)
    if r.returncode:
        raise RuntimeError(f"{args[0]} failed ({r.returncode}): {r.stderr[-2000:]}")
    return r


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def probe(path):
    d = json.loads(_run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                         "-of", "json", path]).stdout)
    streams = d.get("streams", [])
    v = next((s for s in streams if s["codec_type"] == "video"
              and not s.get("disposition", {}).get("attached_pic")), {})
    a = next((s for s in streams if s["codec_type"] == "audio"), {})
    fmt = d.get("format", {})
    return {
        "duration": _f(fmt.get("duration")),
        "width": int(v.get("width", 0)), "height": int(v.get("height", 0)),
        "vcodec": v.get("codec_name"), "acodec": a.get("codec_name"),
        "v_start": _f(v.get("start_time")), "a_start": _f(a.get("start_time")),
        "has_audio": bool(a),
        # extras used by verify(): stream durations, to check end offsets (A5)
        "v_duration": _f(v.get("duration")), "a_duration": _f(a.get("duration")),
        "created": (fmt.get("tags") or {}).get("creation_time"),
    }


def copy_with_hash(src, dst, on_progress=None):
    """Copy src to dst via dst.part (renamed at the end), hashing on the way. -> (sha256, bytes)."""
    src, dst = Path(src), Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    part = dst.with_name(dst.name + ".part")
    total = src.stat().st_size or 1
    h, n = hashlib.sha256(), 0
    with open(src, "rb") as fi, open(part, "wb") as fo:
        while chunk := fi.read(8 << 20):
            fo.write(chunk)
            h.update(chunk)
            n += len(chunk)
            if on_progress:
                on_progress(n / total)
    os.replace(part, dst)
    return h.hexdigest(), n


def speech_intervals(path):
    """Non-silent (s, e) intervals: silencedetect on the first audio stream, inverted over duration."""
    dur = probe(path)["duration"]
    err = _run(["ffmpeg", "-hide_banner", "-nostats", "-vn", "-i", path, "-map", "0:a:0",
                "-af", "silencedetect=noise=-35dB:d=0.5", "-f", "null", "-"]).stderr
    silences, s = [], None
    for kind, t in re.findall(r"silence_(start|end): (-?[\d.]+)", err):
        if kind == "start":
            s = max(0.0, float(t))
        elif s is not None:
            silences.append((s, float(t)))
            s = None
    if s is not None:
        silences.append((s, dur))
    speech, cur = [], 0.0
    for a, b in silences:
        if a - cur > 0.05:  # a few ms between silences is a timestamp edge, not speech
            speech.append((round(cur, 3), round(a, 3)))
        cur = max(cur, b)
    if dur - cur > 0.05:
        speech.append((round(cur, 3), round(dur, 3)))
    return speech


def _clock(created):
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _envelope(path, start, dur):
    """10 ms loudness envelope of the first audio stream over [start, start + dur)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-t", f"{dur:.3f}", "-i", str(path),
                          "-map", "0:a:0", "-ac", "1", "-ar", "4000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float64)
    n = len(x) // 40
    return np.sqrt((x[:n * 40].reshape(n, 40) ** 2).mean(axis=1))


def _match(video, audio, guess, vdur, search):
    """Refine `guess` by cross-correlating loudness envelopes; None when the video is silent or no clear match."""
    w0 = min(60.0, vdur / 4)
    w = min(240.0, vdur - w0)
    v = _envelope(video, w0, w)
    if len(v) < 500 or v.max() < 30:  # under ~-60 dBFS: nothing to match against
        return None
    a0 = max(0.0, w0 + guess - search)
    a = _envelope(audio, a0, w + 2 * search)
    n = len(v)
    if len(a) <= n:
        return None
    v = (v - v.mean()) / (v.std() or 1)
    size = len(a) + n
    c = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(v, size)), size)[:len(a) - n + 1]
    s1, s2 = np.cumsum(np.r_[0, a]), np.cumsum(np.r_[0, a * a])
    mean = (s1[n:] - s1[:-n]) / n
    std = np.sqrt(np.maximum((s2[n:] - s2[:-n]) / n - mean * mean, 1e-9))
    r = c / (n * std)
    k = int(r.argmax())
    return round(a0 + k * 0.01 - w0, 3) if r[k] >= 0.5 else None


def sync_offset(video, audio):
    """Seconds to add to a video time to reach the same moment in a separate recording of the class audio
    (a Zoom M4A beside an OBS video). -> (offset, how): matched by sound when the video has audio,
    else by the files' recording clocks (about 1 s), else assumed to start together."""
    pv, pa = probe(video), probe(audio)
    cv, ca = _clock(pv["created"]), _clock(pa["created"])
    guess = (cv - ca).total_seconds() if cv and ca else None
    if guess is not None and not -pv["duration"] < guess < pa["duration"]:
        guess = None  # clocks that put the two files apart are wrong, not informative
    found = _match(video, audio, guess or 0.0, pv["duration"], 20.0 if guess is not None else 300.0) if pv["has_audio"] else None
    if found is not None:
        return found, "sound"
    return (guess, "clock") if guess is not None else (0.0, "none")


def mux_audio(video, audio, offset, out):
    """Video stream from `video` with `audio` lined up by `offset`, both stream-copied: the audio samples are
    the original recording's, never re-encoded."""
    dur = probe(video)["duration"]
    a_in = ["-ss", f"{offset:.3f}", "-i", audio] if offset >= 0 else ["-itsoffset", f"{-offset:.3f}", "-i", audio]
    part = Path(out).with_name(Path(out).name + ".part")
    _run(["ffmpeg", "-y", "-v", "error", "-i", video, *a_in, "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
          "-t", f"{dur:.3f}", "-movflags", "+faststart", "-f", "mp4", part])
    os.replace(part, out)
    return Path(out)


def audio_chunks(path, out_dir, speech, chunk_s=600):
    """Mono 16 kHz 32 kbps mp3 chunks cut in the middle of the silence gap nearest each
    multiple of chunk_s. -> [(path, offset_s)]"""
    dur = probe(path)["duration"]
    edges = [0.0] + [x for iv in speech for x in iv] + [dur]
    mids = [(a + b) / 2 for a, b in zip(edges[::2], edges[1::2]) if b > a]
    cuts, k = [0.0], 1
    while k * chunk_s < dur:
        target = k * chunk_s
        near = [m for m in mids if abs(m - target) <= chunk_s / 2]
        # ponytail: no gap within chunk_s/2 -> hard cut mid-speech; the transcript join check flags it
        c = min(near, key=lambda m: abs(m - target)) if near else target
        if cuts[-1] + 1 < c < dur - 1:
            cuts.append(c)
        k += 1
    cuts.append(dur)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for i, (a, b) in enumerate(zip(cuts, cuts[1:])):
        f = out_dir / f"chunk{i:03d}.mp3"
        _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-i", path, "-t", f"{b - a:.3f}",
              "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-b:a", "32k", f])
        if f.stat().st_size >= MAX_CHUNK_BYTES:
            raise RuntimeError(f"audio chunk {f.name} is over 24 MB; lower chunk_s")
        chunks.append((f, round(a, 3)))
    return chunks


def _even(x):
    return max(2, int(x) // 2 * 2)


def _crop(box, sw, sh):
    x, y, w, h = box
    cw, ch = _even(sw * w), _even(sh * h)
    cx, cy = min(int(sw * x), sw - cw), min(int(sh * y), sh - ch)
    return f"crop={cw}:{ch}:{max(0, cx)}:{max(0, cy)}", cw, ch


def _fit(w, h, max_h):
    """Scale (w, h) to width 1080, shrinking if taller than max_h. -> even (w, h)."""
    ow, oh = W, W * h / w
    if oh > max_h:
        ow, oh = ow * max_h / oh, max_h
    return _even(ow), _even(oh)


def boxes(layout, sw, sh):
    """Pure layout geometry on the 1080x1920 canvas: {"content": (x, y, w, h), "inset": (x, y, w, h)|None}.
    Content and inset each get their own rectangle inside [TITLE_H, CAP_TOP]; they never overlap."""
    layout = layout or {}
    if layout.get("mode") != "crop":
        ow, oh = _fit(sw, sh, MAX_CONTENT_H)
        top = int(min(max((H - oh) / 2, TITLE_H), CAP_TOP - oh))
        return {"content": ((W - ow) // 2, top, ow, oh), "inset": None}
    _, cw, ch = _crop(layout["crop"], sw, sh)
    inset = None
    room = MAX_CONTENT_H
    if layout.get("inset"):
        _, iw, ih = _crop(layout["inset"], sw, sh)
        iw_out, ih_out = INSET_W, INSET_W * ih / iw
        if ih_out > MAX_CONTENT_H / 3:   # a very tall inset shrinks rather than starving the crop
            iw_out, ih_out = iw_out * MAX_CONTENT_H / 3 / ih_out, MAX_CONTENT_H / 3
        inset = [_even(iw_out), _even(ih_out)]
        room -= inset[1] + INSET_PAD      # crop height cap shrinks so both fit
    ow, oh = _fit(cw, ch, room)
    content = ((W - ow) // 2, TITLE_H, ow, oh)
    if inset:
        inset = (W - inset[0] - INSET_PAD, TITLE_H + oh + INSET_PAD, *inset)
    return {"content": content, "inset": inset}


def _geometry(layout, sw, sh):
    """-> (filtergraph ending in a 1080x1920 composite, content_top, content_bottom).
    content_bottom includes the inset, so captions go below both."""
    b = boxes(layout, sw, sh)
    x, top, ow, oh = b["content"]
    crop = _crop(layout["crop"], sw, sh)[0] if (layout or {}).get("mode") == "crop" else None
    main = ",".join(filter(None, [crop, f"scale={ow}:{oh}", "setsar=1",
                                  f"pad={W}:{H}:{x}:{top}:color={BG}"]))
    if not b["inset"]:
        return f"[0:v]fps={FPS},{main}", top, top + oh
    ix, iy, iw, ih = b["inset"]
    return (f"[0:v]fps={FPS},split[m][i];[m]{main}[bg];"
            f"[i]{_crop(layout['inset'], sw, sh)[0]},scale={iw}:{ih},setsar=1[in];"
            f"[bg][in]overlay={ix}:{iy}"), top, iy + ih


def _t(s):
    cs = int(round(max(0.0, s) * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _esc(text):
    """Plain text for an ASS Dialogue line: no newlines, no override blocks, no \\N-style escapes."""
    text = " ".join(str(text).split())
    return text.replace("\\", "\\\u2060").replace("{", "\\{").replace("}", "\\}")


def _ass(title, captions, title_v, cap_v, duration, w=W, h=H):
    """Title hangs from the top (\\an8) title_v px down; captions sit on a baseline (\\an2) cap_v px up."""
    style = ("Style: {},{},{},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,"
             "1,{},0,{},40,40,{},1")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {w}", f"PlayResY: {h}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style.format("Title", FONT, 52, 2, 8, title_v),
        style.format("Caption", FONT, 58, 4, 2, cap_v), "",
        "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    if title and title.strip():
        lines.append(f"Dialogue: 0,{_t(0)},{_t(duration + 1)},Title,,0,0,0,,{_esc(title)}")
    for c in captions or []:
        if str(c.get("text", "")).strip():
            lines.append(f"Dialogue: 0,{_t(c['start'])},{_t(c['end'])},Caption,,0,0,0,,{_esc(c['text'])}")
    return "\n".join(lines) + "\n"


def render(src, start, end, layout, captions, title, out, preset="veryfast", landscape=False):
    """Accurately cut [start, end) from src into an H.264 mp4 with burned captions: 1080x1920 portrait
    with the title band, or (landscape=True) the whole source frame at 1920x1080 with captions only
    (a title over the frame would cover slide text). The source audio is copied untouched when it
    is AAC; any other codec is encoded to AAC so the file plays everywhere."""
    src, out = Path(src).resolve(), Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    p = probe(src)
    dur = end - start
    if landscape:
        graph = (f"[0:v]fps={FPS},scale={H}:{W}:force_original_aspect_ratio=decrease,"
                 f"pad={H}:{W}:(ow-iw)/2:(oh-ih)/2:color={BG},setsar=1")
        ass_text = _ass("", captions, 0, 50, dur, H, W)
    else:
        graph, top, bottom = _geometry(layout, p["width"], p["height"])
        # the title ends just above the content; captions keep room for ~3 wrapped lines below it
        ass_text = _ass(title, captions, max(30, top - 180), H - min(H - 80, bottom + 290), dur)
    audio = ["-c:a", "copy"] if p["acodec"] == "aac" else ["-c:a", "aac", "-b:a", "192k"]
    # The .ass sits next to the output and ffmpeg runs there, so the filter sees a bare,
    # escape-free filename (mkstemp names are [a-z0-9_]) instead of a Windows path.
    fd, ass = tempfile.mkstemp(suffix=".ass", prefix="shera_", dir=out.parent)
    os.close(fd)
    ass = Path(ass)
    part = out.with_name(out.name + ".part")
    try:
        ass.write_text(ass_text, encoding="utf-8")
        fonts = FONTS_DIR.replace(":", "\\\\:")
        graph += f",ass={ass.name}:fontsdir={fonts},format=yuv420p[v]"
        _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src, "-t", f"{dur:.3f}",
              "-filter_complex", graph, "-map", "[v]", "-map", "0:a:0",
              "-c:v", "libx264", "-preset", preset, "-crf", "20", "-pix_fmt", "yuv420p", "-r", FPS,
              *audio,
              "-movflags", "+faststart", "-f", "mp4", part.name], cwd=out.parent)
        os.replace(part, out)
    finally:
        ass.unlink(missing_ok=True)
        part.unlink(missing_ok=True)
    return out


def thumbnail(video, out_jpg, at_s):
    Path(out_jpg).parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, at_s):.3f}", "-i", video,
          "-frames:v", "1", "-q:v", "3", out_jpg])
    return Path(out_jpg)


def verify(path, expected_duration, size=(W, H)):
    """-> list of problems; empty means OK."""
    try:
        p = probe(path)
    except Exception as e:  # unreadable file is a problem to report, not a crash
        return [f"unreadable: {e}"]
    probs = []
    if p["vcodec"] != "h264":
        probs.append(f"video codec {p['vcodec']}, expected h264")
    if p["acodec"] != "aac":
        probs.append(f"audio codec {p['acodec']}, expected aac")
    if (p["width"], p["height"]) != tuple(size):
        probs.append(f"size {p['width']}x{p['height']}, expected {size[0]}x{size[1]}")
    if abs(p["duration"] - expected_duration) > 0.25:
        probs.append(f"duration {p['duration']:.2f}s, expected {expected_duration:.2f}s")
    if p["has_audio"] and abs(p["v_start"] - p["a_start"]) > 0.2:
        probs.append(f"stream starts differ: video {p['v_start']:.3f}s, audio {p['a_start']:.3f}s")
    v_end, a_end = p["v_start"] + p["v_duration"], p["a_start"] + p["a_duration"]
    if p["has_audio"] and p["v_duration"] and p["a_duration"] and abs(v_end - a_end) > 0.2:
        probs.append(f"stream ends differ: video {v_end:.3f}s, audio {a_end:.3f}s")
    return probs
