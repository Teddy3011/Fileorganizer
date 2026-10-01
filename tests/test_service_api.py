import json
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from studysort.server import create_app
from studysort.service import StudySortService
from studysort.store import Store

FAST = {"checks": 1, "interval": 0.05, "timeout": 1.0}


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


@pytest.fixture
def env(tmp_path):
    """A service watching a temp folder (never the real Downloads) and a test client."""
    watch = tmp_path / "Downloads"
    watch.mkdir()
    db = str(tmp_path / "history.sqlite3")
    services = []

    def make(**kw):
        svc = StudySortService(str(watch), Store(db), stability=FAST, **kw)
        svc.start()
        services.append(svc)
        svc.save_profile({"courses": ["CS101"]})
        return svc, TestClient(create_app(svc, heartbeat=0.1))

    yield watch, make
    for svc in services:
        svc.stop()


def status_of(client, file_id):
    return client.get(f"/api/files/{file_id}").json()["status"]


def first_file(client, status):
    files = client.get("/api/files").json()
    return next((f for f in files if f["status"] == status), None)


def test_new_download_flows_to_approval_then_copy(env):
    watch, make = env
    _, client = make()
    (watch / "CS101_assignment.pdf").write_bytes(b"%PDF-1.4 not really")

    rec = wait_for(lambda: first_file(client, "awaiting_approval"))
    assert rec["course"] == "CS101" and rec["type"] == "Assignments"
    assert rec["planned_destination"] == "_StudySort/CS101/Assignments/CS101_assignment.pdf"
    assert "corrupted" in rec["analysis"]  # bad PDF is reported but still classified by name
    assert not (watch / "_StudySort").exists()  # nothing happens without approval

    assert client.post(f"/api/files/{rec['id']}/approve").status_code == 200
    done = wait_for(lambda: first_file(client, "copied"))
    assert done["actual_destination"] == "_StudySort/CS101/Assignments/CS101_assignment.pdf"
    assert (watch / "CS101_assignment.pdf").exists()  # copy, not move
    assert (watch / done["actual_destination"]).read_bytes() == b"%PDF-1.4 not really"
    assert client.post(f"/api/files/{rec['id']}/approve").status_code == 409
    assert len(client.get("/api/files").json()) == 1  # its own output was not re-processed


def test_crdownload_is_processed_only_after_rename(env):
    watch, make = env
    _, client = make(auto_organize=True)
    partial = watch / "lecture.pdf.crdownload"
    partial.write_bytes(b"half")
    time.sleep(0.5)
    assert client.get("/api/files").json() == []
    partial.rename(watch / "lecture.pdf")
    rec = wait_for(lambda: first_file(client, "copied"))
    assert rec["name"] == "lecture.pdf"


def test_auto_organize_never_overwrites_existing_output(env):
    watch, make = env
    _, client = make(auto_organize=True)
    existing = watch / "_StudySort" / "CS101" / "Exams & Quizzes"
    existing.mkdir(parents=True)
    (existing / "CS101 quiz.pdf").write_text("old")
    (watch / "CS101 quiz.pdf").write_text("new")
    rec = wait_for(lambda: first_file(client, "copied"))
    assert rec["actual_destination"].endswith("CS101 quiz (2).pdf")
    assert (existing / "CS101 quiz.pdf").read_text() == "old"


def test_move_mode_removes_original(env):
    watch, make = env
    _, client = make(auto_organize=True, move=True)
    (watch / "notes.txt").write_text("CS101 lecture notes")
    rec = wait_for(lambda: first_file(client, "moved"))
    assert not (watch / "notes.txt").exists()
    assert (watch / rec["actual_destination"]).read_text() == "CS101 lecture notes"


def test_failure_is_visible_and_retryable(env):
    watch, make = env
    svc, client = make()
    rec = svc.submit(str(watch / "ghost.pdf"))  # vanished before it stabilised
    failed = wait_for(lambda: first_file(client, "failed"))
    assert failed["id"] == rec["id"] and "disappeared" in failed["error"]

    svc.observer.stop()  # so only the Retry button (not the watcher) picks the file up again
    svc.observer.join()
    (watch / "ghost.pdf").write_text("back")
    assert client.post(f"/api/files/{rec['id']}/retry").status_code == 200
    wait_for(lambda: status_of(client, rec["id"]) == "awaiting_approval")


def test_failed_file_that_reappears_reuses_its_card(env):
    watch, make = env
    svc, client = make()
    rec = svc.submit(str(watch / "ghost.pdf"))
    wait_for(lambda: first_file(client, "failed"))
    (watch / "ghost.pdf").write_text("back")
    wait_for(lambda: status_of(client, rec["id"]) == "awaiting_approval")
    assert len(client.get("/api/files").json()) == 1


def test_cancel_and_api_errors(env):
    watch, make = env
    _, client = make()
    (watch / "a.txt").write_text("x")
    rec = wait_for(lambda: first_file(client, "awaiting_approval"))
    assert client.post(f"/api/files/{rec['id']}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/files/{rec['id']}/approve").status_code == 409
    assert client.post("/api/files/nope/approve").status_code == 404
    assert client.get("/api/files/nope").status_code == 404


def test_status_profile_classify_and_clear(env):
    watch, make = env
    _, client = make()
    status = client.get("/api/status").json()
    assert status["watch_dir"] == str(watch) and status["watcher_alive"] and not status["move"]

    assert client.put("/api/profile", json={"courses": ["Calculus"], "bogus": 1}).json()["courses"] == ["Calculus"]
    result = client.post("/api/classify", json={"files": [{"name": "calculus_hw.pdf"}]}).json()
    assert result[0]["course"] == "Calculus"
    body = client.post("/api/corrections", json={"filename": "thermodynamics.pdf", "type": "Reading"}).json()
    assert body["profile"]["corrections"]["thermodynamics"]["type"] == "Reading"

    (watch / "a.txt").write_text("x")
    wait_for(lambda: first_file(client, "awaiting_approval"))
    assert client.delete("/api/files").status_code == 200
    assert client.get("/api/files").json() == []
    assert (watch / "a.txt").exists()  # clearing history never deletes files


def test_history_survives_restart(env):
    watch, make = env
    svc, client = make()
    (watch / "a.txt").write_text("x")
    rec = wait_for(lambda: first_file(client, "awaiting_approval"))
    svc.stop()

    _, client2 = make()
    assert client2.get(f"/api/files/{rec['id']}").json()["status"] == "awaiting_approval"
    assert client2.post(f"/api/files/{rec['id']}/approve").status_code == 200
    wait_for(lambda: status_of(client2, rec["id"]) == "copied")


def test_other_websites_cannot_drive_the_api(env):
    _, make = env
    _, client = make()
    assert client.post("/api/files/x/approve", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/status", headers={"Host": "evil.example"}).status_code == 403
    assert client.get("/").status_code == 200  # dashboard is served


def test_event_stream_pushes_new_downloads_live(env):
    watch, make = env
    svc, _ = make()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(svc, heartbeat=0.2), host="127.0.0.1", port=port,
                                           log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_for(lambda: server.started)
    try:
        with httpx.stream("GET", f"http://127.0.0.1:{port}/api/events/stream", timeout=10) as response:
            assert response.headers["content-type"].startswith("text/event-stream")
            created = False
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if not created:
                    assert event["type"] == "status" and event["status"]["watcher_alive"]
                    (watch / "CS101_slides.pptx").write_text("x")
                    created = True
                elif event["type"] == "file" and event["file"]["status"] == "awaiting_approval":
                    assert event["file"]["name"] == "CS101_slides.pptx"
                    break
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_one_bad_file_does_not_stop_the_watcher(env):
    watch, make = env
    svc, client = make()
    svc.submit(str(watch / "missing.pdf"))
    wait_for(lambda: first_file(client, "failed"))
    (watch / "fine.txt").write_text("ok")
    wait_for(lambda: first_file(client, "awaiting_approval"))
    assert svc.status()["watcher_alive"]
    assert os.path.exists(watch / "fine.txt")
