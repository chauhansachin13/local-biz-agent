"""FastAPI application entrypoint for BizPresence AI."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.settings import settings
from src.api.routes import api_router
from src.database import init_db
from src.utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="BizPresence AI",
    description=(
        "AI-powered multi-agent backend for local businesses: "
        "manage Google Business profiles, social media, customer reviews, and bookings."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow all origins for local & containerized development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    """Initialize database tables on application startup."""
    logger.info("Starting %s and initializing database tables...", settings.app_name)
    await init_db()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Format HTTP exceptions consistently."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return structured validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": True,
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "detail": "Validation error",
            "errors": exc.errors(),
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected server errors cleanly."""
    logger.exception("Unhandled error on %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "detail": "An unexpected internal server error occurred.",
            "path": str(request.url.path),
        },
    )


@app.get("/", tags=["Root"])
async def root() -> dict:
    """Return BizPresence AI API metadata and endpoint index."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "description": "Local Business Digital Presence Agent API",
        "status": "healthy",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "businesses": "/api/businesses",
            "social": "/api/social",
            "reviews": "/api/reviews",
            "bookings": "/api/bookings",
            "agent": "/api/agent",
        },
    }


app.include_router(api_router)
