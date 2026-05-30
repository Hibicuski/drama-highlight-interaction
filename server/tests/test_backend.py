import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

EMPTY_ROOT = Path(tempfile.gettempdir()) / "drama-highlight-interaction-tests-empty"
EMPTY_ROOT.mkdir(exist_ok=True)
os.environ["LOCAL_DRAMA_ROOT"] = str(EMPTY_ROOT)

from app.db.models import InteractionRequest
from app.db.session import InMemoryStore
from app.main import parse_range_header, safe_media_path, safe_video_path
from app.services.media_scanner import POSTER_EXTENSIONS
from app.services.media_scanner import scan_local_dramas


class RangeHeaderTests(unittest.TestCase):
    def test_parses_open_ended_range(self) -> None:
        self.assertEqual((100, 999), parse_range_header("bytes=100-", 1000))

    def test_parses_suffix_range(self) -> None:
        self.assertEqual((800, 999), parse_range_header("bytes=-200", 1000))

    def test_rejects_invalid_and_out_of_bounds_ranges(self) -> None:
        for value in ("items=0-10", "bytes=abc-10", "bytes=1000-", "bytes=0-1,4-5"):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException) as context:
                    parse_range_header(value, 1000)
                self.assertEqual(416, context.exception.status_code)


class VideoPathTests(unittest.TestCase):
    def test_serves_only_video_files_within_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "episode.mp4"
            video_path.write_bytes(b"video")
            (root / "notes.txt").write_text("private", encoding="utf-8")

            self.assertEqual(video_path, safe_video_path(root, "episode.mp4"))

            with self.assertRaises(HTTPException) as context:
                safe_video_path(root, "notes.txt")
            self.assertEqual(404, context.exception.status_code)

            with self.assertRaises(HTTPException) as context:
                safe_video_path(root, "../outside.mp4")
            self.assertEqual(403, context.exception.status_code)

    def test_serves_only_supported_poster_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            poster_path = root / "poster.jpg"
            poster_path.write_bytes(b"poster")
            (root / "notes.txt").write_text("private", encoding="utf-8")

            self.assertEqual(poster_path, safe_media_path(root, "poster.jpg", POSTER_EXTENSIONS))

            with self.assertRaises(HTTPException) as context:
                safe_media_path(root, "notes.txt", POSTER_EXTENSIONS)
            self.assertEqual(404, context.exception.status_code)


class MediaScannerTests(unittest.TestCase):
    def test_scans_real_folder_and_maps_ffprobe_duration(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "测试短剧"
            drama_dir.mkdir()
            (drama_dir / "第2集.mp4").write_bytes(b"video")
            (drama_dir / "poster.jpg").write_bytes(b"poster")

            with patch("app.services.media_scanner.subprocess.check_output", return_value="12.345\n"):
                dramas, episodes, manifests = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertEqual(["测试短剧"], [drama.title for drama in dramas])
            self.assertIn("/posters/", dramas[0].poster)
            self.assertIn("%E6%B5%8B%E8%AF%95%E7%9F%AD%E5%89%A7", dramas[0].poster)
            self.assertEqual(12345, episodes[0].duration_ms)
            self.assertIn("%E6%B5%8B%E8%AF%95%E7%9F%AD%E5%89%A7", episodes[0].video_url)
            self.assertIn(episodes[0].id, manifests)

    def test_preserves_episode_numbers_from_file_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "缺集短剧"
            drama_dir.mkdir()
            (drama_dir / "第4集.mp4").write_bytes(b"video")
            (drama_dir / "第2集.mp4").write_bytes(b"video")

            with patch("app.services.media_scanner.subprocess.check_output", return_value="12\n"):
                _, episodes, _ = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertEqual([2, 4], [episode.episode_index for episode in episodes])


class InteractionStoreTests(unittest.TestCase):
    def test_counts_interactions_without_mutating_previous_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "测试短剧"
            drama_dir.mkdir()
            (drama_dir / "第1集.mp4").write_bytes(b"video")

            with (
                patch.dict(os.environ, {"LOCAL_DRAMA_ROOT": str(root)}),
                patch("app.services.media_scanner.subprocess.check_output", return_value="60\n"),
            ):
                store = InMemoryStore()

            request = InteractionRequest(
                episode_id=1001001,
                highlight_id="hl-1001001-001",
                action="satisfying",
            )
            first_response = store.report_interaction(request)

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda _: store.report_interaction(request), range(19)))

            self.assertEqual(1, first_response.count)
            self.assertEqual(20, store.get_aggregate(request.highlight_id).count)


if __name__ == "__main__":
    unittest.main()
