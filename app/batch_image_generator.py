from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import time
from typing import Callable, Protocol

from PIL import Image


class ReferenceImageClient(Protocol):
    def generate_reference_image(
        self,
        *,
        prompt: str,
        model: str,
        aspect_ratio: str,
        reference_image: Path,
        target: Path,
    ) -> None:
        pass


@dataclass(frozen=True)
class BatchImageRequest:
    reference_image: Path
    prompt: str
    output_dir: Path
    file_prefix: str = "reference-image"
    count: int = 4
    retries: int = 1
    model: str = "auto-image"
    aspect_ratio: str = "9:16"
    retry_delay_seconds: float = 3.0


@dataclass(frozen=True)
class ImageValidation:
    path: Path
    size: tuple[int, int]
    orientation: str
    bytes: int


@dataclass(frozen=True)
class ImageFailure:
    index: int
    error: str


@dataclass(frozen=True)
class BatchImageResult:
    paths: list[Path] = field(default_factory=list)
    failures: list[ImageFailure] = field(default_factory=list)
    validation: list[ImageValidation] = field(default_factory=list)


class BatchImageGenerator:
    def __init__(
        self,
        *,
        client: ReferenceImageClient,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.sleep = sleep

    def run(
        self,
        request: BatchImageRequest,
        on_event: Callable[[str], None] | None = None,
    ) -> BatchImageResult:
        if not request.reference_image.exists():
            raise FileNotFoundError(request.reference_image)
        if request.count < 1:
            raise ValueError("count must be at least 1")
        if request.retries < 0:
            raise ValueError("retries must not be negative")

        request.output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        failures: list[ImageFailure] = []
        validations: list[ImageValidation] = []

        for index in range(1, request.count + 1):
            target = request.output_dir / f"{request.file_prefix}-{index}.png"
            error: Exception | None = None
            for attempt in range(request.retries + 1):
                _emit(on_event, f"第 {index}/{request.count} 张开始生成，尝试 {attempt + 1}/{request.retries + 1}")
                try:
                    self.client.generate_reference_image(
                        prompt=f"{request.prompt}\n\nVariant {index}: keep the same core request with a subtle pose and lighting variation.",
                        model=request.model,
                        aspect_ratio=request.aspect_ratio,
                        reference_image=request.reference_image,
                        target=target,
                    )
                    validation = validate_image(target)
                    paths.append(target)
                    validations.append(validation)
                    _emit(
                        on_event,
                        f"第 {index}/{request.count} 张已保存：{target.name} ({validation.size[0]}x{validation.size[1]})",
                    )
                    error = None
                    break
                except Exception as exc:
                    error = exc
                    if attempt < request.retries:
                        _emit(on_event, f"第 {index}/{request.count} 张失败，准备重试 {attempt + 1}/{request.retries}")
                        self.sleep(request.retry_delay_seconds)
                    else:
                        _emit(on_event, f"第 {index}/{request.count} 张失败，已用完重试：{exc}")
            if error is not None:
                failures.append(ImageFailure(index=index, error=str(error)))

        return BatchImageResult(paths=paths, failures=failures, validation=validations)


def validate_image(path: Path) -> ImageValidation:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.stat().st_size <= 0:
        raise ValueError(f"image is empty: {path}")

    with Image.open(path) as image:
        width, height = image.size
        image.verify()

    if height > width:
        orientation = "portrait"
    elif width > height:
        orientation = "landscape"
    else:
        orientation = "square"
    return ImageValidation(path=path, size=(width, height), orientation=orientation, bytes=path.stat().st_size)


def _emit(on_event: Callable[[str], None] | None, message: str) -> None:
    if on_event is not None:
        on_event(message)
