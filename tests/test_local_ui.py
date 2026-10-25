import json

from fastapi.testclient import TestClient

from shera import app as web, config, db, pipeline, profiles


def test_native_upload_keeps_selection_and_optional_files(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    client = TestClient(web.app, base_url=f"http://127.0.0.1:{config.PORT}")
    monkeypatch.setattr(pipeline, "_spawn", lambda job: None)
    result = client.post("/import/upload", files={"video": ("Interview.mp4", b"synthetic"),
                         "vtt_file": ("Interview.vtt", b"WEBVTT")},
                         data={"preset": "interview", "intent": "Practical answers", "min_s": 10,
                               "target_s": 20, "max_s": 30, "suggest_criteria": "true"}, follow_redirects=False)
    assert result.status_code == 303
    job = db.list_jobs()[0]
    assert job["title"] == "Interview" and job["vtt_path"]
    assert job["profile"]["preset"] == "interview" and job["profile"]["intent"] == "Practical answers"
    assert job["profile"]["suggest_criteria"] is True
    html = client.get("/").text
    assert '/import/upload' in html and 'data-library-search' in html
    assert 'Interview' in html and 'Your video library' in html
    assert client.post("/import/upload", files={"video": ("x.mp4", b"x")},
                       data={"min_s": 90, "target_s": 30, "max_s": 60}).status_code == 400
    assert client.post("/import/upload", headers={"Origin": "https://evil.example"},
                       files={"video": ("x.mp4", b"x")}).status_code == 403


def test_local_ai_criteria_can_be_confirmed_without_spending(tmp_path, monkeypatch):
    config.set_data(tmp_path / "data")
    db.init()
    client = TestClient(web.app, base_url=f"http://127.0.0.1:{config.PORT}")
    profile = profiles.resolve({"preset": "interview", "criteria_proposed": True, "suggest_criteria": True})
    db.x("INSERT INTO jobs(id,created,title,source_path,stage,status,progress,flags,profile) "
         "VALUES('j',0,'Interview','x.mp4','criteria','waiting',1,'[]',?)", json.dumps(profile))
    resumed = []
    monkeypatch.setattr(pipeline, "resume", resumed.append)
    html = client.get("/jobs/j").text
    assert "Review the AI's selection criteria" in html and "Save criteria and continue" in html
    result = client.post("/jobs/j/criteria", data={"intent": "Useful answers", "criteria": "Skip repeats\nKeep full answers",
                         "min_s": 10, "target_s": 20, "max_s": 30}, follow_redirects=False)
    assert result.status_code == 303 and resumed == ["j"]
    saved = db.get_job("j")["profile"]
    assert saved["criteria_confirmed"] is True and saved["criteria"] == ["Skip repeats", "Keep full answers"]
