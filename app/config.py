"""Configuration management using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Twilio Configuration
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_number: str

    # Weather API Configuration
    weather_api_key: str
    weather_api_url: str = "https://api.openweathermap.org/data/2.5/weather"

    # Application Settings
    default_city: str = "Accra"
    default_country: str = "Ghana"

    @property
    def twilio_whatsapp_from(self) -> str:
        """Return the full WhatsApp number format for Twilio."""
        number = self.twilio_whatsapp_number
        if not number.startswith("whatsapp:"):
            return f"whatsapp:{number}"
        return number

    @property
    def default_location(self) -> str:
        """Return the default location string."""
        return f"{self.default_city},{self.default_country}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
