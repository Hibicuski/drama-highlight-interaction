import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from openai import BadRequestError
from pydantic import ValidationError

EMPTY_ROOT = Path(tempfile.gettempdir()) / "drama-highlight-interaction-tests-empty"
EMPTY_ROOT.mkdir(exist_ok=True)
os.environ["LOCAL_DRAMA_ROOT"] = str(EMPTY_ROOT)
os.environ["STORE_BACKEND"] = "memory"

from app.db.models import HighlightAction, HighlightManifest, HighlightPayload, HighlightPoint, InteractionRequest
from app.db.session import InMemoryStore
from app.main import get_poster, parse_range_header, safe_media_path, safe_video_path
from app.services.episode_manifest_pipeline import extract_audio, format_timed_transcript, generate_episode_manifest
from app.services.highlight_generator import generate_highlight_candidates
from app.db.models import HighlightCandidateRequest
from app.services.manifest_store import content_id_from_relative_path, load_manifest, parse_model_manifest, save_manifest
from app.services.media_scanner import DEFAULT_POSTER_FILE_NAME, POSTER_EXTENSIONS
from app.services.media_scanner import scan_local_dramas
from app.services.model_client import ModelClient, extract_responses_output_text, is_unsupported_json_mode_error
from app.services.text_quality import repair_mojibake
from app.services.transcript_enricher import enrich_transcript, format_enriched_transcript


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

    def test_uses_empty_manifest_when_generated_manifest_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as manifest_temp_dir:
            root = Path(temp_dir)
            drama_dir = root / "no-generated-highlight-drama"
            drama_dir.mkdir()
            (drama_dir / "episode-1.mp4").write_bytes(b"video")

            with (
                patch.dict(os.environ, {"MANIFEST_ROOT": str(manifest_temp_dir)}),
                patch("app.services.media_scanner.subprocess.check_output", return_value="60\n"),
            ):
                _, episodes, manifests = scan_local_dramas(root, "http://10.0.2.2:3000")

            self.assertEqual([], manifests[episodes[0].content_id].highlights)


class InteractionStoreTests(unittest.TestCase):
    def test_interaction_request_requires_session_id(self) -> None:
        with self.assertRaises(ValidationError):
            InteractionRequest(
                content_id="content",
                highlight_id="highlight",
                action="tap",
            )

        with self.assertRaises(ValidationError):
            InteractionRequest(
                content_id="content",
                highlight_id="highlight",
                action="tap",
                session_id=" ",
            )

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

            content_id = store.episodes[0].content_id
            highlight_id = f"hl-{content_id}-test"
            store.set_manifest(
                HighlightManifest(
                    content_id=content_id,
                    version="0.2.0",
                    highlights=[
                        HighlightPoint(
                            id=highlight_id,
                            start_ms=12000,
                            end_ms=17000,
                            type="satisfying",
                            template="dual-button",
                            payload=HighlightPayload(
                                title="霸气回怼",
                                actions=[
                                    HighlightAction(key="shuang", label="爽", tone="positive", icon="fire"),
                                    HighlightAction(key="shang-tou", label="上头", tone="positive", icon="boost"),
                                ],
                                effect="particle-burst",
                            ),
                        )
                    ],
                )
            )

            request = InteractionRequest(
                content_id=content_id,
                highlight_id=highlight_id,
                action="shuang",
                session_id="device_test_session",
            )
            first_response = store.report_interaction(request)

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(lambda _: store.report_interaction(request), range(19)))

            self.assertEqual(1, first_response.count)
            self.assertEqual(20, store.get_aggregate(request.highlight_id).count)


class TranscriptEnrichmentTests(unittest.TestCase):
    def test_enrichment_preserves_asr_timing_and_text(self) -> None:
        class FakeModelClient:
            is_configured = True

            def chat(self, messages, *, json_object=False):
                return """{
                  "characters": [
                    {"id": "speaker_1", "name": "容玉", "role": "女主", "traits": ["强势"]}
                  ],
                  "segments": [
                    {
                      "index": 0,
                      "start": 99.0,
                      "end": 100.0,
                      "text": "模型改错的台词",
                      "speaker": "speaker_1",
                      "speaker_name": "容玉",
                      "role": "女主",
                      "scene": "被质疑后强势回击",
                      "emotion": "霸气",
                      "beat_type": "slap-face",
                      "highlight_reason": "一句话压住全场",
                      "confidence": 0.9
                    }
                  ]
                }"""

        transcript = {"segments": [{"start": 63.17, "end": 78.77, "text": "我在哪，纪家就在哪"}]}
        enriched = enrich_transcript(transcript, model_client=FakeModelClient())
        segment = enriched["segments"][0]

        self.assertEqual(63.17, segment["start"])
        self.assertEqual(78.77, segment["end"])
        self.assertEqual("我在哪，纪家就在哪", segment["text"])
        self.assertEqual("容玉", segment["speaker_name"])
        self.assertEqual("speaker_1", segment["speaker"])
        self.assertNotIn("beat_type", segment)
        self.assertNotIn("scene", segment)

    def test_low_confidence_speaker_is_not_formatted_as_context(self) -> None:
        class LowConfidenceModelClient:
            is_configured = True

            def chat(self, messages, *, json_object=False):
                return """{
                  "segments": [
                    {
                      "index": 0,
                      "speaker": "speaker_1",
                      "speaker_name": "容玉",
                      "confidence": 0.3
                    }
                  ]
                }"""

        transcript = {"segments": [{"start": 1.0, "end": 3.0, "text": "我不需要进纪家"}]}
        enriched = enrich_transcript(transcript, model_client=LowConfidenceModelClient())
        formatted = format_enriched_transcript(enriched)

        self.assertIn("text=我不需要进纪家", formatted)
        self.assertNotIn("speaker=容玉", formatted)
        self.assertEqual("", enriched["segments"][0]["speaker_name"])

    def test_high_confidence_speaker_is_formatted_as_advisory_context(self) -> None:
        class HighConfidenceModelClient:
            is_configured = True

            def chat(self, messages, *, json_object=False):
                return """{
                  "characters": [{"id": "speaker_1", "name": "容玉"}],
                  "segments": [
                    {
                      "index": 0,
                      "speaker": "speaker_1",
                      "speaker_name": "容玉",
                      "scene": "被质疑后强势回击",
                      "emotion": "霸气",
                      "beat_type": "slap-face",
                      "highlight_reason": "一句话反转身份地位",
                      "confidence": 0.8
                    }
                  ]
                }"""

        transcript = {"segments": [{"start": 1.0, "end": 3.0, "text": "我在哪，纪家就在哪"}]}
        enriched = enrich_transcript(transcript, model_client=HighConfidenceModelClient())
        formatted = format_enriched_transcript(enriched)

        self.assertIn("speaker=容玉", formatted)
        self.assertIn("speakers: speaker_1=容玉", formatted)
        self.assertNotIn("scene=被质疑后强势回击", formatted)
        self.assertNotIn("reason=一句话反转身份地位", formatted)

    def test_enrichment_prompt_includes_previous_speaker_context(self) -> None:
        class InspectingModelClient:
            is_configured = True

            def chat(self, messages, *, json_object=False):
                self.messages = messages
                return """{
                  "segments": [
                    {
                      "index": 0,
                      "speaker": "speaker_1",
                      "speaker_name": "容玉",
                      "confidence": 0.8
                    }
                  ]
                }"""

        client = InspectingModelClient()
        transcript = {"segments": [{"start": 1.0, "end": 3.0, "text": "我今天必须见到纪老夫人"}]}
        enrich_transcript(
            transcript,
            summary="女主进入纪家。",
            series_context="episode 1 speakers: speaker_1=容玉",
            model_client=client,
        )

        prompt = client.messages[1]["content"]
        self.assertIn("previous_speakers_context", prompt)
        self.assertIn("speaker_1=容玉", prompt)
        self.assertIn("我今天必须见到纪老夫人", prompt)


class ManifestGenerationTests(unittest.TestCase):
    MODEL_JSON = """{
      "content_id": "model-content",
      "version": "0.2.0",
      "highlights": [
        {
          "id": "model-id",
          "start_ms": 12000,
          "end_ms": 17000,
          "type": "revenge",
          "intensity": 1.3,
          "template": "dual-button",
          "payload": {
            "title": "霸气回怼",
            "actions": [
              {"key": "satisfying", "label": "爽", "tone": "positive", "icon": "fire"},
              {"key": "more", "label": "上头", "tone": "support", "icon": "boost"}
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
        self.assertLessEqual(len(manifest.highlights[0].payload.title), 12)
        self.assertEqual("positive", manifest.highlights[0].payload.actions[0].tone)
        self.assertEqual("fire", manifest.highlights[0].payload.actions[0].icon)

    def test_rejects_unknown_action_tone_and_icon_when_no_option_remains(self) -> None:
        invalid_style_json = self.MODEL_JSON.replace('"tone": "positive"', '"tone": "rainbow"').replace(
            '"icon": "fire"',
            '"icon": "unknown-icon"',
        ).replace(
            '"tone": "support"',
            '"tone": "rainbow"',
        ).replace(
            '"icon": "boost"',
            '"icon": "unknown-icon"',
        )
        with self.assertRaises(ValueError):
            parse_model_manifest(invalid_style_json, "test-content", 60000)

    def test_rejects_english_user_visible_copy(self) -> None:
        english_json = self.MODEL_JSON.replace('"霸气回怼"', '"plot twist"')
        with self.assertRaises(ValueError):
            parse_model_manifest(english_json, "test-content", 60000)

    def test_accepts_concise_chinese_plot_title(self) -> None:
        plot_title_json = self.MODEL_JSON.replace('"霸气回怼"', '"身份曝光"')
        manifest = parse_model_manifest(plot_title_json, "test-content", 60000)

        self.assertEqual("身份曝光", manifest.highlights[0].payload.title)

    def test_rejects_low_quality_title_terms(self) -> None:
        low_quality_title_json = self.MODEL_JSON.replace('"霸气回怼"', '"放狠话打脸酸鸡"')
        with self.assertRaises(ValueError):
            parse_model_manifest(low_quality_title_json, "test-content", 60000)

    def test_accepts_clear_operational_title(self) -> None:
        clear_title_json = self.MODEL_JSON.replace('"霸气回怼"', '"当场认错"')
        manifest = parse_model_manifest(clear_title_json, "test-content", 60000)

        self.assertEqual("当场认错", manifest.highlights[0].payload.title)

    def test_rejects_single_action_multi_action_template(self) -> None:
        single_action_json = self.MODEL_JSON.replace(
            ',\n              {"key": "more", "label": "上头", "tone": "support", "icon": "boost"}',
            "",
        )
        with self.assertRaises(ValueError):
            parse_model_manifest(single_action_json, "test-content", 60000)

    def test_rejects_missing_required_manifest_fields(self) -> None:
        missing_version_json = self.MODEL_JSON.replace('      "version": "0.2.0",\n', "")
        with self.assertRaises(ValueError):
            parse_model_manifest(missing_version_json, "test-content", 60000)

    def test_repairs_common_chinese_mojibake(self) -> None:
        self.assertEqual("哎快看，", repair_mojibake("鍝庡揩鐪嬶紝"))

    def test_returns_empty_manifest_when_model_is_not_configured(self) -> None:
        class UnconfiguredModelClient:
            is_configured = False

        manifest = generate_highlight_candidates(
            HighlightCandidateRequest(
                content_id="test-content",
                transcript="[00:12.000 - 00:17.000] 这里反转了",
                duration_ms=60000,
            ),
            model_client=UnconfiguredModelClient(),
            fallback=False,
        )

        self.assertEqual("test-content", manifest.content_id)
        self.assertEqual([], manifest.highlights)

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
                if "summary_hint" in messages[1]["content"]:
                    raise AssertionError("speaker separation should be disabled by default")
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
            enriched_transcript_root = root / "enriched-transcripts"

            client = FakeModelClient()
            with patch("app.services.episode_manifest_pipeline.video_duration_ms", return_value=60000):
                manifest, transcript_path, enriched_transcript_path, manifest_path = generate_episode_manifest(
                    video_path,
                    transcript_json_path=input_transcript_path,
                    manifest_root=manifest_root,
                    transcript_root=transcript_root,
                    enriched_transcript_root=enriched_transcript_root,
                    model_client=client,
                )

            expected_content_id = content_id_from_relative_path(video_path.name)
            self.assertEqual(f"hl-{expected_content_id}-001", manifest.highlights[0].id)
            self.assertTrue(transcript_path.exists())
            self.assertIsNone(enriched_transcript_path)
            self.assertTrue(manifest_path.exists())
            self.assertFalse((enriched_transcript_root / f"{expected_content_id}.json").exists())
            self.assertIn("identity is fake", client.messages[1]["content"])

    def test_generates_manifest_from_existing_enriched_transcript_json(self) -> None:
        class FakeModelClient:
            is_configured = True

            def chat(self, messages, *, json_object=False):
                self.messages = messages
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
            input_enriched_path = root / "input-enriched.json"
            input_enriched_path.write_text(
                '{"segments":[{"index":0,"start":99.0,"end":100.0,"text":"wrong text","speaker":"speaker_1","speaker_name":"旁白","scene":"身份曝光","confidence":0.8}]}',
                encoding="utf-8",
            )

            client = FakeModelClient()
            with patch("app.services.episode_manifest_pipeline.video_duration_ms", return_value=60000):
                manifest, _, enriched_transcript_path, _ = generate_episode_manifest(
                    video_path,
                    transcript_json_path=input_transcript_path,
                    enriched_transcript_json_path=input_enriched_path,
                    manifest_root=root / "manifests",
                    transcript_root=root / "transcripts",
                    enriched_transcript_root=root / "enriched-transcripts",
                    model_client=client,
                )

            self.assertEqual("hl-" + content_id_from_relative_path(video_path.name) + "-001", manifest.highlights[0].id)
            self.assertTrue(enriched_transcript_path.exists())
            self.assertIn("identity is fake", client.messages[1]["content"])
            self.assertNotIn("wrong text", client.messages[1]["content"])
            self.assertIn("speaker=旁白", client.messages[1]["content"])
            self.assertNotIn("scene=身份曝光", client.messages[1]["content"])

    def test_ignores_existing_enriched_transcript_without_useful_metadata(self) -> None:
        class FakeModelClient:
            is_configured = True

            def __init__(self) -> None:
                self.enrichment_calls = 0
                self.messages = []

            def chat(self, messages, *, json_object=False):
                self.messages = messages
                if "summary_hint" in messages[1]["content"]:
                    self.enrichment_calls += 1
                    return """{
                      "segments": [
                        {
                          "index": 0,
                          "speaker": "speaker_1",
                          "speaker_name": "旁白",
                          "confidence": 0.8
                        }
                      ]
                    }"""
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
            stale_enriched_path = root / "stale-enriched.json"
            stale_enriched_path.write_text(
                '{"summary":"stale","segments":[{"index":0,"confidence":0.0}]}',
                encoding="utf-8",
            )

            client = FakeModelClient()
            with patch("app.services.episode_manifest_pipeline.video_duration_ms", return_value=60000):
                generate_episode_manifest(
                    video_path,
                    transcript_json_path=input_transcript_path,
                    enriched_transcript_json_path=stale_enriched_path,
                    manifest_root=root / "manifests",
                    transcript_root=root / "transcripts",
                    enriched_transcript_root=root / "enriched-transcripts",
                    model_client=client,
                )

            self.assertEqual(1, client.enrichment_calls)

    def test_repairs_mojibake_before_prompting_model(self) -> None:
        class InspectingModelClient:
            is_configured = True

            def chat(self, messages, *, json_object=False):
                self.messages = messages
                return ManifestGenerationTests.MODEL_JSON

        client = InspectingModelClient()
        generate_highlight_candidates(
            HighlightCandidateRequest(
                content_id="test-content",
                transcript="[00:00.000 - 00:03.000] 鍝庡揩鐪嬶紝",
                duration_ms=60000,
            ),
            model_client=client,
            fallback=False,
        )

        self.assertIn("哎快看，", client.messages[1]["content"])

    def test_repairs_invalid_generated_manifest(self) -> None:
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

    def test_can_repair_generated_manifest_up_to_three_times(self) -> None:
        class ThirdRepairModelClient:
            is_configured = True

            def __init__(self) -> None:
                self.requests = []

            def chat(self, messages, *, json_object=False):
                self.requests.append(messages)
                if len(self.requests) < 4:
                    return '{"content_id":"test-content","version":"0.2.0","highlights":[]}'
                return ManifestGenerationTests.MODEL_JSON

        client = ThirdRepairModelClient()
        manifest = generate_highlight_candidates(
            HighlightCandidateRequest(
                content_id="test-content",
                transcript="[00:12.000 - 00:17.000] identity is fake",
                duration_ms=60000,
            ),
            model_client=client,
            fallback=False,
        )

        self.assertEqual(4, len(client.requests))
        self.assertEqual("hl-test-content-001", manifest.highlights[0].id)
        self.assertIn("validation_error", client.requests[3][1]["content"])

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

        self.assertEqual(4, client.call_count)


if __name__ == "__main__":
    unittest.main()

