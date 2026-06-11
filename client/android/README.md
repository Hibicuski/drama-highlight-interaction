# Android Client

短剧高光互动系统的 Android 客户端：加载短剧/剧集、播放 MP4，并在 Manifest 定义的剧情时间窗内展示互动浮层、上报互动并回显群体聚合结果。

## 1. 技术栈

| 关注点 | 选型 |
|---|---|
| 语言 / 构建 | Java、Gradle (AGP 9.2.1) |
| 播放 | Media3 ExoPlayer 1.8.0 (exoplayer / dash / datasource / ui) |
| 网络 | Retrofit 3.0.0 + Gson、OkHttp logging-interceptor |
| 图片 | Glide 5.0.5 |
| UI | AppCompat、Material、ConstraintLayout、RecyclerView、CardView |

工程使用 Android Studio 自带 JDK，无需单独配置本地 JDK。

## 2. 模块结构

```text
com.warren.shortdrama
├── core
│   ├── model/          # Drama / Episode / HighlightManifest / HighlightPoint / InteractionModels
│   ├── network/        # ApiService (Retrofit 接口) / RetrofitClient
│   ├── player/         # DramaPlayer (Media3 封装)
│   └── interaction/    # InteractionRepository / InteractionScheduler
└── feature
    ├── drama_list/     # DramaListActivity / DramaAdapter
    ├── episode_list/   # EpisodeListActivity / EpisodeAdapter
    └── episode_player/ # EpisodePlayerActivity / InteractionOverlayController
```

| 组件 | 职责 |
|---|---|
| `DramaListActivity` | 短剧列表入口，加载 `GET /dramas` |
| `EpisodeListActivity` | 剧集列表，加载 `GET /dramas/{id}/episodes` |
| `EpisodePlayerActivity` | 播放页，编排播放、Manifest 加载与互动流程 |
| `DramaPlayer` | Media3 ExoPlayer 封装，提供播放/暂停/进度查询 |
| `InteractionScheduler` | 主线程定时轮询播放进度，命中时间窗时触发高光 |
| `InteractionRepository` | Manifest 拉取、互动上报、`session_id` 管理、请求生命周期管理 |
| `InteractionOverlayController` | 互动浮层渲染、动效与反馈状态 |

## 3. 播放与互动时序

```text
EpisodePlayerActivity.onCreate
  │  从 Intent 取 contentId / videoUrl / 标题
  ├─▶ DramaPlayer 初始化（先不自动播放）
  └─▶ InteractionRepository.fetchManifest(contentId)
         成功 → 构建 InteractionScheduler → allowPlayback() 开始播放
         失败 → allowPlayback()（无互动，正常播放）

InteractionScheduler （每 tick 轮询 getCurrentPosition）
  │  进度落入 [startMs, endMs] 且该高光未展示过
  ├─▶ onShowHighlight → OverlayController 渲染浮层
  │      用户点击 → reportInteraction(contentId, highlightId, actionKey)
  │                   成功 → 回显聚合计数 / 失败 → 简易反馈
  └─▶ 离开时间窗 → onHideHighlight，单次播放内不重复展示同一高光
```

`session_id` 由 `InteractionRepository` 在首次使用时生成 `device_` 前缀 UUID，持久化到 `SharedPreferences`，随每次互动上报发送，用于服务端聚合与去标识统计。

## 4. 配置：后端地址

后端基址通过字符串资源配置（**不是** `RetrofitClient` 的常量）：

```xml
<!-- app/src/main/res/values/strings.xml -->
<string name="config_api_base_url" translatable="false">http://10.0.2.2:3000/api/</string>
```

- 模拟器：`http://10.0.2.2:3000/api/` 即代表宿主机的 `3000` 端口（默认值）。
- 真机：改为电脑的局域网 IP，例如 `http://192.168.x.x:3000/api/`，并确保服务端以 `--host 0.0.0.0` 启动、`PUBLIC_BASE_URL` 指向同一 IP。

`RetrofitClient` 在 base URL 变化时重建实例，DEBUG 构建下挂载 OkHttp Body 日志拦截器。

## 5. 构建与运行

1. 启动实现了所需 REST API 的服务端（监听 `3000`，见 [服务端说明](../../server/README.md)）。
2. 用 Android Studio 打开本目录 `client/android`，等待 Gradle 同步。
3. 运行 `app` 模块（模拟器或真机）。
4. 进入短剧列表 → 选择短剧与剧集 → 播放，进入高光时间窗后浮层出现并可提交互动。

命令行构建：

```powershell
.\gradlew.bat :app:assembleDebug
```

## 6. 网络层 API 映射

`ApiService`（Retrofit，相对 `config_api_base_url`）：

| 方法 | 端点 | 对应后端接口 |
|---|---|---|
| `getDramas()` | `GET dramas` | `/api/dramas` |
| `getEpisodes(id)` | `GET dramas/{id}/episodes` | `/api/dramas/{id}/episodes` |
| `getManifest(contentId)` | `GET contents/{id}/manifest` | `/api/contents/{content_id}/manifest` |
| `reportInteraction(body)` | `POST interactions` | `/api/interactions` |
| `getAggregation(id)` | `GET highlights/{id}/aggregate` | `/api/highlights/{id}/aggregate` |
