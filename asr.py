"""ASR 客户端：音频文件 → 文本。

契约（见 TASKS.md 契约总览）：
    transcribe(audio_path, cfg) -> str
    失败抛 AsrError(message)

provider 切换点（config.yaml 的 asr.provider）：
    local  — 本地/局域网 vLLM 部署的 Qwen 语音模型（OpenAI 兼容 /v1/audio/transcriptions）
    remote — 远程 Qwen ASR 接口（额外带 Authorization: Bearer api_key）
两者请求同形：multipart POST，file=音频、model、language、temperature。

转码约定：vLLM Qwen3-ASR 端点只接受 wav（m4a/AAC 输入会在服务端挂起）。
非 wav 输入先用本地 ffmpeg 转 16k 单声道 wav，发送后删除临时文件。
"""
import shutil
import subprocess
from pathlib import Path

import requests

#: ffmpeg 转码的固定参数（端点要求 16k 单声道）
_WAV_ARGS = ["-ac", "1", "-ar", "16000"]
_CONVERT_TIMEOUT_S = 600


class AsrError(Exception):
    """ASR 调用失败；code 默认 asr_failed，超时时 timeout。"""

    def __init__(self, message, code="asr_failed"):
        super().__init__(message)
        self.code = code


def _convert_to_wav(audio: Path) -> Path:
    """m4a 等非 wav 音频 → 16k 单声道 wav（临时文件 {音频名}.asr.wav）。"""
    if shutil.which("ffmpeg") is None:
        raise AsrError(
            "缺少 ffmpeg：ASR 端点只接受 wav，需先用 ffmpeg 转码（安装后重试）"
        )
    out = audio.with_suffix(".asr.wav")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(audio), *_WAV_ARGS, str(out),
            ],
            check=True,
            timeout=_CONVERT_TIMEOUT_S,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        out.unlink(missing_ok=True)
        raise AsrError(f"ffmpeg 转码失败: {e}")
    if not out.exists():
        raise AsrError(f"ffmpeg 转码未产出文件: {out}")
    return out


def transcribe(audio_path, cfg):
    """音频文件 → 文本。

    返回 ASR 响应中的 text 字段；网络/HTTP/解析/转码异常统一抛 AsrError。
    """
    a = cfg["asr"]
    audio = Path(audio_path)
    if not audio.is_file():
        raise AsrError(f"音频文件不存在: {audio_path}")
    if a.get("provider") == "remote" and not a.get("api_key"):
        raise AsrError("remote provider 需要配置 asr.api_key")

    headers = {}
    if a.get("provider") == "remote":
        headers["Authorization"] = f"Bearer {a['api_key']}"

    form = {"temperature": a.get("temperature", 0.0)}
    if a.get("model"):
        form["model"] = a["model"]
    # language 为空 = 不发送（部分端点传了会行为异常，模型自身能自动检测语言）
    if a.get("language"):
        form["language"] = a["language"]

    # 端点只接受 wav：非 wav 输入先转码（临时文件，发送后删除）
    send_path = audio
    converted = None
    if audio.suffix.lower() != ".wav":
        converted = _convert_to_wav(audio)
        send_path = converted

    timeout = (cfg.get("timeout") or {}).get("asr_s", 600)
    try:
        with send_path.open("rb") as f:
            files = {"file": (send_path.name, f)}
            r = requests.post(
                a["url"], headers=headers, data=form, files=files, timeout=timeout
            )
    except requests.Timeout as e:
        raise AsrError(f"ASR 请求超时（>{timeout}s）: {e}", "timeout")
    except requests.RequestException as e:
        raise AsrError(f"ASR 请求失败: {e}")
    finally:
        if converted is not None:
            converted.unlink(missing_ok=True)

    if r.status_code != 200:
        raise AsrError(f"ASR 返回 HTTP {r.status_code}: {r.text[:200]}")
    try:
        payload = r.json()
    except ValueError as e:
        raise AsrError(f"ASR 响应非 JSON: {e}")
    text = payload.get("text")
    if not isinstance(text, str):
        raise AsrError(f"ASR 响应缺少 text 字段: {payload!r}")
    return text
