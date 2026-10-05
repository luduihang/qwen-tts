"""asr.py 测试：请求形状 / Bearer / 非 200 / 超时 / 解析 / 转码约定。

HTTP 全 mock（requests.post）；转码测试用真实 ffmpeg（系统依赖，
测试环境需已安装），m4a 用例内是真实 wav 字节（ffmpeg 按内容解码）。
"""
import json
import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests as rq

from asr import AsrError, transcribe


def make_cfg(provider="local", api_key="", model="", url="http://127.0.0.1:8000/v1/audio/transcriptions",
             language="", temperature=0.0):
    return {
        "asr": {
            "provider": provider,
            "url": url,
            "api_key": api_key,
            "model": model,
            "language": language,
            "temperature": temperature,
        },
        "timeout": {"asr_s": 7},
    }


def real_wav_bytes(seconds=0.1, rate=16000):
    """生成真实 16k 单声道静音 wav 字节。"""
    frames = int(seconds * rate)
    raw = b"".join(struct.pack("<h", 0) for _ in range(frames))
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(raw)
    return buf.getvalue()


def write_audio(tmp_path, name="BV1GJ411x7h7.wav", content=None):
    p = tmp_path / name
    p.write_bytes(content if content is not None else b"FAKE-AUDIO")
    return p


def ok_resp(payload=None):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = payload if payload is not None else {"text": "你好，世界。"}
    m.text = json.dumps(payload or {"text": "你好，世界。"}, ensure_ascii=False)
    return m


def capture_post(response=None):
    """返回 (mock_post, captured)：在 post 调用内捕获请求形状（文件此时未关）。"""
    captured = {}

    def fake_post(url, **kw):
        captured["url"] = url
        captured["headers"] = kw.get("headers", {})
        captured["data"] = kw.get("data", {})
        captured["timeout"] = kw.get("timeout")
        name, fh = kw["files"]["file"]
        captured["name"] = name
        captured["content"] = fh.read()
        return response if response is not None else ok_resp()

    mock = MagicMock(side_effect=fake_post)
    return mock, captured


@patch("asr.requests.post")
def test_local_request_shape(mock_post, tmp_path):
    mock, cap = capture_post()
    mock_post.side_effect = mock.side_effect

    audio = write_audio(tmp_path)  # .wav：不触发转码
    text = transcribe(str(audio), make_cfg(provider="local", model="qwen-asr"))

    assert text == "你好，世界。"
    assert cap["url"] == "http://127.0.0.1:8000/v1/audio/transcriptions"
    assert "Authorization" not in cap["headers"]
    assert "language" not in cap["data"]  # 默认不发送 language
    assert cap["data"]["model"] == "qwen-asr"
    assert cap["data"]["temperature"] == 0.0
    assert cap["timeout"] == 7
    assert cap["name"] == "BV1GJ411x7h7.wav"


@patch("asr.requests.post")
def test_language_sent_when_configured(mock_post, tmp_path):
    mock, cap = capture_post()
    mock_post.side_effect = mock.side_effect
    transcribe(str(write_audio(tmp_path)), make_cfg(language="zh"))
    assert cap["data"]["language"] == "zh"


@patch("asr.requests.post")
def test_temperature_explicit(mock_post, tmp_path):
    mock, cap = capture_post()
    mock_post.side_effect = mock.side_effect
    transcribe(str(write_audio(tmp_path)), make_cfg(temperature=0.7))
    assert cap["data"]["temperature"] == 0.7


@patch("asr.requests.post")
def test_local_no_model_omits_field(mock_post, tmp_path):
    mock, cap = capture_post()
    mock_post.side_effect = mock.side_effect
    transcribe(str(write_audio(tmp_path)), make_cfg(provider="local"))
    assert "model" not in cap["data"]


@patch("asr.requests.post")
def test_wav_sent_as_is_without_conversion(mock_post, tmp_path):
    """wav 输入不转码：subprocess.run 绝不被调用。"""
    mock, cap = capture_post()
    mock_post.side_effect = mock.side_effect

    def explode(*a, **kw):
        raise AssertionError("wav 输入不应触发 ffmpeg")

    audio = write_audio(tmp_path, content=real_wav_bytes())
    with patch("asr.subprocess.run", side_effect=explode):
        transcribe(str(audio), make_cfg())
    assert cap["name"].endswith(".wav")


@patch("asr.requests.post")
def test_m4a_converted_to_wav_and_temp_cleaned(mock_post, tmp_path):
    """m4a 输入：真实 ffmpeg 转 16k wav → 上传 .asr.wav → 临时文件删除。"""
    import subprocess as sp

    real_run = sp.run
    calls = []

    def spy_run(*a, **kw):
        calls.append(a[0] if a else kw.get("args"))
        return real_run(*a, **kw)

    mock, cap = capture_post()
    mock_post.side_effect = mock.side_effect
    audio = write_audio(tmp_path, name="BV1GJ411x7h7.m4a", content=real_wav_bytes())
    with patch("asr.subprocess.run", side_effect=spy_run):
        transcribe(str(audio), make_cfg(model="Qwen3-ASR-1.7B"))

    # 上传的是转码后的 wav
    assert cap["name"] == "BV1GJ411x7h7.asr.wav"
    assert cap["content"][:4] == b"RIFF"  # 转码产物是真实 wav
    # 临时文件已清理
    assert not (tmp_path / "BV1GJ411x7h7.asr.wav").exists()
    # ffmpeg 参数含 16k 单声道
    assert calls and "16000" in " ".join(str(x) for x in calls[0])
    assert "-ac" in " ".join(str(x) for x in calls[0])


@patch("asr.requests.post")
def test_conversion_failure_raises_and_cleans(mock_post, tmp_path):
    audio = write_audio(tmp_path, name="bad.m4a", content=b"not-audio-garbage-bytes")
    with pytest.raises(AsrError, match="ffmpeg 转码失败"):
        transcribe(str(audio), make_cfg())
    assert not (tmp_path / "bad.asr.wav").exists()
    mock_post.assert_not_called()


def test_ffmpeg_missing_raises(tmp_path):
    audio = write_audio(tmp_path, name="x.m4a", content=real_wav_bytes())
    with patch("asr.shutil.which", return_value=None):
        with pytest.raises(AsrError, match="ffmpeg"):
            transcribe(str(audio), make_cfg())


@patch("asr.requests.post")
def test_remote_bearer_header(mock_post, tmp_path):
    mock, cap = capture_post()
    mock_post.side_effect = mock.side_effect
    text = transcribe(
        str(write_audio(tmp_path)), make_cfg(provider="remote", api_key="sk-123")
    )
    assert text == "你好，世界。"
    assert cap["headers"]["Authorization"] == "Bearer sk-123"


@patch("asr.requests.post")
def test_remote_without_api_key_raises(mock_post, tmp_path):
    with pytest.raises(AsrError, match="api_key"):
        transcribe(str(write_audio(tmp_path)), make_cfg(provider="remote"))
    mock_post.assert_not_called()


def test_missing_audio_file(tmp_path):
    with pytest.raises(AsrError, match="不存在"):
        transcribe(str(tmp_path / "nope.wav"), make_cfg())


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
    with pytest.raises(AsrError, match="超时") as ei:
        transcribe(str(write_audio(tmp_path)), make_cfg())
    assert ei.value.code == "timeout"


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
