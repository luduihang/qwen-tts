# Progress — qwen-tts

> Rolling session summaries. Newest first. Loaded at session start so the next session knows where work left off.
> Each entry is 2-3 sentences. Older entries get pruned/consolidated when this file exceeds ~100 entries or ~8k chars.



<!-- session-in-progress:start=2026-10-03T12:47:24.477Z -->
## 2026-10-03 21:17 — 真相大白：harness 在我 session 开始时（20:50:24）自动创建了 commit `47a9278 "--help"`，将 `.agent/`... _(in progress)_
真相大白：harness 在我 session 开始时（20:50:24）自动创建了 commit `47a9278 "--help"`，将 `.agent/` 的遥测数据和被重写的 PROGRESS.md 提交到了 main（所以 main 的分支指针在我第一次 commit 之前就已经移动了）。由于这是一个"pi memory lab" 实验仓库，`.agent/` 的跟踪是有意为之的，我不会去动它（也不会去重写已经公开的历史记录），只是提醒一下用户。

收尾工作：更新 TASKS/PLAN/PROGRESS 并 push：
<!-- end-session-in-progress -->
## 2026-10-03 21:12 — I found that the previous pkill command matched itself and got blocked (my shell...
I found that the previous pkill command matched itself and got blocked (my shell's command line contained the literal pattern), but fortunately the configuration wasn't modified and all processes are stopped. I'll retry using explicit PID management instead.
## Entries

<!-- newest first -->

## 2026-10-03 21:35 — session3 完成：v1 代码全部实现并合并（T-001~T-012），仅剩 T-013 待 vLLM
按执行路径走完：Phase 1（main）→ worktree A/B 并行（A∥B 物理隔离、零共享文件、契约冻结生效，merge 顺序 A→B→main，均已合入并清理 worktree）→ 整合 T-009/010 → T-011/012。52 条单测全绿；验证：真实拉取 2 个 BV（匿名、无需 Cookie）、stub ASR 全链路 e2e（200 + .txt 落盘 + temp 自动清空）、黑洞 IP 实测 504 JSON（3.5s 不挂死）、config 切 remote 零代码改动 Bearer 送达。踩坑：Flask 2.2.5 测试需持有 app 引用（JSON provider 弱引用）；mock 不消费 multipart 文件句柄；pkill -f 会误杀包含同模式字符串的自身 shell。T-013 blocked：8000 无 vLLM 服务、HF 缓存无 Qwen ASR 模型（有 vllm 0.30.0 可拉起，缺模型）。另注意：harness 在 session 开始时自动 commit 了 47a9278（.agent/ 遥测 + PROGRESS 重写）进 main 并随 push 上库——"pi memory lab" 似为有意设计，未动。

## 2026-10-03 21:20 — session3：Phase 1 完成（T-001~T-004），main 可运行
Phase 1 在 main 串行完成并逐任务 commit：T-001 requirements.txt（Flask/requests/PyYAML 锁定版本）+ .gitignore 补齐；T-002 config.example.yaml（契约唯一事实来源）+ app.py 配置加载校验（缺文件/缺必填项/remote 缺 api_key 均报清晰错误退出）；T-003 /health 返回 200 含 asr.provider，启动自动建 output/temp 目录（已 curl 实测）；T-004 单测 13 条全绿。踩坑记录：Flask 2.2.5 测试中 app 被 GC 后 get_json() 触发 weakref ReferenceError，需持有 app 引用。

## 2026-10-03 20:33 — TASKS 全 phase 预填 + PLAN 并行工作包（`e94bce1`）
TASKS.md 13 个任务全预填，顶部"契约总览"冻结接口（config schema / `bili.get_audio` / `asr.transcribe` / 错误映射 / 命名规则），每个任务带 `Owns:` + `Done when`；PLAN.md 新增 Work packages 节：A ∥ B 分解、worktree 规则、merge 顺序 A→B→main、验收门。执行路径：① Phase 1 串行 main → ② A ∥ B 两 worktree → ③ 整合 T-009/010 → ④ 健壮性+验收 T-011~013（需 vLLM 在线）。

## 2026-10-03 16:41 — scaffold：规划文档齐备，GitHub 仓库已建
Scaffold 流程完成：VISION/PLAN/TASKS 经用户批准并写入（均读回验证），PROGRESS/DECISIONS 模板就位。关键确认：本地 ASR 为 vLLM 部署、OpenAI 兼容接口；部署形态为本地进程，不上 Vercel（scaffold 流程的有意偏离，已在 VISION 记录）。GitHub 仓库 https://github.com/luduihang/qwen-tts （public）已创建并 push 初始 commit。

## Format

```
## YYYY-MM-DD HH:MM — <one-line summary>
<2-3 sentences: what was done, what was verified, what's next>
```
