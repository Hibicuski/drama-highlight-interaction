# Android Client

使用 Android Studio 直接打开本目录：

```text
client/android
```

## 运行

1. 启动实现了所需 REST API 的后端服务，监听电脑的 `3000` 端口。
2. 在 Android Studio 中等待 Gradle 同步完成。
3. 使用模拟器运行 `app` 模块。
4. 打开短剧列表，选择短剧和剧集进行播放。
5. 播放进入 Manifest 定义的时间窗后，确认互动浮层出现并可提交选择。

项目使用 Android Studio 自带 JDK，无需单独安装或配置 JDK。命令行验证时可执行：

```powershell
.\gradlew.bat :app:assembleDebug
```

## 关键实现

- `DramaListActivity`：短剧列表入口
- `EpisodeListActivity`：剧集列表
- `EpisodePlayerActivity`：播放器页面和互动流程编排
- `DramaPlayer`：Media3 ExoPlayer 封装
- `InteractionScheduler`：根据 Manifest 时间窗调度互动浮层
- `InteractionRepository`：Manifest 获取和互动上报
- `InteractionOverlayController`：双按钮浮层、动画和反馈状态

模拟器通过 `http://10.0.2.2:3000/api/` 访问电脑上的后端。客户端不再依赖仓库内的本地示例视频。
