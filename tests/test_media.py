import hashlib
import subprocess

import pytest

from shera import media

MAIN_TONES = [(1, 7), (9, 19), (21, 33), (35, 44), (46, 58)]   # 60 s, silence between
VFR_TONES = [(2, 8), (11, 18)]                                  # 20 s, VFR, streams start at 3 s
CAPS = [{"start": 0, "end": 2, "text": "আজকে আমরা Task 2 নিয়ে কথা বলব।"},
        {"start": 2, "end": 3, "text": "{not a tag} back\\slash"}]


def _make(path, dur, tones, extra_v="", extra_out=()):
    cond = "+".join(f"between(t,{a},{b})" for a, b in tones)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "lavfi", "-i", f"testsrc2=s=1280x720:r=25:d={dur}{extra_v}",
         "-f", "lavfi", "-i", f"aevalsrc='if({cond},0.5*sin(2*PI*440*t),0)':s=48000:d={dur}",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", *extra_out, str(path)],
        check=True)
    return path


@pytest.fixture(scope="module")
def main(tmp_path_factory):
    return _make(tmp_path_factory.mktemp("m") / "main.mp4", 60, MAIN_TONES)


@pytest.fixture(scope="module")
def vfr(tmp_path_factory):
    # jittered timestamps -> variable frame rate; output_ts_offset -> nonzero stream start
    return _make(tmp_path_factory.mktemp("v") / "vfr.mp4", 20, VFR_TONES,
                 extra_v=",settb=1/1000,setpts=(N/25+0.015*sin(N))/TB",
                 extra_out=("-fps_mode", "vfr", "-enc_time_base:v", "1:1000",
                            "-output_ts_offset", "3"))


def _close(got, want, tol=0.3):
    assert len(got) == len(want), got
    for (a, b), (c, d) in zip(got, want):
        assert abs(a - c) <= tol and abs(b - d) <= tol, (got, want)


def test_probe(main, vfr):
    p = media.probe(main)
    assert (p["width"], p["height"], p["vcodec"], p["acodec"], p["has_audio"]) == \
        (1280, 720, "h264", "aac", True)
    assert abs(p["duration"] - 60) < 0.2
    q = media.probe(vfr)
    rates = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                            "stream=r_frame_rate,avg_frame_rate", "-of", "csv=p=0", str(vfr)],
                           capture_output=True, text=True).stdout.split()[0].split(",")
    assert rates[0] != rates[1]   # fixture really is variable frame rate
    assert q["v_start"] >= 2.9 and q["a_start"] >= 2.9 and abs(q["duration"] - 20) < 0.3


def test_copy_with_hash(main, tmp_path):
    dst = tmp_path / "out" / "source.mp4"
    dst.parent.mkdir()
    (dst.parent / "source.mp4.part").write_bytes(b"stale partial copy")
    seen = []
    sha, n = media.copy_with_hash(main, dst, seen.append)
    data = main.read_bytes()
    assert (sha, n) == (hashlib.sha256(data).hexdigest(), len(data))
    assert dst.read_bytes() == data and not (dst.parent / "source.mp4.part").exists()
    assert seen and seen[-1] == 1.0


def test_speech_intervals(main, vfr):
    _close(media.speech_intervals(main), MAIN_TONES)
    _close(media.speech_intervals(vfr), VFR_TONES)   # zero-based despite the 3 s stream start


def test_audio_chunks(main, tmp_path):
    chunks = media.audio_chunks(main, tmp_path, MAIN_TONES, chunk_s=20)
    # gap midpoints nearest 20 s and 40 s are 20.0 and 45.0
    assert [o for _, o in chunks] == pytest.approx([0, 20, 45], abs=0.01)
    for (f, o), end in zip(chunks, [20, 45, 60]):
        p = media.probe(f)
        assert p["acodec"] == "mp3" and abs(p["duration"] - (end - o)) < 0.2


def test_render_full_from_start(main, tmp_path):
    out = media.render(main, 0, 3, {"mode": "full"}, CAPS, "Task 2 টিপস", tmp_path / "a.mp4")
    assert media.verify(out, 3) == []
    assert not list(tmp_path.glob("*.ass")) and not list(tmp_path.glob("*.part"))



def _audio(path):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                           "stream=codec_name,sample_rate,channels,profile", "-of", "csv=p=0", str(path)],
                          capture_output=True, text=True, check=True).stdout


def test_render_landscape_keeps_original_audio(main, tmp_path):
    out = media.render(main, 1, 4, {"mode": "full"}, CAPS, "ignored in landscape", tmp_path / "l.mp4", landscape=True)
    assert media.verify(out, 3, (1920, 1080)) == []
    assert _audio(out) == _audio(main)  # stream-copied: same codec, rate, channels, profile

def test_render_is_cut_on_source_timeline(main, vfr, tmp_path):
    # main tone starts at 1 s -> a clip from 0.5 s hears it at ~0.5 s
    out = media.render(main, 0.5, 4, {"mode": "full"}, [], "", tmp_path / "b.mp4")
    assert media.verify(out, 3.5) == []
    _close(media.speech_intervals(out), [(0.5, 3.5)])
    # vfr tone 2-8 s (zero-based, streams start at 3 s): clip 6-10 -> speech 0-2
    out = media.render(vfr, 6, 10, {"mode": "full"}, [], "", tmp_path / "c.mp4")
    assert media.verify(out, 4) == []
    _close(media.speech_intervals(out), [(0, 2)])


def test_render_crop_inset_to_last_second(vfr, tmp_path):
    dur = media.probe(vfr)["duration"]
    layout = {"mode": "crop", "crop": [0, 0, 0.7, 1], "inset": [0.7, 0.6, 0.3, 0.4]}
    out = media.render(vfr, dur - 3, dur, layout, CAPS, "শিরোনাম", tmp_path / "d.mp4")
    assert media.verify(out, 3) == []
    thumb = media.thumbnail(out, tmp_path / "t.jpg", 1)
    assert thumb.stat().st_size > 1000


@pytest.mark.parametrize("layout,sw,sh", [
    ({"mode": "full"}, 1280, 720), ({"mode": "full"}, 720, 1280),
    ({"mode": "crop", "crop": [0, 0, 0.5, 1], "inset": None}, 1280, 720),
    ({"mode": "crop", "crop": [0.1, 0.1, 0.6, 0.8], "inset": [0.7, 0.7, 0.3, 0.3]}, 1280, 720)])
def test_content_stays_between_bands(layout, sw, sh):
    _, top, bottom = media._geometry(layout, sw, sh)
    assert media.TITLE_H <= top < bottom <= media.CAP_TOP


@pytest.mark.parametrize("crop,inset", [
    ([0, 0, 0.7, 1], [0.7, 0.6, 0.3, 0.4]),        # tall crop: its height cap must shrink
    ([0, 0, 0.3, 1], [0.7, 0.7, 0.3, 0.3]),        # very tall crop
    ([0.1, 0.1, 0.8, 0.4], [0.9, 0.1, 0.05, 0.8]),  # very tall, thin inset
])
def test_inset_never_overlaps_content(crop, inset):
    b = media.boxes({"mode": "crop", "crop": crop, "inset": inset}, 1280, 720)
    (cx, cy, cw, ch), (ix, iy, iw, ih) = b["content"], b["inset"]
    assert iy >= cy + ch or cy >= iy + ih or ix >= cx + cw or cx >= ix + iw
    for x, y, w, h in (b["content"], b["inset"]):
        assert 0 <= x and x + w <= media.W and media.TITLE_H <= y and y + h <= media.CAP_TOP


def test_verify_reports_wrong_file(main):
    probs = media.verify(main, 3)
    assert any("size" in p for p in probs) and any("duration" in p for p in probs)
