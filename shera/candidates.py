"""Deterministic candidate windows over whole transcript units (D17, D24)."""
import re

from shera import config


def build_windows(units, min_s=None, target_s=None, max_s=None, stride_s=30):
    min_s, target_s, max_s = (min_s or config.CLIP_MIN_S, target_s or config.CLIP_TARGET_S, max_s or config.CLIP_MAX_S)
    wins, last = [], None
    for i, u in enumerate(units):
        if last is not None and u["start"] < last + stride_s:
            continue
        last = u["start"]
        j = i
        while (j + 1 < len(units) and units[j]["end"] - u["start"] < target_s
               and units[j + 1]["end"] - u["start"] <= max_s):
            j += 1
        span = units[j]["end"] - u["start"]
        if not min_s <= span <= max_s:
            continue
        window = units[i:j + 1]
        speech = sum(w["end"] - w["start"] for w in window)
        words = sum(len(w["text"].split()) for w in window)
        if speech / span < 0.5 or words < span / 2:  # about 30 words a minute is the floor for real talk
            continue
        wins.append((i, j))
    return wins


def rank_score(v, c, o, postable=None):
    """0..1. With Jev's "postable" answer (D26), usefulness as a standalone video leads the ranking."""
    if postable is None:
        wv, wc, wo = config.WEIGHTS
        return wv * v / 4 + wc * c / 4 + wo * o / 4
    return (0.30 * v + 0.20 * c + 0.10 * o + 0.40 * postable) / 4


def is_teacher(c):
    """Jev's answer to "is this the teacher talking, not a played recording?" (older scores lack it)."""
    return c.get("teacher") is None or c["teacher"] >= 0.5


def jev(c, q):
    """One number from Jev's stored answer (score or yes-probability), or None when not asked."""
    a = (c.get("jev") or {}).get(q) or {}
    v = a.get("score", a.get("noul"))
    return None if v is None else float(v)


def blocker(c):
    """Why Jev's answers rule a scored candidate out, in plain words, or None (mirrors shortlist)."""
    if (c["value"] or 0) < 2 or (c["clarity"] or 0) < 2:
        return "low"
    if not is_teacher(c):
        return "recording"
    if (jev(c, "offtopic") or 0) >= 0.5:
        return "offtopic"
    if (jev(c, "private") or 0) >= 0.5:
        return "private"
    if (jev(c, "postable") if jev(c, "postable") is not None else 4) < 2:
        return "unpostable"
    return None


def shortlist(cands, n=10):
    """cands: dicts with id, start, end, value, clarity, score, and optionally teacher, jev, text_en/text.
    Keeps teacher talk worth >= 2 on value and clarity that Jev finds postable, on-topic and free of student
    details, with no big time overlap and no repeated passage (a listening recording played twice).
    Returns kept ids in rank order (may be empty)."""
    ok = [c for c in cands if blocker(c) is None]
    kept = []
    for c in sorted(ok, key=lambda c: (-c["score"], c["start"])):
        if len(kept) == n:
            break
        if (all(_overlap(c, k) <= 0.3 * min(c["end"] - c["start"], k["end"] - k["start"]) for k in kept)
                and repeat_of(c, kept) is None):
            kept.append(c)
    return [c["id"] for c in kept]


def _words(c):
    return set(re.findall(r"\w+", (c.get("text_en") or c.get("text") or "").lower()))


def repeat_of(c, others, threshold=0.6):
    """The first of `others` whose words mostly match c's (the same passage said or played again), else None."""
    mine = _words(c)
    for o in others:
        theirs = _words(o)
        if mine and theirs and len(mine & theirs) / len(mine | theirs) >= threshold:
            return o
    return None


def _overlap(a, b):
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def _split(text, max_chars):
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > max_chars:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return lines + [cur] if cur else lines


def caption_lines(units, u0, u1, clip_start, clip_end, max_chars=42):
    """Timed caption lines relative to clip_start, clamped to the clip."""
    out, length = [], clip_end - clip_start
    for u in units[u0:u1 + 1]:
        parts = _split(u["text"], max_chars)
        total = sum(len(p) for p in parts) or 1
        t = u["start"]
        for p in parts:
            end = t + (u["end"] - u["start"]) * len(p) / total
            s, e = max(0.0, t - clip_start), min(length, end - clip_start)
            if e > s:
                out.append({"start": round(s, 3), "end": round(e, 3), "text": p})
            t = end
    return out
