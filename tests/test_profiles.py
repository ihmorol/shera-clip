import json

import httpx
import pytest

from shera import config, db, pipeline, profiles, providers


def response(payload):
    return httpx.Response(200, json=payload, request=httpx.Request("POST", providers.CHAT_URL))


def test_presets_and_custom_profile_are_validated():
    assert set(profiles.PRESETS) == {"general", "education", "interview", "product", "story", "ielts"}
    custom = profiles.resolve({"preset": "interview", "intent": "Find candid technical decisions",
                               "criteria": ["Names the tradeoff", "Explains the result"],
                               "min_s": 20, "target_s": 35, "max_s": 50})
    assert custom["intent"] == "Find candid technical decisions"
    assert custom["criteria"] == ["Names the tradeoff", "Explains the result"]
    assert (custom["min_s"], custom["target_s"], custom["max_s"]) == (20, 35, 50)
    assert sum(custom["weights"].values()) == pytest.approx(1)
    with pytest.raises(ValueError, match="durations"):
        profiles.resolve({"preset": "general", "min_s": 90, "target_s": 30})
    with pytest.raises(ValueError, match="weights"):
        profiles.resolve({"preset": "general", "weights": {"value": float("nan"), "clarity": 0,
                                                               "opening": 0, "postable": 1}})
    with pytest.raises(ValueError, match="suggest_criteria"):
        profiles.resolve({"preset": "general", "suggest_criteria": "yes"})


def test_profile_minimums_control_shortlisting():
    from shera import candidates

    item = {"id": 1, "start": 0, "end": 30, "value": 1, "clarity": 1, "score": 0.5,
            "teacher": 1, "jev": {"postable": {"score": 1}, "offtopic": {"noul": 0}, "private": {"noul": 0}}}
    assert candidates.shortlist([item]) == []
    profile = {"preset": "general", "minimums": {"value": 1, "clarity": 1, "postable": 1}}
    assert candidates.shortlist([item], profile=profile) == [1]


def test_new_jobs_store_general_profile_and_old_jobs_use_ielts(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(pipeline, "_spawn", lambda job_id: None)
    job_id = pipeline.start_job(video)
    assert db.get_job(job_id)["profile"]["preset"] == "general"
    db.x("INSERT INTO jobs(id, created, flags) VALUES ('old', 0, '[]')")
    assert pipeline.job_profile("old")["preset"] == "ielts"


def test_generic_jev_uses_profile_goal_and_categories(monkeypatch):
    answers = {q: {"score": 3} for q in providers.SCORES}
    answers.update({q: {"noul": 0.8 if q in ("teacher", "complete", "takeaway") else 0.1}
                    for q in providers.NOULS})
    answers["category"] = {"choice": "answer"}
    sent = {}

    def post(url, **kwargs):
        sent.update(kwargs["json"])
        return response({"answers": answers, "usage": {"cost": 0.001}})

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(httpx, "post", post)
    out, cost = providers.jev_score("A hard choice", profile={"preset": "interview", "criteria": ["Names a tradeoff"]})
    assert out["category"] == "answer" and "skill" not in out and cost == 0.001
    assert "Names a tradeoff" in sent["questions"]["value"]["instructions"]
    assert set(sent["questions"]["category"]["criteria"]) == set(profiles.PRESETS["interview"]["categories"])


def test_profile_suggestion_is_normalized(monkeypatch):
    proposed = {"preset": "product", "intent": "Find demonstrations", "criteria": ["Shows the result"],
                "min_s": 15, "target_s": 30, "max_s": 45}
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: response(
        {"choices": [{"message": {"content": json.dumps(proposed)}}], "usage": {"cost": 0.002}}))
    out, cost = providers.suggest_profile("A product walkthrough")
    assert out["preset"] == "product" and out["criteria"] == ["Shows the result"] and cost == 0.002


def test_auto_criteria_waits_once_then_confirmed_profile_scores(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    initial = profiles.resolve({"preset": "general", "intent": "Find useful product moments",
                                "suggest_criteria": True})
    db.x("INSERT INTO jobs(id, created, duration, authorized_usd, flags, profile) VALUES (?, 0, 75, ?, '[]', ?)",
         "auto", config.CAP_USD, json.dumps(initial))
    folder = pipeline.job_dir("auto")
    folder.mkdir(parents=True)
    units = [{"start": i * 5, "end": i * 5 + 5, "text": f"This product demonstration explains the useful result {i}",
              "en": f"This product demonstration explains the useful result {i}"} for i in range(15)]
    (folder / "transcript.json").write_text(json.dumps({"source": "test", "units": units}), encoding="utf-8")
    suggested = []

    def suggest(description):
        suggested.append(description)
        return {"preset": "product", "intent": "Find useful demonstrations", "criteria": ["Shows the result"],
                "min_s": 30, "target_s": 45, "max_s": 60}, 0.001

    monkeypatch.setattr(providers, "suggest_profile", suggest)
    assert pipeline._criteria("auto") is False
    first = db.get_job("auto")
    assert first["stage"] == "criteria" and first["status"] == "waiting" and not db.candidates("auto")
    assert first["profile"]["criteria_proposed"] and not first["profile"]["criteria_confirmed"]
    assert pipeline._criteria("auto") is False and len(suggested) == 1
    confirmed = {**db.get_job("auto")["profile"], "criteria_confirmed": True}
    db.update_job("auto", profile=confirmed)
    assert pipeline._criteria("auto") is None
    monkeypatch.setattr(providers, "jev_score", lambda text, original=None, profile=None: (
        {"value": 3, "clarity": 3, "opening": 3, "postable": 3, "teacher": 1, "complete": 1,
         "category": "feature_demo", "raw": {"postable": {"score": 3}}}, 0.001))
    pipeline._candidates("auto")
    pipeline._score("auto")
    assert db.candidates("auto") and any(c["shortlisted"] for c in db.candidates("auto"))
    assert len([c for c in db.q("SELECT * FROM paid_calls WHERE job_id=?", "auto") if c["kind"] == "profile"]) == 1
