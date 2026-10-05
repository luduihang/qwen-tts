"""配置加载测试：正常 / 缺文件 / 缺必填项 / provider 非法 / remote 缺 key。"""
import copy

import pytest
import yaml

from app import ConfigError, load_config

EXAMPLE = {
    "asr": {
        "provider": "local",
        "url": "http://127.0.0.1:8000/v1/audio/transcriptions",
        "api_key": "",
        "model": "",
        "language": "zh",
    },
    "output_dir": "./output",
    "temp_dir": "./temp",
    "bilibili": {"cookie": ""},
    "timeout": {"download_s": 300, "asr_s": 600},
}


def write_cfg(tmp_path, data):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_load_ok(tmp_path):
    cfg = load_config(write_cfg(tmp_path, EXAMPLE))
    assert cfg["asr"]["provider"] == "local"
    assert cfg["asr"]["url"].startswith("http://127.0.0.1:8000")
    assert cfg["output_dir"] == "./output"
    assert cfg["temp_dir"] == "./temp"
    assert cfg["bilibili"]["cookie"] == ""


def test_defaults_filled_for_optional(tmp_path):
    minimal = {
        "asr": {"provider": "local", "url": "http://127.0.0.1:8000/v1/audio/transcriptions"},
        "output_dir": "o",
        "temp_dir": "t",
    }
    cfg = load_config(write_cfg(tmp_path, minimal))
    assert cfg["asr"]["api_key"] == ""
    assert cfg["asr"]["model"] == ""
    assert cfg["asr"]["language"] == ""  # 默认不发送 language（端点兼容性）
    assert cfg["asr"]["temperature"] == 0.0
    assert cfg["bilibili"]["cookie"] == ""
    assert cfg["timeout"] == {"download_s": 300, "asr_s": 600}


def test_missing_file_clear_error(tmp_path):
    with pytest.raises(ConfigError, match="配置文件缺失"):
        load_config(tmp_path / "nope.yaml")


def _set(d, key, value):
    d[key] = value


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda d: d["asr"].pop("url"), "asr.url"),
        (lambda d: d["asr"].pop("provider"), "asr.provider"),
        (lambda d: d.pop("output_dir"), "output_dir"),
        (lambda d: _set(d, "temp_dir", ""), "temp_dir"),
    ],
)
def test_missing_required_key(tmp_path, mutate, expected):
    data = copy.deepcopy(EXAMPLE)
    mutate(data)
    with pytest.raises(ConfigError, match=expected):
        load_config(write_cfg(tmp_path, data))


def test_invalid_provider(tmp_path):
    data = copy.deepcopy(EXAMPLE)
    data["asr"]["provider"] = "cloud"
    with pytest.raises(ConfigError, match="local 或 remote"):
        load_config(write_cfg(tmp_path, data))


def test_remote_requires_api_key(tmp_path):
    data = copy.deepcopy(EXAMPLE)
    data["asr"]["provider"] = "remote"
    with pytest.raises(ConfigError, match="api_key"):
        load_config(write_cfg(tmp_path, data))


def test_remote_with_api_key_ok(tmp_path):
    data = copy.deepcopy(EXAMPLE)
    data["asr"]["provider"] = "remote"
    data["asr"]["api_key"] = "sk-test"
    cfg = load_config(write_cfg(tmp_path, data))
    assert cfg["asr"]["api_key"] == "sk-test"
