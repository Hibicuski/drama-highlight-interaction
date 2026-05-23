# Git 分支管理

## 长期分支

| 分支 | 作用 | 合并规则 |
|---|---|---|
| `main` | 稳定可演示版本，只保留已验证功能 | 只从 `dev` 合并，合并前完成演示验证 |
| `dev` | 日常开发整合分支 | 功能分支完成后合入 |

## 功能分支

| 分支 | 范围 |
|---|---|
| `feat/android-player` | 播放器基础能力、时间轴监听、端侧播控 |
| `feat/server-api` | 短剧、剧集、高光点、互动事件、聚合结果 API |
| `feat/highlight-manifest` | 高光点数据结构、标注样例、Manifest 下发格式 |
| `feat/interaction-overlay` | 高光互动组件、视觉反馈、群体结果展示 |
| `feat/docs` | 技术文档、流程图、排期、演示说明 |

## 推荐流程

1. 从 `dev` 拉出功能分支。
2. 在功能分支完成小步提交。
3. 自测通过后合并回 `dev`。
4. `dev` 达到可演示状态后合并到 `main`。
5. 重要演示节点在 `main` 打 tag，例如 `demo-v0.1`。

## 提交信息建议

```text
feat: add highlight manifest schema
fix: avoid duplicate interaction trigger
docs: add module breakdown and schedule
chore: initialize repository structure
```
