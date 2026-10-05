"""qwen-tts — BV 号 → 中文转写 API 入口。

配置加载（config.yaml）、Flask app 工厂与 /transcribe 同步管线：
    POST /transcribe {"bvid": ...} → bili 拉音频 → asr 转写 → 保存 .txt + 清理临时音频
"""
import os
import re
import sys
import time
import traceback
import uuid
from pathlib import Path

import yaml
from flask import Flask, jsonify, request

from asr import AsrError, transcribe
from bili import BV_RE, BiliError, get_audio

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

#: 必填配置项，缺失或为空则拒绝启动
REQUIRED_KEYS = (("asr", "provider"), ("asr", "url"), ("output_dir",), ("temp_dir",))

#: 可选项默认值（缺省时补全）
DEFAULTS = {
    "asr": {"api_key": "", "model": "", "language": "", "temperature": 0.0},
    "bilibili": {"cookie": ""},
    "timeout": {"download_s": 300, "asr_s": 600},
}


class ConfigError(Exception):
    """配置缺失或非法。"""


def load_config(path=None):
    """加载并校验 config.yaml。

    - 文件缺失 / YAML 解析失败 / 必填项缺失 / provider 非法 → 抛 ConfigError
    - 可选项按 DEFAULTS 补全
    """
    path = Path(path) if path else CONFIG_PATH
    if not path.exists():
        raise ConfigError(
            f"配置文件缺失: {path}（复制 config.example.yaml 为 config.yaml 并填写必填项）"
        )
    try:
        with path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"config.yaml 解析失败: {e}")
    if not isinstance(cfg, dict):
        raise ConfigError("config.yaml 顶层必须是键值映射")

    for section, values in DEFAULTS.items():
        node = cfg.setdefault(section, {})
        if not isinstance(node, dict):
            raise ConfigError(f"config.yaml 的 {section} 必须是映射")
        for k, v in values.items():
            node.setdefault(k, v)

    for keys in REQUIRED_KEYS:
        node = cfg
        for k in keys:
            if not isinstance(node, dict) or node.get(k) in (None, ""):
                raise ConfigError(f"config.yaml 缺少必填项: {'.'.join(keys)}")
            node = node[k]

    if cfg["asr"]["provider"] not in ("local", "remote"):
        raise ConfigError(
            f"asr.provider 必须是 local 或 remote，当前: {cfg['asr']['provider']!r}"
        )
    if cfg["asr"]["provider"] == "remote" and not cfg["asr"]["api_key"]:
        raise ConfigError("asr.provider 为 remote 时 asr.api_key 必填")
    return cfg


def ensure_dirs(cfg):
    """启动时自动创建 output_dir / temp_dir。"""
    for key in ("output_dir", "temp_dir"):
        Path(cfg[key]).expanduser().mkdir(parents=True, exist_ok=True)


# 错误码 → HTTP 状态映射（契约见 TASKS.md）
ERROR_STATUS = {
    "invalid_bvid": 400,
    "not_found": 404,
    "fetch_failed": 502,
    "asr_failed": 502,
    "timeout": 504,
}

_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def clean_title(title):
    """标题清洗：去除 \\/:*?"<>| ，空白压缩，截断 40 字符（契约规则）。"""
    t = _INVALID_FILENAME_CHARS.sub("", title or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:40]


def transcription_file_name(bvid, title):
    """转写文件名：{bvid}_{标题清洗}.txt"""
    return f"{bvid}_{clean_title(title)}.txt"


def _error_response(code, exc, cfg, bvid, started, audio_path):
    """按契约返回错误 JSON；失败时保留临时音频并在 message 中给出实际路径。"""
    message = str(exc)
    p = Path(audio_path)
    if p.exists():
        message += f"（临时音频已保留: {p}）"
    print(
        f"[transcribe] bvid={bvid} error={code} elapsed={time.time() - started:.1f}s msg={message}",
        flush=True,
    )
    return jsonify(error={"code": code, "message": message}), ERROR_STATUS.get(code, 502)


def create_app(cfg):
    """Flask app 工厂；cfg 来自 load_config。"""
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify(status="ok", asr={"provider": cfg["asr"]["provider"]})

    @app.post("/transcribe")
    def transcribe_route():
        body = request.get_json(silent=True) or {}
        bvid = body.get("bvid") or ""
        started = time.time()
        print(f"[transcribe] start bvid={bvid}", flush=True)
        # per-request 唯一临时文件名：同 BV 并发转写互不抢文件（T-017）；
        # .asr.wav / .chunk_*.wav 由该 stem 派生，自动隔离
        session = uuid.uuid4().hex[:8]
        audio_path = str(Path(cfg["temp_dir"]) / f"{bvid}_{session}.m4a")
        try:
            title, duration_s, audio_path = get_audio(bvid, cfg, dest_path=audio_path)
            text = transcribe(audio_path, cfg)
            out_path = Path(cfg["output_dir"]) / transcription_file_name(bvid, title)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
            os.remove(audio_path)  # 成功后清理临时音频
        except BiliError as e:
            return _error_response(e.code, e, cfg, bvid, started, audio_path)
        except AsrError as e:
            return _error_response(e.code, e, cfg, bvid, started, audio_path)
        except Exception as e:
            # 未预期异常 → 500 JSON（不是 HTML），堆栈进日志（T-017）
            traceback.print_exc()
            print(
                f"[transcribe] bvid={bvid} error=internal elapsed={time.time() - started:.1f}s msg={e}",
                flush=True,
            )
            return jsonify(error={"code": "internal", "message": f"内部错误: {e}"}), 500
        print(
            f"[transcribe] bvid={bvid} ok elapsed={time.time() - started:.1f}s file={out_path}",
            flush=True,
        )
        return jsonify(
            bvid=bvid, title=title, text=text, file_path=str(out_path), duration_s=duration_s
        )

    return app


def main():
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"[config] {e}", file=sys.stderr)
        sys.exit(1)
    ensure_dirs(cfg)
    app = create_app(cfg)
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()

