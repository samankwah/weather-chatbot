"""Configuration management using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra environment variables
    )

    # Twilio Configuration
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str

    # Twilio Content Templates (for interactive buttons - optional)
    twilio_content_sid_welcome: str | None = None
    twilio_content_sid_weather: str | None = None
    twilio_content_sid_location: str | None = None

    # Weather API Configuration
    weather_api_key: str = ""
    weather_api_url: str = "https://api.openweathermap.org/data/2.5/weather"
    weather_forecast_url: str = "https://api.openweathermap.org/data/2.5/forecast"

    # Groq AI Configuration (optional - falls back to keyword parsing if not set)
    groq_api_key: str | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_timeout: float = 10.0

    # Groq Whisper ASR Configuration (voice-to-text)
    groq_whisper_model: str = "whisper-large-v3"
    groq_whisper_timeout: float = 30.0  # Voice transcription may take longer
    voice_transcription_enabled: bool = True

    # Open-Meteo Configuration (FREE - no API key needed)
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    open_meteo_forecast_days: int = 16
    open_meteo_marine_url: str = "https://marine-api.open-meteo.com/v1/marine"

    # Memory Configuration
    memory_ttl_seconds: int = 3600

    # Redis Configuration
    redis_url: str = "redis://localhost:6379"
    use_redis: bool = False

    # Geocoding Configuration (OpenStreetMap Nominatim - free, no API key)
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_user_agent: str = "weather-chatbot/1.0"
    geocoding_cache_ttl: int = 86400  # 24 hours
    geocoding_confidence_threshold: float = 0.7
    default_country_bias: str = "Ghana"

    # Typing Delay Settings (for natural UX)
    typing_delay_enabled: bool = True
    typing_delay_min: float = 0.5
    typing_delay_max: float = 2.0

    # Conversation Session Settings
    conversation_timeout_seconds: int = 300  # 5 minutes - follow-up detection
    conversation_min_history: int = 2  # Min messages for follow-up detection

    # Localization Settings
    default_language: str = "en"

    @property
    def twilio_whatsapp_from(self) -> str:
        """Return the full WhatsApp number format for Twilio."""
        number = self.twilio_whatsapp_number
        if not number.startswith("whatsapp:"):
            return f"whatsapp:{number}"
        return number


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
