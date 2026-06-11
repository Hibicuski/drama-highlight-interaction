# Drama Highlight Server

短剧高光互动系统的服务端：扫描本地短剧目录、提供视频/封面/元数据接口、持久化互动数据，并离线生成高光互动 Manifest。基于 FastAPI + SQLAlchemy + PostgreSQL。

## 1. 架构与模块职责

```text
app/
├── main.py                 # FastAPI 入口、视频/封面路由、HTTP Range
├── api/                    # 路由层（dramas / manifests / interactions / ai）
├── db/
│   ├── models.py           # Pydantic 数据模型（API 契约）
│   ├── orm.py              # SQLAlchemy 表定义
│   └── session.py          # Store 抽象：DatabaseStore / InMemoryStore
├── services/
│   ├── media_scanner.py            # 扫描目录、生成封面、读取时长、组装剧集
│   ├── manifest_store.py           # content_id、Manifest 校验与归一化、落盘/加载
│   ├── episode_manifest_pipeline.py# 抽音频→转写→格式化→调用 LLM 的编排
│   ├── highlight_generator.py      # 高光生成 prompt、JSON 解析与最多 3 次修复
│   ├── model_client.py             # LLM chat 客户端 + 音频转写客户端
│   ├── local_asr.py                # 可选本地 whisper 引擎（懒加载）
│   ├── text_quality.py             # 乱码修复、文案质量校验
│   └── continuation_generator.py   # 剧情续写（预留占位）
└── scripts/                # 单集生成 CLI 入口
```

| 关注点 | 模块 | 说明 |
|---|---|---|
| 内容下发 | `media_scanner` + `db/session` | 启动时扫描目录，元数据与高光点写入 PostgreSQL |
| 媒体服务 | `main` | 视频按 HTTP Range 分段返回；封面带内置兜底图 |
| 高光生成 | `episode_manifest_pipeline` + `highlight_generator` | 离线流水线，播放链路不实时等待模型 |
| 数据质量 | `manifest_store` + `text_quality` | 时间窗/枚举白名单/文案规则校验，乱码修复 |
| 互动持久化 | `db/session` (DatabaseStore) | 事件明细 + 聚合计数原子 upsert |

## 2. 运行环境

- Python 3.11+
- PostgreSQL 16（推荐用仓库根目录的 `docker-compose.yml`）
- FFmpeg（`ffmpeg` 与 `ffprobe`，用于抽音频与读取时长）

`ffprobe` 缺失时服务仍可启动，但剧集 `duration_ms` 返回 `0`。

## 3. 启动

```powershell
# 仓库根目录启动数据库
docker compose up -d postgres

cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

- 健康检查：`http://localhost:3000/health`（存活）、`http://localhost:3000/ready`（就绪，触发 Store 初始化）
- Swagger 文档：`http://localhost:3000/docs`

> 单机容器化部署（API + PostgreSQL 一套 Compose 栈，含本镜像 `Dockerfile`）见仓库根目录 README 的「轻量化部署」一节。

## 4. 配置

服务端读取 `server/.env`（已被 git 忽略），由 `app/__init__.py` 在启动 API 或运行脚本时自动加载（`override=False`，**Shell 中已设置的同名变量优先**）。复制 `.env.example` 即可开始。

| 变量 | 默认 | 说明 |
|---|---|---|
| `MODEL_BASE_URL` | 空 | OpenAI 兼容文本模型 Base URL（OpenAI 官方可留空） |
| `MODEL_API_KEY` | 空 | 文本模型 API Key |
| `MODEL_NAME` | 空 | 文本模型名 |
| `MODEL_TIMEOUT` | `120` | 单次 chat 请求超时（秒） |
| `MODEL_AUDIO_NAME` | `MODEL_NAME` | 默认 ASR 路径使用的多模态模型 |
| `DATABASE_URL` | 本地开发库 | PostgreSQL 连接串 |
| `STORE_BACKEND` | 空 | 设为 `memory` 走内存存储（测试/临时用） |
| `LOCAL_DRAMA_ROOT` | `../drama` | 短剧目录根 |
| `PUBLIC_BASE_URL` | `http://10.0.2.2:{PORT}` | 拼接视频/封面 URL 的基址 |
| `FFMPEG_PATH` / `FFPROBE_PATH` | PATH | FFmpeg 工具路径（仅在不在 PATH 时设置） |
| `ASR_ENGINE` | 空 | 设为 `whisper` 启用本地离线 ASR |
| `ASR_BASE_URL` / `ASR_API_KEY` / `ASR_MODEL` | 复用 `MODEL_*` | 专用远程 STT 端点 |

> 注意：`server/.env` 会被自动加载，`FFMPEG_PATH`/`FFPROBE_PATH` 若填入无效路径会覆盖 PATH 上可用的 FFmpeg，默认请保持注释。

## 5. 本地短剧目录

默认扫描仓库同级的 `drama` 文件夹：

```text
Projects/
├── drama-highlight-interaction/
└── drama/
    └── 短剧名称/
        ├── poster.jpg        # 可选封面
        ├── 第1集.mp4
        └── 第2集.mp4
```

扫描规则：

- 每个一级子目录是一部短剧，其中直接包含的 `.mp4/ .mov / .mkv / .avi` 被识别为剧集。
- 集数从文件名 `第N集` 解析，缺失时回退到目录内序号。
- 封面优先使用名为 `poster / cover / 封面` 的 `.jpg/.jpeg/.png/.webp`；无封面时用 FFmpeg 抽取首帧生成，再不行使用内置兜底图。
- 短剧列表在启动时扫描；增删视频后重启服务即可重新加载。

## 6. content_id 与生成产物

`content_id = sha1(相对路径).hexdigest()[:16]`，例如：

```text
relative_path = 十八岁太奶奶驾到，重整家族荣耀第三部/第1集.mp4
content_id    = 2fe8f92ec371216d
```

离线生成默认写入：

```text
server/data/transcripts/{content_id}.json   # ASR 带时间戳字幕
server/data/manifests/{content_id}.json     # 客户端使用的高光互动 Manifest
server/data/index.json                       # content_id 与视频路径的人工对照表
```

当前流水线不做文本级说话人分离：ASR 只负责产出带时间戳字幕，剧情理解与高光打标完全由 LLM 基于原始时间戳字幕完成。没有合格 Manifest 时返回空 `highlights`，不伪造固定高光。

## 7. 高光 Manifest 离线生成流程

```text
video.mp4
  │  ffmpeg 抽音频 (mono / 16kHz / mp3)
  ▼
audio.mp3
  │  AudioTranscriptionClient.transcribe
  ▼
带时间戳字幕  ──格式化──▶  [mm:ss.mmm - mm:ss.mmm] 台词
  │  LLM (system prompt + 字幕)，response_format=json_object
  ▼
模型 JSON  ──校验/归一化──▶  失败则最多 3 次修复 prompt
  ▼
HighlightManifest  ──落盘 + 入库──▶ data/manifests + PostgreSQL
```

**校验规则（`manifest_store.normalize_manifest`）：**

- 必填字段齐全；每集 2–4 个不重叠高光，每个时间窗 2–8 秒且不越界。
- `type / template / tone / icon` 必须命中白名单；`effect` 非法时降级为默认 `pulse`（不丢弃整条高光）。
- `dual-button` / `poll` 至少 2 个 actions，`tap-boost` 可只 1 个。
- 标题与 action label 必须是简洁中文，拦截英文/拼音/乱码/低质攻击性词；label 不再强制命中固定情绪词表。

### ASR 三种模式

| 模式 | 配置 | 说明 |
|---|---|---|
| 模型 API（默认） | 留空 `ASR_ENGINE`、`ASR_MODEL` | 走多模态模型音频理解（`MODEL_AUDIO_NAME`），无需本地模型 |
| 远程 STT | `ASR_BASE_URL / ASR_API_KEY / ASR_MODEL` | 专用语音转写端点（如 `whisper-1`） |
| 本地 whisper | `ASR_ENGINE=whisper` + `pip install openai-whisper torch` | 离线转写，按需懒加载；GPU 机器需自行装匹配 CUDA 的 torch |

```powershell
# 远程 STT
$env:ASR_BASE_URL="https://your-audio-transcription-endpoint/v1"
$env:ASR_API_KEY="replace-me"
$env:ASR_MODEL="whisper-1"

# 本地 whisper
$env:ASR_ENGINE="whisper"
$env:WHISPER_MODEL="small"   # tiny/base/small/medium/large/large-v3
$env:ASR_LANGUAGE="zh"
$env:ASR_DEVICE="auto"       # auto: 有 CUDA 版 torch 时走 GPU，否则 CPU
```

### 单集生成

```powershell
cd server
.\.venv\Scripts\python.exe -m app.scripts.generate_episode_manifest `
  "C:\Users\15095\Desktop\Projects\drama\短剧名称\第1集.mp4" `
  --local-drama-root "C:\Users\15095\Desktop\Projects\drama" `
  --summary "可选剧情摘要"

# 复用已有 transcript，跳过 ASR
.\.venv\Scripts\python.exe -m app.scripts.generate_episode_manifest `
  "...\第1集.mp4" --local-drama-root "...\drama" `
  --transcript-json "server\data\transcripts\{content_id}.json"
```

### 批量生成

`scripts/generate_all_manifests.cmd` 包装 PowerShell 脚本，自动临时绕过执行策略，API Key 通过隐藏输入读取、仅存活于当前进程。

```powershell
cd server
.\scripts\generate_all_manifests.cmd -DryRun                       # 预览，不调用模型
.\scripts\generate_all_manifests.cmd -Retranscribe -Force -Limit 1 # 先跑 1 集
.\scripts\generate_all_manifests.cmd                               # 处理全部
.\scripts\generate_all_manifests.cmd -AsrMode whisper -AsrModel small -Limit 1  # 本地 whisper
.\scripts\generate_all_manifests.cmd -FfmpegBin "D:\ffmpeg\bin" -Limit 1        # 指定 FFmpeg
```

行为：已有 Manifest 默认跳过（`-Force` 覆盖）；已有 transcript 默认复用（`-Retranscribe` 重跑）。`-AsrMode remote`（默认）可加 `-AsrApiModel / -AsrBaseUrl / -AsrApiKey` 覆盖端点，默认复用 `MODEL_*`。

## 8. API 参考

| 方法 | 路径 | 请求体 | 返回 |
|---|---|---|---|
| `GET` | `/api/dramas` | — | `Drama[]` |
| `GET` | `/api/dramas/{id}/episodes` | — | `Episode[]` |
| `GET` | `/api/contents/{content_id}/manifest` | — | `HighlightManifest`（不存在返回 404） |
| `POST` | `/api/interactions` | `InteractionRequest` | `InteractionResponse`（实时聚合） |
| `GET` | `/api/highlights/{id}/aggregate` | — | `InteractionResponse` |
| `POST` | `/api/ai/highlight-candidates` | `HighlightCandidateRequest` | `HighlightManifest` |
| `POST` | `/api/ai/continuation` | `ContinuationRequest` | `ContinuationResponse`（占位） |
| `GET` | `/videos/{relative_path}` | — | 视频流（支持 Range / 206） |
| `GET` | `/posters/{relative_path}` | — | 封面图片 |

数据模型见 [app/db/models.py](app/db/models.py)。`POST /api/ai/highlight-candidates` 已接真实模型；`continuation` 目前返回本地占位结果。

## 9. 数据持久化

默认 `DatabaseStore`（PostgreSQL）。`interaction_event` 保存明细并预留可空 `user_id`；`aggregate_snapshot` 用 `ON CONFLICT DO UPDATE` 原子累加计数。表由 SQLAlchemy 启动建表，并执行轻量迁移（补列、回填、非空约束）。设置 `STORE_BACKEND=memory` 可切换内存存储用于测试。

## 10. 测试

```powershell
cd server
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
