# Tasks — qwen-tts

> Granular task list. Each task ID is `T-NNN`.
> 并行模式约定：每个任务声明 `Owns:`（允许改动的文件，并行窗口内零共享）与 `Contract:`（接口契约，冻结后改动需先改这里）。

## 契约总览（先读这个）

- 配置契约 = `config.example.yaml`（T-002 产物，唯一事实来源）：
  ```yaml
  asr:
    provider: local                      # local | remote
    url: http://192.168.0.190:8001/v1/audio/transcriptions  # 完整端点 URL（局域网 vLLM）
    api_key: ""                          # remote 必填，local 可空
    model: Qwen3-ASR-1.7B                # 透传给端点
    language: ""                         # 可选，透传给端点；空 = 不发送（Qwen3-ASR-1.7B vLLM 端点传 language=zh 会重复循环，模型自身能自动检测中文）
    temperature: 0.0                     # 可选，透传给端点
    chunk_seconds: 300                   # 可选，长音频切段长度（秒）；省略/0 = 默认 300
  output_dir: ./output
  temp_dir: ./temp
  bilibili:
    cookie: ""                           # 可选
  timeout:
    download_s: 300
    asr_s: 600
  ```
- 转码约定：ASR 端点（vLLM Qwen3-ASR）只接受 wav；`asr.transcribe` 对非 wav 输入（如 m4a/AAC）先用本地 ffmpeg 转 16k 单声道 wav（临时文件 `{音频名}.asr.wav`，发送后删除），ffmpeg 缺失/转码失败抛 `AsrError`。`language` 为空时不进 form（端点兼容性问题见配置注释）
- 长音频切段约定（T-016）：端点文件大小上限约 30MB（实测 29MB wav 可过、30MB → 400 audio_filesize_mb）；`asr.transcribe` 对时长超过 `chunk_seconds`（默认 300s）的 wav 用 ffmpeg segment 流拷贝切段（临时文件 `{音频名}.chunk_NNN.wav`，发送后删除），逐段转写后按序拼接 text（无分隔符，中文场景）；切段失败抛 `AsrError`；wav 时长用标准库 wave 解析，解析失败（非标准 PCM）视为 0 = 不切段原样发送
- `bili.get_audio(bvid, cfg, dest_path=None) -> (title, duration_s, local_path)`，失败抛 `BiliError(message, code)`，code ∈ {`invalid_bvid`, `not_found`, `fetch_failed`, `timeout`}；dest_path 空时默认 `temp_dir/{bvid}.m4a`，管线传 `temp_dir/{bvid}_{uuid8}.m4a`（并发请求隔离，T-017；.asr.wav/chunk 由其 stem 派生，自动隔离）
- `asr.transcribe(audio_path, cfg) -> str`（中文文本），失败抛 `AsrError(message)`，可选属性 `code`（默认 `asr_failed`，超时时 `timeout`）
- 错误 JSON：`{"error": {"code", "message"}}`；映射：`invalid_bvid`/`invalid_output_dir`→400，`not_found`→404，`fetch_failed`/`asr_failed`→502，`timeout`→504，`internal`→500（路由 generic Exception 统一捕获，T-017）
- 请求：`POST /transcribe {"bvid": "<BV号>", "output_dir": "<可选>"}`；`output_dir` 指定 .txt 保存目录（T-018）：省略/空 = 用 config 的 `output_dir`（保留启动自动创建兜底）；指定时必须是**服务所在机器**上已存在的目录（不自动创建），否则 400 `invalid_output_dir`；响应 `file_path` 为实际落盘路径
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

- [x] T-005 — bili.py 客户端
  - **Owns:** `bili.py`
  - **Contract:** 见契约总览
  - 实现：BV 格式校验（`^BV[1-9A-Za-z]{10}$`）→ `x/web-interface/view` 取 cid/标题/时长 → `x/player/playurl?fnval=16` 取 DASH 音频（dash.audio 首项）→ 流式下载到 `temp_dir/{bvid}.m4a`（带 User-Agent + Referer: www.bilibili.com；cookie 非空则带上）
  - **Done when:** `pytest tests/test_bili.py -q` 全绿（mock HTTP）；另手动真实拉取一个 BV 成功（网络允许时，结果记 PROGRESS）
- [x] T-006 — bili.py 测试
  - **Owns:** `tests/test_bili.py`
  - 覆盖：BV 校验（合法/非法）、view→playurl→下载正常流（mock）、not_found、fetch_failed、cookie 可选头
  - **Done when:** `pytest tests/test_bili.py -q` 全绿

### Phase 3 — 音频 → 文本（工作包 B 与 A 并行；管线接线串行）

- [x] T-007 — asr.py 客户端
  - **Owns:** `asr.py`
  - **Contract:** 见契约总览
  - 实现：按 `cfg["asr"]["provider"]` 分支，两者同形：multipart POST 到 `cfg["asr"]["url"]`（file=音频、model、language=zh）；remote 额外带 `Authorization: Bearer api_key`；超时取 `cfg["timeout"]["asr_s"]`
  - **Done when:** `pytest tests/test_asr.py -q` 全绿（mock local/remote 两分支）
- [x] T-008 — asr.py 测试
  - **Owns:** `tests/test_asr.py`
  - 覆盖：local 分支请求形状、remote 分支 Bearer 头、非 200 → AsrError、超时 → AsrError、响应文本解析
  - **Done when:** `pytest tests/test_asr.py -q` 全绿
- [x] T-009 — /transcribe 管线（整合步骤）
  - **Owns:** `app.py`
  - **Contract:** 见契约总览（响应 `{bvid,title,text,file_path,duration_s}`）
  - 实现：串起 `bili.get_audio` → `asr.transcribe` → 保存 `.txt`（命名规则见契约）→ 成功后删临时音频；失败保留临时文件并在错误信息中给出路径；按映射表返回错误 JSON
  - **Done when:** `pytest tests/test_pipeline.py -q` 全绿
- [x] T-010 — 管线测试
  - **Owns:** `tests/test_pipeline.py`
  - 覆盖：happy path（200 + 字段齐全 + .txt 落盘 + 临时文件已删）、invalid_bvid→400、not_found→404、fetch_failed→502 且临时文件保留、AsrError→502、标题非法字符清洗
  - **Done when:** `pytest tests/test_pipeline.py -q` 全绿

### Phase 4 — 健壮性与验收（串行）

- [x] T-011 — 超时、日志与边界
  - **Owns:** `app.py`, `bili.py`, `asr.py`
  - 统一超时生效（下载/ASR 各取配置）、stdout 日志（每请求：bvid、结果、耗时）、超时返回 504 JSON 而非挂死
  - **Done when:** `pytest tests/ -q` 全绿；手动调小 timeout 触发超时，返回清晰 504 JSON
- [x] T-012 — README
  - **Owns:** `README.md`
  - 简介、快速开始（装依赖/配 config/启动）、curl 示例（成功+错误）、配置项表、本地 vLLM 前置条件、故障排查
  - **Done when:** 按 README 从零走一遍能启动服务（自查记录进 PROGRESS）
- [x] T-013 — 端到端验收
  - **Owns:** 无代码改动（仅验证 + PROGRESS/PLAN 勾选；如需修复则记入 Notes）
  - 真实 vLLM 在线 + 真实 BV 号跑 `POST /transcribe`，逐条核对 PLAN.md Acceptance criteria（6 项）
  - **Done when:** PLAN.md 验收标准全部勾选，结果写入 PROGRESS.md，commit + push
  - **验收结果（2026-10-05）：** 6/6 全过。最后一项"非空中文 text"：BV1dPaZ6qEhd（298s 中文军事评论）→ 200，2122 字符 + .txt 落盘 + temp 清空，11.4s；前 5 项见 10-05 17:15 条目（/health、213s 全链路、.txt 命名、temp 清理、provider 切换、错误 JSON）

### Phase 5 — 真实 vLLM 接入（T-013 解 blocked 的前置代码变更）

- [x] T-014 — asr.py 接入真实 vLLM（temperature 透传 + m4a→wav 转码）
  - **Owns:** `asr.py`, `config.example.yaml`
  - **Contract:** 见契约总览（temperature 透传；非 wav 输入先 ffmpeg 转 16k mono wav）
  - 实测背景：192.168.0.190:8001 的 vLLM Qwen3-ASR-1.7B 端点对 m4a 输入挂起（>150s 无响应），wav 正常（213s 音频 8.9s 转完）；`language`/`temperature` 参数均被接受
  - **Done when:** `pytest tests/ -q` 全绿；真实端点用 m4a 输入（经转码）返回非空文本
- [x] T-015 — T-014 测试
  - **Owns:** `tests/test_asr.py`
  - 覆盖：temperature 进 form、wav 原样发送（不转码）、m4a 转码后发送且临时 wav 清理、转码失败 → AsrError
  - **Done when:** `pytest tests/test_asr.py -q` 全绿
- [x] T-016 — 长音频支持（audio_filesize_mb 超限）
  - **验收（2026-10-05）：** 34 分钟视频 BV1xx411c7mD 真实全管线 ×2 成功（17:47→18:17 1793.8s、18:26→18:52 1579.0s，均 200 + 587KB .txt + temp 清空）；65 条测试全绿
  - **Owns:** `asr.py`（或新增 chunking 模块）+ 其测试 + `config.example.yaml`（chunk_seconds）
  - **背景（2026-10-05 实测）**：34 分钟视频（BV1xx411c7mD，2055s）的 16k mono wav = 63.2MB → 端点 400 `Maximum file size exceeded (audio_filesize_mb=63.22)`；213s 的 6.8MB wav 正常。上限已探明：29MB 可过、30MB → 400（约 30MB，见 PLAN 环境参考）。
  - **实现（2026-10-05，方案 a 分段）**：`asr.chunk_seconds`（默认 300s）：时长超标的 wav → ffmpeg segment 流拷贝切段 → 逐段转写按序拼接；单段 16k mono ≈ 9.6MB 留 3 倍余量；段/转码临时文件 finally 统一清理
  - **Done when:** 34 分钟视频（或 ≥20 分钟）真实 `POST /transcribe` 返回 200 且 text 非空完整；`pytest tests/ -q` 全绿
- [x] T-017 — 同一 BV 并发转写 → 500 HTML（temp 文件名冲突 + 路由未捕 generic Exception）
  - **验收（2026-10-05）：** 修复 = temp 文件名 `{bvid}_{uuid8}.m4a`（get_audio 新增可选 dest_path，.asr.wav/chunk 由 stem 派生自动隔离）+ 路由 generic Exception → 500 JSON（code=internal）；+3 测试（68 全绿）；真实并发验证：同 BV 两请求均 200（16.3s/22.9s）且 temp 无残留
  - **Owns:** `app.py`（及/或 bili.py、asr.py 的 temp 命名）+ 其测试
  - **背景（2026-10-05 实测）**：两个同 BV 的 /transcribe 并发（Flask dev server threaded）共享 `temp/{bvid}.m4a`/`.asr.wav`/`.chunk_*.wav`，一方完成清理后另一方 `FileNotFoundError` → 500 HTML
  - **候选方案**：a) temp 文件名加 per-request uuid 后缀（隔离，改动最小，推荐）；b) 同 bvid 处理中返回 409（需请求状态表，多用户场景再说）；另外路由对 generic Exception 统一 500 JSON
  - **Done when:** 并发重复请求不再 500（两请求均正常完成或 409）；路由任何错误都返回 JSON；`pytest tests/ -q` 全绿

- [x] T-018 — /transcribe 支持可选 output_dir 请求参数（按请求指定 .txt 保存目录）
  - **Owns:** `app.py` + tests + README
  - 请求体 `{"bvid": "...", "output_dir": "/path"}`：output_dir 省略 = 用 config（现状）；指定时必须是服务所在机器上已存在的目录（不自动创建），不存在/不是目录/类型错 → 400 `invalid_output_dir`，不进下载/转写流程
  - **Done when:** 自定义目录落盘 / 目录不存在 400 / 是文件 400 / 类型错 400 四条新测试全绿且既有测试全绿；README 同步；commit + push
  - **验收（2026-10-05）：** 真实 e2e：output_dir=/tmp/t018_out → 200 且 file_path 正确落盘（10.5s）；不存在目录 → 400 JSON 立即返回；+4 测试（72 全绿）；顺手修 _error_response 空路径 bug（Path("").exists() 误拼"临时音频已保留: ."）

## In progress

（无）

## Done

- T-001 — 初始化依赖与 gitignore（commit `3321c1c`）
- T-002 — 配置文件与加载逻辑（commit `3118170`）
- T-003 — Flask 入口与 /health（commit `317d77d`）
- T-004 — Phase 1 单测，13 条全绿（commit `60fb67e` + `d2506a0`）
- T-005 — bili.py 客户端（workA，真实拉取 2 个 BV 成功；commit `9ba3e92` + `74e28d8`）
- T-006 — bili.py 测试（workA，mock 全绿；commit `a3316e8`）
- T-007 — asr.py 客户端（workB；commit `fc1ca51`）
- T-008 — asr.py 测试（workB，mock 全绿；commit `5327dce`）
- T-009 — /transcribe 管线（main 整合；commit `2987abb`）
- T-010 — 管线测试，52 条全绿（commit `2932790` + 后续补充）
- T-011 — 超时→504 JSON + 每请求日志（手动黑洞 IP 实测 3.5s 返回 504；commit `e7770f1`）
- T-012 — README（commit `c6f5964`）
- T-013 — 端到端验收 6/6（无代码改动；BV1dPaZ6qEhd 298s 中文视频 2122 字符收官，PLAN 验收全勾选）
- T-016 — 长音频切段：asr.chunk_seconds 默认 300s，ffmpeg segment 流拷贝，逐段拼接 + finally 统一清理（+7 测试，65 全绿；34 分钟视频 ×2 真实成功；上限探明约 30MB 落文档）
- T-017 — 并发 500 修复：uuid temp 命名 + 路由 500 JSON（+3 测试，68 全绿；真实并发 ×2 均 200）
- T-018 — output_dir 请求参数：按请求指定 .txt 保存目录（默认 config，不存在 400 invalid_output_dir；+4 测试，72 全绿；真实 e2e 落盘验证）
- T-014 — asr.py 接入真实 vLLM：temperature 透传 + m4a→16k wav 转码 + language 默认不发送（契约同步；commit `61192b6`）
- T-015 — T-014 测试（58 条全绿；commit `3c7ce59`）

## Blocked

（无）

## Format conventions

- Task IDs increment monotonically across the project's lifetime — never reuse an ID, even for deleted tasks.
- A task is "active" if it's queued and ready; "in progress" if a session is currently working on it; "done" if its acceptance criteria are met; "blocked" if it can't proceed without resolving a dependency.
- Move tasks between sections as state changes. Don't delete completed tasks — they're a record.
- For larger tasks (>1 session of work), spawn subtasks under it rather than letting it grow.
- 并行约定：`Owns:` 声明的文件之外不得改动；契约变更必须先改本文件"契约总览"并同步相关任务。
