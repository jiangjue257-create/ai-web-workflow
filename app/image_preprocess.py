from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageFilter, ImageOps


TARGET_SIZES = {
    "9:16": (1024, 1792),
    "16:9": (1792, 1024),
    "1:1": (1024, 1024),
}


def prepare_reference_image(
    source: Path,
    *,
    aspect_ratio: str,
    output_dir: Path,
) -> Path:
    target_size = TARGET_SIZES.get(aspect_ratio, TARGET_SIZES["9:16"])
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{source.stem}-prepared-{uuid4().hex}.jpg"

    with Image.open(source) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        if normalized.size == target_size:
            normalized.save(target, format="JPEG", quality=95)
            return target

        background = ImageOps.fit(
            normalized,
            target_size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        ).filter(ImageFilter.GaussianBlur(radius=32))

        foreground = ImageOps.contain(
            normalized,
            target_size,
            method=Image.Resampling.LANCZOS,
        )
        x = (target_size[0] - foreground.width) // 2
        y = (target_size[1] - foreground.height) // 2
        background.paste(foreground, (x, y))
        background.save(target, format="JPEG", quality=95)

    return target
