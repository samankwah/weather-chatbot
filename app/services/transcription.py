"""Voice transcription service using Groq Whisper Large v3."""

import io
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
    ) -> tuple[bytes | None, str | None]:
        """
        Download audio file from URL.

        Args:
            audio_url: URL to download audio from.
            auth: Optional (username, password) tuple for basic auth.

        Returns:
            Tuple of (audio_bytes, content_type) or (None, None) if download failed.
        """
        try:
            logger.info(f"Downloading audio from: {audio_url[:50]}...")
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                if auth:
                    response = await client.get(audio_url, auth=auth)
                else:
                    response = await client.get(audio_url)

                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "audio/ogg")
                    logger.info(
                        f"Downloaded audio: {len(response.content)} bytes, "
                        f"content-type: {content_type}"
                    )
                    return response.content, content_type
                else:
                    logger.error(
                        f"Failed to download audio: HTTP {response.status_code}, "
                        f"body: {response.text[:200]}"
                    )
                    return None, None
        except httpx.TimeoutException:
            logger.error(f"Timeout downloading audio from {audio_url}")
            return None, None
        except Exception as e:
            logger.error(f"Error downloading audio: {e}", exc_info=True)
            return None, None

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
        audio_data, content_type = await self.download_audio(audio_url, auth=auth)
        if not audio_data:
            return TranscriptionResult(
                success=False,
                error="Failed to download audio file",
            )

        try:
            # Parse content type (handle "audio/ogg; codecs=opus" format)
            base_content_type = content_type.split(";")[0].strip() if content_type else "audio/ogg"

            # Determine file extension from content type
            extension_map = {
                "audio/ogg": ".ogg",
                "audio/opus": ".opus",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "audio/wav": ".wav",
                "audio/webm": ".webm",
                "audio/x-m4a": ".m4a",
                "audio/aac": ".aac",
            }
            ext = extension_map.get(base_content_type, ".ogg")
            filename = f"voice_message{ext}"

            # Create a file-like object for the Groq API
            # The API expects a tuple of (filename, file_content, content_type)
            # Use the base content type without codec info
            audio_file = (filename, audio_data, base_content_type)

            # Log audio size for debugging
            logger.info(f"Audio file size: {len(audio_data)} bytes, type: {base_content_type} (original: {content_type})")

            # Call Groq Whisper API
            # Build kwargs dynamically to avoid passing None values
            kwargs = {
                "file": audio_file,
                "model": self.model,
                "response_format": "verbose_json",
            }

            # Add language hint if provided
            # Whisper supports many languages including Twi, Akan, English
            if language:
                kwargs["language"] = language

            transcription = await self.client.audio.transcriptions.create(**kwargs)

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
            logger.error(f"Transcription error: {type(e).__name__}: {e}", exc_info=True)
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
