"""Pydantic models for request/response validation."""

from typing import Optional

from pydantic import BaseModel, Field


class TwilioWebhookRequest(BaseModel):
    """Model for incoming Twilio WhatsApp webhook data."""

    message_sid: str = Field(alias="MessageSid")
    account_sid: str = Field(alias="AccountSid")
    from_number: str = Field(alias="From")
    to_number: str = Field(alias="To")
    body: str = Field(alias="Body")
    num_media: int = Field(default=0, alias="NumMedia")
    profile_name: Optional[str] = Field(default=None, alias="ProfileName")

    class Config:
        populate_by_name = True


class WeatherData(BaseModel):
    """Model for parsed weather information."""

    city: str
    country: str
    temperature: float
    feels_like: float
    humidity: int
    description: str
    wind_speed: float
    icon: str


class WeatherResponse(BaseModel):
    """Model for weather API response."""

    success: bool
    data: Optional[WeatherData] = None
    error_message: Optional[str] = None


class LocationInput(BaseModel):
    """Model for location input (either city name or coordinates)."""

    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    confidence: float = 0.0
    source: str = "unknown"  # "gps", "geocoded", "user_context", "home"

    @property
    def has_coordinates(self) -> bool:
        """Check if coordinates are available."""
        return self.latitude is not None and self.longitude is not None

    @property
    def is_confident(self) -> bool:
        """Check if location confidence is above threshold (0.7)."""
        return self.confidence >= 0.7


class ChatMessage(BaseModel):
    """Model for internal message handling."""

    sender: str
    recipient: str
    content: str
    message_type: str = "text"


class WebhookResponse(BaseModel):
    """Model for webhook response to Twilio."""

    success: bool
    message: str
