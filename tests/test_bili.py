"""bili.py 测试：BV 校验 / view→playurl→下载正常流 / not_found / fetch_failed / cookie 可选头。

全部 mock requests.get，不依赖网络。
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bili import BiliError, get_audio

VALID_BVID = "BV1GJ411x7h7"


def make_cfg(tmp_path, cookie=""):
    return {
        "bilibili": {"cookie": cookie},
        "timeout": {"download_s": 5},
        "temp_dir": str(tmp_path / "temp"),
    }


def json_resp(payload, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload
    return m


def stream_resp(content=b"FAKE-M4A", status=200):
    m = MagicMock()
    m.status_code = status
    m.iter_content.return_value = iter([content])
    m.__enter__.return_value = m
    m.__exit__.return_value = False
    return m


def ok_view():
    return {
        "code": 0,
        "data": {"title": "测试/视频:标题", "duration": 123, "cid": 12345678},
    }


def ok_play():
    return {
        "code": 0,
        "data": {
            "dash": {
                "audio": [
                    {"id": 30280, "baseUrl": "https://example.com/audio-30280.m4a"},
                    {"id": 30232, "baseUrl": "https://example.com/audio-30232.m4a"},
                ]
            }
        },
    }


@pytest.mark.parametrize(
    "bvid",
    [
        "bv1gJ411x7h7",  # 小写前缀
        "BV1",  # 太短
        "BV1GJ411x7h70",  # 太长
        "BV0GJ411x7h7",  # 首位 0
        "CV1GJ411x7h7",  # 非 BV 前缀
        "",
    ],
)
@patch("bili.requests.get")
def test_invalid_bvid(mock_get, bvid):
    with pytest.raises(BiliError) as ei:
        get_audio(bvid, make_cfg(Path("/tmp/never")))
    assert ei.value.code == "invalid_bvid"
    mock_get.assert_not_called()


@patch("bili.requests.get")
def test_happy_path(mock_get, tmp_path):
    cfg = make_cfg(tmp_path)
    mock_get.side_effect = [json_resp(ok_view()), json_resp(ok_play()), stream_resp()]

    title, duration_s, path = get_audio(VALID_BVID, cfg)

    assert title == "测试/视频:标题"
    assert duration_s == 123
    p = Path(path)
    assert p.parent == Path(cfg["temp_dir"])
    assert p.name == f"{VALID_BVID}.m4a"
    assert p.read_bytes() == b"FAKE-M4A"

    # view 请求形状
    _, kw_view = mock_get.call_args_list[0]
    assert kw_view["params"]["bvid"] == VALID_BVID
    # playurl 请求形状：fnval=16 + cid
    _, kw_play = mock_get.call_args_list[1]
    assert kw_play["params"] == {"bvid": VALID_BVID, "cid": 12345678, "fnval": 16}
    # 下载取 dash.audio 首项
    (dl_url,), kw_dl = mock_get.call_args_list[2]
    assert dl_url == "https://example.com/audio-30280.m4a"
    assert kw_dl["stream"] is True


@patch("bili.requests.get")
def test_headers_ua_referer_always(mock_get, tmp_path):
    mock_get.side_effect = [json_resp(ok_view()), json_resp(ok_play()), stream_resp()]
    get_audio(VALID_BVID, make_cfg(tmp_path, cookie=""))
    headers = mock_get.call_args_list[0].kwargs["headers"]
    assert headers["User-Agent"]
    assert headers["Referer"] == "https://www.bilibili.com"
    assert "Cookie" not in headers


@patch("bili.requests.get")
def test_cookie_header_when_configured(mock_get, tmp_path):
    mock_get.side_effect = [json_resp(ok_view()), json_resp(ok_play()), stream_resp()]
    get_audio(VALID_BVID, make_cfg(tmp_path, cookie="SESSDATA=abc; buvid3=xyz"))
    headers = mock_get.call_args_list[0].kwargs["headers"]
    assert headers["Cookie"] == "SESSDATA=abc; buvid3=xyz"
    # 下载请求同样带 cookie
    assert mock_get.call_args_list[2].kwargs["headers"]["Cookie"].startswith("SESSDATA=abc")


@pytest.mark.parametrize(
    "payload,expected_code",
    [
        ({"code": -404, "message": "啥都木有"}, "not_found"),
        ({"code": 62002, "message": "视频不存在"}, "not_found"),
        ({"code": -500, "message": "服务器开了个小差"}, "fetch_failed"),
    ],
)
@patch("bili.requests.get")
def test_view_business_error(mock_get, tmp_path, payload, expected_code):
    mock_get.return_value = json_resp(payload)
    with pytest.raises(BiliError) as ei:
        get_audio(VALID_BVID, make_cfg(tmp_path))
    assert ei.value.code == expected_code
    mock_get.assert_called_once()


@patch("bili.requests.get")
def test_view_http_500_is_fetch_failed(mock_get, tmp_path):
    mock_get.return_value = json_resp({}, status=500)
    with pytest.raises(BiliError) as ei:
        get_audio(VALID_BVID, make_cfg(tmp_path))
    assert ei.value.code == "fetch_failed"


@patch("bili.requests.get")
def test_network_error_is_fetch_failed(mock_get, tmp_path):
    import requests as rq

    mock_get.side_effect = rq.ConnectionError("connection refused")
    with pytest.raises(BiliError) as ei:
        get_audio(VALID_BVID, make_cfg(tmp_path))
    assert ei.value.code == "fetch_failed"


@patch("bili.requests.get")
def test_view_timeout_is_timeout_code(mock_get, tmp_path):
    import requests as rq

    mock_get.side_effect = rq.Timeout("read timed out")
    with pytest.raises(BiliError) as ei:
        get_audio(VALID_BVID, make_cfg(tmp_path))
    assert ei.value.code == "timeout"


@patch("bili.requests.get")
def test_download_timeout_is_timeout_code(mock_get, tmp_path):
    import requests as rq

    mock_get.side_effect = [
        json_resp(ok_view()),
        json_resp(ok_play()),
        rq.Timeout("read timed out"),
    ]
    with pytest.raises(BiliError) as ei:
        get_audio(VALID_BVID, make_cfg(tmp_path))
    assert ei.value.code == "timeout"


@patch("bili.requests.get")
def test_playurl_without_dash_audio(mock_get, tmp_path):
    mock_get.side_effect = [json_resp(ok_view()), json_resp({"code": 0, "data": {}})]
    with pytest.raises(BiliError) as ei:
        get_audio(VALID_BVID, make_cfg(tmp_path))
    assert ei.value.code == "fetch_failed"


@patch("bili.requests.get")
def test_dest_path_used_when_provided(mock_get, tmp_path):
    """dest_path 指定时下载到指定路径（管线并发隔离用，T-017）。"""
    cfg = make_cfg(tmp_path)
    mock_get.side_effect = [json_resp(ok_view()), json_resp(ok_play()), stream_resp()]
    custom = tmp_path / "custom" / "my" / "audio.m4a"
    title, duration_s, path = get_audio(VALID_BVID, cfg, dest_path=custom)
    p = Path(path)
    assert p == custom
    assert p.read_bytes() == b"FAKE-M4A"
    assert title == "测试/视频:标题" and duration_s == 123


@patch("bili.requests.get")
def test_download_http_403_is_fetch_failed_and_no_file(mock_get, tmp_path):
    cfg = make_cfg(tmp_path)
    mock_get.side_effect = [
        json_resp(ok_view()),
        json_resp(ok_play()),
        stream_resp(status=403),
    ]
    with pytest.raises(BiliError) as ei:
        get_audio(VALID_BVID, cfg)
    assert ei.value.code == "fetch_failed"
    assert not Path(cfg["temp_dir"], f"{VALID_BVID}.m4a").exists()
