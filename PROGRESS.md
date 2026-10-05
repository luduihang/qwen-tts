# Progress — qwen-tts

> Rolling session summaries. Newest first. Loaded at session start so the next session knows where work left off.
> Each entry is 2-3 sentences. Older entries get pruned/consolidated when this file exceeds ~100 entries or ~8k chars.



<!-- session-in-progress:start=2026-10-05T09:26:45.895Z -->
## 2026-10-05 19:01 — 你贴的日志（Running: 0, Waiting: 0, KV 0%）正好佐证了：18:52 时服务端是干净的，慢不是队列问题，是**单请求内模型循环生成**... _(in progress)_
你贴的日志（Running: 0, Waiting: 0, KV 0%）正好佐证了：18:52 时服务端是干净的，慢不是队列问题，是**单请求内模型循环生成**烧时间。

## 分段必要性分析（结论：必要，不是可选项）

| 论据 | 证据 |
|---|---|
| **① 硬上限，无客户端解法** | 端点 `audio_filesize_mb` 上限 ≈30MB（实测 29MB 过 / 30MB 秒 400）。16k mono wav = 32KB/s → **单次请求理论极限 ≈16 分钟音频**；你的 34 分钟 = 63.2MB，不切必然 400。替代方案都出局：8k mono 降到 31.6MB 仍超限；调服务端参数要动宿主机 |
| **② token 预算保护** | `max-model-len 32768`。单发长音频输出 token 不可控，撞顶会**静默截断**（拿到半份文本还以为是全的）；分段后单段输出有界（300s 语音段约 10-15s 生成完，最坏撞顶也就 ~9 分钟有界） |
| **③ 失败隔离** | 单发 34 分钟若在第四十分钟挂掉（超...
<!-- end-session-in-progress -->
## 2026-10-05 17:26 — ## ✅ 交接落盘完成，可以安全开新窗口

**现场**：main @ `2a62df0` 已 push，工作树干净，服务已停，58 条测试全绿。保留物：`te...
## ✅ 交接落盘完成，可以安全开新窗口

**现场**：main @ `2a62df0` 已 push，工作树干净，服务已停，58 条测试全绿。保留物：`temp/BV1xx411c7mD.m4a`（17.6MB，T-016 可复用，**勿删**）、`output/` 里的验收产物。

### 本轮成果（已合入 main）
| 任务 | 内容 |
|---|---|
| **T-014/015** | asr.py 接入真实 vLLM：`temperature` 透传（你的原样）、**m4a→16k wav 自动转码**、**language 默认不发送**；+5 条测试（58 全绿） |
| **T-013 验收** | 5/6 通过：/health ✅、213s 视频全链路 ✅（200 + 完整歌词 1898 字符 + .txt + temp 清空，9.8s 含转码）；**34 分钟视频 ❌** |

### 实测发现的端点三坑（都已落文档 + 记忆）
1. **m4a 输入服务端挂起**（>150s 无响应）→ 已用 ffmpeg 转码规避
2. **传 `languag...
## Entries

<!-- newest first -->

## 2026-10-05 19:05 — T-016 长音频切段收官 + T-017 并发 500 修复；v1 无剩余任务
**T-016 完成**：切段实现（asr.chunk_seconds 默认 300s，ffmpeg segment 流拷贝，逐段按序拼接，finally 统一清理段/转码临时文件）+ 7 条新测试；真实 e2e 34 分钟视频 BV1xx411c7mD ×2 全成功（1793.8s / 1579.0s，均 200 + 587KB .txt + temp 清空）。上限探明约 30MB（29MB 过 / 30MB 400）落 PLAN/README/契约。
**34 分钟视频为何要 ~26 分钟（非 bug）**：该视频是音乐合集，模型在纯器乐段循环生成直到撞 max-model-len 32768（每段 ~9 分钟），人声段 ~10s；循环输出属模型质量限制（README 故障排查已记）。用户 vLLM 服务端日志确认 18:52 队列干净（Running 0 / KV 0%），慢在单请求内生成。
**T-017 完成**：同 BV 并发转写撞 temp 文件名 → 一方清理后另一方 FileNotFoundError → 500 HTML。修复 = 管线 temp 用 `{bvid}_{uuid8}.m4a`（get_audio 新增可选 dest_path，.asr.wav/chunk 由 stem 派生自动隔离）+ 路由 generic Exception → 500 JSON（code=internal，堆栈进日志）；+3 测试，68 全绿；真实并发验证：同 BV 两请求均 200（16.3s/22.9s）且 temp 无残留。
**我的失误（教训已入记忆库）**：探大小上限时发了 4 个共约 30 分钟音频的静音 wav——小于上限的文件会触发真实转写，把远端 GPU 队列堵了约 30 分钟，拖长第一次 e2e。教训：探上限只发超限文件（400 立即返回，不占 GPU）。
**现场**：main 已 push（2 commits：T-016 代码、T-017 代码+全部文档），服务已停，68 条测试全绿，端点正常；T-013/T-016/T-017 全部核销，v1 无剩余任务。保留物：output/ 里 3 份验收产物（含 34 分钟视频 587KB 转写）。

## 2026-10-05 17:30 — T-013 端到端验收完成（6/6），v1 收官；下一步 T-016
**T-013 收官**：最后一项"非空中文 text"一次通过——从首页热门榜选 BV1dPaZ6qEhd（298s 中文军事评论）POST /transcribe → 200（11.4s），2122 字符连贯中文 + `output/BV1dPaZ6qEhd_老外：这个中国机枪手….txt` 落盘 + temp 自动清空（仅剩 T-016 保留物 `BV1xx411c7mD.m4a`）。PLAN.md 验收 6 项全部勾选，T-013 → Done。
**现场**：main 已 push（docs-only commit，无代码改动，58 条测试保持全绿）；服务已停；config.yaml 仍指向真实 vLLM（192.168.0.190:8001，/health 在线）。
**下一步**：T-016 长音频支持——推荐方案 a：ffmpeg 切 ~5 分钟段逐段转写后拼接 text；直接用保留的 m4a（2055s/17.6MB）开发，修完用同一视频复验 200 + 完整文本。

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
