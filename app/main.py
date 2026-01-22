"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.routes.webhook import router as webhook_router
from app.services.memory import clear_memory_store
from app.services.weather import close_http_client


def get_rate_limit_key(request: Request) -> str:
    """
    Get rate limit key from request.

    For WhatsApp webhooks, use the From number if available.
    Falls back to remote address.
    """
    # Try to get WhatsApp number from form data (for POST requests)
    # Note: This is called before body is parsed, so we use headers/IP
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    yield
    # Cleanup on shutdown
    await close_http_client()
    clear_memory_store()


app = FastAPI(
    title="AI Agro-Weather Chatbot API",
    description="AI-powered WhatsApp agricultural weather assistant for Ghana farmers",
    version="2.0.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://api.twilio.com"],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["X-Twilio-Signature", "Content-Type"],
)

app.include_router(webhook_router, tags=["webhook"])


@app.get("/health")
async def health_check() -> dict:
    """
    Enhanced health check endpoint with service status.

    Returns:
        Status dictionary with service health information.
    """
    from datetime import datetime
    from app.config import get_settings

    settings = get_settings()

    # Check Redis if enabled
    redis_status = "disabled"
    if settings.use_redis:
        try:
            import redis
            r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
            r.ping()
            redis_status = "healthy"
        except Exception:
            redis_status = "unhealthy"

    # Check if Groq API is configured
    groq_status = "configured" if settings.groq_api_key else "not_configured"

    # Check if weather API is configured
    weather_api_status = "configured" if settings.weather_api_key else "not_configured"

    return {
        "status": "healthy",
        "service": "weather-chatbot",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "services": {
            "redis": redis_status,
            "groq_ai": groq_status,
            "openweathermap": weather_api_status,
        },
    }


@app.get("/")
async def root() -> dict:
    """
    Root endpoint.

    Returns:
        Welcome message with API information.
    """
    return {
        "message": "Weather Chatbot API",
        "docs": "/docs",
        "health": "/health",
    }
