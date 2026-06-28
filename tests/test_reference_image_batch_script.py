from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.xai_client import ProviderError


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "reference-image-batch.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("reference_image_batch_script", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HangingXAIClient:
    @staticmethod
    def submit_image_generation(**_kwargs):
        return {"task_id": "task_123"}

    @staticmethod
    def extract_image_result(_data):
        return None

    @staticmethod
    def extract_task_id(_data):
        return "task_123"

    @staticmethod
    def get_image_status(_request_id):
        return {"status": "in_progress"}


def test_relay_client_abandons_polling_after_timeout(tmp_path: Path):
    module = _load_script_module()
    sleep_calls: list[float] = []
    now_values = iter([0.0, 0.0, 181.0])
    relay = module.RelayReferenceImageClient(
        HangingXAIClient(),
        poll_timeout_seconds=180,
        poll_interval_seconds=3,
        sleep=sleep_calls.append,
        monotonic=lambda: next(now_values),
    )

    with pytest.raises(ProviderError) as exc:
        relay.generate_reference_image(
            prompt="portrait",
            model="auto-image",
            aspect_ratio="9:16",
            reference_image=tmp_path / "ref.jpg",
            target=tmp_path / "out.png",
        )

    assert "180" in str(exc.value)
    assert sleep_calls == [3]
