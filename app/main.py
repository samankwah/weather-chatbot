"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.webhook import router as webhook_router
from app.services.weather import close_http_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    yield
    await close_http_client()


app = FastAPI(
    title="Weather Chatbot API",
    description="WhatsApp weather chatbot for Accra, Ghana users",
    version="1.0.0",
    lifespan=lifespan,
)

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
    Health check endpoint.

    Returns:
        Status dictionary indicating the service is running.
    """
    return {"status": "healthy", "service": "weather-chatbot"}


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
