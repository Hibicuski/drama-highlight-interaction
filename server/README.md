# Drama FastAPI Server

短剧高光互动 Demo 的 Python + FastAPI 后端。当前使用内存存储，启动时扫描本地短剧文件夹，并优先加载已经离线生成好的高光互动 Manifest。

## 前置环境

- Python 3.11 或更高版本
- FFmpeg，其中需要用到 `ffmpeg` 和 `ffprobe`

先确认 `ffprobe` 已经可以执行：

```powershell
ffprobe -version
```

如果 FFmpeg 没有加入 `PATH`，可以通过环境变量指定完整路径：

```powershell
$env:FFMPEG_PATH="C:\path\to\ffmpeg.exe"
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
- `GET /api/contents/{content_id}/manifest`
- `POST /api/interactions`
- `GET /api/highlights/{id}/aggregate`

互动数据目前保存在内存中，服务重启后会清空。`db/schema.sql` 是下一阶段接入真实数据库时使用的结构草案。

以下 AI 接口已经预留：

- `POST /api/ai/highlight-candidates`
- `POST /api/ai/continuation`

其中高光候选接口会在配置文本模型后调用真实模型；剧情续写接口目前仍返回本地占位结果。

## 稳定内容 ID

Manifest、转写文件、Manifest 查询和互动上报都使用稳定的 `content_id`。

`content_id` 由视频相对路径生成 hash，例如：

```text
relative_path = 十八岁太奶奶驾到，重整家族荣耀第三部/第1集.mp4
content_id    = 2fe8f92ec371216d
```

对应文件：

```text
server/data/manifests/2fe8f92ec371216d.json
server/data/transcripts/2fe8f92ec371216d.json
server/data/index.json
```

`index.json` 只用于人工查看 hash 与视频路径的对应关系。新增短剧后，动态数字 `Episode.id` 可能变化，但已有 Manifest 不会套错剧集。

## AI 高光 Manifest 离线生成

播放链路不会实时等待模型。对于没有字幕的 MP4，先离线提取音频并转写，再让模型生成带时间窗口的互动 Manifest。生成文件默认保存在 `server/data/`，服务重启扫描视频时会优先加载生成结果；没有生成文件时继续使用默认 Manifest。

配置 OpenAI 兼容的文本模型和语音识别模型。代码只依赖三项通用配置：`MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME`。可以参考 `.env.example`：

```powershell
$env:MODEL_BASE_URL="https://your-openai-compatible-endpoint/v1"
$env:MODEL_API_KEY="replace-me"
$env:MODEL_NAME="replace-me"
$env:ASR_BASE_URL="https://your-audio-transcription-endpoint/v1"
$env:ASR_API_KEY="replace-me"
$env:ASR_MODEL="whisper-1"
```

使用火山方舟 `Doubao-Seed-2.0-lite` 时，填写官方 Model ID 即可。没有配置独立 `ASR_MODEL` 时，脚本会调用 Responses API 的音频理解能力完成第一版转写：

```powershell
$env:MODEL_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
$env:MODEL_API_KEY="仅保存在本机的 API Key"
$env:MODEL_NAME="doubao-seed-2-0-lite-260428"
Remove-Item Env:ASR_BASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:ASR_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ASR_MODEL -ErrorAction SilentlyContinue
```

切换到 OpenAI 或其他兼容服务时，不需要改业务代码，只换环境变量：

```powershell
# OpenAI 官方接口：MODEL_BASE_URL 可以不设置
Remove-Item Env:MODEL_BASE_URL -ErrorAction SilentlyContinue
$env:MODEL_API_KEY="你的 OpenAI API Key"
$env:MODEL_NAME="你选择的 OpenAI 模型名"

# 其他 OpenAI-compatible 服务
$env:MODEL_BASE_URL="https://provider.example.com/v1"
$env:MODEL_API_KEY="对应服务的 API Key"
$env:MODEL_NAME="对应服务的模型名"
```

为单集视频生成高光 Manifest：

```powershell
cd server
.\.venv\Scripts\python.exe -m app.scripts.generate_episode_manifest `
  "D:\videos\drama\短剧名称\第1集.mp4" `
  --local-drama-root "D:\videos\drama" `
  --summary "女主回归家族并揭露身份骗局"
```

如果已经有 ASR 的 `verbose_json` 转写结果，可以跳过 FFmpeg 和在线转写：

```powershell
.\.venv\Scripts\python.exe -m app.scripts.generate_episode_manifest `
  "D:\videos\drama\短剧名称\第1集.mp4" `
  --local-drama-root "D:\videos\drama" `
  --transcript-json "D:\videos\第1集-transcript.json"
```

文本模型输出会经过后端规则校验：高光时间窗口必须有效且不重叠，组件、动效、选项 tone 和 icon 必须来自白名单，互动选项必须可用。如果模型第一次返回的 JSON 无法解析或不满足规则，后端会自动请求一次修复。

## 批量生成

仓库内置 PowerShell 批处理脚本。脚本会扫描 `Projects/drama` 下的全部短剧，按视频相对路径 hash 生成稳定文件名，并逐集生成 Manifest。API Key 通过隐藏输入读取，只保存在当前 PowerShell 进程中，不会写入文件。

先预览待处理剧集，不会调用模型：

```powershell
cd server
.\scripts\generate_all_manifests.cmd -DryRun
```

建议先生成一集，确认模型输出质量和额度消耗：

```powershell
.\scripts\generate_all_manifests.cmd -Limit 1
```

批处理脚本默认使用火山方舟 Model ID `doubao-seed-2-0-lite-260428` 和方舟 Base URL。切换其他可用模型或服务：

```powershell
.\scripts\generate_all_manifests.cmd -BaseUrl "https://provider.example.com/v1" -ModelName "your-model" -Limit 1
```

使用 OpenAI 官方接口时，用 `-UseOpenAIDefaultBaseUrl` 让 SDK 使用默认 OpenAI 地址：

```powershell
.\scripts\generate_all_manifests.cmd -UseOpenAIDefaultBaseUrl -ModelName "your-openai-model" -Limit 1
```

确认后批量生成全部剧集：

```powershell
.\scripts\generate_all_manifests.cmd
```

已有 Manifest 默认会跳过。需要覆盖已有结果时使用：

```powershell
.\scripts\generate_all_manifests.cmd -Force
```

已有转写文件默认会复用，避免重复消耗音频理解调用。需要重新转写时使用：

```powershell
.\scripts\generate_all_manifests.cmd -Retranscribe -Limit 1
```

如果 FFmpeg 没有加入 `PATH`，显式指定其 `bin` 目录：

```powershell
.\scripts\generate_all_manifests.cmd -FfmpegBin "D:\ffmpeg\bin" -Limit 1
```

`.cmd` 启动器会自动为当前命令临时绕过 PowerShell 脚本执行策略，不会修改系统配置。也可以直接运行 `.ps1`：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\generate_all_manifests.ps1 -DryRun
```

## 测试

```powershell
cd server
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
