import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from openai import BadRequestError

EMPTY_ROOT = Path(tempfile.gettempdir()) / "drama-highlight-interaction-tests-empty"
EMPTY_ROOT.mkdir(exist_ok=True)
os.environ["LOCAL_DRAMA_ROOT"] = str(EMPTY_ROOT)

from app.db.models import InteractionRequest
from app.db.session import InMemoryStore
from app.main import get_poster, parse_range_header, safe_media_path, safe_video_path
from app.services.episode_manifest_pipeline import extract_audio, format_timed_transcript, generate_episode_manifest
from app.services.highlight_generator import generate_highlight_candidates
from app.db.models import HighlightCandidateRequest
from app.services.manifest_store import content_id_from_relative_path, load_manifest, parse_model_manifest, save_manifest
from app.services.media_scanner import DEFAULT_POSTER_FILE_NAME, POSTER_EXTENSIONS
from app.services.media_scanner import scan_local_dramas
from app.services.model_client import ModelClient, extract_responses_output_text, is_unsupported_json_mode_error


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
            drama_dir = root / "test-drama"
            drama_dir.mkdir()
            (drama_dir / "episode-1.mp4").write_bytes(b"video")
            (drama_dir / "poster.jpg").write_bytes(b"poster")

            with patch("app.services.media_scanner.subprocess.check_output", return_value="12.345\n"):
                dramas, episodes, manifests = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertEqual(["test-drama"], [drama.title for drama in dramas])
            self.assertIn("/posters/", dramas[0].poster)
            self.assertIn("test-drama", dramas[0].poster)
            self.assertEqual(12345, episodes[0].duration_ms)
            self.assertIn("test-drama", episodes[0].video_url)
            self.assertIn(episodes[0].content_id, manifests)

    def test_uses_episode_poster_and_falls_back_for_drama_poster(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "posterless-drama"
            drama_dir.mkdir()
            (drama_dir / "episode-1.mp4").write_bytes(b"video")
            (drama_dir / "episode-1.jpg").write_bytes(b"episode-poster")

            with patch("app.services.media_scanner.subprocess.check_output", return_value="12\n"):
                dramas, episodes, _ = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertIn("/posters/posterless-drama/episode-1.jpg", dramas[0].poster)
            self.assertEqual(dramas[0].poster, episodes[0].poster)

    def test_generates_episode_poster_when_image_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "generated-poster-drama"
            drama_dir.mkdir()
            (drama_dir / "episode-1.mp4").write_bytes(b"video")

            def fake_run(command, **kwargs):
                Path(command[-1]).write_bytes(b"generated-poster")
                return SimpleNamespace(returncode=0)

            with (
                patch("app.services.media_scanner.subprocess.check_output", return_value="12\n"),
                patch("app.services.media_scanner.subprocess.run", side_effect=fake_run),
            ):
                dramas, episodes, _ = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertIn("/posters/.generated-posters/", episodes[0].poster)
            self.assertTrue((root / ".generated-posters").exists())
            self.assertEqual(episodes[0].poster, dramas[0].poster)

    def test_uses_default_poster_when_episode_poster_cannot_be_generated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "default-poster-drama"
            drama_dir.mkdir()
            (drama_dir / "episode-1.mp4").write_bytes(b"video")

            with (
                patch("app.services.media_scanner.subprocess.check_output", return_value="12\n"),
                patch("app.services.media_scanner.subprocess.run", side_effect=OSError("ffmpeg missing")),
            ):
                dramas, episodes, _ = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertEqual(f"http://10.0.2.2:3000/posters/{DEFAULT_POSTER_FILE_NAME}", dramas[0].poster)
            self.assertEqual(dramas[0].poster, episodes[0].poster)

    def test_serves_builtin_default_poster(self) -> None:
        response = get_poster(DEFAULT_POSTER_FILE_NAME)

        self.assertEqual("image/png", response.media_type)
        self.assertGreater(len(response.body), 0)

    def test_preserves_episode_numbers_from_file_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "missing-episodes"
            drama_dir.mkdir()
            (drama_dir / "episode-2.mp4").write_bytes(b"video")
            (drama_dir / "episode-4.mp4").write_bytes(b"video")

            with patch("app.services.media_scanner.subprocess.check_output", return_value="12\n"):
                _, episodes, _ = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertEqual([2, 4], [episode.episode_index for episode in episodes])

    def test_loads_generated_manifest_instead_of_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as manifest_temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "generated-highlight-drama"
            drama_dir.mkdir()
            (drama_dir / "episode-1.mp4").write_bytes(b"video")
            manifest_root = Path(manifest_temp_dir)
            content_id = content_id_from_relative_path("generated-highlight-drama/episode-1.mp4")
            (manifest_root / f"{content_id}.json").write_text(
                ManifestGenerationTests.MODEL_JSON,
                encoding="utf-8",
            )

            with (
                patch.dict(os.environ, {"MANIFEST_ROOT": str(manifest_root)}),
                patch("app.services.media_scanner.subprocess.check_output", return_value="60\n"),
            ):
                _, episodes, manifests = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertEqual(f"hl-{episodes[0].content_id}-001", manifests[episodes[0].content_id].highlights[0].id)
            self.assertTrue(manifests[episodes[0].content_id].highlights[0].payload.title)


class InteractionStoreTests(unittest.TestCase):
    def test_counts_interactions_without_mutating_previous_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "test-drama"
            drama_dir.mkdir()
            (drama_dir / "episode-1.mp4").write_bytes(b"video")

            with (
                patch.dict(os.environ, {"LOCAL_DRAMA_ROOT": str(root)}),
                patch("app.services.media_scanner.subprocess.check_output", return_value="60\n"),
            ):
                store = InMemoryStore()

            request = InteractionRequest(
                content_id=store.episodes[0].content_id,
                highlight_id=f"hl-{store.episodes[0].content_id}-001",
                action="satisfying",
            )
            first_response = store.report_interaction(request)

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda _: store.report_interaction(request), range(19)))

            self.assertEqual(1, first_response.count)
            self.assertEqual(20, store.get_aggregate(request.highlight_id).count)


class ManifestGenerationTests(unittest.TestCase):
    MODEL_JSON = """{
      "content_id": "model-content",
      "version": "draft",
      "highlights": [
        {
          "id": "model-id",
          "start_ms": 12000,
          "end_ms": 17000,
          "type": "revenge",
          "intensity": 1.3,
          "template": "dual-button",
          "payload": {
            "title": "evidence reveal",
            "actions": [
              {"key": "satisfying", "label": "nice", "tone": "positive", "icon": "fire"},
              {"key": "more", "label": "more", "tone": "support", "icon": "boost"}
            ],
            "effect": "particle-burst"
          }
        }
      ]
    }"""

    def test_normalizes_model_manifest_and_rebuilds_ids(self) -> None:
        manifest = parse_model_manifest(f"```json\n{self.MODEL_JSON}\n```", "test-content", 60000)

        self.assertEqual("test-content", manifest.content_id)
        self.assertEqual("0.2.0", manifest.version)
        self.assertEqual("hl-test-content-001", manifest.highlights[0].id)
        self.assertEqual(1.0, manifest.highlights[0].intensity)
        self.assertLessEqual(len(manifest.highlights[0].payload.title), 24)
        self.assertEqual("positive", manifest.highlights[0].payload.actions[0].tone)
        self.assertEqual("fire", manifest.highlights[0].payload.actions[0].icon)

    def test_drops_unknown_action_tone_and_icon(self) -> None:
        invalid_style_json = self.MODEL_JSON.replace('"tone": "positive"', '"tone": "rainbow"').replace(
            '"icon": "fire"',
            '"icon": "unknown-icon"',
        )
        manifest = parse_model_manifest(invalid_style_json, "test-content", 60000)

        self.assertIsNone(manifest.highlights[0].payload.actions[0].tone)
        self.assertIsNone(manifest.highlights[0].payload.actions[0].icon)

    def test_rejects_manifest_without_valid_highlights(self) -> None:
        invalid_json = self.MODEL_JSON.replace('"end_ms": 17000', '"end_ms": 13001')
        with self.assertRaises(ValueError):
            parse_model_manifest(invalid_json, "test-content", 60000)

    def test_saves_and_loads_generated_manifest(self) -> None:
        manifest = parse_model_manifest(self.MODEL_JSON, "test-content", 60000)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            content_id = content_id_from_relative_path("test-drama/episode-1.mp4")
            output_path = save_manifest(manifest, root, content_id=content_id)
            loaded = load_manifest(content_id, 60000, root)

        self.assertTrue(output_path.name.endswith(".json"))
        self.assertEqual(f"{content_id}.json", output_path.name)
        self.assertIsNotNone(loaded)
        self.assertEqual(f"hl-{content_id}-001", loaded.highlights[0].id)

    def test_formats_timestamped_asr_segments(self) -> None:
        transcript = {
            "segments": [
                {"start": 12.3, "end": 16.8, "speaker": "speaker_1", "text": "identity is fake"},
            ]
        }
        self.assertEqual(
            "[00:12.300 - 00:16.800] speaker_1: identity is fake",
            format_timed_transcript(transcript),
        )

    def test_extract_audio_uses_tolerant_utf8_decoding_for_ffmpeg_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "episode-1.mp4"
            audio_path = root / "audio.mp3"
            video_path.write_bytes(b"video")

            with patch("app.services.episode_manifest_pipeline.subprocess.run") as run:
                extract_audio(video_path, audio_path)

            self.assertEqual("utf-8", run.call_args.kwargs["encoding"])
            self.assertEqual("replace", run.call_args.kwargs["errors"])

    def test_extracts_responses_output_text(self) -> None:
        response = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"text":"identity is fake","segments":[]}',
                        }
                    ]
                }
            ]
        }
        self.assertEqual(
            '{"text":"identity is fake","segments":[]}',
            extract_responses_output_text(response),
        )

    def test_detects_unsupported_json_mode_error(self) -> None:
        self.assertTrue(
            is_unsupported_json_mode_error(
                Exception("response_format.type json_object is not supported by this model")
            )
        )
        self.assertFalse(is_unsupported_json_mode_error(Exception("authentication failed")))

    def test_retries_chat_without_json_mode_when_model_rejects_it(self) -> None:
        class FakeCompletions:
            def __init__(self) -> None:
                self.requests = []

            def create(self, **request):
                self.requests.append(request)
                if "response_format" in request:
                    raise BadRequestError(
                        "response_format.type json_object is not supported by this model",
                        response=SimpleNamespace(
                            status_code=400,
                            headers={},
                            request=SimpleNamespace(),
                        ),
                        body=None,
                    )
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content='{"highlights":[]}'))]
                )

        completions = FakeCompletions()
        fake_openai = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with (
            patch.dict(
                os.environ,
                {
                    "MODEL_BASE_URL": "https://example.test/v1",
                    "MODEL_API_KEY": "test-key",
                    "MODEL_NAME": "test-model",
                },
            ),
            patch("openai.OpenAI", return_value=fake_openai),
        ):
            output = ModelClient().chat([{"role": "user", "content": "test"}], json_object=True)

        self.assertEqual('{"highlights":[]}', output)
        self.assertIn("response_format", completions.requests[0])
        self.assertNotIn("response_format", completions.requests[1])

    def test_generates_manifest_from_existing_transcript_json(self) -> None:
        class FakeModelClient:
            is_configured = True

            def chat(self, messages, *, json_object=False):
                self.messages = messages
                self.json_object = json_object
                return ManifestGenerationTests.MODEL_JSON

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            video_path = root / "episode-1.mp4"
            video_path.write_bytes(b"video")
            input_transcript_path = root / "input-transcript.json"
            input_transcript_path.write_text(
                '{"segments":[{"start":12.3,"end":16.8,"text":"identity is fake"}]}',
                encoding="utf-8",
            )
            manifest_root = root / "manifests"
            transcript_root = root / "transcripts"

            with patch("app.services.episode_manifest_pipeline.video_duration_ms", return_value=60000):
                manifest, transcript_path, manifest_path = generate_episode_manifest(
                    video_path,
                    transcript_json_path=input_transcript_path,
                    manifest_root=manifest_root,
                    transcript_root=transcript_root,
                    model_client=FakeModelClient(),
                )

            expected_content_id = content_id_from_relative_path(video_path.name)
            self.assertEqual(f"hl-{expected_content_id}-001", manifest.highlights[0].id)
            self.assertTrue(transcript_path.exists())
            self.assertTrue(manifest_path.exists())

    def test_repairs_invalid_generated_manifest_once(self) -> None:
        class RepairingModelClient:
            is_configured = True

            def __init__(self) -> None:
                self.requests = []

            def chat(self, messages, *, json_object=False):
                self.requests.append(messages)
                if len(self.requests) == 1:
                    return '{"content_id":"test-content","highlights":[]}'
                return ManifestGenerationTests.MODEL_JSON

        client = RepairingModelClient()
        manifest = generate_highlight_candidates(
            HighlightCandidateRequest(
                content_id="test-content",
                transcript="[00:12.000 - 00:17.000] identity is fake",
                duration_ms=60000,
            ),
            model_client=client,
            fallback=False,
        )

        self.assertEqual(2, len(client.requests))
        self.assertEqual("hl-test-content-001", manifest.highlights[0].id)
        self.assertIn("validation_error", client.requests[1][1]["content"])

    def test_raises_when_repaired_manifest_is_still_invalid(self) -> None:
        class BrokenModelClient:
            is_configured = True

            def __init__(self) -> None:
                self.call_count = 0

            def chat(self, messages, *, json_object=False):
                self.call_count += 1
                return '{"content_id":"test-content","highlights":[]}'

        client = BrokenModelClient()
        with self.assertRaises(ValueError):
            generate_highlight_candidates(
                HighlightCandidateRequest(
                    content_id="test-content",
                    transcript="[00:12.000 - 00:17.000] identity is fake",
                    duration_ms=60000,
                ),
                model_client=client,
                fallback=False,
            )

        self.assertEqual(2, client.call_count)


if __name__ == "__main__":
    unittest.main()

