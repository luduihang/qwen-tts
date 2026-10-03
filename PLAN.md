# Plan — v1：BV 号 → 中文转写 API

> Active work plan. One feature/phase at a time. Replace contents when starting a new feature, or fork to `docs/plans/<name>.md` to archive.

## Goal
一条 curl 调用（BV 号进）返回中文转写文本（JSON），同时把 .txt 保存到配置路径 —— 主流程全打通。

## Approach
单 Flask 服务 + 两个薄客户端模块（bili.py / asr.py）+ 一份 config.yaml，同步流水线，无 DB、无队列、无抽象层。ASR 侧用 provider 配置（local/remote）做唯一切换点：local 走 vLLM 的 OpenAI 兼容接口，remote 走远程 Qwen ASR，两者对上层返回同样的文本。选 Flask 而非 FastAPI 是因为同步流程用不上异步，保持依赖最少。

## Phases

1. **骨架与配置** — 项目结构、`config.example.yaml`/`config.yaml`、Flask app 启动、`GET /health`。产出：可运行的空服务，配置是唯一参数来源。
2. **BV 号 → 音频落盘** — bili.py：view 接口取 cid/标题，playurl 取 DASH 音频流 URL（支持可选 Cookie），下载到临时目录。产出：给定 BV 号能在临时目录拿到 m4a。
3. **音频 → 文本（核心链路）** — asr.py：local provider 调 vLLM OpenAI 兼容 `/v1/audio/transcriptions`，remote provider 调远程 Qwen ASR；`POST /transcribe` 串起全链路，返回 JSON 并保存转写文件，成功后清理临时音频。产出：v1 核心目标达成。
4. **健壮性与验收** — 错误处理（BV 不存在 / 拉流失败 / ASR 失败返回 JSON 错误而非 500 HTML）、超时与日志、README（curl 示例 + 配置说明）、端到端验收跑一遍。产出：可交付的 v1。

## Files that will change

| File | Change | Phase |
|---|---|---|
| `app.py` | 新建 — Flask 入口，配置加载，/health 与 /transcribe | 1, 3 |
| `config.example.yaml` | 新建 — 配置样例（提交入库） | 1 |
| `config.yaml` | 新建 — 本地实际配置（gitignore，可含 api_key） | 1 |
| `bili.py` | 新建 — B 站 view/playurl/下载 | 2 |
| `asr.py` | 新建 — local/remote ASR 客户端 | 3 |
| `requirements.txt` | 新建 — flask, requests, pyyaml | 1 |
| `tests/` | 新建 — 配置加载、BV 号校验、文件命名等轻量单测 | 1-4 |
| `README.md` | 新建 — 启动方式、curl 示例、配置说明 | 4 |
| `.gitignore` | 修改 — 增加 config.yaml、输出/临时目录 | 1 |

## Acceptance criteria

- [ ] `python app.py` 启动服务，`curl localhost:5000/health` 返回 200
- [ ] `curl -X POST localhost:5000/transcribe -H 'Content-Type: application/json' -d '{"bvid":"<真实BV号>"}'` 返回 200，JSON 含非空中文 text 与 file_path
- [ ] 转写 .txt 出现在配置的输出目录，文件名含 BV 号
- [ ] 成功转写后临时音频目录为空（自动清理生效）
- [ ] `config.yaml` 中 `asr.provider: local` 改为 `remote` 后无需改代码即可切换
- [ ] 错误场景（非法 BV 号 / 拉流失败 / ASR 不可达）返回 4xx/5xx JSON，不是 500 HTML

## Not in scope

- 前端页面、CLI、桌面客户端
- 批量转写、任务队列、异步任务（v1 同步）
- 多用户、认证、数据库
- CC 字幕回退、多语言优化
- Vercel 或任何远程部署

## Open questions

- 本地 vLLM 服务的地址/端口是多少？验收时需要它在线（给我一个可用地址，或告诉我启动命令）
- 目标视频匿名（无 Cookie）能拉到音频吗？若需要登录态，把 Cookie 写进 config.yaml 即可

## References

- `VISION.md` — 项目定位与领域词汇

## Current step

not started（等待 PLAN/TASKS 批准）

## Notes

- 2026-10-03 规划：ASR 本地服务确认为 vLLM 部署、OpenAI 兼容接口
