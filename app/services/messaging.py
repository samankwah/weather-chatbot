"""Messaging service with provider abstraction."""

import logging
from functools import lru_cache
from typing import Protocol

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import get_settings
from app.models.schemas import WeatherData

logger = logging.getLogger(__name__)


class MessagingProvider(Protocol):
    """Protocol for messaging providers."""

    def send_message(self, to: str, body: str) -> bool:
        """Send a message to a recipient."""
        ...


class TwilioProvider:
    """Twilio WhatsApp messaging provider."""

    def __init__(self) -> None:
        """Initialize Twilio client."""
        settings = get_settings()
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self.from_number = settings.twilio_whatsapp_from

    def send_message(self, to: str, body: str) -> bool:
        """
        Send a WhatsApp message via Twilio.

        Args:
            to: Recipient's WhatsApp number (with whatsapp: prefix).
            body: Message content.

        Returns:
            True if message was sent successfully.
        """
        try:
            message = self.client.messages.create(
                from_=self.from_number,
                to=to,
                body=body,
            )
            return message.sid is not None
        except TwilioRestException as e:
            logger.error(f"Twilio API error sending message to {to}: {e.code} - {e.msg}")
            return False


class MetaCloudProvider:
    """
    Placeholder for Meta Cloud API messaging provider.

    To implement:
    1. Add META_ACCESS_TOKEN and META_PHONE_NUMBER_ID to config
    2. Implement send_message using Meta's WhatsApp Business API
    3. Handle webhook verification for Meta webhooks
    """

    def __init__(self) -> None:
        """Initialize Meta Cloud API client."""
        pass

    def send_message(self, to: str, body: str) -> bool:
        """Send a WhatsApp message via Meta Cloud API."""
        raise NotImplementedError("Meta Cloud API provider not yet implemented")


@lru_cache(maxsize=1)
def get_messaging_provider() -> MessagingProvider:
    """
    Get the configured messaging provider.

    Returns:
        MessagingProvider instance (currently TwilioProvider).
    """
    return TwilioProvider()


def format_weather_message(weather: WeatherData) -> str:
    """
    Format weather data into a friendly WhatsApp message.

    Args:
        weather: WeatherData model with weather information.

    Returns:
        Formatted message string.
    """
    weather_emoji = get_weather_emoji(weather.icon)

    message = (
        f"{weather_emoji} Weather in {weather.city}, {weather.country}\n\n"
        f"Temperature: {weather.temperature:.1f}°C\n"
        f"Feels like: {weather.feels_like:.1f}°C\n"
        f"Conditions: {weather.description.capitalize()}\n"
        f"Humidity: {weather.humidity}%\n"
        f"Wind: {weather.wind_speed} km/h\n\n"
        f"Have a great day!"
    )

    return message


def format_error_message(error: str) -> str:
    """
    Format error message for user-friendly display.

    Args:
        error: Error message string.

    Returns:
        Formatted error message.
    """
    return f"Oops! {error}"


def format_help_message() -> str:
    """
    Generate help message for users.

    Returns:
        Help message with usage instructions.
    """
    return (
        "Hi there! I'm your weather assistant.\n\n"
        "Here's how to use me:\n"
        "• Send 'weather' for Accra weather\n"
        "• Send 'weather in Lagos' for Lagos weather\n"
        "• Or just type a city name like 'Kumasi'\n"
        "• For smaller towns, add country: 'Kade, Ghana'\n"
        "• Share your location for local weather\n\n"
        "Try it out!"
    )


def get_weather_emoji(icon_code: str) -> str:
    """
    Get weather emoji based on OpenWeatherMap icon code.

    Args:
        icon_code: OpenWeatherMap weather icon code.

    Returns:
        Corresponding emoji string.
    """
    emoji_map = {
        "01d": "☀️",
        "01n": "🌙",
        "02d": "⛅",
        "02n": "☁️",
        "03d": "☁️",
        "03n": "☁️",
        "04d": "☁️",
        "04n": "☁️",
        "09d": "🌧️",
        "09n": "🌧️",
        "10d": "🌦️",
        "10n": "🌧️",
        "11d": "⛈️",
        "11n": "⛈️",
        "13d": "❄️",
        "13n": "❄️",
        "50d": "🌫️",
        "50n": "🌫️",
    }
    return emoji_map.get(icon_code, "🌡️")
