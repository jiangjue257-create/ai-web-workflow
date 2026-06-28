from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_config
from app.image_preprocess import prepare_reference_image
from app.xai_client import XAIClient


SUCCESS_STATUSES = {"done", "succeeded", "completed", "success"}
FAILED_STATUSES = {"failed", "error", "canceled", "cancelled"}


def extract_video_url(data: dict[str, Any]) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="真实调用中转站：本地参考图生成视频。")
    parser.add_argument("--image", required=True, help="本地参考图路径，建议 JPG/PNG，至少 512x512。")
    parser.add_argument("--prompt", required=True, help="视频提示词。")
    parser.add_argument("--aspect-ratio", default="9:16", choices=["9:16", "16:9", "1:1"])
    parser.add_argument("--duration", default=6, type=int)
    parser.add_argument("--resolution", default="720p", choices=["720p", "1080p"])
    parser.add_argument("--output", default="", help="输出 mp4 路径。默认写入 outputs/videos。")
    parser.add_argument("--yes", action="store_true", help="确认消耗额度并执行真实生成。")
    args = parser.parse_args()

    if not args.yes:
        print("这会真实调用中转站并消耗额度。确认执行请加 --yes。")
        return 1

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists() or not image_path.is_file():
        print(f"参考图不存在：{image_path}")
        return 2

    config = load_config()
    print(f"base_url: {config.api_base_url}")
    print(f"api_key_set: {bool(config.api_key)}")
    print(f"image: {image_path}")
    print(f"image_bytes: {image_path.stat().st_size}")
    print("model: grok-imagine-video-1.5-preview")

    if not config.api_key:
        print("未配置 API key。请先打开网页设置保存 key。")
        return 3

    client = XAIClient(config)
    prepared_image_path = prepare_reference_image(
        image_path,
        aspect_ratio=args.aspect_ratio,
        output_dir=PROJECT_ROOT / "outputs" / "refs",
    )
    print(f"prepared_image: {prepared_image_path.resolve()}")
    request_id = client.submit_video(
        prompt=args.prompt,
        duration=args.duration,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        reference_image_path=image_path,
        prepared_reference_image_path=prepared_image_path,
    )
    print(f"submitted_task_id: {request_id}")

    last_data: dict[str, Any] = {}
    for attempt in range(1, 121):
        last_data = client.get_video_status(request_id)
        status = str(last_data.get("status", "")).lower()
        progress = last_data.get("progress")
        size = last_data.get("size")
        print(f"poll {attempt}: status={status} progress={progress} size={size}")
        if status in SUCCESS_STATUSES:
            break
        if status in FAILED_STATUSES:
            print("final_status: failed")
            print(json.dumps(last_data, ensure_ascii=False)[:3000])
            return 4
        time.sleep(5)
    else:
        print("final_status: timeout")
        print(json.dumps(last_data, ensure_ascii=False)[:3000])
        return 5

    output_path = Path(args.output).expanduser() if args.output else PROJECT_ROOT / "outputs" / "videos" / f"{request_id}.mp4"
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path

    video_url = extract_video_url(last_data)
    if video_url:
        client.download_file(video_url, output_path)
    else:
        client.download_video_content(request_id, output_path)

    print("final_status: completed")
    print(f"output: {output_path.resolve()}")
    print(f"output_bytes: {output_path.stat().st_size}")
    print("final_json:")
    print(json.dumps(last_data, ensure_ascii=False)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
