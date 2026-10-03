# Tasks — qwen-tts

> Granular task list. Each task ID is `T-NNN`.

## Active

### Phase 1 — 骨架与配置

- [ ] T-001 — 初始化依赖与 gitignore
  - 新建 `requirements.txt`（flask、requests、pyyaml）；`.gitignore` 增加 `config.yaml`、输出目录、临时目录
  - **Done when:** `pip install -r requirements.txt` 成功，`python -c "import flask, requests, yaml"` 无错
- [ ] T-002 — 配置文件与加载逻辑
  - 新建 `config.example.yaml`：`asr.provider`（local/remote）、`asr.url`、`asr.api_key`（可空）、`output_dir`、`temp_dir`、`bilibili.cookie`（可空）、`timeout`；`app.py` 实现配置加载（缺文件/缺必填项时报清晰错误）
  - **Done when:** 以 `config.example.yaml` 为 `config.yaml` 可正常加载；删除 `config.yaml` 后启动报明确的"配置文件缺失"错误
- [ ] T-003 — Flask 入口与 /health
  - `app.py`：启动时自动创建 `output_dir`/`temp_dir`；`GET /health` 返回 200 JSON（含 `asr.provider`）
  - **Done when:** `python app.py` 启动后 `curl localhost:5000/health` 返回 200 且 JSON 含 `asr.provider`
- [ ] T-004 — Phase 1 单测
  - `tests/`：配置加载（正常/缺文件/缺必填项）、目录自动创建、/health 响应
  - **Done when:** `pytest tests/ -q` 全绿

## In progress

（无）

## Done

（无）

## Blocked

（无）

## Format conventions

- Task IDs increment monotonically across the project's lifetime — never reuse an ID, even for deleted tasks.
- A task is "active" if it's queued and ready; "in progress" if a session is currently working on it; "done" if its acceptance criteria are met; "blocked" if it can't proceed without resolving a dependency.
- Move tasks between sections as state changes. Don't delete completed tasks — they're a record.
- For larger tasks (>1 session of work), spawn subtasks under it rather than letting it grow.
