# Progress — qwen-tts

> Rolling session summaries. Newest first. Loaded at session start so the next session knows where work left off.
> Each entry is 2-3 sentences. Older entries get pruned/consolidated when this file exceeds ~100 entries or ~8k chars.

## Entries

<!-- newest first -->

## 2026-10-05 17:15 — 真实 vLLM 接入完成（T-014/015），T-013 验收 5/6；⬅️ 交接：剩中文长视频一项

**本 session 完成**（全部已 merge 进 main @ `e3e0279` 并 push，worktree/分支已清理，58 条测试全绿）：
- **T-014/T-015**：asr.py 接入真实 vLLM（192.168.0.190:8001，Qwen3-ASR-1.7B）。实测发现并修复两个端点坑：① **m4a 输入会让端点挂起**（>150s 无响应）→ asr.py 对非 wav 输入先用本地 ffmpeg 转 16k 单声道 wav（临时 `{名}.asr.wav`，发后删除）；② **传 `language=zh` 会重复循环**（输出 145K 字符的循环副歌）→ 契约改：language 默认空=不发送，模型自动检测语言（中文视频也出中文）；另按用户原样接入 `temperature` 透传。
- **T-013 端到端验收（in progress，5/6）**：✅ /health 200；✅ BV1GJ411x7h7（213s 英文歌）真实 e2e：200 + 完整歌词 1898 字符 + .txt 落盘（`output/BV1GJ411x7h7_【官方 MV】Never Gonna Give You Up - Rick As.txt`）+ temp 自动清空，9.8s 含转码；❌ **34 分钟视频 BV1xx411c7mD**：502 asr_failed ← 端点 400 `Maximum file size exceeded (audio_filesize_mb=63.22)` —— 2055s 的 16k wav 有 63.2MB 超限（6.8MB 的 213s 能过，具体上限未知，6.8~63.2MB 之间）。
- **现场保留**：`temp/BV1xx411c7mD.m4a`（17.6MB，失败按契约保留，T-016 开发可直接复用，勿删）；config.yaml 已指向真实 vLLM（本地文件，gitignored）。

**接手步骤（新 session）**：
1. **完成 T-013 最后一步（最快路径）**：找一个**短中文视频（≤6 分钟**，wav 约 ≤12MB 避开文件上限）跑 `python app.py` + `POST /transcribe` → 确认非空中文 text → T-013 Done、PLAN 验收第 2 项勾选。
2. **T-016（新任务，Active）**：长音频支持（audio_filesize_mb 超限）。候选方案见 TASKS.md（推荐分段转写拼接）。修完用 34 分钟视频复验。
3. vLLM 部署详情与启动参数在 **PLAN.md「环境参考」** 节（用户特别强调重要，勿删）。
4. 端点三坑（m4a 挂起 / language=zh 循环 / 文件大小上限）已写入 README 故障排查 + config 注释 + 契约转码约定。

## 2026-10-03 21:35 — session3 完成：v1 代码全部实现并合并（T-001~T-012），仅剩 T-013 待 vLLM
按执行路径走完：Phase 1（main）→ worktree A/B 并行（A∥B 物理隔离、零共享文件、契约冻结生效，merge 顺序 A→B→main，均已合入并清理）→ 整合 T-009/010 → T-011/012。52 条单测全绿；验证：真实拉取 2 个 BV（匿名、无需 Cookie）、stub ASR 全链路 e2e、黑洞 IP 实测 504 JSON（3.5s 不挂死）、config 切 remote 零代码改动 Bearer 送达。踩坑：Flask 2.2.5 测试需持有 app 引用（JSON provider 弱引用）；mock 不消费 multipart 文件句柄；pkill -f 会误杀包含同模式字符串的自身 shell（用显式 PID）。另注意：harness 会在 session 边界自动 commit `.agent/` 遥测进 main（47a9278）——"pi memory lab" 有意设计，勿动。

## 2026-10-03 21:20 — session3：Phase 1 完成（T-001~T-004），main 可运行
Phase 1 在 main 串行完成并逐任务 commit：T-001 requirements.txt（Flask/requests/PyYAML 锁定版本）+ .gitignore 补齐；T-002 config.example.yaml（契约唯一事实来源）+ app.py 配置加载校验（缺文件/缺必填项/remote 缺 api_key 均报清晰错误退出）；T-003 /health 返回 200 含 asr.provider，启动自动建 output/temp 目录（已 curl 实测）；T-004 单测 13 条全绿。

## 2026-10-03 20:33 — TASKS 全 phase 预填 + PLAN 并行工作包（`e94bce1`）
TASKS.md 13 个任务全预填，顶部"契约总览"冻结接口（config schema / `bili.get_audio` / `asr.transcribe` / 错误映射 / 命名规则），每个任务带 `Owns:` + `Done when`；PLAN.md 新增 Work packages 节：A ∥ B 分解、worktree 规则、merge 顺序 A→B→main、验收门。

## 2026-10-03 16:41 — scaffold：规划文档齐备，GitHub 仓库已建
Scaffold 流程完成：VISION/PLAN/TASKS 经用户批准并写入，PROGRESS/DECISIONS 模板就位。关键确认：本地 ASR 为 vLLM 部署、OpenAI 兼容接口；部署形态为本地进程，不上 Vercel。GitHub 仓库 https://github.com/luduihang/qwen-tts （public）已创建并 push 初始 commit。

## Format

```
## YYYY-MM-DD HH:MM — <one-line summary>
<2-3 sentences: what was done, what was verified, what's next>
```
