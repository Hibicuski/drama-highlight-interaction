from __future__ import annotations

import mimetypes
from base64 import b64decode
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.api import ai, dramas, interactions, manifests
from app.db.session import get_store
from app.services.media_scanner import DEFAULT_POSTER_FILE_NAME, POSTER_EXTENSIONS, VIDEO_EXTENSIONS

app = FastAPI(title="Drama Highlight Interaction API")

DEFAULT_POSTER_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mM8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dramas.router)
app.include_router(manifests.router)
app.include_router(interactions.router)
app.include_router(ai.router)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/videos/{relative_path:path}")
def get_video(relative_path: str, request: Request) -> StreamingResponse:
    store = get_store()
    video_path = safe_video_path(store.local_drama_root, relative_path)
    file_size = video_path.stat().st_size
    content_type = mimetypes.guess_type(video_path.name)[0] or "video/mp4"

    range_header = request.headers.get("range")
    if range_header:
        start, end = parse_range_header(range_header, file_size)
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(end - start + 1),
        }
        return StreamingResponse(
            iter_file(video_path, start, end),
            status_code=206,
            media_type=content_type,
            headers=headers,
        )

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
    }
    return StreamingResponse(
        iter_file(video_path, 0, file_size - 1),
        media_type=content_type,
        headers=headers,
    )


@app.get("/posters/{relative_path:path}")
def get_poster(relative_path: str) -> Response:
    if relative_path == DEFAULT_POSTER_FILE_NAME:
        return Response(content=DEFAULT_POSTER_PNG, media_type="image/png")

    store = get_store()
    poster_path = safe_media_path(store.local_drama_root, relative_path, POSTER_EXTENSIONS)
    return FileResponse(poster_path)


def safe_video_path(local_drama_root: Path, relative_path: str) -> Path:
    return safe_media_path(local_drama_root, relative_path, VIDEO_EXTENSIONS)


def safe_media_path(local_drama_root: Path, relative_path: str, allowed_extensions: set[str]) -> Path:
    local_drama_root = local_drama_root.resolve()
    media_path = (local_drama_root / relative_path).resolve()
    try:
        media_path.relative_to(local_drama_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid media path") from exc

    if not media_path.exists() or not media_path.is_file():
        raise HTTPException(status_code=404, detail="Media not found")
    if media_path.suffix.lower() not in allowed_extensions:
        raise HTTPException(status_code=404, detail="Media not found")
    return media_path


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
    if file_size <= 0 or not range_header.startswith("bytes="):
        raise HTTPException(status_code=416, detail="Invalid range")

    start_text, _, end_text = range_header.removeprefix("bytes=").partition("-")
    if not _ or "," in end_text or (not start_text and not end_text):
        raise HTTPException(status_code=416, detail="Invalid range")

    try:
        if not start_text:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise ValueError
            return max(file_size - suffix_length, 0), file_size - 1

        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
    except ValueError as exc:
        raise HTTPException(status_code=416, detail="Invalid range") from exc

    if start < 0 or start >= file_size or end < start:
        raise HTTPException(status_code=416, detail="Invalid range")
    return start, min(end, file_size - 1)


def iter_file(video_path: Path, start: int, end: int, chunk_size: int = 1024 * 1024):
    with video_path.open("rb") as file:
        file.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = file.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
