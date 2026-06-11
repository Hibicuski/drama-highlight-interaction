from __future__ import annotations

import argparse
from pathlib import Path

from app.services.episode_manifest_pipeline import generate_episode_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an AI highlight manifest for one drama episode.")
    parser.add_argument("video", type=Path, help="Path to the source video file")
    parser.add_argument("--summary", default="", help="Optional short plot summary")
    parser.add_argument("--transcript-json", type=Path, help="Reuse an existing ASR transcript JSON file")
    parser.add_argument("--local-drama-root", type=Path, help="Root used to compute stable content hash from relative video path")
    args = parser.parse_args()

    manifest, transcript_path, manifest_path = generate_episode_manifest(
        args.video,
        summary=args.summary,
        transcript_json_path=args.transcript_json,
        local_drama_root=args.local_drama_root,
    )
    print(f"Generated {len(manifest.highlights)} highlights")
    print(f"Transcript: {transcript_path}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
