import pytest

from shera.candidates import build_windows, caption_lines, rank_score, shortlist

WORDS = "one two three four five six seven eight nine ten"


def units(n, dur=5.0, gap=0.0, text=WORDS):
    return [{"start": i * (dur + gap), "end": i * (dur + gap) + dur, "text": text, "speaker": None} for i in range(n)]


def test_windows_are_whole_units_within_limits():
    us = units(60)
    wins = build_windows(us)
    assert wins
    starts = [us[a]["start"] for a, _ in wins]
    assert all(b - a >= 20 for a, b in zip(starts, starts[1:]))
    for a, b in wins:
        span = us[b]["end"] - us[a]["start"]
        assert 15 <= span <= 60
    assert us[wins[0][1]]["end"] - us[wins[0][0]]["start"] == 35  # extends to the target


def test_window_stops_before_exceeding_max():
    us = units(3, dur=25.0)
    assert build_windows(us) == [(0, 1), (1, 2)]  # 50 s spans; adding a third unit would be 75 s


def test_low_speech_and_low_word_windows_are_skipped():
    assert build_windows(units(20, dur=2.0, gap=6.0)) == []  # coverage 25%
    assert build_windows(units(20, text="hi there")) == []  # 14 words in 35 s


def test_rank_score():
    assert rank_score(4, 4, 4) == pytest.approx(1.0)
    assert rank_score(2, 0, 0) == pytest.approx(0.225)


def c(id, start, end, v=3, cl=3, o=2):
    return {"id": id, "start": start, "end": end, "value": v, "clarity": cl, "score": rank_score(v, cl, o)}


def test_shortlist_eligibility_order_and_overlap():
    cands = [c(1, 0, 40, o=1), c(2, 20, 60, o=4), c(3, 100, 140), c(4, 200, 240, v=1, o=4),
             c(5, 300, 340, cl=1), c(6, 400, 440, o=1)]
    # 4 and 5 are ineligible; 1 overlaps 2 by 20 s > 30% of 40 s
    assert shortlist(cands) == [2, 3, 6]
    assert shortlist([c(7, 500, 530), c(8, 100, 130)]) == [8, 7]  # ties go to the earlier start


def test_shortlist_may_be_empty_and_respects_n():
    assert shortlist([c(1, 0, 30, v=1)]) == []
    assert len(shortlist([c(i, i * 100, i * 100 + 30) for i in range(15)])) == 10


def test_caption_lines_relative_and_clamped():
    us = [{"start": 10.0, "end": 14.0, "text": "আজকে আমরা Task 2 নিয়ে কথা বলব। " * 3, "speaker": None},
          {"start": 14.0, "end": 16.0, "text": "short", "speaker": None}]
    lines = caption_lines(us, 0, 1, 11.0, 15.0)
    assert all(len(x["text"]) <= 42 for x in lines)
    assert lines[0]["start"] == 0.0 and lines[-1]["end"] == 4.0
    assert lines[-1]["text"] == "short"
    assert all(a["end"] <= b["start"] + 1e-9 for a, b in zip(lines, lines[1:]))
    assert lines[0]["text"].startswith("আজকে আমরা Task 2")  # text preserved as spoken
