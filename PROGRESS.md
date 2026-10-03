# Progress — qwen-tts

> Rolling session summaries. Newest first. Loaded at session start so the next session knows where work left off.
> Each entry is 2-3 sentences. Older entries get pruned/consolidated when this file exceeds ~100 entries or ~8k chars.


<!-- session-in-progress:start=2026-10-03T08:19:48.192Z -->
## 2026-10-03 16:48 — ## 状态汇总

**✅ 规划文档全部完成并验证**（已提交 `9c7f44d`）：
- `VISION.md` — 项目定位 + 领域词汇表（含 "Avoid... _(in progress)_
## 状态汇总

**✅ 规划文档全部完成并验证**（已提交 `9c7f44d`）：
- `VISION.md` — 项目定位 + 领域词汇表（含 "Avoided terms: 不叫 TTS"）
- `PLAN.md` — v1 四阶段：骨架 → BV号→音频 → 音频→文本 → 健壮性验收
- `TASKS.md` — Phase 1 四个任务（T-001~T-004），每个带 Done when
- `PROGRESS.md` — 已记第一条（scaffold 完成）
- `DECISIONS.md` — ADR 空模板（技术栈决策的正式条目将在实现时记录）

**✅ 本地 git**：已提交初始 scaffold commit。`.gitignore` 预先加上了 `config.yaml`（可能含 api_key，不入库）、`output/`、`temp/`。

**⛔ GitHub 仓库：卡住** —— `gh` 已装好（brew，v2.102.0）但未认证，git 凭据里也没有 GitHub token。需要你做一步（二选一）：

1. 在你的终端跑 `gh aut...
<!-- end-session-in-progress -->
## Format

```
## YYYY-MM-DD HH:MM — <one-line summary>
<2-3 sentences: what was done, what was verified, what's next>
```

## Entries

<!-- newest first -->

## 2026-10-03 16:41 — scaffold：规划文档齐备，GitHub 仓库已建
Scaffold 流程完成：VISION/PLAN/TASKS 经用户批准并写入（均读回验证），PROGRESS/DECISIONS 模板就位。关键确认：本地 ASR 为 vLLM 部署、OpenAI 兼容接口；部署形态为本地进程，不上 Vercel。GitHub 仓库 https://github.com/luduihang/qwen-tts （public）已创建并 push 初始 commit。下一步：T-001 开始 Phase 1 实现。
