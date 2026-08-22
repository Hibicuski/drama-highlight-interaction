"""端到端集成验证：真实 PostgreSQL（docker postgres:16）+ 真实素材目录。

覆盖：
1. 管理端认证（401 / 通过）
2. 内容管理（dramas / episodes / 详情）
3. Manifest 版本流：新建草稿 → 编辑(reviewing) → 发布 → 客户端读路径生效
4. 部分唯一索引：第二次发布顶替旧 published 为 archived
5. scan 种子语义：重新扫描不覆盖已发布内容
6. AI 生成任务：受理 → worker 执行失败(ASR 未配置) → 重试回 pending
7. 审计日志可查
8. 客户端互动链路不受影响
"""
import json
import os
import sys
import time
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_ROOT))  # 使 `from app.main import app` 可解析
# 素材目录在仓库同级再上一级（Projects/drama），与 README 约定一致
DRAMA_ROOT = os.getenv("DRAMA_ROOT", str(SERVER_ROOT.parent.parent / "drama"))

os.environ["STORE_BACKEND"] = "database"
os.environ["DATABASE_URL"] = "postgresql+psycopg://drama:drama_dev@localhost:5432/drama_highlight"
os.environ["LOCAL_DRAMA_ROOT"] = DRAMA_ROOT
os.environ["ADMIN_TOKEN"] = "integration-test-token"
os.environ["ADMIN_WORKER_ENABLED"] = "1"
# 用独立临时目录放生成产物，避免污染仓库 server/data
os.environ["MANIFEST_ROOT"] = str(Path(os.environ.get("TEMP", ".")) / "dsh-integration-manifests")
os.environ["MANIFEST_INDEX_PATH"] = str(Path(os.environ.get("TEMP", ".")) / "dsh-integration-index.json")
os.environ["TRANSCRIPT_ROOT"] = str(Path(os.environ.get("TEMP", ".")) / "dsh-integration-transcripts")


def postgres_available() -> bool:
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 3})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


HEADERS = {"Authorization": "Bearer integration-test-token", "X-Admin-Operator": "integration-tester"}

VALID_PAYLOAD = {
    "content_id": "placeholder",
    "version": "0.2.0",
    "highlights": [
        {
            "id": "candidate-1",
            "start_ms": 12000,
            "end_ms": 17000,
            "type": "twist",
            "intensity": 0.9,
            "template": "dual-button",
            "payload": {
                "title": "身份曝光",
                "actions": [
                    {"key": "shuang", "label": "爽", "tone": "positive", "icon": "fire"},
                    {"key": "more", "label": "上头", "tone": "support", "icon": "boost"},
                ],
                "effect": "ratio-reveal",
            },
        },
        {
            "id": "candidate-2",
            "start_ms": 30000,
            "end_ms": 35000,
            "type": "satisfying",
            "intensity": 0.8,
            "template": "tap-boost",
            "payload": {
                "title": "当场认错",
                "actions": [{"key": "satisfied", "label": "解气", "tone": "positive", "icon": "check"}],
                "effect": "particle-burst",
            },
        },
    ],
}

results: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    results.append(f"[{status}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        print(f"\n!!! FAILED: {name}\n{detail}\n")


def main() -> int:
    if not postgres_available():
        print("SKIP: PostgreSQL not available (run `docker compose up -d postgres` first)")
        return 0

    from fastapi.testclient import TestClient  # noqa: E402

    from app.main import app  # noqa: E402

    with TestClient(app) as client:  # lifespan: worker 线程启动
        # ---------- 1. 认证 ----------
        check("无 token 返回 401", client.get("/admin/api/dramas").status_code == 401)
        check("错误 token 返回 401", client.get("/admin/api/dramas", headers={"Authorization": "Bearer nope"}).status_code == 401)
        r = client.get("/admin/api/dramas", headers=HEADERS)
        check("正确 token 可访问", r.status_code == 200)
        if r.status_code != 200:
            print("dramas response:", r.text)
            return 1
        dramas = r.json()
        check("扫描到 5 部短剧", len(dramas) == 5, f"got {len(dramas)}")
        drama = dramas[0]
        check("短剧带聚合统计", "episode_count" in drama and "total_interactions" in drama, str(drama))

        # ---------- 2. 剧集列表 ----------
        r = client.get(f"/admin/api/episodes?drama_id={drama['id']}", headers=HEADERS)
        check("剧集列表 200", r.status_code == 200)
        episodes = r.json()["items"]
        check("剧集列表非空", len(episodes) > 0, f"got {len(episodes)}")
        episode = episodes[0]
        content_id = episode["content_id"]
        check("剧集带 manifest_status", "manifest_status" in episode, str(episode.keys()))
        check("剧集带 highlight/interaction 计数", "highlight_count" in episode and "interaction_count" in episode)

        r = client.get(f"/admin/api/episodes/{content_id}", headers=HEADERS)
        check("剧集详情 200（含版本摘要）", r.status_code == 200 and "versions" in r.json())
        episode_detail = r.json()

        # ---------- 3. 版本流：草稿 → 审核 → 发布 → 客户端读路径 ----------
        payload = json.loads(json.dumps(VALID_PAYLOAD))
        payload["content_id"] = content_id
        r = client.post(f"/admin/api/contents/{content_id}/versions", json={"source": "manual"}, headers=HEADERS)
        check("新建草稿 201", r.status_code == 201, r.text)
        version = r.json()
        version_id = version["id"]
        check("草稿高光数为 0（复制空模板）", version["highlight_count"] == 0, str(version))

        r = client.put(
            f"/admin/api/contents/{content_id}/versions/{version_id}",
            json={"payload": payload, "status": "reviewing"},
            headers=HEADERS,
        )
        check("编辑草稿 200（校验+归一化）", r.status_code == 200, r.text)
        updated = r.json()
        check("归一化重建高光 id", updated["payload"]["highlights"][0]["id"].startswith("hl-"), updated["payload"]["highlights"][0]["id"])
        check("状态变为 reviewing", updated["status"] == "reviewing")

        # 非法 payload 必须 422 带 reasons（全部高光非法时整体拒绝；部分非法会被归一化丢弃）
        bad_payload = json.loads(json.dumps(payload))
        for highlight in bad_payload["highlights"]:
            highlight["end_ms"] = highlight["start_ms"] - 1  # 时间窗非法
        r = client.put(
            f"/admin/api/contents/{content_id}/versions/{version_id}",
            json={"payload": bad_payload},
            headers=HEADERS,
        )
        check("非法 payload 422 + reasons", r.status_code == 422 and r.json()["detail"]["reasons"], r.text)

        r = client.post(f"/admin/api/contents/{content_id}/versions/{version_id}/publish", headers=HEADERS)
        check("发布 200", r.status_code == 200, r.text)
        publish_resp = r.json()
        check("发布后 2 个高光", publish_resp["highlight_count"] == 2, str(publish_resp))

        # 客户端读路径（公开 API，无需 token）
        r = client.get(f"/api/contents/{content_id}/manifest")
        check("客户端 manifest 立即生效", r.status_code == 200, r.text)
        manifest = r.json()
        check("客户端读到发布版高光", len(manifest["highlights"]) == 2, str(manifest))
        check("客户端高光 id 为归一化 id", manifest["highlights"][0]["id"].startswith("hl-"))
        first_hl = manifest["highlights"][0]["id"]

        # 重复发布同一版本：幂等
        r = client.post(f"/admin/api/contents/{content_id}/versions/{version_id}/publish", headers=HEADERS)
        check("重复发布幂等 200", r.status_code == 200, r.text)

        # ---------- 4. 部分唯一索引：第二个 published 顶替第一个 ----------
        payload_v2 = json.loads(json.dumps(payload))
        payload_v2["highlights"][0]["start_ms"] = 5000
        payload_v2["highlights"][0]["end_ms"] = 9000
        r = client.post(f"/admin/api/contents/{content_id}/versions", json={"payload": payload_v2, "source": "ai_edited"}, headers=HEADERS)
        check("新建第二个版本 201", r.status_code == 201, r.text)
        version2_id = r.json()["id"]
        r = client.post(f"/admin/api/contents/{content_id}/versions/{version2_id}/publish", headers=HEADERS)
        check("第二次发布 200", r.status_code == 200, r.text)
        check("第二个版本替换了第一个", r.json()["replaced_version_id"] == version_id, r.text)

        r = client.get(f"/admin/api/contents/{content_id}/versions", headers=HEADERS)
        versions = r.json()
        status_by_id = {v["id"]: v["status"] for v in versions}
        check("只有一个是 published", list(status_by_id.values()).count("published") == 1, str(status_by_id))
        check("第一个版本被归档", status_by_id[version_id] == "archived", str(status_by_id))

        r = client.get(f"/api/contents/{content_id}/manifest")
        check("客户端读到新版本", r.json()["highlights"][0]["start_ms"] == 5000, r.text)

        # 回滚到第一个版本
        r = client.post(f"/admin/api/contents/{content_id}/versions/{version_id}/rollback", headers=HEADERS)
        check("回滚 200", r.status_code == 200, r.text)
        check("回滚顶替当前 published", r.json()["replaced_version_id"] == version2_id, r.text)
        r = client.get(f"/api/contents/{content_id}/manifest")
        check("客户端读回第一版", r.json()["highlights"][0]["start_ms"] == 12000, r.text)

        # ---------- 5. scan 种子语义：不覆盖已发布 ----------
        r = client.post("/admin/api/scan", headers=HEADERS)
        check("scan 200", r.status_code == 200, r.text)
        check("scan 返回统计", r.json().get("episodes_scanned", 0) == 25, r.text)
        r = client.get(f"/api/contents/{content_id}/manifest")
        check("scan 后线上内容不变", r.json()["highlights"][0]["start_ms"] == 12000, r.text)

        # ---------- 6. 生成任务：受理 → worker 失败(ASR 未配置) → 重试 ----------
        r = client.post("/admin/api/generation/tasks", json={"content_id": content_id}, headers=HEADERS)
        check("创建任务 202", r.status_code == 202, r.text)
        task_id = r.json()["task_id"]

        # 冲突：同 content_id 已有 pending/running 任务
        r = client.post("/admin/api/generation/tasks", json={"content_id": content_id}, headers=HEADERS)
        check("重复任务 409", r.status_code == 409, r.text)

        deadline = time.time() + 30
        task_status = "pending"
        while time.time() < deadline:
            r = client.get(f"/admin/api/generation/tasks/{task_id}", headers=HEADERS)
            task_status = r.json()["status"]
            if task_status in ("succeeded", "failed"):
                break
            time.sleep(1)
        check("worker 领取并结束任务", task_status in ("succeeded", "failed"), f"status={task_status}")
        task = r.json()
        check("失败时记录 error_message", task_status == "failed" and bool(task.get("error_message")), str(task))

        r = client.post(f"/admin/api/generation/tasks/{task_id}/retry", headers=HEADERS)
        check("失败任务可重试 202", r.status_code == 202, r.text)
        check("重试后回 pending", r.json()["status"] == "pending", r.text)
        r = client.post(f"/admin/api/generation/tasks/{task_id}/retry", headers=HEADERS)
        check("非失败任务不可重试 409", r.status_code == 409, r.text)

        # ---------- 7. 审计日志 ----------
        r = client.get("/admin/api/audit-logs", headers=HEADERS)
        check("审计日志可查", r.status_code == 200 and r.json()["total"] > 0, r.text)
        operations = {item["operation"] for item in r.json()["items"]}
        check(
            "审计覆盖关键操作",
            {"create_version", "update_version", "publish", "rollback", "scan", "generate", "retry"} <= operations,
            str(operations),
        )
        r = client.get(f"/admin/api/audit-logs?target_type=manifest_version&target_id={version_id}", headers=HEADERS)
        check("按目标过滤审计", r.json()["total"] >= 2, r.text)

        # ---------- 8. 客户端互动链路不受影响 ----------
        r = client.post(
            "/api/interactions",
            json={"content_id": content_id, "highlight_id": first_hl, "action": "shuang", "session_id": "device_integration"},
        )
        check("互动上报 200", r.status_code == 200, r.text)
        r = client.get(f"/api/highlights/{first_hl}/aggregate")
        check("聚合查询 200", r.status_code == 200 and r.json()["count"] >= 1, r.text)

        r = client.get(f"/admin/api/episodes?drama_id={drama['id']}", headers=HEADERS)
        ep2 = next(e for e in r.json()["items"] if e["content_id"] == content_id)
        check("剧集互动计数已更新", ep2["interaction_count"] >= 1, str(ep2))

    print("\n================ RESULTS ================")
    passed = sum(1 for line in results if line.startswith("[PASS]"))
    failed = sum(1 for line in results if line.startswith("[FAIL]"))
    for line in results:
        print(line)
    print(f"\nTOTAL: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
