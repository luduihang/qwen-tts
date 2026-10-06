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

## Work packages（并行）

v1 任务图支持并行执行（详见 TASKS.md 的 Owns/Contract 字段）：

```
Phase 1（串行，地基）: T-001 → T-004                 [main]
      │
      ├── 工作包 A: T-005 bili.py + T-006 其测试      [独立分支]
      └── 工作包 B: T-007 asr.py + T-008 其测试       [独立分支]   ← A ∥ B
      │
Phase 3b（串行整合）: T-009 管线 + T-010 管线测试
Phase 4（串行）: T-011 健壮性, T-012 README, T-013 端到端验收
```

规则：
- A/B 用 `git worktree` 各占一个分支，物理隔离；merge 顺序 A → B → main
- 并行窗口内零共享文件（由 `Owns:` 保证）
- 接口契约冻结在 TASKS.md“契约总览”，改动须先改契约
- 整合验收门：`pytest tests/ -q` 全绿 + curl 验收（见 Acceptance criteria）
- 每任务一个 commit，格式 `T-00N: <摘要>`

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

- [x] `python app.py` 启动服务，`curl localhost:5000/health` 返回 200
- [x] `curl -X POST localhost:5000/transcribe -H 'Content-Type: application/json' -d '{"bvid":"<真实BV号>"}'` 返回 200，JSON 含非空中文 text 与 file_path（真实 vLLM 验证：BV1dPaZ6qEhd 298s 中文视频，2122 字符，11.4s，2026-10-05）
- [x] 转写 .txt 出现在配置的输出目录，文件名含 BV 号
- [x] 成功转写后临时音频目录为空（自动清理生效）
- [x] `config.yaml` 中 `asr.provider: local` 改为 `remote` 后无需改代码即可切换（e2e 验证 Bearer 送达）
- [x] 错误场景（非法 BV 号 / 拉流失败 / ASR 不可达）返回 4xx/5xx JSON，不是 500 HTML（400/404/502/504 单测 + 504 手动实测）

## Not in scope

- 前端页面、CLI、桌面客户端
- 批量转写、任务队列、异步任务（v1 同步）
- 多用户、认证、数据库
- CC 字幕回退、多语言优化
- Vercel 或任何远程部署

## Open questions

- 本地 vLLM 服务的地址/端口是多少？验收时需要它在线（给我一个可用地址，或告诉我启动命令）
- 目标视频匿名（无 Cookie）能拉到音频吗？若需要登录态，把 Cookie 写进 config.yaml 即可

## 环境参考 — 真实 vLLM ASR 部署（2026-10-05，用户强调重要）

- **端点**：`http://192.168.0.190:8001/v1/audio/transcriptions`（局域网；客户端机器 192.168.0.12；宿主机为 A100×2 Docker guest，80GB 显卡，主机用户 fuzadw）
- **模型**：`/mnt/docker-data/hf-models/Qwen3-ASR-1.7B`，served-model-name `Qwen3-ASR-1.7B`（max_model_len 32768）
- **宿主机启动脚本** `~/llm_home/llm_script/qwen3-asr-1.7b.sh`（带推测解码加速说明；先 unset 全部代理变量，conda 环境 `cu130`）：
  ```bash
  CUDA_VISIBLE_DEVICES=1 \
  HF_HUB_OFFLINE=1 \
  PYTORCH_ALLOC_CONF=expandable_segments:True \
  vllm serve /mnt/docker-data/hf-models/Qwen3-ASR-1.7B \
    --served-model-name Qwen3-ASR-1.7B \
    --host 0.0.0.0 --port 8001 \
    --dtype bfloat16 \
    --max-model-len 32768 \
    --gpu-memory-utilization 0.6 \
    --max-num-seqs 16 \
    --max-num-batched-tokens 32768 \
    --enable-chunked-prefill
  ```
- **已知端点行为（实测，T-014 期间）**：
  1. **m4a/AAC 输入挂起**（>150s 无响应；wav 正常）→ 客户端已用 ffmpeg 转码规避（asr.py）
  2. **传 `language=zh` 会重复循环**（145K 字符循环副歌；不传则模型自动检测语言，中英文均正常）→ 客户端默认不发送 language
  3. **音频文件大小上限**（参数 `audio_filesize_mb`，上限约 30MB）：29MB wav 可过、30MB（29.999MiB）→ 400（2026-10-05 探明；⚠️ 过大小检查的文件会触发真实转写占 GPU——探上限曾把队列堵约 30 分钟）。客户端已规避：T-016 按 `chunk_seconds`（默认 300s ≈ 9.6MB/段）切段
- **吞吐参考**（服务端日志）：生成约 49~67 tokens/s；213s 音频 8.9s 转完（1898 字符）

## References

- `VISION.md` — 项目定位与领域词汇

## Current step

**v1 全部收官**（2026-10-05）：T-013 验收 6/6 → T-016 长音频切段（34 分钟视频 ×2 真实成功）→ T-017 并发 500 修复（uuid temp 命名 + 500 JSON）→ T-018 `output_dir` 请求参数（按请求指定 .txt 保存目录，默认 config，目录不存在 400），72 条测试全绿。无剩余任务；如继续，按 Not in scope 里的方向（批量/队列/多用户 409 等）开新 feature 走 plan-then-implement。

## Notes

- 2026-10-03 规划：ASR 本地服务确认为 vLLM 部署、OpenAI 兼容接口
- 2026-10-03 计划调整：TASKS 全 phase 预填 + 接口契约冻结 + 文件所有权（Owns），支持 A∥B 并行（git worktree，merge 顺序 A→B→main）
