# Vision — B 站 BV 号 → 中文转写 API（qwen-tts）

> Loaded at session start. The agent uses this to ground every decision in *what the app is supposed to be*.
> Update when the answer to "what is this app" actually changes — not for every new feature.

## What this app is
轻量本地 HTTP API 服务：传入 B 站 BV 号，自动拉取音频、调用本地 Qwen ASR 服务转写成中文文本，API 返回并保存转写文件到配置路径。

## Who it's for
仅我自己（个人视频转写），无外部用户。

## What problem it solves
把 B 站视频转成文字目前要手动下载音频、手动跑 ASR、手动管理文本文件，链路繁琐。希望一次 API 调用（BV 号进）直接拿到中文文本。

## How a user gets value
`POST /transcribe`，body `{"bvid": "BV1xx411c7mD"}`，同步等待后返回 JSON：
`{ "bvid", "title", "text", "file_path", "duration_s" }`

主流程（单次请求内顺序执行）：
1. BV 号 → B 站 playurl API → 取 DASH 音频流 URL（m4a）
2. 下载音频到配置的临时目录
3. 调用 ASR 服务（本地 vLLM 部署的 Qwen 模型优先，配置文件可切远程 Qwen ASR）
4. 返回文本 + 保存转写文件（`.txt` 到输出目录，BV 号 + 标题命名）
5. 成功后自动删除临时音频（失败时保留以便排查，可配置）

## What it's not
- 不是前端页面 / CLI 工具 / 桌面客户端 —— 只出 API 接口
- 不是多用户服务 —— 无认证、无账号、单用户本地运行
- 不是批处理系统 —— 无批量转写、无任务队列；v1 同步执行，长视频超时是已知取舍
- 不做 CC 字幕回退、不做多语言优化 —— 走音频 ASR，中文为主
- 不部署 Vercel —— 依赖本地 ASR 服务，部署形态是本地进程

## Success looks like
- 一条 `curl -X POST /transcribe -d '{"bvid":"<真实BV号>"}'` 返回 200，JSON 含非空中文文本
- 转写 `.txt` 出现在配置的输出目录，临时音频目录在成功后为空
- 改 `config.yaml` 的 `asr.provider` 即可在本地 vLLM 与远程 Qwen ASR 之间切换，无需改代码

## Current phase
v0 —— 规划完成（VISION/PLAN/TASKS 就绪），Phase 1 未开始。

## Architecture

**Components:**
- `app.py` — Flask 入口，`/health` 与 `/transcribe` 路由
- `bili.py` — B 站客户端：view 取 cid/标题，playurl 取音频流 URL，下载到临时目录
- `asr.py` — ASR 客户端：按配置调用本地 vLLM（OpenAI 兼容 `/v1/audio/transcriptions`）或远程 Qwen ASR
- `config.yaml` — 全部核心参数（ASR provider/地址、输出目录、临时目录、可选 Cookie、超时）
- 转写文件 — `.txt` 产物，写入输出目录

**Data flow:** `HTTP POST /transcribe → bili（BV号→cid→音频流URL→m4a 落盘）→ asr（m4a→中文文本）→ 返回 JSON + 保存 .txt + 清理临时音频`

**Key tech choices:**
- Python 3 + Flask + requests + pyyaml（轻量依赖，无 DB、无 ORM、无队列）
- 本地 ASR：vLLM 部署的 Qwen 语音模型，OpenAI 兼容接口
- 同步流水线：单请求内完成全链路，无后台任务

## Constraints worth knowing
- 运行在本地机器：需可达本地 vLLM 服务与 B 站网络
- 中文识别为主
- 轻量：不引入复杂架构和冗余依赖
- 临时音频转写成功后自动清理，减少磁盘占用
- 所有核心参数走配置文件，不散落在代码里

## Domain glossary
> Use these terms exactly. Avoid synonyms or paraphrasing in code, comments, UI, docs, or chat.

| Term | Definition |
|---|---|
| BV 号 | B 站视频 ID（如 BV1GJ411x7h7），API 唯一必需输入 |
| playurl API | B 站 `x/player/playurl` 接口，返回视频可播放流地址；本项目只取 DASH 音频流 |
| 音频流 URL | playurl 返回的 m4a 音频地址，有时效，需每次现取 |
| ASR 服务 | 接收音频返回中文文本的 HTTP 端点；`local` = 本地 vLLM 部署的 Qwen 语音模型（OpenAI 兼容接口），`remote` = 远程 Qwen ASR 接口 |
| 转写文件 | 保存的 `.txt` 结果，按 BV 号（+标题）命名，位于输出目录 |
| 临时音频 | 下载的音频文件，转写成功后自动删除 |
| Cookie | 可选的 B 站登录态；部分视频/音质需要登录，写入配置文件 |

**Avoided terms:** 不叫 "TTS" —— 本项目是 ASR（语音转文字），目录名 `qwen-tts` 是历史误称；不说 "下载视频" —— 拉取的是音频流（m4a），不涉及视频画面。
