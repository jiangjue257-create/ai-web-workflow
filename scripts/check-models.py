from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import load_config
from app.xai_client import XAIClient


def main() -> int:
    config = load_config()
    print(f"base_url: {config.api_base_url}")
    print(f"api_key_set: {bool(config.api_key)}")
    if not config.api_key:
        print("未配置 API key。请先打开网页设置保存 key。")
        return 1

    client = XAIClient(config)
    response = client.session.get(
        client._url("/v1/models"),
        headers=client._headers(),
        timeout=60,
    )
    if response.status_code >= 400:
        print(f"models_failed: HTTP {response.status_code}")
        print(response.text[:500])
        return 2

    data = response.json()
    models = data.get("data", data)
    print("models_ok: true")
    if isinstance(models, list):
        print(f"model_count: {len(models)}")
        names = []
        for item in models:
            if isinstance(item, dict):
                name = item.get("id") or item.get("name")
                if name:
                    names.append(str(name))
            elif isinstance(item, str):
                names.append(item)
        for name in names[:30]:
            print(f"- {name}")
    else:
        print(str(data)[:1000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
