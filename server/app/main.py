from __future__ import annotations

import mimetypes
import os
from base64 import b64decode
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from app.api import ai, dramas, interactions, manifests
from app.api.admin import router as admin_router
from app.db.session import get_store
from app.services.manifest_service import ManifestValidationError
from app.services.media_scanner import DEFAULT_POSTER_FILE_NAME, POSTER_EXTENSIONS, VIDEO_EXTENSIONS


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 后台生成 worker：DB 后端下随 API 进程启动（lazily 获取 store，Postgres 未就绪不影响启动）。
    worker = None
    if os.getenv("STORE_BACKEND", "").lower() != "memory" and os.getenv("ADMIN_WORKER_ENABLED", "1") != "0":
        from app.worker import GenerationWorker

        worker = GenerationWorker(get_store)
        worker.start()
    try:
        yield
    finally:
        if worker is not None:
            worker.stop()


app = FastAPI(title="Drama Highlight Interaction API", lifespan=lifespan)

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
app.include_router(admin_router)


@app.exception_handler(ManifestValidationError)
async def manifest_validation_handler(request: Request, exc: ManifestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": {"message": "Manifest validation failed", "reasons": exc.reasons}},
    )


# 管理端静态资源：/admin 挂载 Vue 构建产物（client_admin/dist 或容器内 admin_dist）。
# 必须在 /admin/api 路由之后挂载，保证 API 优先匹配。dist 不存在时（未构建前端）跳过挂载。
def _admin_dist_dir() -> Path | None:
    server_root = Path(__file__).resolve().parents[1]
    project_root = server_root.parent
    for candidate in (
        server_root / "admin_dist",          # 容器内构建产物
        project_root / "client_admin" / "dist",  # 宿主机前端构建产物
    ):
        if (candidate / "index.html").exists():
            return candidate
    return None


_admin_dist = _admin_dist_dir()
if _admin_dist is not None:
    from fastapi.staticfiles import StaticFiles

    app.mount("/admin", StaticFiles(directory=_admin_dist, html=True), name="admin-ui")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/ready")
def ready() -> dict[str, bool]:
    get_store()
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
