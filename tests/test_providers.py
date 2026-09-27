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
    monkeypatch.setenv("OPENAI_API_KEY", "k-test")


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
