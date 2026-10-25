import json
import time

from fastapi.testclient import TestClient

from shera import app as web, companion, config, db, ledger, pipeline, profiles, providers


def test_paired_review_and_criteria_roundtrip(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    client = TestClient(web.app, base_url=f"http://127.0.0.1:{config.PORT}")
    headers = {"Authorization": f"Bearer {companion.TOKEN}", "Origin": next(iter(companion.origins()))}
    profile = profiles.resolve("interview")
    db.x("INSERT INTO jobs(id,created,title,source_path,stage,status,progress,duration,flags,profile) "
         "VALUES('j',?,'Interview','x.mp4','authorize','waiting',0,120,'[]',?)", time.time(), json.dumps(profile))
    folder = pipeline.job_dir("j")
    folder.mkdir(parents=True)
    (folder / "transcript.json").write_text(json.dumps({"units": [{"start": 0, "end": 10, "text": "Synthetic answer"}]}))
    assert client.get("/companion/jobs").status_code == 401
    assert client.get("/companion/jobs", headers=headers).status_code == 200
    assert client.post("/import", headers=headers).status_code == 403
    proposed = profiles.resolve({"preset": "interview", "criteria": ["Keep practical answers"]})
    monkeypatch.setattr(providers, "suggest_profile", lambda description: (proposed, 0.001))
    result = client.post("/companion/jobs/j/suggest-profile", headers=headers,
                         json={"authorize": True, "intent": "Advice for new founders"})
    assert result.status_code == 200 and result.json()["profile"]["criteria"] == ["Keep practical answers"]
    assert ledger.spent("j") == 0.001
    assert db.get_job("j")["profile"]["criteria"] == []
    assert client.post("/companion/jobs/j/profile", headers=headers, json=proposed).status_code == 200
    cid = db.x('INSERT INTO candidates(job_id,u0,u1,start,"end",text,category) '
               "VALUES('j',0,0,0,10,'Synthetic answer','insight')")
    path = f"/companion/jobs/j/clips/{cid}"
    assert client.post(path, headers=headers, json={"category": "insight", "title": "An insight"}).status_code == 200
    assert client.post(path, headers=headers, json={"category": "exam_tip"}).status_code == 422
    assert client.post(path, headers=headers, json=[]).status_code == 422
    assert client.post(path, headers=headers, json={"drafts": {"youtube": "bad"}}).status_code == 422
    assert client.post(path + "/decision", headers=headers, json={"decision": "approve"}).status_code == 409
    assert client.post("/companion/jobs/j/profile", headers=headers, json=profile).status_code == 409
    assert client.post(path + "/decision", headers=headers, json={"decision": "reject"}).status_code == 200
    assert db.review(cid)["status"] == "rejected"
