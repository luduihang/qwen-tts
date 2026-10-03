"""ASR 客户端：音频文件 → 中文文本。

契约（见 TASKS.md 契约总览）：
    transcribe(audio_path, cfg) -> str
    失败抛 AsrError(message)

provider 切换点（config.yaml 的 asr.provider）：
    local  — 本地 vLLM 部署的 Qwen 语音模型（OpenAI 兼容 /v1/audio/transcriptions）
    remote — 远程 Qwen ASR 接口（额外带 Authorization: Bearer api_key）
两者请求同形：multipart POST，file=音频、model（可选透传）、language=zh。
"""
from pathlib import Path

import requests


class AsrError(Exception):
    """ASR 调用失败；code 默认 asr_failed，超时时 timeout。"""

    def __init__(self, message, code="asr_failed"):
        super().__init__(message)
        self.code = code


def transcribe(audio_path, cfg):
    """音频文件 → 中文文本。

    返回 ASR 响应中的 text 字段；网络/HTTP/解析异常统一抛 AsrError。
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

    form = {"language": a.get("language") or "zh"}
    if a.get("model"):
        form["model"] = a["model"]

    timeout = (cfg.get("timeout") or {}).get("asr_s", 600)
    try:
        with audio.open("rb") as f:
            files = {"file": (audio.name, f)}
            r = requests.post(
                a["url"], headers=headers, data=form, files=files, timeout=timeout
            )
    except requests.Timeout as e:
        raise AsrError(f"ASR 请求超时（>{timeout}s）: {e}", "timeout")
    except requests.RequestException as e:
        raise AsrError(f"ASR 请求失败: {e}")

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
