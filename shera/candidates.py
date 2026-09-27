"""Deterministic candidate windows over whole transcript units (D17)."""
from shera import config


def build_windows(units, min_s=15, target_s=35, max_s=60, stride_s=20):
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
        if speech / span < 0.5 or words < 20:
            continue
        wins.append((i, j))
    return wins


def rank_score(v, c, o):
    wv, wc, wo = config.WEIGHTS
    return wv * v / 4 + wc * c / 4 + wo * o / 4


def shortlist(cands, n=10):
    """cands: dicts with id, start, end, value, clarity, score. Returns kept ids in rank order (may be empty)."""
    ok = [c for c in cands if (c["value"] or 0) >= 2 and (c["clarity"] or 0) >= 2]
    kept = []
    for c in sorted(ok, key=lambda c: (-c["score"], c["start"])):
        if len(kept) == n:
            break
        if all(_overlap(c, k) <= 0.3 * min(c["end"] - c["start"], k["end"] - k["start"]) for k in kept):
            kept.append(c)
    return [c["id"] for c in kept]


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
