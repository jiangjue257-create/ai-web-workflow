from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.batch_image_generator import BatchImageGenerator, BatchImageRequest


class FakeImageClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.outcomes: list[bytes | Exception] = []

    def generate_reference_image(
        self,
        *,
        prompt: str,
        model: str,
        aspect_ratio: str,
        reference_image: Path,
        target: Path,
    ) -> None:
        self.calls.append(
            {
                "prompt": prompt,
                "model": model,
                "aspect_ratio": aspect_ratio,
                "reference_image": reference_image,
                "target": target,
            }
        )
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        target.write_bytes(outcome)


def _png_bytes(size: tuple[int, int] = (1024, 1536)) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_batch_generator_saves_each_image_and_retries_transient_failure(tmp_path: Path):
    reference = tmp_path / "ref.jpg"
    reference.write_bytes(b"reference")
    client = FakeImageClient()
    client.outcomes = [
        _png_bytes(),
        RuntimeError("upstream failed once"),
        _png_bytes(),
        _png_bytes((1024, 1536)),
    ]
    events: list[str] = []
    generator = BatchImageGenerator(client=client, sleep=lambda _seconds: None)

    result = generator.run(
        BatchImageRequest(
            reference_image=reference,
            prompt="portrait",
            output_dir=tmp_path / "images",
            file_prefix="portrait",
            count=3,
            retries=1,
        ),
        on_event=events.append,
    )

    assert [path.name for path in result.paths] == [
        "portrait-1.png",
        "portrait-2.png",
        "portrait-3.png",
    ]
    assert all(path.exists() for path in result.paths)
    assert result.failures == []
    assert len(client.calls) == 4
    assert any("第 2/3 张失败，准备重试 1/1" in event for event in events)
    assert any("第 3/3 张已保存" in event for event in events)
    assert result.validation[0].size == (1024, 1536)
    assert result.validation[0].orientation == "portrait"


def test_batch_generator_records_failure_after_retries_are_exhausted(tmp_path: Path):
    reference = tmp_path / "ref.jpg"
    reference.write_bytes(b"reference")
    client = FakeImageClient()
    client.outcomes = [
        RuntimeError("first"),
        RuntimeError("second"),
    ]
    generator = BatchImageGenerator(client=client, sleep=lambda _seconds: None)

    result = generator.run(
        BatchImageRequest(
            reference_image=reference,
            prompt="portrait",
            output_dir=tmp_path / "images",
            file_prefix="portrait",
            count=1,
            retries=1,
        )
    )

    assert result.paths == []
    assert len(result.failures) == 1
    assert result.failures[0].index == 1
    assert "second" in result.failures[0].error
    assert len(client.calls) == 2


def test_batch_request_rejects_missing_reference_image(tmp_path: Path):
    generator = BatchImageGenerator(client=FakeImageClient())

    try:
        generator.run(
            BatchImageRequest(
                reference_image=tmp_path / "missing.jpg",
                prompt="portrait",
                output_dir=tmp_path / "images",
                count=1,
            )
        )
    except FileNotFoundError as exc:
        assert "missing.jpg" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")
