# Client

当前客户端为原生 Android App，项目目录为：

```text
client/android
```

## 页面流程

1. `DramaListActivity` 请求 `GET /api/dramas`，展示短剧列表。
2. 点击短剧后，`EpisodeListActivity` 请求 `GET /api/dramas/{id}/episodes`，展示剧集列表。
3. 点击剧集后，`EpisodePlayerActivity` 使用 Media3 ExoPlayer 播放 `video_url` 指向的 MP4。
4. 播放页请求 `GET /api/episodes/{id}/manifest`。
5. `InteractionScheduler` 根据 `start_ms` 和 `end_ms` 自动触发互动浮层。
6. 用户点击互动按钮后，客户端通过 `POST /api/interactions` 上报选择并展示聚合人数。

## 后端地址

Android 模拟器使用：

```text
http://10.0.2.2:3000/api/
```

真机调试时，将 `RetrofitClient.BASE_URL` 改为电脑的局域网 IP，例如：

```text
http://192.168.x.x:3000/api/
```

## 视频兜底

剧集的 `video_url` 为空时，播放器会使用远程示例 MP4。仓库内不包含 `sample.mp4`，正常演示时应由后端返回本地扫描出的真实视频地址。
