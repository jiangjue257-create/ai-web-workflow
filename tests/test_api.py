from fastapi.testclient import TestClient

from app.main import app


def test_root_serves_html():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "AI Web Workflow" in response.text


def test_config_round_trip_does_not_return_secret(tmp_path, monkeypatch):
    config_path = tmp_path / "config.local.json"
    monkeypatch.setattr("app.main.CONFIG_PATH", config_path)

    client = TestClient(app)
    response = client.post(
        "/api/config",
        json={
            "api_base_url": "https://api.x.ai/",
            "api_key": "secret-key",
            "output_dir": "outputs",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_base_url"] == "https://api.x.ai"
    assert payload["api_key_set"] is True
    assert payload["api_key_preview"] == "secr...-key"
    assert "api_key" not in payload


def test_missing_prompt_returns_400():
    client = TestClient(app)

    response = client.post("/api/generate/image", data={"prompt": "   "})

    assert response.status_code == 400
    assert "prompt" in response.text.lower()


def test_generate_image_accepts_multipart_text_to_image(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr("app.main.CONFIG_PATH", tmp_path / "config.local.json")
    monkeypatch.setattr("app.main._start_thread", lambda target, args: started.append((target, args)))

    client = TestClient(app)
    response = client.post(
        "/api/generate/image",
        data={
            "prompt": "cat",
            "mode": "text",
            "model": "nano_banana_2-1K-square",
            "aspect_ratio": "1:1",
            "count": "1",
        },
    )

    assert response.status_code == 200
    task_id = response.json()["task_id"]
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["kind"] == "image"
    assert task["prompt"] == "cat"
    assert task["status"] == "pending"
    assert len(started) == 1
    assert started[0][1][1].model == "nano_banana_2-1K-square"
    assert started[0][1][1].mode == "text"
    assert started[0][1][1].reference_path is None


def test_generate_image_accepts_multipart_image_reference(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr("app.main.CONFIG_PATH", tmp_path / "config.local.json")
    monkeypatch.setattr("app.main.ROOT", tmp_path)
    monkeypatch.setattr("app.main._start_thread", lambda target, args: started.append((target, args)))

    client = TestClient(app)
    response = client.post(
        "/api/generate/image",
        data={
            "prompt": "turn it into watercolor",
            "mode": "image",
            "model": "auto-image",
            "aspect_ratio": "9:16",
            "count": "1",
        },
        files={"reference_image": ("ref.jpg", b"jpg-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    task_id = response.json()["task_id"]
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["kind"] == "image"
    assert task["prompt"] == "turn it into watercolor"
    assert len(started) == 1
    request = started[0][1][1]
    assert request.mode == "image"
    assert request.model == "auto-image"
    assert request.reference_path.read_bytes() == b"jpg-bytes"
    assert request.reference_path.name.endswith(".jpg")


def test_generate_video_accepts_optional_reference_image(monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr("app.main.CONFIG_PATH", tmp_path / "config.local.json")
    monkeypatch.setattr("app.main.ROOT", tmp_path)
    monkeypatch.setattr("app.main._start_thread", lambda target, args: started.append((target, args)))

    client = TestClient(app)
    response = client.post(
        "/api/generate/video",
        data={
            "prompt": "moving clouds",
            "aspect_ratio": "9:16",
            "duration": "6",
            "resolution": "720p",
        },
        files={"reference_image": ("ref.png", b"image-bytes", "image/png")},
    )

    assert response.status_code == 200
    task_id = response.json()["task_id"]
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["kind"] == "video"
    assert task["prompt"] == "moving clouds"
    assert len(started) == 1
    assert started[0][1][-1].read_bytes() == b"image-bytes"
    assert started[0][1][-1].name.endswith(".png")


def test_files_route_rejects_unknown_kind():
    client = TestClient(app)

    response = client.get("/api/files/secrets/config.local.json")

    assert response.status_code == 404
