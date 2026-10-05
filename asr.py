"""ASR 客户端：音频文件 → 文本。

契约（见 TASKS.md 契约总览）：
    transcribe(audio_path, cfg) -> str
    失败抛 AsrError(message)

provider 切换点（config.yaml 的 asr.provider）：
    local  — 本地/局域网 vLLM 部署的 Qwen 语音模型（OpenAI 兼容 /v1/audio/transcriptions）
    remote — 远程 Qwen ASR 接口（额外带 Authorization: Bearer api_key）
两者请求同形：multipart POST，file=音频、model、language、temperature。

转码约定：vLLM Qwen3-ASR 端点只接受 wav（m4a/AAC 输入会在服务端挂起）。
非 wav 输入先用本地 ffmpeg 转 16k 单声道 wav（临时文件 {音频名}.asr.wav，发送后删除）。

长音频约定（T-016）：端点有文件大小上限（实测 29MB wav 可过、30MB wav → 400
audio_filesize_mb，上限约 30MB）。时长超过 asr.chunk_seconds（默认 300s，
省略/0 同默认）的 wav 先用 ffmpeg 切段（segment 流拷贝，{音频名}.chunk_NNN.wav，
发送后删除），逐段转写后按序拼接 text。默认每段 300s，16k 单声道下 ≈ 9.6MB，
离上限余量充足。
"""
import shutil
import subprocess
import wave
from pathlib import Path

import requests

#: ffmpeg 转码的固定参数（端点要求 16k 单声道）
_WAV_ARGS = ["-ac", "1", "-ar", "16000"]
_CONVERT_TIMEOUT_S = 600
_CHUNK_TIMEOUT_S = 600

#: 默认切段长度（秒）；省略/0 = 用默认。300s 16k 单声道 wav ≈ 9.6MB（上限约 30MB）
DEFAULT_CHUNK_S = 300


class AsrError(Exception):
    """ASR 调用失败；code 默认 asr_failed，超时时 timeout。"""

    def __init__(self, message, code="asr_failed"):
        super().__init__(message)
        self.code = code


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _convert_to_wav(audio: Path) -> Path:
    """m4a 等非 wav 音频 → 16k 单声道 wav（临时文件 {音频名}.asr.wav）。"""
    if not _ffmpeg_available():
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


def _wav_duration_s(path: Path) -> float:
    """wav 时长（秒）；无法解析（非标准 PCM wav）时返回 0 = 不切段、原样发送。"""
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except (wave.Error, EOFError):
        return 0.0


def _split_wav(wav: Path, chunk_s: int) -> list:
    """ffmpeg segment 切段（流拷贝，不重编码）→ 按序返回段文件列表。"""
    if not _ffmpeg_available():
        raise AsrError("缺少 ffmpeg：长音频切段需要 ffmpeg")
    stem = wav.stem
    # 清理同名的历史残留段（上次失败留下的）
    for stale in wav.parent.glob(f"{stem}.chunk_*.wav"):
        stale.unlink(missing_ok=True)
    pattern = str(wav.parent / f"{stem}.chunk_%03d.wav")
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(wav),
                "-f", "segment", "-segment_time", str(chunk_s),
                "-c", "copy", pattern,
            ],
            check=True,
            timeout=_CHUNK_TIMEOUT_S,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        raise AsrError(f"ffmpeg 切段失败: {e}")
    chunks = sorted(wav.parent.glob(f"{stem}.chunk_*.wav"))
    if not chunks:
        raise AsrError(f"ffmpeg 切段未产出文件: {wav}")
    return chunks


def _post_audio(path: Path, url: str, headers: dict, form: dict, timeout: int, label: str) -> str:
    """发送单个音频文件，返回 text 字段；网络/HTTP/解析异常统一 AsrError。"""
    try:
        with path.open("rb") as f:
            r = requests.post(
                url, headers=headers, data=form,
                files={"file": (path.name, f)}, timeout=timeout,
            )
    except requests.Timeout as e:
        raise AsrError(f"ASR 请求超时（>{timeout}s）{label}: {e}", "timeout")
    except requests.RequestException as e:
        raise AsrError(f"ASR 请求失败{label}: {e}")
    if r.status_code != 200:
        raise AsrError(f"ASR 返回 HTTP {r.status_code}{label}: {r.text[:200]}")
    try:
        payload = r.json()
    except ValueError as e:
        raise AsrError(f"ASR 响应非 JSON: {e}")
    text = payload.get("text")
    if not isinstance(text, str):
        raise AsrError(f"ASR 响应缺少 text 字段: {payload!r}")
    return text


def transcribe(audio_path, cfg):
    """音频文件 → 文本。

    返回 ASR 响应中的 text 字段（长音频为逐段按序拼接）；
    网络/HTTP/解析/转码/切段异常统一抛 AsrError。
    """
    a = cfg["asr"]
    audio = Path(audio_path)
    if not audio.is_file():
        raise AsrError(f"音频文件不存在: {audio_path}")
    if a.get("provider") == "remote" and not a.get("api_key"):
        raise AsrError("remote provider 需要配置 asr.api_key")

    try:
        chunk_s = int(a.get("chunk_seconds") or DEFAULT_CHUNK_S)
    except (TypeError, ValueError):
        raise AsrError("asr.chunk_seconds 必须是整数（秒）")
    if chunk_s < 1:
        raise AsrError("asr.chunk_seconds 必须 >= 1")

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
    converted = None
    if audio.suffix.lower() != ".wav":
        converted = _convert_to_wav(audio)
        send_path = converted
    else:
        send_path = audio

    chunk_files = []
    timeout = (cfg.get("timeout") or {}).get("asr_s", 600)
    try:
        if _wav_duration_s(send_path) > chunk_s:
            chunk_files = _split_wav(send_path, chunk_s)
            send_paths = chunk_files
        else:
            send_paths = [send_path]

        texts = [
            _post_audio(
                p, a["url"], headers, form, timeout,
                f"（段 {i}/{len(send_paths)}）" if len(send_paths) > 1 else "",
            )
            for i, p in enumerate(send_paths, 1)
        ]
        return "".join(texts)
    finally:
        for c in chunk_files:
            c.unlink(missing_ok=True)
        if converted is not None:
            converted.unlink(missing_ok=True)
