# Drama Highlight Interaction

短剧高光互动系统。围绕"剧情高光点的离线打标 → 人工审核发布 → 下发 → 端上即时互动 → 互动数据聚合回流"构建端到端闭环，包含 Android 客户端、FastAPI 服务端与 Vue3 管理后台（内容生产与运营）。

## 1. 系统概览

```text
┌──────────────────────┐        REST/JSON         ┌───────────────────────────┐
│   Android 客户端      │  ───────────────────────▶│     FastAPI 服务端         │
│                      │                          │                           │
│  剧集列表 / 播放器     │  ◀─ dramas / episodes ── │  媒体扫描  ┐               │
│  互动浮层调度          │  ◀─ manifest ─────────── │  Manifest │── PostgreSQL  │
│  互动上报 / 聚合展示    │  ── interactions ──────▶ │  互动聚合  ┘              │
└──────────────────────┘  ◀─ aggregate ────────── └───────────┬───────────────┘
                                                              │ 视频 / 封面 (HTTP Range)
                                                              ▼
                                             本地短剧目录 (drama/) + 生成产物 (data/)

┌──────────────────────┐   Bearer ADMIN_TOKEN    ┌───────────────────────────┐
│  管理后台 (Vue3)      │  ──────────────────────▶│  /admin/api               │
│  内容管理 / 版本编辑    │                         │  生成任务 + Worker 轮询     │
│  AI 任务 / 审计        │                         │  FFmpeg → ASR → LLM 流水线 │
└──────────────────────┘                         └───────────────────────────┘
```

整个系统分为四条数据流：

| 数据流 | 触发时机 | 说明 |
|---|---|---|
| 内容下发 | 启动扫描 / 客户端请求 | 服务端扫描本地短剧目录，下发剧集元数据、视频流和高光 Manifest |
| 内容生产（AI 打标） | 管理后台触发生成任务，worker 轮询执行 | 视频 → FFmpeg 抽音频 → ASR 转写 → LLM 生成高光 Manifest → 落为 `draft` 版本 |
| 人工审核发布 | 运营在管理后台编辑 | `draft` → `reviewing` → 发布：物化到 `highlight_point`，客户端立即生效 |
| 互动回流 | 用户点击互动组件 | 客户端上报互动事件，服务端持久化并返回实时聚合计数 |

## 2. 技术栈

| 层 | 选型 |
|---|---|
| 客户端 | Android (Java)、Media3 ExoPlayer、Retrofit + Gson、OkHttp、Glide |
| 服务端 | Python 3.11、FastAPI、SQLAlchemy 2 |
| 管理后台 | Vue 3 + Vite + Element Plus + vue-router（`client_admin/`） |
| 持久化 | PostgreSQL 16（可降级到内存存储用于测试） |
| 内容理解 | FFmpeg 抽音频；ASR 默认走模型 API（可选本地 whisper）；LLM 走 OpenAI 兼容接口生成高光与续写 |

## 3. 仓库结构

```text
.
├── client/android/             # Android Studio 工程（客户端）
├── client_admin/               # 管理后台前端（Vue3 + Vite + Element Plus，构建产物随 API 镜像挂载 /admin）
├── server/                     # FastAPI 服务端、媒体扫描、AI 高光生成、管理端 API 与生成 worker
│   ├── Dockerfile              # 多阶段镜像：Stage1 构建管理端 UI，Stage2 API（含 FFmpeg、非 root）
│   ├── .env.example            # 本地开发环境变量样例（模型 / 数据库 / 管理端）
│   └── .env.server.example     # 轻量化部署环境变量样例
├── docs/                       # 项目排期 / 数据库设计 / 管理端 API 设计
├── assets/                     # Manifest 示例
├── docker-compose.yml          # 本地开发用 PostgreSQL
└── docker-compose.server.yml   # 轻量化单机部署（API + PostgreSQL + 管理后台）
```

短剧素材目录 `drama/` 位于本仓库同级（默认 `../drama`），不纳入版本控制。

## 4. 内容标识与数据模型

每集视频以"相对路径 SHA-1 前 16 位"生成稳定 `content_id`，作为 Manifest、转写文件、Manifest 查询与互动上报的统一主键。`Episode.id` 仅为当前扫描结果中的运行时数字 ID，新增剧集后可能变化，不参与上述关联。

| 表 | 主键 | 用途 |
|---|---|---|
| `drama` | `id` | 短剧元数据 |
| `episode` | `id` / `content_id`(唯一) | 剧集元数据、视频地址、时长 |
| `highlight_point` | `id` | 高光点时间窗、类型、互动 payload |
| `interaction_event` | `id` | 每次互动点击的明细事件（含预留、暂未使用的可空 `user_id`） |
| `aggregate_snapshot` | `(highlight_id, action)` | 高光点各动作的聚合计数 |
| `branch_session` | `id` | 剧情续写会话（预留） |
| `manifest_version` | `id` | 内容生产版本（draft/reviewing/published/archived），整份 Manifest JSONB |
| `generation_task` | `id` | AI 生成任务（pending/running/succeeded/failed），worker 轮询领取执行 |
| `admin_operation_log` | `id` | 管理端审计日志（谁 / 何时 / 对什么 / 改前改后） |

完整表结构见 [server/db/schema.sql](server/db/schema.sql)（运行时由 SQLAlchemy 建表，schema.sql 为说明版本）；内容生产层三张表的设计与状态机见 [docs/db-design.md](docs/db-design.md)。

## 5. API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/dramas` | 短剧列表 |
| `GET` | `/api/dramas/{id}/episodes` | 指定短剧的剧集列表 |
| `GET` | `/api/contents/{content_id}/manifest` | 指定剧集的高光 Manifest |
| `POST` | `/api/interactions` | 上报互动事件，返回实时聚合 |
| `GET` | `/api/highlights/{id}/aggregate` | 查询高光点聚合计数 |
| `POST` | `/api/ai/highlight-candidates` | 生成高光候选（`persist=true` 时直接落库） |
| `POST` | `/api/ai/continuation` | 剧情续写 |
| `GET` | `/videos/{relative_path}` | 视频流，支持 HTTP Range |
| `GET` | `/posters/{relative_path}` | 封面图片 |
| `GET` | `/health` | 健康检查（进程存活） |
| `GET` | `/ready` | 就绪检查（触发 Store 初始化，供容器 healthcheck 使用） |

管理后台接口（`/admin/api/*`，需 `Authorization: Bearer <ADMIN_TOKEN>`）与内容生产闭环见 [管理端 API 设计](docs/admin-api-design.md)。

互动上报必须携带客户端本地持久化的 `session_id`（首次使用生成 `device_` 前缀 UUID）。事件写入 `interaction_event` 并同步更新 `aggregate_snapshot`，服务重启后聚合结果不丢失。

接口的实现细节、AI 离线生成流程与配置见各子文档。

## 6. 快速开始（本地开发）

```powershell
# 1. 启动数据库
docker compose up -d postgres

# 2. 启动服务端（见 server/README.md）
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3000

# 3. 用 Android Studio 打开 client/android，运行 app 模块

# 4.（可选）管理后台：在 server/.env 设置 ADMIN_TOKEN 后重启；构建前端后访问 http://localhost:3000/admin/
#    cd client_admin && npm install && npm run build
```

## 7. 轻量化部署（单机容器）

面向"个人 PC / 一台云主机"的低成本部署：`docker-compose.server.yml` 把 **API + PostgreSQL** 打包为一套 Compose 栈，API 由内置 `Dockerfile` 构建（已含 FFmpeg、非 root 运行、多 worker uvicorn），短剧目录以**只读**挂载，互动数据与 Manifest 落在命名卷上重启不丢。

```powershell
# 1. 准备环境变量
copy server\.env.server.example server\.env.server
# 编辑 server\.env.server：设置强密码、PUBLIC_BASE_URL（http://服务器IP:3000）、
# DRAMA_HOST_PATH（服务器上存放短剧目录的绝对路径），可选填模型接入点

# 2. 构建并启动（API + PostgreSQL）
docker compose -f docker-compose.server.yml up -d --build

# 3. 把已生成的高光 Manifest 灌入数据卷，再重启 API 让其入库
#    （manifests 不随镜像打包，首次部署数据卷为空，否则所有剧集都没有高光）
docker compose -f docker-compose.server.yml cp `
  server/data/manifests/. api:/data/manifests/
docker compose -f docker-compose.server.yml restart api

# 4. 验证
curl http://localhost:3000/ready      # {"ok": true}
curl http://localhost:3000/api/dramas
```

客户端将 `config_api_base_url` 指向 `http://服务器IP:3000/api/` 即可（见 [Android 客户端说明](client/android/README.md)）。

> **管理后台**：`http://服务器IP:3000/admin/`（Vue3 + Element Plus，随 API 镜像打包）。设置 `ADMIN_TOKEN` 后即可登录使用，支持 Manifest 编辑器（AI 候选 → 人工审核 → 发布）、AI 生成任务与审计日志。开发/部署细节见 [管理端 API 设计](docs/admin-api-design.md)。

> 服务器上若需现场生成 Manifest（而非仅下发已有产物）：CLI 脚本 `python -m app.scripts.generate_episode_manifest <video>` 已随 API 镜像打包，可在容器内直接执行（生成目录通过 `TRANSCRIPT_ROOT` / `MANIFEST_ROOT` 指向 `/data` 卷）；离线流水线的完整说明（ASR 三种模式、批量生成）见 [server/README.md](server/README.md)。

## 8. 文档索引

- [服务端技术说明](server/README.md) — 架构、配置、Manifest 离线生成、API 参考

- [Android 客户端技术说明](client/android/README.md) — 模块结构、播放与互动时序、网络层

- [项目拆解与排期](docs/project-plan.md)

- [数据库设计（内容生产层）](docs/db-design.md) — 管理后台数据模型、`manifest_version` / `generation_task` / 审计日志

- [管理端 API 设计](docs/admin-api-design.md) — `/admin/api` 接口规范、Manifest 编辑器与 AI 生成工作台流程

  
