"""Messaging service with provider abstraction."""

import asyncio
import logging
import random
import re
from functools import lru_cache
from typing import Protocol

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import get_settings
from app.models.schemas import WeatherData

logger = logging.getLogger(__name__)

# Typing delay configuration (in seconds)
TYPING_DELAYS: dict[str, tuple[float, float]] = {
    "short": (0.5, 1.0),    # Greeting/Help - quick responses
    "medium": (1.0, 2.0),   # Weather queries
    "long": (2.0, 3.5),     # Forecast/Seasonal - more complex data
}


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


def format_whatsapp_message(
    text: str,
    bold_words: list[str] | None = None,
    italic_phrases: list[str] | None = None,
) -> str:
    """
    Apply WhatsApp markdown formatting to a message.

    WhatsApp supports:
    - *bold*
    - _italic_
    - ~strikethrough~
    - ```monospace```

    Args:
        text: The message text to format.
        bold_words: List of words/phrases to make bold.
        italic_phrases: List of phrases to make italic.

    Returns:
        Formatted message with WhatsApp markdown.
    """
    formatted = text

    # Apply bold formatting
    if bold_words:
        for word in bold_words:
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(word) + r'\b'
            formatted = re.sub(pattern, f"*{word}*", formatted, flags=re.IGNORECASE)

    # Apply italic formatting
    if italic_phrases:
        for phrase in italic_phrases:
            formatted = formatted.replace(phrase, f"_{phrase}_")

    return formatted


def format_weather_response(
    city: str,
    temperature: float,
    feels_like: float,
    description: str,
    humidity: int,
    wind_speed: float,
    weather_emoji: str,
    tip: str | None = None,
) -> str:
    """
    Format weather data with WhatsApp markdown for a conversational response.

    Args:
        city: City name.
        temperature: Temperature in Celsius.
        feels_like: Feels like temperature.
        description: Weather description.
        humidity: Humidity percentage.
        wind_speed: Wind speed in km/h.
        weather_emoji: Emoji for weather condition.
        tip: Optional tip text.

    Returns:
        Formatted WhatsApp message.
    """
    msg = f"*{city} Weather* {weather_emoji}\n\n"
    msg += f"It's *{temperature:.0f}°C* (feels like {feels_like:.0f}°C)\n"
    msg += f"{weather_emoji} {description.capitalize()}\n"
    msg += f"💧 {humidity}% | 💨 {wind_speed:.0f} km/h"

    if tip:
        msg += f"\n\n_💡 {tip}_"

    return msg


def get_weather_tip(
    temperature: float,
    humidity: int,
    description: str,
) -> str:
    """
    Generate a contextual weather tip based on conditions.

    Args:
        temperature: Temperature in Celsius.
        humidity: Humidity percentage.
        description: Weather description.

    Returns:
        Weather tip string.
    """
    desc_lower = description.lower()

    # Rain conditions
    if any(word in desc_lower for word in ["rain", "drizzle", "shower"]):
        return "Grab an umbrella if heading out!"

    # Storm conditions
    if any(word in desc_lower for word in ["storm", "thunder"]):
        return "Stay indoors if possible - stormy weather!"

    # Hot conditions
    if temperature >= 35:
        return "Very hot! Stay hydrated and take breaks in shade."
    if temperature >= 32:
        return "Quite warm today - perfect for early morning fieldwork."

    # High humidity
    if humidity >= 80:
        return "High humidity - good for transplanting seedlings!"
    if humidity <= 40:
        return "Dry air today - consider irrigation for crops."

    # Clear/sunny
    if any(word in desc_lower for word in ["clear", "sunny"]):
        return "Beautiful day! Great for outdoor work."

    # Cloudy
    if any(word in desc_lower for word in ["cloud", "overcast"]):
        return "Cloudy but comfortable - good working weather!"

    # Default
    return "Have a productive day!"


async def simulate_typing_delay(
    response_length: int,
    complexity: str = "medium",
) -> None:
    """
    Add realistic typing delay based on response complexity.

    This simulates human-like typing behavior for a better UX.

    Args:
        response_length: Length of the response message.
        complexity: "short", "medium", or "long" based on query type.
    """
    min_delay, max_delay = TYPING_DELAYS.get(complexity, TYPING_DELAYS["medium"])

    # Adjust based on response length (longer = more delay)
    length_factor = min(response_length / 200, 1.0)  # Cap at 200 chars
    adjusted_min = min_delay + (length_factor * 0.5)
    adjusted_max = max_delay + (length_factor * 0.5)

    delay = random.uniform(adjusted_min, adjusted_max)
    await asyncio.sleep(delay)


def get_complexity_for_query(query_type: str) -> str:
    """
    Determine response complexity based on query type.

    Args:
        query_type: The type of query (e.g., "weather", "forecast", "greeting").

    Returns:
        Complexity level: "short", "medium", or "long".
    """
    short_queries = {"greeting", "help"}
    long_queries = {"forecast", "seasonal", "seasonal_onset", "seasonal_cessation",
                    "dry_spell", "season_length", "crop_advice", "dekadal"}

    if query_type in short_queries:
        return "short"
    elif query_type in long_queries:
        return "long"
    return "medium"
