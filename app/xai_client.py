from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import requests

from app.config import AppConfig


class ProviderError(RuntimeError):
    pass


class XAIClient:
    def __init__(self, config: AppConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()

    def generate_image(self, *, prompt: str, aspect_ratio: str, count: int) -> dict[str, Any]:
        return self.submit_image_generation(
            prompt=prompt,
            model="nano_banana_2-1K-square",
            aspect_ratio=aspect_ratio,
            count=count,
        )

    def submit_image_generation(
        self,
        *,
        prompt: str,
        model: str,
        aspect_ratio: str,
        count: int = 1,
        image_path: Path | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": max(1, int(count)),
            "response_format": "url",
            "aspectRatio": aspect_ratio,
            "size": _image_size(aspect_ratio),
        }
        if image_path is not None:
            payload["image"] = _image_data_url(image_path)

        response = self.session.post(
            self._url("/v1/images/generations?async=true"),
            json=payload,
            headers=self._headers(),
            timeout=180,
        )
        return self._json_or_error(response)

    def submit_image_edit(
        self,
        *,
        prompt: str,
        model: str,
        image_path: Path,
    ) -> dict[str, Any]:
        file_handle = image_path.open("rb")
        try:
            response = self.session.post(
                self._url("/v1/images/edits"),
                data={"model": model, "prompt": prompt},
                files={
                    "image": (
                        image_path.name,
                        file_handle,
                        mimetypes.guess_type(image_path.name)[0] or "application/octet-stream",
                    )
                },
                headers=self._headers(),
                timeout=180,
            )
        finally:
            file_handle.close()
        return self._json_or_error(response)

    def get_image_status(self, task_id: str) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"/v1/images/{task_id}"),
            headers=self._headers(),
            timeout=60,
        )
        return self._json_or_error(response)

    def submit_video(
        self,
        *,
        prompt: str,
        model: str = "grok-imagine-1.0-video",
        duration: int,
        aspect_ratio: str,
        resolution: str,
        reference_image_path: Path | None = None,
        prepared_reference_image_path: Path | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": _video_size(aspect_ratio, resolution),
            "seconds": str(duration),
            "async": True,
        }
        if reference_image_path is not None:
            upload_path = prepared_reference_image_path or reference_image_path
            payload["model"] = "grok-imagine-video-1.5-preview"
            payload["size"] = _video_size(aspect_ratio, "1080p")
            file_handle = upload_path.open("rb")
            try:
                response = self.session.post(
                    self._url("/v1/videos"),
                    data={**payload, "async": "true"},
                    files={
                        "input_reference[]": (
                            upload_path.name,
                            file_handle,
                            mimetypes.guess_type(upload_path.name)[0]
                            or "application/octet-stream",
                        )
                    },
                    headers=self._headers(),
                    timeout=180,
                )
            finally:
                file_handle.close()
            data = self._json_or_error(response)
            request_id = data.get("request_id") or data.get("id")
            if not request_id:
                raise ProviderError(f"视频任务提交成功，但没有返回 request_id：{data}")
            return str(request_id)

        response = self.session.post(
            self._url("/v1/videos"),
            json=payload,
            headers=self._headers(),
            timeout=180,
        )
        data = self._json_or_error(response)
        request_id = data.get("request_id") or data.get("id")
        if not request_id:
            raise ProviderError(f"视频任务提交成功，但没有返回 request_id：{data}")
        return str(request_id)

    def get_video_status(self, request_id: str) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"/v1/videos/{request_id}"),
            headers=self._headers(),
            timeout=60,
        )
        return self._json_or_error(response)

    def download_file(self, url: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        response = self.session.get(url, stream=True, timeout=900)
        if response.status_code >= 400:
            raise ProviderError(f"下载失败：HTTP {response.status_code}")

        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)

    def download_video_content(self, request_id: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        response = self.session.get(
            self._url(f"/v1/videos/{request_id}/content"),
            headers=self._headers(),
            stream=True,
            timeout=900,
        )
        if response.status_code >= 400:
            raise ProviderError(f"下载视频失败：HTTP {response.status_code}")

        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)

    def download_image_content(self, task_id: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        response = self.session.get(
            self._url(f"/v1/images/{task_id}/content"),
            headers=self._headers(),
            stream=True,
            timeout=900,
        )
        if response.status_code >= 400:
            raise ProviderError(f"下载图片失败：HTTP {response.status_code}")

        with target.open("wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)

    @staticmethod
    def extract_task_id(data: dict[str, Any]) -> str:
        value = data.get("task_id") or data.get("request_id") or data.get("id")
        if value:
            return str(value)

        items = data.get("data")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                value = first.get("task_id") or first.get("request_id") or first.get("id")
                if value:
                    return str(value)
        return ""

    @staticmethod
    def extract_image_result(data: dict[str, Any]) -> dict[str, str] | None:
        def from_mapping(item: dict[str, Any]) -> dict[str, str] | None:
            b64_json = item.get("b64_json")
            if b64_json:
                return {"kind": "b64_json", "value": str(b64_json)}
            url = item.get("url") or item.get("image_url")
            if url:
                return {"kind": "url", "value": str(url)}
            return None

        items = data.get("data")
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                result = from_mapping(first)
                if result:
                    return result

        return from_mapping(data)

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key:
            raise ProviderError("请先在设置里填写 API key")
        return {"Authorization": f"Bearer {self.config.api_key}"}

    def _url(self, path: str) -> str:
        return f"{self.config.api_base_url.rstrip('/')}{path}"

    def _json_or_error(self, response: Any) -> dict[str, Any]:
        if response.status_code < 400:
            return response.json()
        text = str(getattr(response, "text", "") or "")
        if response.status_code == 522:
            raise ProviderError("中转站超时：api.hellobabygo.com 返回 HTTP 522。请稍后重试，或联系中转服务商确认视频接口是否正常。")
        if response.status_code in {401, 403}:
            raise ProviderError("API key 无效或没有权限")
        if response.status_code == 429:
            raise ProviderError("额度不足或请求太频繁")
        if response.status_code == 400:
            if "requires an input image" in text:
                raise ProviderError(
                    "视频模型需要参考图：grok-imagine-video-1.5-preview 不支持纯文字生成。"
                    "请在视频模式选择一张本地图片，或改用不带参考图的纯文视频模型。"
                )
            raise ProviderError(f"参数不被接口接受：{text}")
        raise ProviderError(f"接口请求失败：HTTP {response.status_code} {text}")


def _video_size(aspect_ratio: str, resolution: str) -> str:
    if aspect_ratio == "16:9":
        return "1280x720" if resolution == "720p" else "1792x1024"
    if aspect_ratio == "1:1":
        return "1024x1024"
    return "720x1280" if resolution == "720p" else "1024x1792"


def _image_size(aspect_ratio: str) -> str:
    if aspect_ratio == "16:9":
        return "1536x1024"
    if aspect_ratio == "9:16":
        return "1024x1536"
    return "1024x1024"


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
