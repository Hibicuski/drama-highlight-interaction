# Drama Highlight Interaction

短剧高光互动 Demo。当前已完成 Android 客户端和 FastAPI 后端 MVP：展示真实短剧列表和剧集列表、播放本地 MP4，并在指定剧情时间点展示互动浮层。

## 当前能力

- 从后端加载真实短剧和剧集数据
- 使用 Media3 ExoPlayer 播放 MP4
- 获取每集高光 Manifest
- 根据播放进度自动展示双按钮互动浮层
- 上报用户选择并展示聚合互动人数
- 在单次播放中避免重复展示同一个高光点

## 目录

```text
.
├── client/
│   └── android/        # Android Studio 项目
├── server/             # FastAPI 后端、本地视频扫描和接口测试
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

后端启动时扫描仓库同级的 `drama` 文件夹。安装 FFmpeg 后，服务会通过 `ffprobe` 读取每集真实时长：

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
- `GET /api/episodes/{id}/manifest`
- `POST /api/interactions`
- `GET /api/highlights/{id}/aggregate`

剧集数据中的 `video_url` 应指向可访问的 MP4 地址。如果地址为空，客户端会使用远程示例视频兜底；仓库内不再包含本地示例 MP4。

## 文档

- [Android 运行说明](client/android/README.md)
- [后端运行说明](server/README.md)
- [分支管理](docs/branching.md)
