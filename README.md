# Drama Highlight Interaction

短剧高光互动 Demo。当前已完成 Android 客户端和 FastAPI 后端 MVP：展示真实短剧列表和剧集列表、播放本地 MP4，并在指定剧情时间点展示互动浮层。

## 当前能力

- 从后端加载真实短剧和剧集数据
- 展示短剧目录中的可选封面图片
- 使用 Media3 ExoPlayer 播放 MP4
- 获取每集高光 Manifest
- 支持离线 ASR 转写和高光 Manifest 生成，可选实验文本级说话人标注
- 根据播放进度自动展示互动浮层
- 支持 1 到 3 个互动选项、白名单 UI 风格、选项图标和选项色彩
- 上报用户选择并展示聚合互动人数
- 在单次播放中避免重复展示同一个高光点
- 没有合格 Manifest 时返回空高光列表，不使用固定假高光兜底

## 目录

```text
.
├── client/
│   └── android/        # Android Studio 项目
├── server/             # FastAPI 后端、本地视频扫描、AI 高光生成和接口测试
├── docs/               # 项目规划和分支说明
└── assets/             # Manifest 示例等资源
```

## Android 客户端

使用 Android Studio 打开 `client/android`，运行 `app` 模块。项目使用 Android Studio 自带 JDK，无需额外配置本地 JDK。

Android 模拟器通过以下地址访问电脑上的后端：

```text
http://10.0.2.2:3000/api/
```

真机调试时，需要将 `RetrofitClient.BASE_URL` 改为电脑的局域网 IP。

## FastAPI 后端

后端默认使用 PostgreSQL 持久化短剧、剧集、高光点、互动事件和聚合快照。先启动本地数据库：

```powershell
docker compose up -d postgres
```

后端启动时扫描仓库同级的 `drama` 文件夹，同步元数据和高光点到 PostgreSQL。安装 FFmpeg 后，服务会通过 `ffprobe` 读取每集真实时长：

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
ffprobe -version
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

详细配置见 [后端运行说明](server/README.md)。

## 后端接口

Android 客户端依赖以下 REST API：

- `GET /api/dramas`
- `GET /api/dramas/{id}/episodes`
- `GET /api/contents/{content_id}/manifest`
- `POST /api/interactions`
- `GET /api/highlights/{id}/aggregate`

剧集数据中的 `content_id` 是由视频相对路径 hash 得到的稳定内容 ID。`Episode.id` 仍可能存在，但只作为当前扫描结果里的运行时数字 ID，不再用于 Manifest 文件名、Manifest 查询或互动上报。

互动上报必须包含客户端本地持久化的 `session_id`，Android 会在首次使用时生成 `device_` 前缀的 UUID。服务端会写入 `interaction_event`，并同步更新 `aggregate_snapshot`。因此服务重启后，已经产生的互动人数和动作分布不会丢失。后续接用户系统时，可在同一事件表补充可空的 `user_id`。

## 文档

- [Android 运行说明](client/android/README.md)
- [后端运行说明](server/README.md)
- [分支管理](docs/branching.md)
