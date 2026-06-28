from pathlib import Path

from app.config import (
    AppConfig,
    default_config_path,
    load_config,
    project_root,
    public_config,
    save_config,
)


def test_load_config_returns_defaults_when_file_missing(tmp_path):
    config_path = tmp_path / "config.json"

    config = load_config(config_path)

    assert config == AppConfig()
    assert config.api_base_url == "https://api.x.ai"
    assert config.api_key == ""
    assert config.output_dir == "outputs"


def test_load_config_returns_defaults_when_file_has_bad_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("{bad json", encoding="utf-8")

    config = load_config(config_path)

    assert config == AppConfig()


def test_load_config_returns_defaults_when_file_is_empty(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text("", encoding="utf-8")

    config = load_config(config_path)

    assert config == AppConfig()


def test_load_config_returns_defaults_when_top_level_is_not_object(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('["not", "an", "object"]', encoding="utf-8")

    config = load_config(config_path)

    assert config == AppConfig()


def test_load_config_strips_api_base_url_trailing_slashes(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"api_base_url": "https://example.test////"}', encoding="utf-8")

    config = load_config(config_path)

    assert config.api_base_url == "https://example.test"


def test_load_config_uses_default_when_api_base_url_is_only_slashes(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text('{"api_base_url": "////"}', encoding="utf-8")

    config = load_config(config_path)

    assert config.api_base_url == "https://api.x.ai"


def test_load_config_uses_defaults_for_null_fields(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        '{"api_base_url": null, "api_key": null, "output_dir": null}',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.api_base_url == "https://api.x.ai"
    assert config.api_key == ""
    assert config.output_dir == "outputs"


def test_save_config_then_load_config_round_trips(tmp_path):
    config_path = tmp_path / "config.json"
    original = AppConfig(
        api_base_url="https://example.test",
        api_key="secret-key",
        output_dir="custom-output",
    )

    save_config(config_path, original)
    loaded = load_config(config_path)

    assert loaded == original


def test_public_config_hides_api_key():
    config = AppConfig(
        api_base_url="https://example.test",
        api_key="abc123456789",
        output_dir="custom-output",
    )

    result = public_config(config)

    assert result == {
        "api_base_url": "https://example.test",
        "output_dir": "custom-output",
        "api_key_set": True,
        "api_key_preview": "abc1...6789",
    }
    assert "api_key" not in result


def test_public_config_short_api_key_preview_does_not_leak_fragments():
    config = AppConfig(api_key="short")

    result = public_config(config)

    assert result["api_key_set"] is True
    assert result["api_key_preview"] == "set"
    assert "short" not in result["api_key_preview"]


def test_default_config_path_is_anchored_to_project_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    config_path = default_config_path()

    assert config_path == project_root() / "config.local.json"
    assert config_path.is_absolute()


def test_load_config_accepts_unicode_path_objects(tmp_path):
    config_dir = tmp_path / "中文目录"
    config_dir.mkdir()
    config_path = config_dir / "config.local.json"
    config_path.write_text(
        '{"api_base_url": "https://example.test", "api_key": "secret"}',
        encoding="utf-8",
    )

    config = load_config(Path(config_path))

    assert config.api_base_url == "https://example.test"
    assert config.api_key == "secret"


def test_load_config_uses_default_config_path_when_path_is_omitted(monkeypatch, tmp_path):
    config_path = tmp_path / "config.local.json"
    config_path.write_text(
        '{"api_base_url": "https://example.test", "api_key": "secret"}',
        encoding="utf-8",
    )
    monkeypatch.setattr("app.config.default_config_path", lambda: config_path)

    config = load_config()

    assert config.api_base_url == "https://example.test"
    assert config.api_key == "secret"
