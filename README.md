# qwen-tts — B 站 BV 号 → 中文转写 API

轻量本地 HTTP API：传入 B 站 BV 号，自动拉取音频、调用 Qwen ASR 转写成中文文本，
返回 JSON 并把 `.txt` 转写文件保存到配置的输出目录。

> 项目是 **ASR**（语音转文字），目录名 `qwen-tts` 是历史误称。
> 仅单人本地使用：无认证、无队列、同步执行（长视频超时是已知取舍）。

## 快速开始

```bash
# 1. 装依赖（Python 3.10+）
pip install -r requirements.txt

# 2. 配置（config.yaml 不入库，可含敏感信息）
cp config.example.yaml config.yaml
# 按需修改：asr.url / asr.api_key / output_dir / temp_dir / bilibili.cookie

# 3. 启动
python app.py
```

前置条件（`asr.provider: local`）：本地 vLLM 已部署 Qwen 语音模型，
且其 OpenAI 兼容转写端点可达（默认 `http://127.0.0.1:8000/v1/audio/transcriptions`）。
启动前用一条 curl 确认 ASR 在线：

```bash
# vLLM 部署示例（启动命令以实际部署为准）
vllm serve <qwen-语音模型路径> --port 8000
```

## 使用

```bash
curl -X POST localhost:5000/transcribe \
  -H 'Content-Type: application/json' \
  -d '{"bvid":"BV1GJ411x7h7"}'
```

成功（200）：

```json
{
  "bvid": "BV1GJ411x7h7",
  "title": "【官方 MV】Never Gonna Give You Up - Rick Astley",
  "text": "（中文转写文本…）",
  "file_path": "./output/BV1GJ411x7h7_【官方 MV】Never Gonna Give Up - Rick Astley.txt",
  "duration_s": 213
}
```

健康检查：`curl localhost:5000/health` → `{"status":"ok","asr":{"provider":"local"}}`

失败（4xx/5xx，统一 JSON，不是 500 HTML）：

```json
{"error": {"code": "not_found", "message": "B 站接口错误 code=-404 message='啥都木有'"}}
```

| HTTP | code | 含义 |
|---|---|---|
| 400 | `invalid_bvid` | BV 号格式非法 / 请求体缺失 |
| 404 | `not_found` | 视频不存在（匿名不可见的按不存在处理，可配 Cookie） |
| 502 | `fetch_failed` | B 站接口 / 音频下载失败 |
| 502 | `asr_failed` | ASR 调用失败（不可达、非 200、响应无 text 等） |
| 504 | `timeout` | 下载或 ASR 超过配置超时；失败时临时音频保留，message 中含路径 |

转写成功后临时音频（`temp/{bvid}.m4a`）自动删除；失败时保留以便排查。

## 配置项（config.yaml）

| 键 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `asr.provider` | ✅ | — | `local`（本地 vLLM，OpenAI 兼容）或 `remote`（远程 Qwen ASR） |
| `asr.url` | ✅ | — | 完整转写端点 URL（…/v1/audio/transcriptions） |
| `asr.api_key` | remote 必填 | `""` | remote 时作 `Authorization: Bearer <key>` |
| `asr.model` | | `""` | 可选，非空时透传给端点 |
| `asr.language` | | `zh` | 透传给端点 |
| `output_dir` | ✅ | — | 转写 `.txt` 输出目录（启动自动创建） |
| `temp_dir` | ✅ | — | 临时音频目录（启动自动创建） |
| `bilibili.cookie` | | `""` | 可选 B 站登录态；部分视频/音质需登录 |
| `timeout.download_s` | | `300` | BV 号→音频 全流程（view/playurl/下载）超时 |
| `timeout.asr_s` | | `600` | ASR 转写超时 |

改 `asr.provider` 即可在本地 vLLM 与远程 Qwen ASR 间切换，无需改代码。

## 故障排查

| 现象 | 排查 |
|---|---|
| 启动报 `配置文件缺失` | `cp config.example.yaml config.yaml` |
| 启动报 `缺少必填项` / `remote 需要 api_key` | 对照上表补 config.yaml |
| 404 `not_found` | 视频可能需登录态：把 B 站 Cookie 写进 `bilibili.cookie`；或视频已删除/不可见 |
| 502 `fetch_failed` | B 站接口/CDN 异常，重试；持续失败时检查网络与 Cookie |
| 502 `asr_failed` | ASR 服务未启动或 URL 错误；先 `curl` 直连 `asr.url` 验证 |
| 504 `timeout` | 音频太长或 ASR 太慢：调大 `timeout.asr_s`；临时音频已保留（见 message 中路径） |
| 转写文本为空/异常 | 检查模型是否为语音转写模型（ASR，不是 TTS）；`asr.language` 是否为 `zh` |

## 开发与测试

```bash
python -m pytest tests/ -q   # 全 mock，不依赖网络与 ASR
```

- `bili.py` — B 站 view/playurl/下载；`asr.py` — local/remote ASR 客户端
- 接口契约冻结在 `TASKS.md` 顶部"契约总览"，改契约先改文档
