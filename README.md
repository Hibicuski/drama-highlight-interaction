# Drama Highlight Interaction

短剧高光互动项目，目标是在短剧播放时间轴上提供低门槛、强反馈、可扩展的即时互动闭环。

## 项目定位

本项目优先完成“高光剧情互动”主线：短剧列表、播放、时间点打标、互动触发、互动结果展示和服务部署。剧情续写或分支作为加分能力，以轻量文本卡片或结局卡形式实现，避免在短周期内承担完整分支视频生成的高风险。

## MVP 闭环

1. 短剧列表与播放器基础能力
2. 高光点 Manifest 下发
3. 客户端按播放时间本地触发互动组件
4. 用户点击互动并获得可视化反馈
5. 服务端记录互动事件并返回群体聚合结果
6. 剧尾或关键节点提供轻量剧情续写能力

## 推荐技术路线

| 模块 | 建议方案 |
|---|---|
| 客户端 | Web 或 Android 播放器，优先保证演示闭环 |
| 高光触发 | 客户端基于本地播放时间轴触发 Manifest 中的高光点 |
| 服务端 API | 提供短剧、剧集、高光点、互动事件、聚合结果接口 |
| 存储 | PostgreSQL 存元数据，Redis 存热状态和实时聚合 |
| 动效 | Lottie / CSS Motion / 粒子反馈 |
| 生成能力 | 剧尾轻量续写卡，接入模型生成文本结果 |
| 部署 | 公有云容器或本地局域网 Local Server |

## 目录规划

```text
.
├── client/                 # 客户端播放器和互动浮层
├── server/                 # 服务端 API、存储和聚合逻辑
├── docs/                   # 技术文档、排期、分支策略
├── assets/                 # 设计素材、示例 Manifest、演示资源
└── recordings/             # 展示录屏，本地保存，不提交 Git
```

## 分支策略

详见 [docs/branching.md](docs/branching.md)。

核心分支：

- `main`: 稳定可演示版本
- `dev`: 日常开发整合分支
- `feat/android-player`: Android 或播放器能力
- `feat/server-api`: 服务端 API 与存储
- `feat/highlight-manifest`: 高光点标注与 Manifest
- `feat/interaction-overlay`: 互动浮层与可视化
- `feat/docs`: 文档、排期和演示材料

## 交付清单

- GitHub 项目源码
- 可运行 Demo
- 项目展示录屏
- 飞书技术文档
- AI 辅助使用说明
