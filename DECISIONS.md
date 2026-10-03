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
