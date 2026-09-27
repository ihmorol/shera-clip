"""Transcript units from VTT or speech-to-text (verbose_json) output. `text` is kept exactly as spoken;
an English translation, when made, sits beside it in `en`."""
import html
import re

TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{3})")
TAG = re.compile(r"<[^>]+>")
# ponytail: a speaker is 1-5 letter-only words before ": " ("Rimon Ahmed: ..."); "Task 2: ..." is not.
# A lone word like "Note: ..." is mistaken for a speaker; tighten if real VTTs show it.
SPEAKER = re.compile(r"^([^\W\d_]+(?:[ .'-]+[^\W\d_]+){0,4}):\s+(.*)$", re.S)


def _secs(m):
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000


def parse_vtt(text):
    units, prev = [], None
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n").lstrip("﻿")):
        lines = block.strip().split("\n")
        idx = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        times = [_secs(m) for m in TIME.finditer(lines[idx])]
        if len(times) < 2:
            continue
        start, end = times[:2]
        raw = html.unescape(TAG.sub("", " ".join(lines[idx + 1:]))).strip()
        speaker = None
        m = SPEAKER.match(raw)
        if m:
            speaker, raw = m.group(1), m.group(2).strip()
        body = raw
        if prev and raw.startswith(prev):  # rolling caption: keep only the new words
            body = raw[len(prev):].strip()
        if raw:
            prev = raw
        if not body:
            if units and raw:
                units[-1]["end"] = max(units[-1]["end"], end)
            continue
        units.append({"start": start, "end": end, "text": body, "speaker": speaker})
    return units


def units_from_whisper(chunks):
    """chunks: [(offset_s, verbose_json)]. Returns (units with absolute times, flags)."""
    units, flags = [], []
    for n, (offset, data) in enumerate(chunks):
        segs = _lines(data.get("words")) or [s for s in data.get("segments") or [] if s.get("text", "").strip()]
        for i, s in enumerate(segs):
            u = {"start": offset + s["start"], "end": offset + s["end"], "text": s["text"].strip(), "speaker": None}
            if n and i == 0 and units:
                if u["start"] - units[-1]["end"] > 2:
                    flags.append(f"transcription join at {_clock(offset)} has a {u['start'] - units[-1]['end']:.1f}s gap")
                if u["text"] == units[-1]["text"]:
                    continue
            units.append(u)
    return units, flags


END = re.compile(r"[.?!।]['\")\]]*$")


def _lines(words, gap=0.8, longest=12.0):
    """Sentence-sized lines from word timestamps: a line ends at sentence punctuation, a pause, or ~12 s.
    Providers such as MAI-Transcribe split segments only by language, which is too coarse for clips."""
    out, cur = [], []
    for w in words or []:
        text = str(w.get("word") or w.get("text") or "").strip()
        if not text or w.get("start") is None or w.get("end") is None:
            continue
        if cur and (w["start"] - cur[-1]["end"] > gap or cur[-1]["end"] - cur[0]["start"] > longest):
            out.append(cur)
            cur = []
        cur.append({"start": float(w["start"]), "end": float(w["end"]), "text": text})
        if END.search(text):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{"start": c[0]["start"], "end": c[-1]["end"], "text": " ".join(x["text"] for x in c)} for c in out]


def _clock(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"


def check_alignment(units, speech, duration):
    if not units:
        return ["transcript has no cues"]
    flags = []
    if len(units) < 20:
        flags.append(f"transcript has only {len(units)} cues")
    for u in {id(u): u for u in (units[0], units[len(units) // 2], units[-1])}.values():
        if not any(s <= u["start"] + 1 and e >= u["start"] - 1 for s, e in speech):
            flags.append(f"cue at {_clock(u['start'])} has no speech within 1 s")
    if units[-1]["end"] > duration + 1:
        flags.append(f"last cue ends at {_clock(units[-1]['end'])}, after the recording ends")
    return flags
