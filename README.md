# qwen-tts — B 站 BV 号 → 中文转写 API

轻量本地 HTTP API：传入 B 站 BV 号，自动拉取音频、调用 Qwen ASR 转写成中文文本，
返回 JSON 并把 `.txt` 转写文件保存到配置的输出目录。

> 项目是 **ASR**（语音转文字），目录名 `qwen-tts` 是历史误称。
> 仅单人本地使用：无认证、无队列、同步执行（长视频超时是已知取舍）。

## 快速开始

```bash
# 1. 装依赖（Python 3.10+；另需系统已装 ffmpeg —— ASR 端点只收 wav，m4a 会先本地转码）
pip install -r requirements.txt

# 2. 配置（config.yaml 不入库，可含敏感信息）
cp config.example.yaml config.yaml
# 按需修改：asr.url / asr.api_key / output_dir / temp_dir / bilibili.cookie

# 3. 启动
python app.py
```

前置条件（`asr.provider: local`）：局域网/本地 vLLM 已部署 Qwen 语音模型（Qwen3-ASR），
且其 OpenAI 兼容转写端点可达（默认 `http://192.168.0.190:8001/v1/audio/transcriptions`，见 config.example.yaml）。
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

可选 `output_dir` 指定 .txt 保存目录（服务所在机器上已存在的目录，不自动创建；不指定则用 config 的 `output_dir`）：

```bash
curl -X POST localhost:5000/transcribe \
  -H 'Content-Type: application/json' \
  -d '{"bvid":"BV1GJ411x7h7", "output_dir":"/home/me/subtitles"}'
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
| 400 | `invalid_output_dir` | 请求指定的 `output_dir` 不存在、不是目录或类型错（不自动创建目录） |
| 404 | `not_found` | 视频不存在（匿名不可见的按不存在处理，可配 Cookie） |
| 502 | `fetch_failed` | B 站接口 / 音频下载失败 |
| 502 | `asr_failed` | ASR 调用失败（不可达、非 200、响应无 text 等） |
| 504 | `timeout` | 下载或 ASR 超过配置超时；失败时临时音频保留，message 中含路径 |

> **vLLM Qwen3-ASR 端点已知行为**（2026-10-05 实测，详见 DECISIONS.md / PLAN 环境参考）：
> ① 只接受 wav —— m4a/AAC 会在服务端挂起，asr.py 已自动用 ffmpeg 转码（需系统装 ffmpeg）；
> ② 不要传 `language=zh`（`asr.language` 保持空）—— 端点会重复循环，模型自身能自动检测语言；
> ③ 音频文件大小有上限（`audio_filesize_mb`，上限约 30MB：实测 29MB 过、30MB → 400）—— asr.py 已按 `asr.chunk_seconds`（默认 300s，单段 ≈ 9.6MB）自动 ffmpeg 切段逐段转写拼接，长音频已支持（T-016）。

转写成功后临时音频（`temp/{bvid}_{uuid}.m4a`，per-request 唯一名，并发隔离）自动删除；失败时保留以便排查（路径在错误 message 里）。

## 领域提示词：给转写注入领域术语（进阶）

转写领域音频（如命理学讲座）时，可以给 vLLM 转写端点传一个含术语表的 `prompt`，引导模型对同音词优先选领域规范术语。2026-10-11 实测验证（Qwen3-ASR-1.7B + vLLM 0.30.0，证据在 `spike/`）：

```bash
# 直连 vLLM 端点（与 config.yaml 的 asr.url 同 URL）
curl -X POST http://192.168.0.190:8001/v1/audio/transcriptions \
  -F file=@lecture.wav \
  -F model=Qwen3-ASR-1.7B \
  -F 'prompt=这是一段命理学讲座的转写任务。同音词请优先采用命理学规范术语：八字、四柱、天干、地支、五行、日主、大运、流年、喜用神、正财、偏财、正官、七杀、正印、偏印、食神、伤官、比肩、劫财、纳音、命宫、身宫、桃花、驿马、华盖、空亡、叫应、入墓。'
```

**实测结论**（15s 命理学讲座片段 × 10 次请求，temperature=0，变体内 100% 可复现）：

| 方法 | 效果 |
|---|---|
| `/v1/audio/transcriptions` 加 `prompt` 表单字段 | ✅ **有效**（推荐；返回干净 `{"text"}`） |
| `/v1/chat/completions` 带 `audio_url` 内容块 + system 消息 | ✅ 有效，但原始输出带 `language Chinese<asr_text>` 前缀需自行剥离，不如上面干净 |
| `hot_words` 字段 | ❌ **被静默忽略**（200 但输出与基线逐字相同），不要用 |

**三个注意事项**：

1. **术语表要包含音频里实际会说的词**——提示词是真实的同音选择先验，表里没有的词可能被带偏（实测：表里无"叫应"时输出 `叫硬受伤`，加入后恢复 `叫应受伤`）。
2. **措辞克制**——只给术语表，少加指令性文字（提示词还会影响输出风格，如实测提示词版本会去掉标点）。
3. 本仓库 `/transcribe` 服务当前**不透传** `prompt`（契约未变，`asr.py` 请求形状不变）；需要时可在契约加可选 `prompt` 请求参数透传。

## 配置项（config.yaml）

| 键 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `asr.provider` | ✅ | — | `local`（本地 vLLM，OpenAI 兼容）或 `remote`（远程 Qwen ASR） |
| `asr.url` | ✅ | — | 完整转写端点 URL（…/v1/audio/transcriptions） |
| `asr.api_key` | remote 必填 | `""` | remote 时作 `Authorization: Bearer <key>` |
| `asr.model` | | `""` | 可选，非空时透传给端点 |
| `asr.language` | | `""` | 透传给端点；**保持空**（传 `zh` 会触发端点循环，模型自身能自动检测语言） |
| `asr.temperature` | | `0.0` | 透传给端点 |
| `asr.chunk_seconds` | | `300` | 长音频切段长度（秒）；省略/0 = 默认 300。端点文件上限约 30MB，单段 16k wav ≈ 9.6MB 留足余量 |
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
| 502 `asr_failed` | ASR 服务未启动或 URL 错误；先 `curl` 直连 `asr.url` 验证。若 message 含 `Maximum file size exceeded`：单段仍超限，调小 `asr.chunk_seconds`（长音频默认已自动切段，一般不会再遇到） |
| 504 `timeout` | 音频太长或 ASR 太慢：调大 `timeout.asr_s`；临时音频已保留（见 message 中路径） |
| 500 `internal` | 未预期异常（堆栈在服务端日志）；先重试，持续出现报 issue |
| 转写文本重复循环 | ① 检查 `asr.language` 是否为空（传 `zh` 会触发端点循环，见端点行为②）；② 纯音乐/无语音内容上模型也会自循环（模型限制，语音内容不受影响） |
| 转写文本为空/异常 | 检查模型是否为语音转写模型（ASR，不是 TTS） |

## 开发与测试

```bash
python -m pytest tests/ -q   # 全 mock，不依赖网络与 ASR
```

- `bili.py` — B 站 view/playurl/下载；`asr.py` — local/remote ASR 客户端
- 接口契约冻结在 `TASKS.md` 顶部"契约总览"，改契约先改文档
