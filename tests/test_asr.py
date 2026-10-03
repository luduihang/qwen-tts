"""asr.py 测试：local/remote 请求形状、Bearer 头、非 200、超时、响应解析。

全部 mock requests.post，不依赖网络。
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests as rq

from asr import AsrError, transcribe

AUDIO_CONTENT = b"FAKE-M4A-AUDIO"


def make_cfg(provider="local", api_key="", model="", url="http://127.0.0.1:8000/v1/audio/transcriptions"):
    return {
        "asr": {
            "provider": provider,
            "url": url,
            "api_key": api_key,
            "model": model,
            "language": "zh",
        },
        "timeout": {"asr_s": 7},
    }


def write_audio(tmp_path):
    p = tmp_path / "BV1GJ411x7h7.m4a"
    p.write_bytes(AUDIO_CONTENT)
    return p


def ok_resp(payload=None):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = payload if payload is not None else {"text": "你好，世界。"}
    m.text = json.dumps(payload or {"text": "你好，世界。"}, ensure_ascii=False)
    return m


@patch("asr.requests.post")
def test_local_request_shape(mock_post, tmp_path):
    audio = write_audio(tmp_path)
    mock_post.return_value = ok_resp()

    text = transcribe(str(audio), make_cfg(provider="local", model="qwen-asr"))

    assert text == "你好，世界。"
    (url,), kw = mock_post.call_args
    assert url == "http://127.0.0.1:8000/v1/audio/transcriptions"
    assert "Authorization" not in kw["headers"]
    assert kw["data"]["language"] == "zh"
    assert kw["data"]["model"] == "qwen-asr"
    assert kw["timeout"] == 7
    name, fh = kw["files"]["file"]
    assert name == "BV1GJ411x7h7.m4a"
    assert fh.read() == AUDIO_CONTENT


@patch("asr.requests.post")
def test_local_no_model_omits_field(mock_post, tmp_path):
    mock_post.return_value = ok_resp()
    transcribe(str(write_audio(tmp_path)), make_cfg(provider="local"))
    assert "model" not in mock_post.call_args.kwargs["data"]


@patch("asr.requests.post")
def test_remote_bearer_header(mock_post, tmp_path):
    mock_post.return_value = ok_resp({"text": "远程转写结果"})
    text = transcribe(
        str(write_audio(tmp_path)), make_cfg(provider="remote", api_key="sk-123")
    )
    assert text == "远程转写结果"
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer sk-123"


@patch("asr.requests.post")
def test_remote_without_api_key_raises(mock_post, tmp_path):
    with pytest.raises(AsrError, match="api_key"):
        transcribe(str(write_audio(tmp_path)), make_cfg(provider="remote"))
    mock_post.assert_not_called()


def test_missing_audio_file(tmp_path):
    with pytest.raises(AsrError, match="不存在"):
        transcribe(str(tmp_path / "nope.m4a"), make_cfg())


@patch("asr.requests.post")
def test_non_200_raises_with_status(mock_post, tmp_path):
    m = MagicMock()
    m.status_code = 500
    m.text = "internal error"
    m.json.return_value = {}
    mock_post.return_value = m
    with pytest.raises(AsrError, match="500"):
        transcribe(str(write_audio(tmp_path)), make_cfg())


@patch("asr.requests.post")
def test_timeout_raises_asr_error(mock_post, tmp_path):
    mock_post.side_effect = rq.Timeout("read timed out")
    with pytest.raises(AsrError, match="ASR 请求失败"):
        transcribe(str(write_audio(tmp_path)), make_cfg())


@patch("asr.requests.post")
def test_connection_error_raises_asr_error(mock_post, tmp_path):
    mock_post.side_effect = rq.ConnectionError("connection refused")
    with pytest.raises(AsrError, match="ASR 请求失败"):
        transcribe(str(write_audio(tmp_path)), make_cfg())


@patch("asr.requests.post")
def test_non_json_response_raises(mock_post, tmp_path):
    m = MagicMock()
    m.status_code = 200
    m.json.side_effect = ValueError("no json")
    m.text = "<html>gateway</html>"
    mock_post.return_value = m
    with pytest.raises(AsrError, match="非 JSON"):
        transcribe(str(write_audio(tmp_path)), make_cfg())


@patch("asr.requests.post")
def test_missing_text_field_raises(mock_post, tmp_path):
    mock_post.return_value = ok_resp({"detail": "unsupported format"})
    with pytest.raises(AsrError, match="text 字段"):
        transcribe(str(write_audio(tmp_path)), make_cfg())
