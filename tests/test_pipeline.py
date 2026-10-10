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


# ---------- T-018 output_dir 请求参数 ----------


def test_output_dir_param_uses_custom_dir(tmp_path):
    """指定已存在的 output_dir：.txt 落盘到该目录（T-018）。"""
    cfg = make_cfg(tmp_path)
    custom = Path(tmp_path) / "my_subs"
    custom.mkdir()
    with patch("app.get_audio", side_effect=fake_get_audio_ok), patch(
        "app.transcribe", return_value="文本"
    ):
        client = make_client(cfg)
        r = client.post("/transcribe", json={"bvid": BVID, "output_dir": str(custom)})
    assert r.status_code == 200
    out = Path(r.get_json()["file_path"])
    assert out.parent == custom
    assert out.name == f"{BVID}_T.txt"
    assert out.read_text(encoding="utf-8") == "文本"


def test_output_dir_missing_400_and_pipeline_not_started(tmp_path):
    """output_dir 不存在 → 400 invalid_output_dir，不进下载/转写（T-018）。"""
    cfg = make_cfg(tmp_path)
    with patch("app.get_audio", side_effect=fake_get_audio_ok) as mock_ga:
        client = make_client(cfg)
        r = client.post(
            "/transcribe", json={"bvid": BVID, "output_dir": str(Path(tmp_path) / "nope")}
        )
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "invalid_output_dir"
    assert "临时音频" not in r.get_json()["error"]["message"]  # 未进管线，不应提临时文件
    mock_ga.assert_not_called()  # 校验在下载之前


def test_output_dir_is_file_400(tmp_path):
    cfg = make_cfg(tmp_path)
    a_file = Path(cfg["temp_dir"]) / "x.txt"
    a_file.parent.mkdir(parents=True, exist_ok=True)
    a_file.write_bytes(b"not a dir")
    with patch("app.get_audio", side_effect=fake_get_audio_ok):
        client = make_client(cfg)
        r = client.post("/transcribe", json={"bvid": BVID, "output_dir": str(a_file)})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "invalid_output_dir"


def test_output_dir_wrong_type_400(tmp_path):
    cfg = make_cfg(tmp_path)
    with patch("app.get_audio", side_effect=fake_get_audio_ok):
        client = make_client(cfg)
        r = client.post("/transcribe", json={"bvid": BVID, "output_dir": 123})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "invalid_output_dir"


# ---------- T-019 prompt 请求参数 ----------

def test_prompt_passed_to_transcribe(tmp_path):
    """非空 prompt 透传给 asr.transcribe（T-019）。"""
    cfg = make_cfg(tmp_path)
    with patch(
        "app.get_audio",
        side_effect=lambda bvid, cfg_, dest_path=None: fake_get_audio_ok(bvid, cfg_, dest_path),
    ), patch("app.transcribe", return_value="转写文本") as m_transcribe:
        client = make_client(cfg)
        r = client.post("/transcribe", json={"bvid": BVID, "prompt": "命理学：八字、叫应"})

    assert r.status_code == 200
    assert m_transcribe.call_args.kwargs.get("prompt") == "命理学：八字、叫应"


def test_prompt_omitted_passes_none(tmp_path):
    """省略 prompt → transcribe 收到 prompt=None（请求形状不变，T-019）。"""
    cfg = make_cfg(tmp_path)
    with patch(
        "app.get_audio",
        side_effect=lambda bvid, cfg_, dest_path=None: fake_get_audio_ok(bvid, cfg_, dest_path),
    ), patch("app.transcribe", return_value="转写文本") as m_transcribe:
        client = make_client(cfg)
        r = client.post("/transcribe", json={"bvid": BVID})

    assert r.status_code == 200
    assert m_transcribe.call_args.kwargs.get("prompt") is None


def test_prompt_wrong_type_400_and_pipeline_not_started(tmp_path):
    """prompt 非字符串类型 → 400 invalid_prompt，不进下载/转写（T-019）。"""
    cfg = make_cfg(tmp_path)
    with patch("app.get_audio") as m_get, patch("app.transcribe") as m_tr:
        client = make_client(cfg)
        for bad in (123, True, ["八字"], {"x": 1}):
            r = client.post("/transcribe", json={"bvid": BVID, "prompt": bad})
            assert r.status_code == 400
            assert r.get_json()["error"]["code"] == "invalid_prompt"
    m_get.assert_not_called()
    m_tr.assert_not_called()


def test_prompt_empty_string_is_noop(tmp_path):
    """prompt = 空串 = 等同未提供（路由放行，asr 不进 form）（T-019）。"""
    cfg = make_cfg(tmp_path)
    with patch(
        "app.get_audio",
        side_effect=lambda bvid, cfg_, dest_path=None: fake_get_audio_ok(bvid, cfg_, dest_path),
    ), patch("app.transcribe", return_value="转写文本") as m_transcribe:
        client = make_client(cfg)
        r = client.post("/transcribe", json={"bvid": BVID, "prompt": ""})

    assert r.status_code == 200
    assert m_transcribe.call_args.kwargs.get("prompt") == ""
