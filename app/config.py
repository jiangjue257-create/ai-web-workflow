from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AppConfig:
    api_base_url: str = "https://api.x.ai"
    api_key: str = ""
    output_dir: str = "outputs"


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_config_path() -> Path:
    return project_root() / "config.local.json"


def load_config(path: Path | None = None) -> AppConfig:
    defaults = AppConfig()
    path = path or default_config_path()

    if not path.exists():
        return defaults

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return defaults

    if not isinstance(data, dict):
        return defaults

    api_base_url = _clean_string(
        data.get("api_base_url"),
        defaults.api_base_url,
    ).rstrip("/")
    if not api_base_url:
        api_base_url = defaults.api_base_url

    return AppConfig(
        api_base_url=api_base_url,
        api_key=_clean_string(data.get("api_key"), defaults.api_key),
        output_dir=_clean_string(data.get("output_dir"), defaults.output_dir),
    )


def _clean_string(value: object, default: str) -> str:
    if value is None:
        return default
    return str(value)


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def public_config(config: AppConfig) -> dict[str, object]:
    return {
        "api_base_url": config.api_base_url,
        "output_dir": config.output_dir,
        "api_key_set": bool(config.api_key),
        "api_key_preview": _preview_api_key(config.api_key),
    }


def _preview_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "set"
    return f"{api_key[:4]}...{api_key[-4:]}"
