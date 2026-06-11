# Drama Highlight Interaction

短剧高光互动系统。围绕"剧情高光点的离线打标 → 下发 → 端上即时互动 → 互动数据聚合回流"构建端到端闭环，包含 Android 客户端与 FastAPI 服务端。

## 1. 系统概览

```text
┌──────────────────────┐        REST/JSON         ┌───────────────────────────┐
│   Android 客户端      │  ───────────────────────▶│     FastAPI 服务端         │
│                      │                          │                           │
│  剧集列表 / 播放器     │  ◀─ dramas / episodes ── │  媒体扫描  ┐                │
│  互动浮层调度          │  ◀─ manifest ─────────── │  Manifest │── PostgreSQL  │
│  互动上报 / 聚合展示    │  ── interactions ──────▶ │  互动聚合  ┘               │
└──────────────────────┘  ◀─ aggregate ────────── └───────────┬───────────────┘
                                                              │ 视频 / 封面 (HTTP Range)
                                                              ▼
                                            本地短剧目录 (drama/) + 离线生成产物 (data/)
```

整个系统分为三条数据流：

| 数据流 | 触发时机 | 说明 |
|---|---|---|
| 内容下发 | 启动扫描 / 客户端请求 | 服务端扫描本地短剧目录，下发剧集元数据、视频流和高光 Manifest |
| 离线打标 | 运维侧手动 / 批处理脚本 | 视频 → 抽音频 → ASR 转写 → LLM 生成高光 Manifest → 落盘并入库 |
| 互动回流 | 用户点击互动组件 | 客户端上报互动事件，服务端持久化并返回实时聚合计数 |

## 2. 技术栈

| 层 | 选型 |
|---|---|
| 客户端 | Android (Java)、Media3 ExoPlayer、Retrofit + Gson、OkHttp、Glide |
| 服务端 | Python 、FastAPI、SQLAlchemy |
| 持久化 | PostgreSQL 16（可降级到内存存储用于测试） |
| 内容理解 | FFmpeg 抽音频，ASR + LLM 离线流水线 |

## 3. 仓库结构

```text
.
├── client/android/             # Android Studio 工程（客户端）
├── server/                     # FastAPI 服务端、媒体扫描、AI 高光生成、接口测试
│   ├── Dockerfile              # API 容器镜像（含 FFmpeg、非 root 运行）
│   └── .env.server.example     # 轻量化部署环境变量样例
├── docs/                       # 项目排期
├── assets/                     # Manifest 示例资源
├── docker-compose.yml          # 本地开发用 PostgreSQL
└── docker-compose.server.yml   # 轻量化单机部署（API + PostgreSQL）
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

完整表结构见 [server/db/schema.sql](server/db/schema.sql)（运行时由 SQLAlchemy 建表，schema.sql 为说明版本）。

## 5. API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/dramas` | 短剧列表 |
| `GET` | `/api/dramas/{id}/episodes` | 指定短剧的剧集列表 |
| `GET` | `/api/contents/{content_id}/manifest` | 指定剧集的高光 Manifest |
| `POST` | `/api/interactions` | 上报互动事件，返回实时聚合 |
| `GET` | `/api/highlights/{id}/aggregate` | 查询高光点聚合计数 |
| `GET` | `/videos/{relative_path}` | 视频流，支持 HTTP Range |
| `GET` | `/posters/{relative_path}` | 封面图片 |
| `GET` | `/health` | 健康检查（进程存活） |
| `GET` | `/ready` | 就绪检查（触发 Store 初始化，供容器 healthcheck 使用） |

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

> 服务器上若需现场生成 Manifest（而非仅下发已有产物），仍按 [server/README.md](server/README.md) 在宿主机虚拟环境里跑离线流水线，再将产物 `cp` 进数据卷；生成脚本不随 API 镜像打包，保持运行镜像精简。

## 8. 文档索引

- [服务端技术说明](server/README.md) — 架构、配置、Manifest 离线生成、API 参考

- [Android 客户端技术说明](client/android/README.md) — 模块结构、播放与互动时序、网络层

- [项目拆解与排期](docs/project-plan.md)

  
