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
