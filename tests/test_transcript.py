from shera.transcript import check_alignment, parse_vtt, units_from_whisper

ZOOM = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
Rimon Ahmed: আজকে আমরা Task 2 নিয়ে কথা বলব।

2
00:00:03.000 --> 00:00:05.500 align:start position:0%
Rimon Ahmed: Task 2: introduction first.

3
00:01:02.250 --> 01:00:04.000
Student: &lt;ok&gt; <c>thanks</c>
"""


def test_zoom_vtt_speaker_times_and_bangla():
    u = parse_vtt(ZOOM)
    assert u[0] == {"start": 1.0, "end": 3.0, "text": "আজকে আমরা Task 2 নিয়ে কথা বলব।", "speaker": "Rimon Ahmed"}
    assert u[1]["text"] == "Task 2: introduction first." and u[1]["end"] == 5.5
    assert u[2]["start"] == 62.25 and u[2]["end"] == 3604.0
    assert u[2]["speaker"] == "Student" and u[2]["text"] == "<ok> thanks"


def test_mm_ss_times_and_no_speaker():
    u = parse_vtt("WEBVTT\n\n01:02.500 --> 01:04.000\nTask 2: plan your essay\n")
    assert u == [{"start": 62.5, "end": 64.0, "text": "Task 2: plan your essay", "speaker": None}]


def test_rolling_captions_keep_only_new_words_and_drop_repeats():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:01.000
Hello everyone

00:00:01.000 --> 00:00:02.000
Hello everyone today we

00:00:02.000 --> 00:00:03.000
Hello everyone today we

00:00:03.000 --> 00:00:04.000
Hello everyone today we learn Task 2

00:00:04.000 --> 00:00:05.000

"""
    u = parse_vtt(vtt.replace("\n", "\r\n"))
    assert [x["text"] for x in u] == ["Hello everyone", "today we", "learn Task 2"]
    assert u[1]["end"] == 3.0  # the repeated cue extends the previous unit


def test_whisper_offsets_become_absolute_and_joins_flagged():
    a = {"segments": [{"start": 0.5, "end": 4.0, "text": " প্রথম অংশ"}, {"start": 4.0, "end": 9.0, "text": " same"}]}
    b = {"segments": [{"start": 0.0, "end": 2.0, "text": "same"}, {"start": 5.0, "end": 8.0, "text": " next part"}]}
    units, flags = units_from_whisper([(0, a), (1200.0, b)])
    assert [(x["start"], x["end"], x["text"]) for x in units] == [
        (0.5, 4.0, "প্রথম অংশ"), (4.0, 9.0, "same"), (1205.0, 1208.0, "next part")]
    assert len(flags) == 1 and "join" in flags[0]


def test_check_alignment():
    units = [{"start": i * 5.0, "end": i * 5 + 4.0, "text": "x", "speaker": None} for i in range(30)]
    assert check_alignment(units, [(0, 150)], 150) == []
    flags = check_alignment(units, [(0, 50)], 150)
    assert any("no speech" in f for f in flags)
    assert any("after the recording" in f for f in check_alignment(units, [(0, 150)], 100))
    assert any("only 5" in f for f in check_alignment(units[:5], [(0, 150)], 150))


def test_word_timestamps_become_sentence_lines():
    words = [{"word": w, "start": s, "end": s + 0.4} for w, s in
             [("আজকে", 0.0), ("আমরা", 0.5), ("Task", 1.0), ("2", 1.4), ("পড়ব।", 1.8),
              ("Paraphrase", 2.4), ("the", 2.9), ("question", 3.3), ("first", 5.0)]]  # 1.3 s pause before "first"
    units, flags = units_from_whisper([(100.0, {"segments": [{"start": 0, "end": 6, "text": "one long language segment"}],
                                                "words": words})])
    assert [u["text"] for u in units] == ["আজকে আমরা Task 2 পড়ব।", "Paraphrase the question", "first"]
    assert units[0]["start"] == 100.0 and units[1]["end"] == 103.7 and not flags
