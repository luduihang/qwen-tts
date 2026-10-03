"""qwen-tts — BV 号 → 中文转写 API 入口。

配置加载（config.yaml）与 Flask app 工厂。/transcribe 管线在 Phase 3 接线。
"""
import os
import sys
from pathlib import Path

import yaml
from flask import Flask, jsonify

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"

#: 必填配置项，缺失或为空则拒绝启动
REQUIRED_KEYS = (("asr", "provider"), ("asr", "url"), ("output_dir",), ("temp_dir",))

#: 可选项默认值（缺省时补全）
DEFAULTS = {
    "asr": {"api_key": "", "model": "", "language": "zh"},
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


def create_app(cfg):
    """Flask app 工厂；cfg 来自 load_config。"""
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify(status="ok", asr={"provider": cfg["asr"]["provider"]})

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

