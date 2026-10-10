# Decisions — qwen-tts

> Architecture Decision Record (ADR-lite). Freezes decisions with context,
> alternatives, and tradeoffs. No ceremony — just enough to answer "why did
> we do this?" six months later.
>
> Add new decisions at the top. Mark superseded decisions with a status update
> and a pointer to the replacement. Never delete old entries.

---

## Template

```
## YYYY-MM-DD — <Decision title>

**Status:** Proposed | Accepted | Deprecated | Superseded by <link>

**Context:** What drove this decision? What was the situation, constraint, or
problem that required a choice?

**Decision:** What did we choose? Be specific — name the technology, pattern, or
approach.

**Alternatives considered:**
- **<Alternative A>:** <Why we rejected it>
- **<Alternative B>:** <Why we rejected it>

**Tradeoffs:**
- **Gain:** <What this decision gives us>
- **Cost/Risk:** <What this decision costs us or risks>
```

---

<!-- 新决策加在上方、模板下方。示例条目在首次真实决策时替换。 -->
## 2026-10-11 — T-019 领域提示词透传：/transcribe 加可选 `prompt` 请求参数（空 = no-op，切段每段都带）

**Status:** Accepted

**Context:** Spike（证据 `spike/`）确认 Qwen3-ASR vLLM 端点的 `prompt` 字段真实影响同音词选择，但用户需要多人可用：转写垂直领域（如命理学）音频时，经服务 /transcribe 也要能按请求注入领域术语，而不只是直连端点。

**Decision:** `/transcribe` 加可选 `prompt` 请求参数（契约：TASKS.md T-019）：省略/`null`/空串 = 无提示词（请求 form 形状不变，对不支持该字段的端点安全）；非空字符串 = 以 form 字段 `prompt` 随每个请求发送（长音频时每个段都带同一 prompt）；非字符串类型 → 400 `invalid_prompt`（不进下载/转写）。`asr.transcribe(audio_path, cfg, prompt=None)`：asr 层对非字符串静默忽略（类型校验在路由层）。

**Alternatives considered:**
- **config.yaml 加 asr.prompt：** 拒绝——prompt 是情境性的（不同音频不同术语），应是请求参数而非全局配置；服务供多人调用
- **空串 → 400（对齐 output_dir 语义）：** 拒绝——对"提示"字段，空 = 无提示是自然 no-op，对调用方更友好；只有类型错才 400
- **`hot_words` 透传：** 拒绝——端点实测静默忽略，零效果（2026-10-11 spike）

**Tradeoffs:**
- **Gain:** 调用方零改造即可注入领域术语（JSON 加一个字段）；不传参数时与旧请求 100% 兼容
- **Cost/Risk:** 不支持 `prompt` 字段的端点可能拒绝未知字段（当前 Qwen3-ASR vLLM 已验证接受；remote provider 需先验证）；prompt 质量决定效果——术语表必须含实际所言之词，否则带偏（见 README 领域提示词节）



## 2026-10-11 — 领域提示词注入：transcriptions `prompt` 字段为推荐路径（spike 实测）

**Status:** Accepted

**Context:** 用户需要转写命理学领域音频时注入领域术语提示词，让模型对同音词有所侧重（提高术语准确性）。需确认现有 vLLM 端点（不改启动脚本）能否接受 prompt/热词并真实影响输出。

**Decision:** 经 spike 实测（15s 命理学讲座片段 × 10 次请求，temperature=0，变体内 100% 可复现，证据 `spike/`）：① 推荐路径 = `/v1/audio/transcriptions` 的 `prompt` 表单字段（vLLM 0.30.0 接受并真实改变输出，返回干净 `{"text"}`）；② `/v1/chat/completions` 的 system 消息同样有效但输出带 `language Chinese<asr_text>` 前缀，不作推荐；③ `hot_words` 字段被静默忽略，禁用。用法与三条注意事项（术语表须含实际所言之词、措辞克制、/transcribe 服务暂不透传）写入 README「领域提示词」节 + PLAN 环境参考第 4 条。

**Alternatives considered:**
- **改 vLLM 启动脚本/换模型：** 无需——`prompt` 是请求时字段，启动参数一字不动
- **chat 端点 + system 消息：** 同样有效但响应需剥离前缀，集成成本高于 transcriptions
- **`hot_words` 字段：** 实测被静默忽略（200 但输出不变），无效果

**Tradeoffs:**
- **Gain:** 不改代码、不改部署即可注入领域先验；实测术语表含实际所言之词时同音纠正生效（叫应 2/2 稳定）
- **Cost/Risk:** 提示词是双向的——术语表缺词会把模型带偏（实测 叫应→叫硬）；提示词还会改变输出风格（去标点）；本仓库 /transcribe 契约未变，透传 prompt 需后续单独改契约

## 2026-10-05 — ASR 请求形状修正：m4a→wav 转码 + language 默认不发送 + temperature 透传

**Status:** Accepted

**Context:** 接入真实 vLLM 部署（192.168.0.190:8001，Qwen3-ASR-1.7B）时实测发现两个端点坑：① m4a/AAC 输入会在服务端挂起（>150s 无响应，重试稳定复现），同内容 wav 8.9s 完成；② 请求带 `language=zh` 时模型进入重复循环（145,659 字符循环副歌，两次复现），不传 language 则正常且模型能自动检测语言（英文歌出英文、中文内容出中文）。此外用户的原始调用脚本带 `temperature: 0.0`，契约原未覆盖。

**Decision:** ① `asr.transcribe` 对非 wav 输入先用本地 ffmpeg 转 16k 单声道 wav（临时 `{音频名}.asr.wav`，发送后删除；ffmpeg 缺失/转码失败抛 AsrError）；② `language` 改为可选，默认空 = 不进 form（契约 + config.example + app.py DEFAULTS 同步）；③ `temperature` 可配置默认 0.0，透传给端点。ffmpeg 成为系统级依赖（已写入 README）。

**Alternatives considered:**
- **直传 m4a：** 端点挂起，不可用
- **保持 language=zh 强制：** 循环输出，不可用；中文识别靠模型自动检测已验证可行

**Tradeoffs:**
- **Gain:** 真实端点 213s 视频 9.8s（含转码）出完整歌词；中文视频不传 language 也出中文；契约与实际部署行为一致
- **Cost/Risk:** 多一个系统依赖 ffmpeg；转码临时文件占用短暂磁盘（已自动清理）；端点行为是 vLLM 部署侧的怪癖，换模型/升级版本可能变化（复现条件已记 PLAN 环境参考）

## 2026-10-03 — 超时单独成错码 timeout → 504 JSON

**Status:** Accepted

**Context:** v1 是同步流水线（单请求内 BV 号→音频→转写），长音频 + 不稳定网络时单个请求可能长时间无响应。原契约只定义了 400/404/502，超时行为未定义；若把超时折叠进 fetch_failed/asr_failed（502），客户端无法区分"上游失败"与"太慢"，重试策略没法定。

**Decision:** 下载与 ASR 的超时（requests.Timeout）在 bili.py/asr.py 内先于其他异常捕获，单独错码 `timeout`，映射 504 JSON `{"error":{"code":"timeout","message":...}}`。为此契约扩展：`BiliError.code` 集合加入 `timeout`；`AsrError` 增加可选属性 `code`（默认 `asr_failed`，超时为 `timeout`）。日志每请求输出 bvid/结果/耗时（stdout，print flush）。

**Alternatives considered:**
- **折叠进 502：** 实现最简，但客户端无法区分慢与坏，且 504 语义更准
- **不处理、靠 TCP 层超时：** 响应可能拖到分钟级，违背"不挂死"要求

**Tradeoffs:**
- **Gain:** 客户端可快速重试；日志/排障能区分超时与失败；实测黑洞 IP + asr_s=3 在 3.5s 返回 504
- **Cost/Risk:** 错误路径多一条（timeout）；契约已同步进 TASKS.md 契约总览
