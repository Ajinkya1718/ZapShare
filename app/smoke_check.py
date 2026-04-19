import os
import sys
import tempfile
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

sandbox = tempfile.mkdtemp(prefix="zapshare_smoke_")
os.environ["DATA_DIR"] = sandbox
os.environ["DATABASE_NAME"] = str(Path(sandbox) / "zapshare.db")
os.environ["UPLOADS_DIR"] = str(Path(sandbox) / "uploads")
os.environ["SECRET_KEY"] = "smoke-test-secret"

import main


def expect(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def run_smoke() -> None:
    with TestClient(main.app) as alice_client:
        r = alice_client.get("/login")
        expect(r.status_code == 200, f"GET /login expected 200, got {r.status_code}")

        r = alice_client.post("/register", data={"username": "alice", "password": "pw1"}, follow_redirects=False)
        expect(r.status_code in (302, 303), f"register alice expected redirect, got {r.status_code}")

        r = alice_client.post("/register", data={"username": "bob", "password": "pw2"}, follow_redirects=False)
        expect(r.status_code in (302, 303), f"register bob expected redirect, got {r.status_code}")

        r = alice_client.post("/login", data={"username": "alice", "password": "pw1"}, follow_redirects=False)
        expect(r.status_code in (302, 303), f"login alice expected redirect, got {r.status_code}")

        with main.db_session() as db:
            bob_id = int(db.execute("SELECT id FROM users WHERE username='bob'").fetchone()["id"])
            alice_id = int(db.execute("SELECT id FROM users WHERE username='alice'").fetchone()["id"])

        r = alice_client.get(f"/chat/{bob_id}")
        expect(r.status_code == 200, f"GET /chat/{{bob}} expected 200, got {r.status_code}")

        r = alice_client.get(f"/api/messages/{alice_id}")
        expect(r.status_code == 400, f"self receiver expected 400, got {r.status_code}")

        r = alice_client.get("/api/messages/999999")
        expect(r.status_code == 404, f"unknown receiver expected 404, got {r.status_code}")

        r = alice_client.post("/api/send", json={"receiver_id": bob_id, "content": "hello live"})
        expect(r.status_code == 200, f"api send expected 200, got {r.status_code}")
        sent = r.json()
        expect(sent.get("content") == "hello live", "sent message content mismatch")

        r = alice_client.get(f"/api/messages/{bob_id}?after_msg=0&after_file=0")
        expect(r.status_code == 200, f"poll expected 200, got {r.status_code}")
        body = r.json()
        expect(any(m.get("id") == sent.get("id") for m in body.get("messages", [])), "sent message missing from poll")

        r = alice_client.post(
            "/upload",
            data={"receiver_id": str(bob_id)},
            files={"file": ("note.txt", b"hello file", "text/plain")},
            follow_redirects=False,
        )
        expect(r.status_code in (302, 303), f"upload expected redirect, got {r.status_code}")

        r = alice_client.get(f"/api/messages/{bob_id}?after_msg={sent.get('id')}&after_file=0")
        expect(r.status_code == 200, f"poll after upload expected 200, got {r.status_code}")
        files = r.json().get("files", [])
        expect(len(files) >= 1, "uploaded file missing from poll")
        file_id = int(files[-1]["id"])

        r = alice_client.get(f"/download/{file_id}")
        expect(r.status_code == 200, f"download expected 200, got {r.status_code}")

        # Validate SSE route registration and access checks.
        events_path = main.app.url_path_for("api_events", receiver_id=str(bob_id))
        expect(str(events_path) == f"/api/events/{bob_id}", "api_events route path mismatch")

        # Unit-level fan-out check keeps this test deterministic without blocking on stream reads.
        hub = main.RealtimeHub()
        convo_key, q1, became_online = hub.register(alice_id, bob_id)
        expect(became_online is True, "first register should mark user as online")
        _key2, q2, became_online_2 = hub.register(bob_id, alice_id)
        expect(became_online_2 is True, "peer first register should mark peer online")

        payload = {"id": 123, "content": "rt"}
        hub.publish_conversation_event(alice_id, bob_id, "message", payload)
        frame1 = q1.get(timeout=1)
        frame2 = q2.get(timeout=1)
        expect("event: message" in frame1 and '"id":123' in frame1, "sender queue did not receive message frame")
        expect("event: message" in frame2 and '"id":123' in frame2, "receiver queue did not receive message frame")

        became_offline_1 = hub.unregister(alice_id, convo_key, q1)
        expect(became_offline_1 is True, "sender unregister should mark offline when last connection closes")
        became_offline_2 = hub.unregister(bob_id, convo_key, q2)
        expect(became_offline_2 is True, "receiver unregister should mark offline when last connection closes")

        with TestClient(main.app) as anon_client:
            r = anon_client.get(f"/api/events/{bob_id}")
            expect(r.status_code == 401, f"anonymous sse expected 401, got {r.status_code}")


if __name__ == "__main__":
    try:
        run_smoke()
        print("SMOKE_OK")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
