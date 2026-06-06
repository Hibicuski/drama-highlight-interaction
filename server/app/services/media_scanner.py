from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import quote

from app.db.models import (
    Drama,
    Episode,
    HighlightManifest,
)
from app.services.manifest_store import content_id_from_relative_path, load_manifest

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
POSTER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PREFERRED_POSTER_NAMES = {"poster", "cover", "封面"}
GENERATED_POSTER_DIR_NAME = ".generated-posters"
DEFAULT_POSTER_FILE_NAME = "__default_poster__.png"
LOGGER = logging.getLogger(__name__)


def scan_local_dramas(local_drama_root: Path, public_base_url: str) -> tuple[list[Drama], list[Episode], dict[str, HighlightManifest]]:
    dramas: list[Drama] = []
    episodes: list[Episode] = []
    manifests: dict[str, HighlightManifest] = {}

    if not local_drama_root.exists():
        return dramas, episodes, manifests

    drama_dirs = sorted(
        [entry for entry in local_drama_root.iterdir() if entry.is_dir()],
        key=lambda item: item.name,
    )

    for drama_index, drama_dir in enumerate(drama_dirs, start=1):
        video_files = sorted(
            [entry for entry in drama_dir.iterdir() if entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS],
            key=episode_sort_key,
        )
        if not video_files:
            continue

        drama_id = 1000 + drama_index
        poster_file = find_poster_file(drama_dir)
        episode_posters_by_path: dict[Path, str] = {}

        for video_file in video_files:
            relative_path = video_file.relative_to(local_drama_root)
            content_id = content_id_from_relative_path(relative_path)
            episode_poster = find_episode_poster_file(video_file)
            if episode_poster is None:
                episode_poster = generate_episode_poster(video_file, local_drama_root, content_id)
            if episode_poster is not None:
                episode_posters_by_path[video_file] = poster_url_for_file(episode_poster, local_drama_root, public_base_url)

        poster_url = ""
        if poster_file is not None:
            poster_url = poster_url_for_file(poster_file, local_drama_root, public_base_url)
        elif video_files:
            poster_url = episode_posters_by_path.get(video_files[0], default_poster_url(public_base_url))

        dramas.append(
            Drama(
                id=drama_id,
                title=drama_dir.name,
                poster=poster_url,
                tags=["local", "demo"],
                description=f"本地短剧，共 {len(video_files)} 集。",
            )
        )

        for episode_position, video_file in enumerate(video_files, start=1):
            parsed_episode_index = episode_index_from_name(video_file.name)
            episode_index = parsed_episode_index if parsed_episode_index is not None else episode_position
            episode_runtime_id = drama_id * 1000 + episode_position
            relative_path = video_file.relative_to(local_drama_root)
            encoded_path = quote(relative_path.as_posix(), safe="/")
            content_id = content_id_from_relative_path(relative_path)

            duration_ms = video_duration_ms(video_file)
            episodes.append(
                Episode(
                    id=episode_runtime_id,
                    content_id=content_id,
                    drama_id=drama_id,
                    episode_index=episode_index,
                    title=video_file.stem,
                    video_url=f"{public_base_url}/videos/{encoded_path}",
                    poster=episode_posters_by_path.get(video_file, poster_url),
                    duration_ms=duration_ms,
                )
            )
            manifests[content_id] = load_manifest(content_id, duration_ms) or empty_manifest(content_id)

    return dramas, episodes, manifests


def find_poster_file(drama_dir: Path) -> Path | None:
    poster_files = sorted(
        [entry for entry in drama_dir.iterdir() if entry.is_file() and entry.suffix.lower() in POSTER_EXTENSIONS],
        key=lambda item: (item.stem.lower() not in PREFERRED_POSTER_NAMES, item.name),
    )
    return poster_files[0] if poster_files else None


def find_episode_poster_file(video_file: Path) -> Path | None:
    for extension in POSTER_EXTENSIONS:
        candidate = video_file.with_suffix(extension)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def generate_episode_poster(video_file: Path, local_drama_root: Path, content_id: str) -> Path | None:
    poster_dir = local_drama_root / GENERATED_POSTER_DIR_NAME
    poster_path = poster_dir / f"{content_id}.jpg"
    if poster_path.exists() and poster_path.is_file():
        return poster_path

    ffmpeg_path = os.getenv("FFMPEG_PATH", "ffmpeg")
    try:
        poster_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                str(video_file),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(poster_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return poster_path if poster_path.exists() and poster_path.is_file() else None
    except (OSError, subprocess.SubprocessError):
        LOGGER.warning("Unable to generate poster for %s. Install ffmpeg or set FFMPEG_PATH.", video_file)
        return None


def poster_url_for_file(poster_file: Path, local_drama_root: Path, public_base_url: str) -> str:
    poster_path = quote(poster_file.relative_to(local_drama_root).as_posix(), safe="/")
    return f"{public_base_url}/posters/{poster_path}"


def default_poster_url(public_base_url: str) -> str:
    return f"{public_base_url}/posters/{DEFAULT_POSTER_FILE_NAME}"


def episode_sort_key(video_file: Path) -> tuple[bool, int, str]:
    episode_index = episode_index_from_name(video_file.name)
    return episode_index is None, episode_index or 0, video_file.name


def episode_index_from_name(file_name: str) -> int | None:
    match = re.search(r"第\s*(\d+)\s*集", file_name)
    if match:
        return int(match.group(1))

    fallback = re.search(r"(\d+)", file_name)
    return int(fallback.group(1)) if fallback else None


def video_duration_ms(video_path: Path) -> int:
    ffprobe_path = os.getenv("FFPROBE_PATH", "ffprobe")
    try:
        output = subprocess.check_output(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.DEVNULL,
        )
        seconds = float(output.strip())
        return round(seconds * 1000)
    except (OSError, subprocess.SubprocessError, ValueError):
        LOGGER.warning("Unable to read duration for %s. Install ffprobe or set FFPROBE_PATH.", video_path)
        return 0


def empty_manifest(content_id: str) -> HighlightManifest:
    return HighlightManifest(
        content_id=content_id,
        version="0.2.0",
        highlights=[],
    )
