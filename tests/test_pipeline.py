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


def fake_get_audio_ok(bvid, cfg, dest_path=None, title="T", duration_s=10):
    """模拟 get_audio：把“下载到的”音频写入 dest_path（T-017 后为 per-request 唯一名）并返回契约三元组。"""
    p = Path(dest_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"FAKE-AUDIO")
    return (title, duration_s, str(p))


def post_bvid(client, bvid):
    return client.post("/transcribe", json={"bvid": bvid})


def test_happy_path(tmp_path):
    cfg = make_cfg(tmp_path)
    with patch(
        "app.get_audio",
        side_effect=lambda bvid, cfg_, dest_path=None: fake_get_audio_ok(
            bvid, cfg_, dest_path, title="Rick Astley 官方 MV", duration_s=213
        ),
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
    # 成功后临时音频已删（uuid 命名下 temp_dir 无任何残留）
    assert not list(Path(cfg["temp_dir"]).glob("*.m4a"))


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
    def fake_get_fail(bvid, cfg, dest_path=None):
        p = Path(dest_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"PARTIAL-AUDIO")  # 模拟部分下载残留
        raise BiliError("B 站接口错误 code=-500", "fetch_failed")

    cfg = make_cfg(tmp_path)
    with patch("app.get_audio", side_effect=fake_get_fail):
        client = make_client(cfg)
        r = post_bvid(client, BVID)
    assert r.status_code == 502
    err = r.get_json()["error"]
    assert err["code"] == "fetch_failed"
    kept = list(Path(cfg["temp_dir"]).glob("*.m4a"))
    assert len(kept) == 1 and str(kept[0]) in err["message"]  # 错误信息含保留路径


def test_asr_error_502_and_temp_kept(tmp_path):
    cfg = make_cfg(tmp_path)
    with patch("app.get_audio", side_effect=fake_get_audio_ok), patch(
        "app.transcribe", side_effect=AsrError("ASR 请求失败: connection refused")
    ):
        client = make_client(cfg)
        r = post_bvid(client, BVID)
    assert r.status_code == 502
    err = r.get_json()["error"]
    assert err["code"] == "asr_failed"
    kept = list(Path(cfg["temp_dir"]).glob("*.m4a"))
    assert len(kept) == 1 and str(kept[0]) in err["message"]


def test_asr_timeout_504_and_temp_kept(tmp_path):
    cfg = make_cfg(tmp_path)
    with patch("app.get_audio", side_effect=fake_get_audio_ok), patch(
        "app.transcribe", side_effect=AsrError("ASR 请求超时（>1s）", "timeout")
    ):
        client = make_client(cfg)
        r = post_bvid(client, BVID)
    assert r.status_code == 504
    assert r.get_json()["error"]["code"] == "timeout"
    assert len(list(Path(cfg["temp_dir"]).glob("*.m4a"))) == 1


def test_bili_timeout_504(tmp_path):
    with patch(
        "app.get_audio", side_effect=BiliError("B 站接口请求超时（>1s）", "timeout")
    ):
        client = make_client(make_cfg(tmp_path))
        r = post_bvid(client, BVID)
    assert r.status_code == 504
    assert r.get_json()["error"]["code"] == "timeout"


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


def test_generic_exception_500_json(tmp_path):
    """未预期异常 → 500 JSON（不是 Flask 默认 500 HTML），T-017。"""
    cfg = make_cfg(tmp_path)
    with patch("app.get_audio", side_effect=fake_get_audio_ok), patch(
        "app.transcribe", side_effect=RuntimeError("boom")
    ):
        client = make_client(cfg)
        r = post_bvid(client, BVID)
    assert r.status_code == 500
    err = r.get_json()["error"]
    assert err["code"] == "internal"
    assert "boom" in err["message"]


def test_concurrent_same_bvid_both_ok(tmp_path):
    """同 BV 并发两请求：uuid temp 名隔离，均 200 且临时文件互不干扰，T-017。"""
    import threading

    cfg = make_cfg(tmp_path)
    Path(cfg["temp_dir"]).mkdir(parents=True, exist_ok=True)
    dests = []
    barrier = threading.Barrier(2, timeout=10)  # 保证两请求同时处于“已下载未清理”窗口

    def fake_get(bvid, cfg_, dest_path=None):
        dests.append(Path(dest_path))
        p = Path(dest_path)
        p.write_bytes(b"FAKE-AUDIO")
        barrier.wait()
        return ("标题", 10, str(p))

    results = []

    def post():
        with patch("app.get_audio", side_effect=fake_get), patch(
            "app.transcribe", return_value="文本"
        ):
            results.append(make_client(cfg).post("/transcribe", json={"bvid": BVID}).status_code)

    threads = [threading.Thread(target=post) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert results == [200, 200]
    assert len(set(dests)) == 2  # 两请求用了不同的临时文件名
    assert not list(Path(cfg["temp_dir"]).glob("*.m4a"))  # 各自清理，无残留
