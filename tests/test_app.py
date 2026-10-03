"""app 入口测试：/health 响应、目录自动创建。"""
from pathlib import Path

from app import create_app, ensure_dirs


def make_cfg(tmp_path):
    return {
        "asr": {
            "provider": "local",
            "url": "http://127.0.0.1:8000/v1/audio/transcriptions",
            "api_key": "",
            "model": "",
            "language": "zh",
        },
        "output_dir": str(tmp_path / "out"),
        "temp_dir": str(tmp_path / "tmp"),
        "bilibili": {"cookie": ""},
        "timeout": {"download_s": 1, "asr_s": 1},
    }


def test_health_200_with_provider(tmp_path):
    client = create_app(make_cfg(tmp_path)).test_client()
    r = client.get("/health")
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["asr"]["provider"] == "local"


def test_health_reflects_config_provider(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg["asr"]["provider"] = "remote"
    r = create_app(cfg).test_client().get("/health")
    assert r.get_json()["asr"]["provider"] == "remote"


def test_ensure_dirs_creates_output_and_temp(tmp_path):
    cfg = make_cfg(tmp_path)
    ensure_dirs(cfg)
    assert Path(cfg["output_dir"]).is_dir()
    assert Path(cfg["temp_dir"]).is_dir()
