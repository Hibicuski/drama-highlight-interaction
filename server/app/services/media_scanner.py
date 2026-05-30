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
    HighlightAction,
    HighlightManifest,
    HighlightPayload,
    HighlightPoint,
)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi"}
LOGGER = logging.getLogger(__name__)


def scan_local_dramas(local_drama_root: Path, public_base_url: str) -> tuple[list[Drama], list[Episode], dict[int, HighlightManifest]]:
    dramas: list[Drama] = []
    episodes: list[Episode] = []
    manifests: dict[int, HighlightManifest] = {}

    if not local_drama_root.exists():
        return dramas, episodes, manifests

    drama_dirs = sorted(
        [entry for entry in local_drama_root.iterdir() if entry.is_dir()],
        key=lambda item: item.name,
    )

    for drama_index, drama_dir in enumerate(drama_dirs, start=1):
        video_files = sorted(
            [entry for entry in drama_dir.iterdir() if entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS],
            key=lambda item: (episode_index_from_name(item.name), item.name),
        )
        if not video_files:
            continue

        drama_id = 1000 + drama_index
        dramas.append(
            Drama(
                id=drama_id,
                title=drama_dir.name,
                poster="",
                tags=["local", "demo"],
                description=f"本地短剧，共 {len(video_files)} 集。",
            )
        )

        for episode_index, video_file in enumerate(video_files, start=1):
            episode_id = drama_id * 1000 + episode_index
            relative_path = video_file.relative_to(local_drama_root)
            encoded_path = quote(relative_path.as_posix(), safe="/")

            episodes.append(
                Episode(
                    id=episode_id,
                    drama_id=drama_id,
                    episode_index=episode_index,
                    title=video_file.stem,
                    video_url=f"{public_base_url}/videos/{encoded_path}",
                    duration_ms=video_duration_ms(video_file),
                )
            )
            manifests[episode_id] = default_manifest(episode_id)

    return dramas, episodes, manifests


def episode_index_from_name(file_name: str) -> int:
    match = re.search(r"第\s*(\d+)\s*集", file_name)
    if match:
        return int(match.group(1))

    fallback = re.search(r"(\d+)", file_name)
    return int(fallback.group(1)) if fallback else 999999


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
            stderr=subprocess.DEVNULL,
        )
        seconds = float(output.strip())
        return round(seconds * 1000)
    except (OSError, subprocess.SubprocessError, ValueError):
        LOGGER.warning("Unable to read duration for %s. Install ffprobe or set FFPROBE_PATH.", video_path)
        return 0


def default_manifest(episode_id: int) -> HighlightManifest:
    return HighlightManifest(
        episode_id=episode_id,
        highlights=[
            HighlightPoint(
                id=f"hl-{episode_id}-001",
                start_ms=12000,
                end_ms=18000,
                type="satisfying",
                intensity=0.9,
                template="dual-button",
                payload=HighlightPayload(
                    title="爽点来了",
                    actions=[
                        HighlightAction(key="satisfying", label="爽了"),
                        HighlightAction(key="more", label="继续狠一点"),
                    ],
                    effect="particle-burst",
                ),
            ),
            HighlightPoint(
                id=f"hl-{episode_id}-002",
                start_ms=45000,
                end_ms=52000,
                type="twist",
                intensity=0.85,
                template="dual-button",
                payload=HighlightPayload(
                    title="这波反转你怎么看？",
                    actions=[
                        HighlightAction(key="expected", label="意料之中"),
                        HighlightAction(key="surprised", label="没想到"),
                    ],
                    effect="ratio-reveal",
                ),
            ),
        ],
    )
