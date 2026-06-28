import base64
from pathlib import Path

import pytest

from app.config import AppConfig
from app.xai_client import ProviderError, XAIClient


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        payload: dict | None = None,
        content: bytes = b"data",
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = text or str(self._payload)

    def json(self) -> dict:
        return self._payload

    def iter_content(self, chunk_size: int = 8192):
        yield self.content


class FakeSession:
    def __init__(self) -> None:
        self.calls = []
        self.responses = []

    def post(self, url: str, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)

    def get(self, url: str, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)


def test_submit_image_generation_uses_async_endpoint_and_json_body():
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"task_id": "img_123"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    data = client.submit_image_generation(
        prompt="cat",
        model="nano_banana_2-1K-square",
        aspect_ratio="16:9",
        count=1,
    )

    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url == "https://api.x.ai/v1/images/generations?async=true"
    assert kwargs["json"] == {
        "model": "nano_banana_2-1K-square",
        "prompt": "cat",
        "n": 1,
        "response_format": "url",
        "aspectRatio": "16:9",
        "size": "1536x1024",
    }
    assert kwargs["headers"]["Authorization"] == "Bearer key"
    assert data["task_id"] == "img_123"


def test_submit_image_generation_sends_reference_image_as_data_url(tmp_path: Path):
    image_path = tmp_path / "reference.jpg"
    image_path.write_bytes(b"jpg-data")
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"id": "img_ref"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    client.submit_image_generation(
        prompt="edit this",
        model="auto-image",
        aspect_ratio="9:16",
        count=1,
        image_path=image_path,
    )

    body = session.calls[0][2]["json"]
    assert body["model"] == "auto-image"
    assert body["image"] == "data:image/jpeg;base64," + base64.b64encode(b"jpg-data").decode("ascii")
    assert body["aspectRatio"] == "9:16"
    assert body["size"] == "1024x1536"


def test_extract_image_task_id_accepts_task_id_and_id():
    assert XAIClient.extract_task_id({"task_id": "task_1"}) == "task_1"
    assert XAIClient.extract_task_id({"id": "task_2"}) == "task_2"
    assert XAIClient.extract_task_id({"data": [{"id": "task_3"}]}) == "task_3"


def test_extract_image_result_accepts_b64_json_and_urls():
    assert XAIClient.extract_image_result({"data": [{"b64_json": "abc"}]}) == {
        "kind": "b64_json",
        "value": "abc",
    }
    assert XAIClient.extract_image_result({"data": [{"url": "https://file/image.png"}]}) == {
        "kind": "url",
        "value": "https://file/image.png",
    }
    assert XAIClient.extract_image_result({"image_url": "https://file/image2.png"}) == {
        "kind": "url",
        "value": "https://file/image2.png",
    }


def test_get_image_status_returns_json():
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"status": "completed"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    data = client.get_image_status("img_123")

    assert data["status"] == "completed"
    assert session.calls[0][1] == "https://api.x.ai/v1/images/img_123"


def test_download_image_content_writes_content(tmp_path: Path):
    session = FakeSession()
    session.responses.append(FakeResponse(content=b"png-bytes"))
    client = XAIClient(AppConfig(api_key="key"), session=session)
    target = tmp_path / "image.png"

    client.download_image_content("img_123", target)

    assert session.calls[0][1] == "https://api.x.ai/v1/images/img_123/content"
    assert target.read_bytes() == b"png-bytes"


def test_submit_video_uses_relay_video_endpoint_and_payload():
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"request_id": "req_123"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    request_id = client.submit_video(
        prompt="waves",
        duration=6,
        aspect_ratio="9:16",
        resolution="720p",
    )

    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url == "https://api.x.ai/v1/videos"
    assert kwargs["json"] == {
        "model": "grok-imagine-1.0-video",
        "prompt": "waves",
        "size": "720x1280",
        "seconds": "6",
        "async": True,
    }
    assert request_id == "req_123"


def test_submit_video_accepts_selected_text_to_video_model():
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"request_id": "req_veo"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    client.submit_video(
        prompt="waves",
        model="veo_3_1-fast-landscape",
        duration=6,
        aspect_ratio="16:9",
        resolution="720p",
    )

    assert session.calls[0][2]["json"]["model"] == "veo_3_1-fast-landscape"


def test_submit_video_sends_reference_image_as_multipart_file(tmp_path: Path):
    image_path = tmp_path / "reference.png"
    image_path.write_bytes(b"png-data")
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"request_id": "req_ref"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    client.submit_video(
        prompt="animate this",
        duration=6,
        aspect_ratio="16:9",
        resolution="720p",
        reference_image_path=image_path,
    )

    assert "json" not in session.calls[0][2]
    assert session.calls[0][2]["data"] == {
        "model": "grok-imagine-video-1.5-preview",
        "prompt": "animate this",
        "size": "1792x1024",
        "seconds": "6",
        "async": "true",
    }
    file_name, file_handle, mime_type = session.calls[0][2]["files"]["input_reference[]"]
    assert file_name == "reference.png"
    assert file_handle.closed is True
    assert mime_type == "image/png"


def test_submit_reference_video_preserves_portrait_ratio_with_relay_supported_size(tmp_path: Path):
    image_path = tmp_path / "reference.jpg"
    image_path.write_bytes(b"jpg-data")
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"request_id": "req_ref"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    client.submit_video(
        prompt="animate this",
        duration=6,
        aspect_ratio="9:16",
        resolution="720p",
        reference_image_path=image_path,
    )

    assert session.calls[0][2]["data"]["size"] == "1024x1792"


def test_submit_reference_video_uploads_preprocessed_reference_image(tmp_path: Path):
    image_path = tmp_path / "reference.jpg"
    image_path.write_bytes(b"jpg-data")
    prepared_path = tmp_path / "prepared.jpg"
    prepared_path.write_bytes(b"prepared-data")
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"request_id": "req_ref"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    client.submit_video(
        prompt="animate this",
        duration=6,
        aspect_ratio="9:16",
        resolution="720p",
        reference_image_path=image_path,
        prepared_reference_image_path=prepared_path,
    )

    file_name, file_handle, mime_type = session.calls[0][2]["files"]["input_reference[]"]
    assert file_name == "prepared.jpg"
    assert file_handle.closed is True
    assert mime_type == "image/jpeg"


def test_provider_error_summarizes_cloudflare_522_html():
    session = FakeSession()
    session.responses.append(
        FakeResponse(
            status_code=522,
            text="<html><title>hellobabygo.com | 522: Connection timed out</title></html>",
        )
    )
    client = XAIClient(AppConfig(api_key="key"), session=session)

    with pytest.raises(ProviderError) as exc:
        client.submit_video(prompt="x", duration=6, aspect_ratio="9:16", resolution="720p")

    message = str(exc.value)
    assert "中转站超时" in message
    assert "HTTP 522" in message
    assert "<html>" not in message


def test_submit_video_maps_supported_aspect_ratios_to_relay_sizes():
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"id": "req_square"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    client.submit_video(prompt="square", duration=10, aspect_ratio="1:1", resolution="720p")

    assert session.calls[0][2]["json"]["size"] == "1024x1024"
    assert session.calls[0][2]["json"]["seconds"] == "10"


def test_submit_video_maps_1080p_to_relay_supported_sizes():
    session = FakeSession()
    session.responses.extend(
        [
            FakeResponse(payload={"id": "req_portrait"}),
            FakeResponse(payload={"id": "req_landscape"}),
        ]
    )
    client = XAIClient(AppConfig(api_key="key"), session=session)

    client.submit_video(prompt="portrait", duration=6, aspect_ratio="9:16", resolution="1080p")
    client.submit_video(prompt="landscape", duration=6, aspect_ratio="16:9", resolution="1080p")

    assert session.calls[0][2]["json"]["size"] == "1024x1792"
    assert session.calls[1][2]["json"]["size"] == "1792x1024"


def test_get_video_status_returns_json():
    session = FakeSession()
    session.responses.append(FakeResponse(payload={"status": "done", "video": {"url": "http://video"}}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    data = client.get_video_status("req_123")

    assert data["status"] == "done"
    assert session.calls[0][1] == "https://api.x.ai/v1/videos/req_123"


def test_download_video_content_writes_content(tmp_path: Path):
    session = FakeSession()
    session.responses.append(FakeResponse(content=b"video-bytes"))
    client = XAIClient(AppConfig(api_key="key"), session=session)
    target = tmp_path / "video.mp4"

    client.download_video_content("req_123", target)

    assert session.calls[0][0] == "get"
    assert session.calls[0][1] == "https://api.x.ai/v1/videos/req_123/content"
    assert session.calls[0][2]["headers"]["Authorization"] == "Bearer key"
    assert target.read_bytes() == b"video-bytes"


def test_download_file_writes_content(tmp_path: Path):
    session = FakeSession()
    session.responses.append(FakeResponse(content=b"abc"))
    client = XAIClient(AppConfig(api_key="key"), session=session)
    target = tmp_path / "file.mp4"

    client.download_file("https://files.example/video.mp4", target)

    assert target.read_bytes() == b"abc"


def test_provider_error_for_missing_api_key():
    client = XAIClient(AppConfig(api_key=""), session=FakeSession())

    with pytest.raises(ProviderError) as exc:
        client.generate_image(prompt="cat", aspect_ratio="1:1", count=1)

    assert "API key" in str(exc.value)


def test_provider_error_for_unauthorized_response():
    session = FakeSession()
    session.responses.append(FakeResponse(status_code=401, payload={"error": "bad key"}))
    client = XAIClient(AppConfig(api_key="key"), session=session)

    with pytest.raises(ProviderError) as exc:
        client.submit_video(prompt="x", duration=6, aspect_ratio="9:16", resolution="720p")

    assert "API key" in str(exc.value)
