from __future__ import annotations

import base64
from pathlib import Path
from threading import Thread
import time
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import AppConfig, default_config_path, load_config, public_config, save_config
from app.image_preprocess import prepare_reference_image
from app.task_store import TaskStore
from app.xai_client import ProviderError, XAIClient


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
CONFIG_PATH = default_config_path()

app = FastAPI(title="AI Web Workflow")
tasks = TaskStore()


class ConfigRequest(BaseModel):
    api_base_url: str = "https://api.x.ai"
    api_key: str = ""
    output_dir: str = "outputs"


class ImageRequest(BaseModel):
    prompt: str
    model: str = "nano_banana_2-1K-square"
    mode: str = "text"
    aspect_ratio: str = "1:1"
    count: int = 1
    reference_path: Path | None = None


@app.get("/", response_class=HTMLResponse)
def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<!doctype html><title>AI Web Workflow</title><h1>AI Web Workflow</h1>")


@app.get("/api/config")
def get_config() -> dict[str, object]:
    return public_config(load_config(CONFIG_PATH))


@app.post("/api/config")
def update_config(request: ConfigRequest) -> dict[str, object]:
    config = AppConfig(
        api_base_url=(request.api_base_url or "https://api.x.ai").rstrip("/") or "https://api.x.ai",
        api_key=request.api_key or "",
        output_dir=request.output_dir or "outputs",
    )
    save_config(CONFIG_PATH, config)
    return public_config(config)


@app.post("/api/generate/image")
def generate_image(
    prompt: str = Form(...),
    model: str = Form("nano_banana_2-1K-square"),
    mode: str = Form("text"),
    aspect_ratio: str = Form("1:1"),
    count: int = Form(1),
    reference_image: UploadFile | None = File(None),
) -> dict[str, str]:
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt ????")

    clean_mode = "image" if mode == "image" else "text"
    reference_path = _save_reference_image(reference_image) if reference_image else None
    if clean_mode == "image" and reference_path is None:
        raise HTTPException(status_code=400, detail="??????????")

    request = ImageRequest(
        prompt=prompt,
        model=(model or _default_image_model(clean_mode)).strip() or _default_image_model(clean_mode),
        mode=clean_mode,
        aspect_ratio=aspect_ratio,
        count=max(1, min(int(count), 4)),
        reference_path=reference_path,
    )
    task = tasks.create(kind="image", prompt=prompt)
    _start_thread(_run_image_task, (task["id"], request))
    return {"task_id": task["id"]}


@app.post("/api/generate/video")
def generate_video(
    prompt: str = Form(...),
    model: str = Form("grok-imagine-1.0-video"),
    mode: str = Form("text"),
    aspect_ratio: str = Form("9:16"),
    duration: int = Form(6),
    resolution: str = Form("720p"),
    reference_image: UploadFile | None = File(None),
) -> dict[str, str]:
    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise HTTPException(status_code=400, detail="prompt 不能为空")

    reference_path = _save_reference_image(reference_image) if reference_image else None
    task = tasks.create(kind="video", prompt=clean_prompt)
    _start_thread(
        _run_video_task,
        (
            task["id"],
            clean_prompt,
            (model or _default_video_model("image" if mode == "image" else "text")).strip()
            or _default_video_model("image" if mode == "image" else "text"),
            aspect_ratio,
            max(1, int(duration)),
            resolution,
            reference_path,
        ),
    )
    return {"task_id": task["id"]}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.get("/api/files/{kind}/{filename}")
def get_file(kind: str, filename: str) -> FileResponse:
    if kind not in {"images", "videos", "refs"}:
        raise HTTPException(status_code=404, detail="文件类型不存在")

    path = (_output_root() / kind / filename).resolve()
    allowed_root = (_output_root() / kind).resolve()
    if allowed_root not in path.parents or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path)


def _start_thread(target, args: tuple[Any, ...]) -> None:
    Thread(target=target, args=args, daemon=True).start()


def _output_root() -> Path:
    config = load_config(CONFIG_PATH)
    output = Path(config.output_dir)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    return output


def _save_reference_image(reference_image: UploadFile) -> Path:
    suffix = Path(reference_image.filename or "").suffix.lower() or ".bin"
    target = _output_root() / "refs" / f"{uuid4().hex}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as file:
        file.write(reference_image.file.read())
    return target


def _run_image_task(task_id: str, request: ImageRequest) -> None:
    tasks.update(task_id, status="submitting", message="????????...")
    try:
        client = XAIClient(load_config(CONFIG_PATH))
        data = client.submit_image_generation(
            prompt=request.prompt,
            model=request.model,
            aspect_ratio=request.aspect_ratio,
            count=request.count,
            image_path=request.reference_path if request.mode == "image" else None,
        )
        target = _output_root() / "images" / f"{task_id}.png"
        result = client.extract_image_result(data)
        request_id = client.extract_task_id(data)

        if not result and request_id:
            tasks.update(task_id, status="generating", message="??????...", raw={"request_id": request_id})
            last_data: dict[str, Any] = data
            for _ in range(120):
                last_data = client.get_image_status(request_id)
                result = client.extract_image_result(last_data)
                status = str(last_data.get("status", "")).lower()
                if result or status in {"done", "succeeded", "completed", "success"}:
                    break
                if status in {"failed", "error", "canceled", "cancelled"}:
                    raise ProviderError(f"??????: {last_data}")
                time.sleep(3)
            data = last_data

        if result:
            tasks.update(task_id, status="downloading", message="??????...", raw=data)
            if result["kind"] == "url":
                client.download_file(result["value"], target)
            else:
                _write_base64_image(result["value"], target)
        elif request_id:
            tasks.update(task_id, status="downloading", message="????????...", raw=data)
            client.download_image_content(request_id, target)
        elif request.mode == "image" and request.reference_path is not None:
            fallback_data = client.submit_image_edit(
                prompt=request.prompt,
                model="gpt-image-2",
                image_path=request.reference_path,
            )
            fallback_result = client.extract_image_result(fallback_data)
            if not fallback_result:
                raise ProviderError(f"????????: {fallback_data}")
            tasks.update(task_id, status="downloading", message="???? fallback ??...", raw=fallback_data)
            if fallback_result["kind"] == "url":
                client.download_file(fallback_result["value"], target)
            else:
                _write_base64_image(fallback_result["value"], target)
            data = fallback_data
        else:
            raise ProviderError(f"???????????????: {data}")

        tasks.update(
            task_id,
            status="completed",
            message="?????",
            file_name=target.name,
            file_url=f"/api/files/images/{target.name}",
            raw=data,
        )
    except Exception as exc:
        tasks.update(task_id, status="failed", message="??????", error=str(exc))


def _run_video_task(
    task_id: str,
    prompt: str,
    model: str,
    aspect_ratio: str,
    duration: int,
    resolution: str,
    reference_path: Path | None,
) -> None:
    tasks.update(task_id, status="submitting", message="正在提交视频任务...")
    try:
        client = XAIClient(load_config(CONFIG_PATH))
        prepared_reference_path = (
            prepare_reference_image(
                reference_path,
                aspect_ratio=aspect_ratio,
                output_dir=_output_root() / "refs",
            )
            if reference_path
            else None
        )
        request_id = client.submit_video(
            prompt=prompt,
            model=model,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            reference_image_path=reference_path,
            prepared_reference_image_path=prepared_reference_path,
        )
        tasks.update(task_id, status="generating", message="视频正在生成...", raw={"request_id": request_id})

        video_url = ""
        last_data: dict[str, Any] = {}
        for _ in range(180):
            last_data = client.get_video_status(request_id)
            status = str(last_data.get("status", "")).lower()
            if status in {"done", "succeeded", "completed", "success"}:
                video_url = _extract_video_url(last_data)
                break
            if status in {"failed", "error", "canceled", "cancelled"}:
                raise ProviderError(f"视频生成失败: {last_data}")
            time.sleep(5)

        target = _output_root() / "videos" / f"{task_id}.mp4"
        tasks.update(task_id, status="downloading", message="正在下载视频...", raw=last_data)
        if video_url:
            client.download_file(video_url, target)
        else:
            client.download_video_content(request_id, target)
        tasks.update(
            task_id,
            status="completed",
            message="视频已完成",
            file_name=target.name,
            file_url=f"/api/files/videos/{target.name}",
            raw=last_data,
        )
    except Exception as exc:
        tasks.update(task_id, status="failed", message="视频生成失败", error=str(exc))


def _extract_image_url(data: dict[str, Any]) -> str:
    items = data.get("data")
    if isinstance(items, list) and items:
        first = items[0]
        if isinstance(first, dict):
            return str(first.get("url") or first.get("image_url") or "")
    return str(data.get("url") or data.get("image_url") or "")


def _write_base64_image(value: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(base64.b64decode(value))


def _default_image_model(mode: str) -> str:
    return "auto-image" if mode == "image" else "nano_banana_2-1K-square"


def _default_video_model(mode: str) -> str:
    return "grok-imagine-video-1.5-preview" if mode == "image" else "grok-imagine-1.0-video"


def _extract_video_url(data: dict[str, Any]) -> str:
    video = data.get("video")
    if isinstance(video, dict):
        value = video.get("url") or video.get("video_url")
        if value:
            return str(value)

    output = data.get("output")
    if isinstance(output, dict):
        value = output.get("url") or output.get("video_url")
        if value:
            return str(value)
    if isinstance(output, list) and output:
        first = output[0]
        if isinstance(first, dict):
            value = first.get("url") or first.get("video_url")
            if value:
                return str(value)
        if isinstance(first, str):
            return first

    return str(data.get("url") or data.get("video_url") or "")


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
