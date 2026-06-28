from __future__ import annotations

import argparse
import base64
from pathlib import Path
import sys
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.batch_image_generator import BatchImageGenerator, BatchImageRequest
from app.config import load_config
from app.xai_client import ProviderError, XAIClient


class RelayReferenceImageClient:
    def __init__(
        self,
        client: XAIClient,
        *,
        poll_timeout_seconds: float = 180,
        poll_interval_seconds: float = 3,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.poll_timeout_seconds = poll_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.sleep = sleep
        self.monotonic = monotonic

    def generate_reference_image(
        self,
        *,
        prompt: str,
        model: str,
        aspect_ratio: str,
        reference_image: Path,
        target: Path,
    ) -> None:
        data = self.client.submit_image_generation(
            prompt=prompt,
            model=model,
            aspect_ratio=aspect_ratio,
            count=1,
            image_path=reference_image,
        )
        result = self.client.extract_image_result(data)
        request_id = self.client.extract_task_id(data)
        last_data: dict[str, Any] = data

        if not result and request_id:
            started_at = self.monotonic()
            while True:
                last_data = self.client.get_image_status(request_id)
                result = self.client.extract_image_result(last_data)
                status = str(last_data.get("status", "")).lower()
                if result or status in {"done", "succeeded", "completed", "success"}:
                    break
                if status in {"failed", "error", "canceled", "cancelled"}:
                    raise ProviderError(f"image generation failed: {last_data}")
                if self.monotonic() - started_at >= self.poll_timeout_seconds:
                    raise ProviderError(
                        f"upstream did not return an image within {int(self.poll_timeout_seconds)} seconds"
                    )
                self.sleep(self.poll_interval_seconds)

        if result:
            if result["kind"] == "url":
                self.client.download_file(result["value"], target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(base64.b64decode(result["value"]))
            return

        if request_id:
            client_with_content = getattr(self.client, "download_image_content", None)
            if client_with_content is None:
                raise ProviderError(f"no downloadable image result: {last_data}")
            client_with_content(request_id, target)
            return

        raise ProviderError(f"no downloadable image result: {last_data}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-generate reference-based portrait images.")
    parser.add_argument("--image", required=True, help="Reference image path.")
    parser.add_argument("--prompt", required=True, help="Image prompt.")
    parser.add_argument("--count", type=int, default=4, help="How many images to generate.")
    parser.add_argument("--retries", type=int, default=1, help="Retries per image after a failure.")
    parser.add_argument("--aspect-ratio", default="9:16", choices=["9:16", "16:9", "1:1"])
    parser.add_argument("--model", default="auto-image")
    parser.add_argument("--prefix", default="reference-image")
    parser.add_argument("--out-dir", default=str(ROOT / "outputs" / "images"))
    parser.add_argument(
        "--poll-timeout-seconds",
        type=float,
        default=180,
        help="Give up one upstream request after this many seconds without a result.",
    )
    args = parser.parse_args()

    request = BatchImageRequest(
        reference_image=Path(args.image).expanduser(),
        prompt=args.prompt,
        output_dir=Path(args.out_dir).expanduser(),
        file_prefix=args.prefix,
        count=args.count,
        retries=args.retries,
        model=args.model,
        aspect_ratio=args.aspect_ratio,
    )
    generator = BatchImageGenerator(
        client=RelayReferenceImageClient(
            XAIClient(load_config(ROOT / "config.local.json")),
            poll_timeout_seconds=args.poll_timeout_seconds,
        )
    )
    result = generator.run(request, on_event=print)

    print("\nGeneration result:")
    for item in result.validation:
        print(f"- success: {item.path} ({item.size[0]}x{item.size[1]}, {item.orientation}, {item.bytes} bytes)")
    for failure in result.failures:
        print(f"- failed: image {failure.index}, reason: {failure.error}")

    return 0 if not result.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
