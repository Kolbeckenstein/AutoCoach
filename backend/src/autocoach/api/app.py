"""FastAPI application factory for AutoCoach v0.

Synchronous pose pipeline — route is ``def`` (not ``async def``) so FastAPI
auto-dispatches to a thread pool.  Acceptable for 1-3 concurrent users.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from autocoach.blob import LocalBlobStorage
from autocoach.config import AppConfig
from autocoach.pose.extractor import PoseExtractionError
from autocoach.pose.pipeline import PipelineError, PosePipeline

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_DURATION_SECONDS = 30
ALLOWED_MIME_PREFIXES = ("video/",)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _video_duration_seconds(path: Path) -> float:
    """Return video duration in seconds using OpenCV."""
    import cv2

    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0:
            # iOS Safari sometimes reports 0 FPS — fall back to frame count
            # with a conservative estimate
            return frame_count / 30.0 if frame_count > 0 else 0.0
        return frame_count / fps
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    *,
    config: AppConfig | None = None,
    pipeline: PosePipeline | None = None,
) -> FastAPI:
    """Build and return the FastAPI application.

    Accepts optional pre-built dependencies for testing.
    """
    cfg = config or AppConfig()
    blob = LocalBlobStorage(root=Path(cfg.blob_storage_root))
    pipe = pipeline or PosePipeline()

    templates_dir = Path(__file__).parent / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    app = FastAPI(title="AutoCoach", version="0.1.0")

    # Serve blob files (keyframes, etc.) — development only
    blob_root = Path(cfg.blob_storage_root)
    blob_root.mkdir(parents=True, exist_ok=True)
    app.mount("/static/blob", StaticFiles(directory=str(blob_root)), name="blob")

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def upload_page(request: Request) -> HTMLResponse:
        """Render the video upload form."""
        return templates.TemplateResponse(request, "upload.html")

    @app.post("/upload", response_class=HTMLResponse)
    def upload_and_process(
        request: Request,
        file: UploadFile = File(...),
    ) -> HTMLResponse:
        """Accept a video, run the pose pipeline, render results."""
        # --- MIME check ---
        content_type = file.content_type or ""
        if not any(content_type.startswith(p) for p in ALLOWED_MIME_PREFIXES):
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "error_title": "Invalid file type",
                    "error_message": "Please upload a video file (MP4, MOV, WebM).",
                    "show_help": False,
                },
                status_code=400,
            )

        # --- Read upload + size check ---
        video_id = uuid.uuid4().hex[:12]
        suffix = Path(file.filename or "upload.mp4").suffix or ".mp4"
        tmp = NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            size = 0
            for chunk in file.file:
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    Path(tmp.name).unlink(missing_ok=True)
                    return templates.TemplateResponse(
                        request,
                        "error.html",
                        {
                            "error_title": "File too large",
                            "error_message": f"Maximum upload size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                            "show_help": False,
                        },
                        status_code=400,
                    )
                tmp.write(chunk)
            tmp.close()
            tmp_path = Path(tmp.name)

            # --- Duration check ---
            duration = _video_duration_seconds(tmp_path)
            if duration > MAX_DURATION_SECONDS:
                tmp_path.unlink(missing_ok=True)
                return templates.TemplateResponse(
                    request,
                    "error.html",
                    {
                        "error_title": "Video too long",
                        "error_message": f"Maximum duration is {MAX_DURATION_SECONDS} seconds. Your video is {duration:.0f}s.",
                        "show_help": False,
                    },
                    status_code=400,
                )

            # --- Persist video via blob storage ---
            blob_key = f"videos/{video_id}{suffix}"
            blob.upload(blob_key, tmp_path)

            # --- Run pose pipeline synchronously ---
            features = pipe.process(
                video_path=tmp_path,
                video_id=video_id,
                lift_type="Squat",
            )

            return templates.TemplateResponse(
                request,
                "results.html",
                {"features": features},
            )

        except PipelineError as exc:
            msg = str(exc)
            if "frontal" in msg.lower() or "side" in msg.lower():
                return templates.TemplateResponse(
                    request,
                    "error.html",
                    {
                        "error_title": "Wrong camera angle",
                        "error_message": "Re-film from the side for accurate analysis.",
                        "show_help": True,
                    },
                    status_code=400,
                )
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "error_title": "Processing failed",
                    "error_message": "Could not analyze this video. The recording may be too short or unclear.",
                    "show_help": True,
                },
                status_code=400,
            )
        except PoseExtractionError:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "error_title": "Could not process video",
                    "error_message": "Try a different recording — make sure the camera can see your full body.",
                    "show_help": True,
                },
                status_code=400,
            )
        except Exception:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "error_title": "Something went wrong",
                    "error_message": "An unexpected error occurred. Please try again.",
                    "show_help": False,
                },
                status_code=500,
            )
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    return app
