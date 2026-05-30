# Drama FastAPI Server

短剧高光互动 Demo 的 Python + FastAPI 后端。当前使用内存存储，启动时扫描本地短剧文件夹，不会生成英文假数据。

## 前置环境

- Python 3.11 或更高版本
- FFmpeg，其中需要用到 `ffprobe`

先确认 `ffprobe` 已经可以执行：

```powershell
ffprobe -version
```

如果 `ffprobe` 没有加入 `PATH`，可以通过环境变量指定完整路径：

```powershell
$env:FFPROBE_PATH="C:\path\to\ffprobe.exe"
```

没有安装或配置 `ffprobe` 时，服务仍可启动，但剧集接口中的 `duration_ms` 会返回 `0`。

## 启动

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

启动后可以打开：

- 健康检查：`http://localhost:3000/health`
- Swagger 接口文档：`http://localhost:3000/docs`

## 本地短剧

服务默认扫描仓库同级的 `drama` 文件夹：

```text
Projects/
├── drama-highlight-interaction/
└── drama/
    └── 短剧名称/
        ├── poster.jpg
        ├── 第1集.mp4
        └── 第2集.mp4
```

每个一级子文件夹是一部短剧，其中直接包含的 `.mp4`、`.mov`、`.mkv` 或 `.avi` 文件会被识别为剧集。服务使用 `ffprobe` 读取每集真实时长，并通过以下接口提供视频文件：

```text
GET /videos/{relative_path}
```

封面图片是可选的。可以在短剧目录下放入 `.jpg`、`.jpeg`、`.png` 或 `.webp` 图片。优先使用名为 `poster`、`cover` 或 `封面` 的图片，否则使用目录中的第一张图片。封面通过以下接口提供：

```text
GET /posters/{relative_path}
```

视频接口支持 HTTP Range 请求，可以满足播放器拖动进度条和分段加载。需要自定义短剧目录时，设置：

```powershell
$env:LOCAL_DRAMA_ROOT="D:\videos\drama"
```

短剧列表会在服务启动时扫描。增删视频文件后，重启服务即可重新加载。

## Android 模拟器和真机

Android 模拟器通过以下地址访问电脑：

```text
http://10.0.2.2:3000/api/
```

真机调试时，将视频地址改为电脑的局域网 IP：

```powershell
$env:PUBLIC_BASE_URL="http://192.168.x.x:3000"
uvicorn app.main:app --host 0.0.0.0 --port 3000
```

Android 客户端中的 `RetrofitClient.BASE_URL` 也需要改为相同局域网 IP 下的 `/api/` 地址。

## API

- `GET /api/dramas`
- `GET /api/dramas/{id}/episodes`
- `GET /api/episodes/{id}/manifest`
- `POST /api/interactions`
- `GET /api/highlights/{id}/aggregate`

互动数据目前保存在内存中，服务重启后会清空。`db/schema.sql` 是下一阶段接入真实数据库时使用的结构草案。

以下 AI 接口目前只返回本地占位结果，不会调用真实模型：

- `POST /api/ai/highlight-candidates`
- `POST /api/ai/continuation`

## 测试

```powershell
cd server
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
