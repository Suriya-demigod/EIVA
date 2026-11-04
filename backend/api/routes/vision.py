"""Image analysis and task-scoped browser screenshot vision."""

import base64
import binascii
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from backend.api.schemas import VisionAnalyzeResponse, VisionScreenRequest
from backend.config import get_settings
from backend.core.model_router import ModelRouter, get_model_router
from backend.core.permission_manager import PermissionDenied
from backend.tasks.manager import TaskNotFound
from backend.tools.gateway import ToolExecutionFailure, ToolInputError

router = APIRouter(prefix="/vision", tags=["vision"])
IMAGE_SIGNATURES = {
    "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
    "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda data: len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
}


async def _read_image(request: Request) -> tuple[bytes, str]:
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if mime_type not in IMAGE_SIGNATURES:
        raise HTTPException(status_code=415, detail="Only JPEG, PNG, and WebP images are supported")

    max_bytes = get_settings().vision_max_image_bytes
    announced_length = request.headers.get("content-length")
    if announced_length and announced_length.isdigit() and int(announced_length) > max_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the configured size limit")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="Image exceeds the configured size limit")
        chunks.append(chunk)
    image_bytes = b"".join(chunks)
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Image body is empty")
    if not IMAGE_SIGNATURES[mime_type](image_bytes):
        raise HTTPException(status_code=415, detail="Image content does not match its media type")
    return image_bytes, mime_type


def _screenshot_image(result: dict, max_bytes: int) -> tuple[bytes, str]:
    content = result.get("content", [])
    item = next((entry for entry in content if isinstance(entry, dict) and entry.get("type") == "image"), None)
    if item is None or not isinstance(item.get("data"), str):
        raise HTTPException(status_code=502, detail="Browser screenshot did not return image data")
    mime_type = item.get("mimeType")
    if mime_type not in IMAGE_SIGNATURES:
        raise HTTPException(status_code=502, detail="Browser screenshot returned an unsupported image type")
    encoded = item["data"]
    if len(encoded) > ((max_bytes + 2) // 3) * 4:
        raise HTTPException(status_code=413, detail="Browser screenshot exceeds the configured size limit")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Browser screenshot returned invalid image data") from exc
    if not image_bytes or len(image_bytes) > max_bytes or not IMAGE_SIGNATURES[mime_type](image_bytes):
        raise HTTPException(status_code=502, detail="Browser screenshot image validation failed")
    return image_bytes, mime_type


@router.post(
    "/analyze",
    response_model=VisionAnalyzeResponse,
    summary="Analyze a supplied image",
    description="Send JPEG, PNG, or WebP bytes as the request body; include the question as a query parameter.",
)
async def analyze_image(
    request: Request,
    question: str = Query(min_length=1, max_length=4_000),
    model_router: ModelRouter = Depends(get_model_router),
) -> VisionAnalyzeResponse:
    image_bytes, mime_type = await _read_image(request)
    answer, model = await model_router.analyze_image(
        question, image_bytes, mime_type, request.state.request_id
    )
    return VisionAnalyzeResponse(answer=answer, model=model, request_id=request.state.request_id)


@router.post(
    "/screen",
    response_model=VisionAnalyzeResponse,
    summary="Capture and analyze a task-scoped browser page",
)
async def analyze_browser_screen(
    payload: VisionScreenRequest,
    request: Request,
    model_router: ModelRouter = Depends(get_model_router),
) -> VisionAnalyzeResponse:
    settings = get_settings()
    supervisor = request.app.state.supervisor
    try:
        supervisor.tasks.get(payload.task_id)
    except TaskNotFound as exc:
        raise HTTPException(status_code=404, detail="Task was not found") from exc

    supervisor.events.publish(
        payload.task_id,
        "vision.screenshot_started",
        {"request_id": str(request.state.request_id)},
    )
    try:
        result = await supervisor.tools.call(
            "playwright.take_screenshot",
            {},
            task_id=payload.task_id,
            request_id=request.state.request_id,
        )
        image_bytes, mime_type = _screenshot_image(result, settings.vision_max_image_bytes)
        answer, model = await model_router.analyze_image(
            payload.question, image_bytes, mime_type, request.state.request_id
        )
    except asyncio.CancelledError:
        supervisor.events.publish(payload.task_id, "vision.screenshot_cancelled", {})
        raise
    except PermissionDenied as exc:
        supervisor.events.publish(payload.task_id, "vision.screenshot_denied", {})
        raise HTTPException(status_code=403, detail="Browser screenshot permission was denied") from exc
    except ToolInputError as exc:
        supervisor.events.publish(payload.task_id, "vision.screenshot_failed", {"reason": "invalid_tool_arguments"})
        raise HTTPException(status_code=400, detail="Browser screenshot arguments were rejected") from exc
    except ToolExecutionFailure as exc:
        supervisor.events.publish(payload.task_id, "vision.screenshot_failed", {"reason": exc.error_type})
        raise HTTPException(status_code=503, detail="Browser screenshot is unavailable") from exc
    except HTTPException:
        supervisor.events.publish(payload.task_id, "vision.screenshot_failed", {"reason": "invalid_image_result"})
        raise
    finally:
        await supervisor.tools.close_task(payload.task_id)

    supervisor.events.publish(
        payload.task_id,
        "vision.screenshot_analyzed",
        {"request_id": str(request.state.request_id), "model": model},
    )
    return VisionAnalyzeResponse(answer=answer, model=model, request_id=request.state.request_id)
