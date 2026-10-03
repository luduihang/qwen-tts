# Tasks — qwen-tts

> Granular task list. Each task ID is `T-NNN`.
> 并行模式约定：每个任务声明 `Owns:`（允许改动的文件，并行窗口内零共享）与 `Contract:`（接口契约，冻结后改动需先改这里）。

## 契约总览（先读这个）

- 配置契约 = `config.example.yaml`（T-002 产物，唯一事实来源）：
  ```yaml
  asr:
    provider: local                      # local | remote
    url: http://127.0.0.1:8000/v1/audio/transcriptions  # 完整端点 URL
    api_key: ""                          # remote 必填，local 可空
    model: ""                            # 可选，透传给端点
    language: zh
  output_dir: ./output
  temp_dir: ./temp
  bilibili:
    cookie: ""                           # 可选
  timeout:
    download_s: 300
    asr_s: 600
  ```
- `bili.get_audio(bvid, cfg) -> (title, duration_s, local_path)`，失败抛 `BiliError(message, code)`，code ∈ {`invalid_bvid`, `not_found`, `fetch_failed`}
- `asr.transcribe(audio_path, cfg) -> str`（中文文本），失败抛 `AsrError(message)`
- 错误 JSON：`{"error": {"code", "message"}}`；映射：`invalid_bvid`→400，`not_found`→404，`fetch_failed`/`AsrError`→502
- 转写文件名：`{bvid}_{标题清洗}.txt`（清洗：去除 `\/:*?"<>|`，空白压缩，截断 40 字符）

## Active

### Phase 1 — 骨架与配置（串行，main）

- [x] T-001 — 初始化依赖与 gitignore
  - **Owns:** `requirements.txt`, `.gitignore`
  - 新建 `requirements.txt`（flask、requests、pyyaml）；gitignore 已含 `config.yaml`/`output/`/`temp/`，核对补齐
  - **Done when:** `pip install -r requirements.txt` 成功，`python -c "import flask, requests, yaml"` 无错
- [x] T-002 — 配置文件与加载逻辑
  - **Owns:** `config.example.yaml`, `app.py`（配置加载部分）
  - 按契约总览建 `config.example.yaml`；`app.py` 实现加载：`config.yaml` 缺失或必填项（asr.provider/url、output_dir、temp_dir）缺失时报清晰错误并退出
  - **Done when:** 以 example 为 `config.yaml` 可正常加载；删掉 `config.yaml` 启动报明确的"配置文件缺失"
- [x] T-003 — Flask 入口与 /health
  - **Owns:** `app.py`
  - 启动时自动创建 `output_dir`/`temp_dir`；`GET /health` 返回 200 JSON（含 `asr.provider`）
  - **Done when:** `python app.py` 启动后 `curl localhost:5000/health` 返回 200 且含 `asr.provider`
- [x] T-004 — Phase 1 单测
  - **Owns:** `tests/test_config.py`, `tests/test_app.py`
  - 覆盖：配置加载（正常/缺文件/缺必填项）、目录自动创建、/health 响应
  - **Done when:** `pytest tests/ -q` 全绿

### Phase 2 — BV 号 → 音频落盘（工作包 A，可与 B 并行）

- [ ] T-005 — bili.py 客户端
  - **Owns:** `bili.py`
  - **Contract:** 见契约总览
  - 实现：BV 格式校验（`^BV[1-9A-Za-z]{10}$`）→ `x/web-interface/view` 取 cid/标题/时长 → `x/player/playurl?fnval=16` 取 DASH 音频（dash.audio 首项）→ 流式下载到 `temp_dir/{bvid}.m4a`（带 User-Agent + Referer: www.bilibili.com；cookie 非空则带上）
  - **Done when:** `pytest tests/test_bili.py -q` 全绿（mock HTTP）；另手动真实拉取一个 BV 成功（网络允许时，结果记 PROGRESS）
- [ ] T-006 — bili.py 测试
  - **Owns:** `tests/test_bili.py`
  - 覆盖：BV 校验（合法/非法）、view→playurl→下载正常流（mock）、not_found、fetch_failed、cookie 可选头
  - **Done when:** `pytest tests/test_bili.py -q` 全绿

### Phase 3 — 音频 → 文本（工作包 B 与 A 并行；管线接线串行）

- [ ] T-007 — asr.py 客户端
  - **Owns:** `asr.py`
  - **Contract:** 见契约总览
  - 实现：按 `cfg["asr"]["provider"]` 分支，两者同形：multipart POST 到 `cfg["asr"]["url"]`（file=音频、model、language=zh）；remote 额外带 `Authorization: Bearer api_key`；超时取 `cfg["timeout"]["asr_s"]`
  - **Done when:** `pytest tests/test_asr.py -q` 全绿（mock local/remote 两分支）
- [ ] T-008 — asr.py 测试
  - **Owns:** `tests/test_asr.py`
  - 覆盖：local 分支请求形状、remote 分支 Bearer 头、非 200 → AsrError、超时 → AsrError、响应文本解析
  - **Done when:** `pytest tests/test_asr.py -q` 全绿
- [ ] T-009 — /transcribe 管线（整合步骤）
  - **Owns:** `app.py`
  - **Contract:** 见契约总览（响应 `{bvid,title,text,file_path,duration_s}`）
  - 实现：串起 `bili.get_audio` → `asr.transcribe` → 保存 `.txt`（命名规则见契约）→ 成功后删临时音频；失败保留临时文件并在错误信息中给出路径；按映射表返回错误 JSON
  - **Done when:** `pytest tests/test_pipeline.py -q` 全绿
- [ ] T-010 — 管线测试
  - **Owns:** `tests/test_pipeline.py`
  - 覆盖：happy path（200 + 字段齐全 + .txt 落盘 + 临时文件已删）、invalid_bvid→400、not_found→404、fetch_failed→502 且临时文件保留、AsrError→502、标题非法字符清洗
  - **Done when:** `pytest tests/test_pipeline.py -q` 全绿

### Phase 4 — 健壮性与验收（串行）

- [ ] T-011 — 超时、日志与边界
  - **Owns:** `app.py`, `bili.py`, `asr.py`
  - 统一超时生效（下载/ASR 各取配置）、stdout 日志（每请求：bvid、结果、耗时）、超时返回 504 JSON 而非挂死
  - **Done when:** `pytest tests/ -q` 全绿；手动调小 timeout 触发超时，返回清晰 504 JSON
- [ ] T-012 — README
  - **Owns:** `README.md`
  - 简介、快速开始（装依赖/配 config/启动）、curl 示例（成功+错误）、配置项表、本地 vLLM 前置条件、故障排查
  - **Done when:** 按 README 从零走一遍能启动服务（自查记录进 PROGRESS）
- [ ] T-013 — 端到端验收
  - **Owns:** 无代码改动（仅验证 + PROGRESS/PLAN 勾选；如需修复则记入 Notes）
  - 真实 vLLM 在线 + 真实 BV 号跑 `POST /transcribe`，逐条核对 PLAN.md Acceptance criteria（6 项）
  - **Done when:** PLAN.md 验收标准全部勾选，结果写入 PROGRESS.md，commit + push

## In progress

（无）

## Done

- T-001 — 初始化依赖与 gitignore（commit `3321c1c`）
- T-002 — 配置文件与加载逻辑（commit `3118170`）
- T-003 — Flask 入口与 /health（commit `317d77d`）
- T-004 — Phase 1 单测，13 条全绿（commit `60fb67e` + `d2506a0`）

## Blocked

（无）

## Format conventions

- Task IDs increment monotonically across the project's lifetime — never reuse an ID, even for deleted tasks.
- A task is "active" if it's queued and ready; "in progress" if a session is currently working on it; "done" if its acceptance criteria are met; "blocked" if it can't proceed without resolving a dependency.
- Move tasks between sections as state changes. Don't delete completed tasks — they're a record.
- For larger tasks (>1 session of work), spawn subtasks under it rather than letting it grow.
- 并行约定：`Owns:` 声明的文件之外不得改动；契约变更必须先改本文件"契约总览"并同步相关任务。
