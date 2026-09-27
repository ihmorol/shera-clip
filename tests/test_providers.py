import json

import httpx
import pytest

from shera import config, providers
from shera.ledger import ProviderError


def fake_post(payload, status=200):
    def post(url, **kw):
        post.sent = kw
        return httpx.Response(status, json=payload, request=httpx.Request("POST", url))
    return post


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k-test")


def jev_answer(**over):
    a = {"value": {"score": 3.4}, "clarity": {"score": 2}, "opening": {"score": 1},
         "category": {"choice": "exam_tip"}}
    a.update(over)
    return {"answers": a, "usage": {"cost": 0.0012}}


def test_jev_parses_scores_category_and_cost(monkeypatch):
    post = fake_post(jev_answer())
    monkeypatch.setattr(httpx, "post", post)
    out, cost = providers.jev_score("Task 2 tip")
    assert out == {"value": 3.4, "clarity": 2.0, "opening": 1.0, "category": "exam_tip"}
    assert cost == 0.0012
    body = post.sent["json"]
    assert body["model"] == "typesafe/jev-1.13" and body["state"] == {"excerpt": "Task 2 tip"}
    assert set(body["questions"]) == {"value", "clarity", "opening", "category"}


def test_jev_bad_shape_is_billed_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", fake_post(jev_answer(category={"choice": "made_up"})))
    with pytest.raises(ProviderError) as e:
        providers.jev_score("x")
    assert e.value.billed and e.value.cost == 0.0012


def test_draft_shape_and_http_error(monkeypatch):
    content = {p: {"title": "t", "description": "d", "cta": "c"} for p in ("facebook", "youtube")}
    monkeypatch.setattr(httpx, "post", fake_post(
        {"choices": [{"message": {"content": json.dumps(content)}}], "usage": {"cost": 0.0003}}))
    assert providers.draft_post("x", "exam_tip") == (content, 0.0003)
    monkeypatch.setattr(httpx, "post", fake_post({"error": "no"}, status=402))
    with pytest.raises(httpx.HTTPStatusError):
        providers.draft_post("x", "exam_tip")


def test_missing_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    monkeypatch.setattr(config, "openrouter_key", lambda: None)
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        providers.jev_score("x")


def test_transcribe_uses_openrouter_and_falls_back_on_400(monkeypatch, tmp_path):
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"x")
    seen = []

    def post(url, **kw):
        seen.append((url, kw["data"]["model"], kw["headers"]["Authorization"]))
        if kw["data"]["model"] == config.STT_MODEL:
            return httpx.Response(400, json={"error": "timestamps unsupported"}, request=httpx.Request("POST", url))
        return httpx.Response(200, json={"segments": [{"start": 0, "end": 1, "text": "hi"}], "duration": 60,
                                         "usage": {"cost": 0.004}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    data, cost = providers.transcribe(audio)
    assert [s[0] for s in seen] == [providers.STT_URL] * 2 and "openrouter.ai" in providers.STT_URL
    assert [s[1] for s in seen] == [config.STT_MODEL, "openai/whisper-1"]
    assert seen[0][2] == "Bearer k-test" and data["model"] == "openai/whisper-1" and cost == 0.004
