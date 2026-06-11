# 项目拆解与排期

## 目标

在最终交付前完成一个包含客户端和服务端的短剧高光互动闭环。评分优先级按“完整闭环、技术实现、创新探索、文档表达”排序。

## 模块拆解

| 模块 | 核心任务 | 交付物 |
|---|---|---|
| 播放器 | 短剧列表、播放、暂停、进度条、时间轴监听 | 可播放的客户端页面或 App |
| Manifest | 高光点结构、类型、触发时间、互动模板、payload | 示例 JSON 和下发接口 |
| 互动浮层 | 按高光类型展示按钮、动效、结果面板 | 爽点、反转、撒糖、名场面等组件 |
| 服务端 API | 剧集列表、高光点、互动上报、聚合结果 | REST API 或 WebSocket API |
| 聚合展示 | 点击数、占比、热度、实时反馈 | 群体感知可视化 |
| 剧情拓展 | 剧尾续写卡或结局卡 | 轻量生成结果 |
| 文档和演示 | 架构图、流程图、排期、AI 使用说明、录屏 | 飞书文档和展示视频 |

## 里程碑

| 阶段 | 时间 | 重点 |
|---|---|---|
| M1 | 5 月 23 日至 5 月 26 日 | 仓库、分支、技术文档骨架、Manifest 样例 |
| M2 | 5 月 27 日至 6 月 1 日 | 播放器、高光触发、基础互动浮层 |
| M3 | 6 月 2 日至 6 月 6 日 | 服务端 API、互动上报、聚合结果 |
| M4 | 6 月 7 日至 6 月 9 日 | 剧尾轻量续写、动效 polish、部署 |
| M5 | 6 月 10 日至 6 月 11 日 | 录屏、文档完善、最终演示验证 |

## 数据模型

| 表 | 字段 |
|---|---|
| `drama` | `id`, `title`, `poster`, `tags` |
| `episode` | `id`, `content_id`, `drama_id`, `title`, `video_url`, `duration_ms` |
| `highlight_point` | `id`, `content_id`, `start_ms`, `end_ms`, `type`, `intensity`, `payload` |
| `interaction_event` | `id`, `session_id`, `content_id`, `highlight_id`, `action`, `created_at`，`user_id`（预留，接入用户系统后使用） |
| `aggregate_snapshot` | `content_id`, `highlight_id`, `counter`, `updated_at` |
| `branch_session` | `id`, `session_id`, `content_id`, `prompt`, `result`, `status`，`user_id`（预留，接入用户系统后使用） |

> `user_id` 为预留的可空字段，当前互动与续写均以 `session_id` 标识访客，接入用户系统后再回填。

## AI 辅助说明

允许在需求分析、技术选型、代码生成、文档整理、测试用例设计和演示稿润色中使用 AI。最终文档需要说明 AI 参与范围、人工校验方式，以及关键实现由项目成员完成和验证。
