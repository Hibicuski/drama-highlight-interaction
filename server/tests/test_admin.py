"""管理后台（内容生产层）单元测试。

本文件不依赖 PostgreSQL，覆盖：
1. ManifestValidator：校验/归一化/逐条 reasons（无 DB 纯逻辑）；
2. 新表 schema：列、CHECK 约束、部分唯一索引、DDL 可编译（无连接编译验证）；
3. 工具函数：video_url → relative_path 反解。

DB 依赖的发布/任务集成链路需真实 Postgres（docker compose up -d postgres）后验证。
"""

import unittest
from copy import deepcopy

from sqlalchemy import CheckConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.orm import AdminOperationLogRow, Base, GenerationTaskRow, ManifestVersionRow
from app.services.generation_service import relative_path_from_video_url
from app.services.manifest_service import ManifestValidationError, ManifestValidator

VALID_PAYLOAD = {
    "content_id": "placeholder",
    "version": "0.2.0",
    "highlights": [
        {
            "id": "model-id",
            "start_ms": 12000,
            "end_ms": 17000,
            "type": "twist",
            "intensity": 1.0,
            "template": "dual-button",
            "payload": {
                "title": "身份曝光",
                "actions": [
                    {"key": "shuang", "label": "爽", "tone": "positive", "icon": "fire"},
                    {"key": "more", "label": "上头", "tone": "support", "icon": "boost"},
                ],
                "effect": "ratio-reveal",
            },
        }
    ],
}

EMPTY_PAYLOAD = {"content_id": "placeholder", "version": "0.2.0", "highlights": []}


class ManifestValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ManifestValidator()

    def test_valid_payload_is_normalized_with_rebuilt_ids(self) -> None:
        manifest = self.validator.validate_payload(deepcopy(VALID_PAYLOAD), "real-content", 60000)
        self.assertEqual("real-content", manifest.content_id)
        self.assertEqual("hl-real-content-001", manifest.highlights[0].id)
        self.assertEqual("0.2.0", manifest.version)

    def test_invalid_window_raises_with_reasons(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        payload["highlights"][0]["end_ms"] = payload["highlights"][0]["start_ms"] - 1
        with self.assertRaises(ManifestValidationError) as context:
            self.validator.validate_payload(payload, "real-content", 60000)
        self.assertTrue(context.exception.reasons)
        self.assertTrue(any("time window" in reason for reason in context.exception.reasons))

    def test_overlapping_windows_dedupe_to_one_valid_highlight(self) -> None:
        # 重叠的候选会被丢弃；只要还剩合法高光，归一化仍返回（不整体失败）
        payload = deepcopy(VALID_PAYLOAD)
        payload["highlights"].append(deepcopy(payload["highlights"][0]))
        manifest = self.validator.validate_payload(payload, "real-content", 60000)
        self.assertEqual(1, len(manifest.highlights))

    def test_missing_required_field_produces_reasons(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        del payload["highlights"][0]["start_ms"]  # HighlightPoint.start_ms 必填
        with self.assertRaises(ManifestValidationError) as context:
            self.validator.validate_payload(payload, "real-content", 60000)
        self.assertTrue(any("start_ms" in reason for reason in context.exception.reasons))

    def test_shape_only_accepts_empty_highlights_for_draft(self) -> None:
        # 草稿可以没有可用高光（中间状态），发布时才要求全量合法
        manifest = self.validator.validate_shape(deepcopy(EMPTY_PAYLOAD))
        self.assertEqual([], manifest.highlights)

    def test_shape_only_rejects_malformed_payload(self) -> None:
        # highlights 类型错误（应为 list）结构校验即失败
        with self.assertRaises(ManifestValidationError):
            self.validator.validate_shape({"content_id": "x", "version": "0.2.0", "highlights": "not-a-list"})

    def test_empty_manifest_cannot_be_published(self) -> None:
        with self.assertRaises(ManifestValidationError):
            self.validator.validate_payload(deepcopy(EMPTY_PAYLOAD), "real-content", 60000)

    def test_non_allowlisted_highlight_type_is_rejected(self) -> None:
        payload = deepcopy(VALID_PAYLOAD)
        payload["highlights"][0]["type"] = "random-type"
        with self.assertRaises(ManifestValidationError):
            self.validator.validate_payload(payload, "real-content", 60000)


class AdminSchemaTests(unittest.TestCase):
    def test_new_tables_registered(self) -> None:
        for table_name in ("manifest_version", "generation_task", "admin_operation_log"):
            self.assertIn(table_name, Base.metadata.tables)

    def test_manifest_version_constraints_and_partial_unique_index(self) -> None:
        table = Base.metadata.tables["manifest_version"]
        self.assertIn("status", table.columns)
        self.assertIn("published_at", table.columns)
        check_names = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
        self.assertIn("ck_manifest_version_status", check_names)
        self.assertIn("ck_manifest_version_source", check_names)
        index = next(i for i in table.indexes if i.name == "uq_manifest_version_published")
        self.assertTrue(index.unique)
        self.assertIsNotNone(index.dialect_options["postgresql"].get("where"))

    def test_generation_task_has_task_type_and_status_checks(self) -> None:
        table = Base.metadata.tables["generation_task"]
        self.assertIn("task_type", table.columns)
        self.assertIn("relative_path", table.columns)
        self.assertIn("created_version_id", table.columns)
        check_names = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
        self.assertIn("ck_generation_task_type", check_names)
        self.assertIn("ck_generation_task_status", check_names)

    def test_admin_operation_log_target_columns_are_not_nullable(self) -> None:
        table = Base.metadata.tables["admin_operation_log"]
        self.assertFalse(table.columns["target_type"].nullable)
        self.assertFalse(table.columns["target_id"].nullable)
        check_names = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
        self.assertIn("ck_admin_log_target_type", check_names)

    def test_ddl_compiles_for_postgres(self) -> None:
        dialect = postgresql.dialect()
        for table in (
            Base.metadata.tables["manifest_version"],
            Base.metadata.tables["generation_task"],
            Base.metadata.tables["admin_operation_log"],
        ):
            ddl = str(CreateTable(table).compile(dialect=dialect))
            self.assertIn("CREATE TABLE", ddl)
            self.assertIn(table.name, ddl)


class VideoUrlHelperTests(unittest.TestCase):
    def test_decodes_plain_relative_path(self) -> None:
        self.assertEqual(
            "drama/episode-1.mp4",
            relative_path_from_video_url("http://127.0.0.1:3000/videos/drama/episode-1.mp4"),
        )

    def test_decodes_url_encoded_chinese_path(self) -> None:
        self.assertEqual(
            "都市赘婿/第01集.mp4",
            relative_path_from_video_url(
                "http://127.0.0.1:3000/videos/%E9%83%BD%E5%B8%82%E8%B5%98%E5%A9%BF/%E7%AC%AC01%E9%9B%86.mp4"
            ),
        )

    def test_ignores_path_without_videos_prefix(self) -> None:
        self.assertEqual(
            "other/x.mp4",
            relative_path_from_video_url("http://127.0.0.1:3000/other/x.mp4"),
        )


if __name__ == "__main__":
    unittest.main()
