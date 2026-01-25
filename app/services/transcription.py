"""Voice transcription service using Groq Whisper Large v3."""

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from groq import AsyncGroq

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Result of voice transcription."""

    success: bool
    text: str | None = None
    error: str | None = None
    language: str | None = None
    duration: float | None = None


class TranscriptionProvider(Protocol):
    """Protocol for transcription providers."""

    async def transcribe_audio(
        self,
        audio_url: str,
        language: str | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio from a URL.

        Args:
            audio_url: URL to the audio file.
            language: Optional language hint (ISO 639-1 code).

        Returns:
            TranscriptionResult with transcribed text or error.
        """
        ...


class GroqWhisperProvider:
    """Groq Whisper Large v3 transcription provider."""

    def __init__(self) -> None:
        """Initialize Groq Whisper provider."""
        settings = get_settings()
        self.api_key = settings.groq_api_key
        self.model = settings.groq_whisper_model
        self.timeout = settings.groq_whisper_timeout
        self.enabled = settings.voice_transcription_enabled

        if self.api_key:
            self.client = AsyncGroq(api_key=self.api_key)
        else:
            self.client = None
            logger.warning("Groq API key not configured - voice transcription disabled")

    async def download_audio(
        self,
        audio_url: str,
        auth: tuple[str, str] | None = None,
    ) -> bytes | None:
        """
        Download audio file from URL.

        Args:
            audio_url: URL to download audio from.
            auth: Optional (username, password) tuple for basic auth.

        Returns:
            Audio file bytes or None if download failed.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if auth:
                    response = await client.get(audio_url, auth=auth)
                else:
                    response = await client.get(audio_url)

                if response.status_code == 200:
                    return response.content
                else:
                    logger.error(
                        f"Failed to download audio: HTTP {response.status_code}"
                    )
                    return None
        except httpx.TimeoutException:
            logger.error(f"Timeout downloading audio from {audio_url}")
            return None
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            return None

    async def transcribe_audio(
        self,
        audio_url: str,
        language: str | None = None,
        auth: tuple[str, str] | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio from a URL using Groq Whisper.

        Args:
            audio_url: URL to the audio file (Twilio media URL).
            language: Optional language hint (ISO 639-1 code, e.g., 'en', 'tw').
            auth: Optional (username, password) for Twilio media authentication.

        Returns:
            TranscriptionResult with transcribed text or error.
        """
        if not self.enabled:
            return TranscriptionResult(
                success=False,
                error="Voice transcription is disabled",
            )

        if not self.client:
            return TranscriptionResult(
                success=False,
                error="Groq API key not configured",
            )

        # Download the audio file
        audio_data = await self.download_audio(audio_url, auth=auth)
        if not audio_data:
            return TranscriptionResult(
                success=False,
                error="Failed to download audio file",
            )

        try:
            # Create a file-like tuple for the Groq API
            # Format: (filename, content, content_type)
            audio_file = ("voice_message.ogg", audio_data, "audio/ogg")

            # Build transcription parameters
            transcription_params = {
                "file": audio_file,
                "model": self.model,
                "response_format": "verbose_json",
            }

            # Add language hint if provided
            # Whisper supports many languages including Twi (tw), Akan, English (en)
            if language:
                transcription_params["language"] = language

            # Call Groq Whisper API
            transcription = await self.client.audio.transcriptions.create(
                **transcription_params
            )

            # Extract results
            text = transcription.text.strip() if transcription.text else None
            detected_language = getattr(transcription, "language", None)
            duration = getattr(transcription, "duration", None)

            if text:
                logger.info(
                    f"Transcription successful: '{text[:50]}...' "
                    f"(lang={detected_language}, duration={duration}s)"
                )
                return TranscriptionResult(
                    success=True,
                    text=text,
                    language=detected_language,
                    duration=duration,
                )
            else:
                return TranscriptionResult(
                    success=False,
                    error="Transcription returned empty text",
                )

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return TranscriptionResult(
                success=False,
                error=f"Transcription failed: {str(e)}",
            )


class FallbackTranscriptionProvider:
    """Fallback provider when Groq is not available."""

    async def transcribe_audio(
        self,
        audio_url: str,
        language: str | None = None,
        auth: tuple[str, str] | None = None,
    ) -> TranscriptionResult:
        """Return error for missing transcription service."""
        return TranscriptionResult(
            success=False,
            error="Voice transcription is not available. Please send a text message.",
        )


# Singleton instance
_transcription_provider: GroqWhisperProvider | FallbackTranscriptionProvider | None = None


def get_transcription_provider() -> GroqWhisperProvider | FallbackTranscriptionProvider:
    """Get the transcription provider instance."""
    global _transcription_provider

    if _transcription_provider is None:
        settings = get_settings()
        if settings.groq_api_key and settings.voice_transcription_enabled:
            _transcription_provider = GroqWhisperProvider()
        else:
            _transcription_provider = FallbackTranscriptionProvider()

    return _transcription_provider
