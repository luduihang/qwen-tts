"""管线测试：happy path / 错误映射 / 失败保留临时音频 / 标题清洗。

mock bili.get_audio 与 asr.transcribe，不依赖网络与真实 ASR。
"""
from pathlib import Path
from unittest.mock import patch

from asr import AsrError
from bili import BiliError

BVID = "BV1GJ411x7h7"


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
        "timeout": {"download_s": 5, "asr_s": 5},
    }


def make_client(cfg):
    from app import create_app

    app = create_app(cfg)  # 持有引用（Flask 2.2 JSON provider 弱引用 app）
    return app.test_client()


def write_temp_audio(cfg):
    p = Path(cfg["temp_dir"]) / f"{BVID}.m4a"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"FAKE-AUDIO")
    return p


def post_bvid(client, bvid):
    return client.post("/transcribe", json={"bvid": bvid})


def test_happy_path(tmp_path):
    cfg = make_cfg(tmp_path)
    temp_audio = write_temp_audio(cfg)
    with patch(
        "app.get_audio", return_value=("Rick Astley 官方 MV", 213, str(temp_audio))
    ), patch("app.transcribe", return_value="Never gonna give you up."):
        client = make_client(cfg)
        r = post_bvid(client, BVID)

    assert r.status_code == 200
    body = r.get_json()
    assert body["bvid"] == BVID
    assert body["title"] == "Rick Astley 官方 MV"
    assert body["text"] == "Never gonna give you up."
    assert body["duration_s"] == 213

    out = Path(body["file_path"])
    assert out.parent == Path(cfg["output_dir"])
    assert out.name == f"{BVID}_Rick Astley 官方 MV.txt"
    assert out.read_text(encoding="utf-8") == "Never gonna give you up."
    assert not temp_audio.exists()  # 成功后临时音频已删


def test_invalid_bvid_400(tmp_path):
    with patch("app.get_audio", side_effect=BiliError("非法 BV 号", "invalid_bvid")):
        client = make_client(make_cfg(tmp_path))
        r = post_bvid(client, "BV1GJ411x7h7")
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"]["code"] == "invalid_bvid"


def test_missing_bvid_400_without_patch(tmp_path):
    """真实 get_audio 处理空 bvid → invalid_bvid，无需 mock。"""
    client = make_client(make_cfg(tmp_path))
    r = client.post("/transcribe", json={})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "invalid_bvid"


def test_not_found_404(tmp_path):
    with patch("app.get_audio", side_effect=BiliError("视频不存在", "not_found")):
        client = make_client(make_cfg(tmp_path))
        r = post_bvid(client, BVID)
    assert r.status_code == 404
    assert r.get_json()["error"]["code"] == "not_found"


def test_fetch_failed_502_and_temp_kept(tmp_path):
    cfg = make_cfg(tmp_path)
    temp_audio = write_temp_audio(cfg)
    with patch(
        "app.get_audio", side_effect=BiliError("B 站接口错误 code=-500", "fetch_failed")
    ):
        client = make_client(cfg)
        r = post_bvid(client, BVID)
    assert r.status_code == 502
    err = r.get_json()["error"]
    assert err["code"] == "fetch_failed"
    assert str(temp_audio) in err["message"]  # 错误信息含保留路径
    assert temp_audio.exists()  # 失败保留临时音频


def test_asr_error_502_and_temp_kept(tmp_path):
    cfg = make_cfg(tmp_path)
    temp_audio = write_temp_audio(cfg)
    with patch("app.get_audio", return_value=("T", 10, str(temp_audio))), patch(
        "app.transcribe", side_effect=AsrError("ASR 请求失败: connection refused")
    ):
        client = make_client(cfg)
        r = post_bvid(client, BVID)
    assert r.status_code == 502
    err = r.get_json()["error"]
    assert err["code"] == "asr_failed"
    assert str(temp_audio) in err["message"]
    assert temp_audio.exists()


def test_title_illegal_chars_cleaned(tmp_path):
    cfg = make_cfg(tmp_path)
    temp_audio = write_temp_audio(cfg)
    dirty = 'A/B\\C:D"E<F>G|H   标题'
    with patch("app.get_audio", return_value=(dirty, 10, str(temp_audio))), patch(
        "app.transcribe", return_value="文本"
    ):
        client = make_client(cfg)
        r = post_bvid(client, BVID)
    assert r.status_code == 200
    name = Path(r.get_json()["file_path"]).name
    assert name == f"{BVID}_ABCDEFGH 标题.txt"


def test_title_truncated_to_40_chars(tmp_path):
    from app import clean_title

    long_title = "字" * 60
    assert clean_title(long_title) == "字" * 40
    # 文件名 = BV 号 + 下划线 + 40 字符 + .txt
    assert len(f"{BVID}_{clean_title(long_title)}.txt") == len(BVID) + 1 + 40 + 4


def test_non_json_body_400(tmp_path):
    client = make_client(make_cfg(tmp_path))
    r = client.post(
        "/transcribe", data="not-json", content_type="text/plain"
    )
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "invalid_bvid"
