"""EIVA API entry point, lifecycle, and common error handling."""

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from groq import GroqError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.api.errors import (
    groq_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from backend.api.routes import agents, approvals, chat, knowledge, memories, tasks, vision, voice
from backend.config import get_settings
from backend.lifecycle import app_lifespan
from backend.observability.logging import configure_logging

settings = get_settings()
configure_logging()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=app_lifespan)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(agents.router, prefix=settings.api_prefix)
app.include_router(approvals.router, prefix=settings.api_prefix)
app.include_router(tasks.router, prefix=settings.api_prefix)
app.include_router(memories.router, prefix=settings.api_prefix)
app.include_router(knowledge.router, prefix=settings.api_prefix)
app.include_router(voice.router, prefix=settings.api_prefix)
app.include_router(vision.router, prefix=settings.api_prefix)
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/voice-ui", StaticFiles(directory=str(_frontend_dir / "voice"), html=True), name="voice-ui")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = uuid4()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request_id)
    return response


app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(GroqError, groq_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


app.mount("/", StaticFiles(directory=str(_frontend_dir / "app"), html=True), name="frontend")
