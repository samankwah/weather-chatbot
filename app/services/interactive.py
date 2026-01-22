"""Interactive messaging service for Twilio WhatsApp buttons and quick replies."""

import logging
from typing import Optional

from twilio.rest import Client

from app.config import get_settings

logger = logging.getLogger(__name__)

# Quick reply button configurations
WEATHER_QUICK_REPLIES: list[dict[str, str]] = [
    {"title": "Today's Weather", "id": "weather_today"},
    {"title": "Tomorrow", "id": "weather_tomorrow"},
    {"title": "This Week", "id": "weather_week"},
]

FORECAST_QUICK_REPLIES: list[dict[str, str]] = [
    {"title": "3-Day Forecast", "id": "forecast_3day"},
    {"title": "Weekly Forecast", "id": "forecast_week"},
    {"title": "Weekend", "id": "forecast_weekend"},
]

FARMING_QUICK_REPLIES: list[dict[str, str]] = [
    {"title": "Crop Advice", "id": "crop_advice"},
    {"title": "Soil Moisture", "id": "soil_moisture"},
    {"title": "Seasonal Outlook", "id": "seasonal_outlook"},
]

LOCATION_QUICK_REPLIES: list[dict[str, str]] = [
    {"title": "Accra", "id": "location_accra"},
    {"title": "Kumasi", "id": "location_kumasi"},
    {"title": "Tamale", "id": "location_tamale"},
    {"title": "Share Location 📍", "id": "location_share"},
]

# Button payload to query type mapping
BUTTON_PAYLOAD_MAP: dict[str, dict[str, str]] = {
    # Weather buttons
    "weather_today": {"query_type": "weather", "time": "today"},
    "weather_tomorrow": {"query_type": "forecast", "time": "tomorrow"},
    "weather_week": {"query_type": "forecast", "time": "this_week"},

    # Forecast buttons
    "forecast_3day": {"query_type": "forecast", "days": "3"},
    "forecast_week": {"query_type": "forecast", "days": "7"},
    "forecast_weekend": {"query_type": "forecast", "time": "weekend"},

    # Farming buttons
    "crop_advice": {"query_type": "crop_advice"},
    "soil_moisture": {"query_type": "soil"},
    "seasonal_outlook": {"query_type": "seasonal"},

    # Location buttons
    "location_accra": {"city": "Accra"},
    "location_kumasi": {"city": "Kumasi"},
    "location_tamale": {"city": "Tamale"},
    "location_share": {"action": "request_location"},
}


def parse_button_payload(payload: str) -> Optional[dict[str, str]]:
    """
    Parse a button payload ID into query parameters.

    Args:
        payload: The button payload ID (e.g., "weather_today").

    Returns:
        Dict with query parameters or None if not recognized.
    """
    return BUTTON_PAYLOAD_MAP.get(payload)


def get_welcome_message_with_buttons() -> str:
    """
    Get the welcome message text (buttons sent separately via content template).

    Returns:
        Welcome message string.
    """
    return (
        "👋 *Welcome to Ghana Weather Bot!*\n\n"
        "I can help you with:\n"
        "☀️ Current weather conditions\n"
        "📅 Weather forecasts\n"
        "🌱 Farming & crop advice\n"
        "🪴 Soil moisture data\n\n"
        "What would you like to know?"
    )


def get_quick_reply_message(category: str) -> tuple[str, list[dict[str, str]]]:
    """
    Get message text and quick reply buttons for a category.

    Args:
        category: The button category ("weather", "forecast", "farming", "location").

    Returns:
        Tuple of (message_text, buttons_list).
    """
    if category == "weather":
        return (
            "What weather info do you need?",
            WEATHER_QUICK_REPLIES,
        )
    elif category == "forecast":
        return (
            "Choose your forecast period:",
            FORECAST_QUICK_REPLIES,
        )
    elif category == "farming":
        return (
            "What farming info would help?",
            FARMING_QUICK_REPLIES,
        )
    elif category == "location":
        return (
            "Select a city or share your location:",
            LOCATION_QUICK_REPLIES,
        )
    else:
        return (
            "What can I help you with?",
            WEATHER_QUICK_REPLIES,
        )


class TwilioInteractiveProvider:
    """Provider for Twilio interactive messages (buttons, quick replies)."""

    def __init__(self) -> None:
        """Initialize Twilio client."""
        settings = get_settings()
        self.client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        self.from_number = settings.twilio_whatsapp_from
        self.content_sid_welcome = getattr(settings, 'twilio_content_sid_welcome', None)
        self.content_sid_weather = getattr(settings, 'twilio_content_sid_weather', None)
        self.content_sid_location = getattr(settings, 'twilio_content_sid_location', None)

    def send_quick_reply(
        self,
        to: str,
        body: str,
        buttons: list[dict[str, str]],
    ) -> bool:
        """
        Send a WhatsApp message with quick reply buttons.

        Note: This requires a pre-approved Content Template in Twilio.
        For sandbox testing, use regular messages instead.

        Args:
            to: Recipient's WhatsApp number.
            body: Message body text.
            buttons: List of button dicts with 'title' and 'id' keys.

        Returns:
            True if message was sent successfully.
        """
        try:
            # For Twilio WhatsApp, interactive messages require Content Templates
            # This is a simplified version that falls back to text with button hints
            button_hints = " | ".join([f"[{b['title']}]" for b in buttons[:3]])
            full_body = f"{body}\n\n{button_hints}"

            message = self.client.messages.create(
                from_=self.from_number,
                to=to,
                body=full_body,
            )
            return message.sid is not None

        except Exception as e:
            logger.error(f"Error sending quick reply to {to}: {e}")
            return False

    def send_content_template(
        self,
        to: str,
        content_sid: str,
        content_variables: dict[str, str] | None = None,
    ) -> bool:
        """
        Send a pre-approved Content Template message with buttons.

        Args:
            to: Recipient's WhatsApp number.
            content_sid: The Twilio Content SID for the template.
            content_variables: Variables to substitute in the template.

        Returns:
            True if message was sent successfully.
        """
        if not content_sid:
            logger.warning("No content SID provided for template message")
            return False

        try:
            message_params = {
                "from_": self.from_number,
                "to": to,
                "content_sid": content_sid,
            }

            if content_variables:
                message_params["content_variables"] = content_variables

            message = self.client.messages.create(**message_params)
            return message.sid is not None

        except Exception as e:
            logger.error(f"Error sending content template to {to}: {e}")
            return False

    def send_welcome_with_buttons(self, to: str) -> bool:
        """
        Send welcome message with quick action buttons.

        Args:
            to: Recipient's WhatsApp number.

        Returns:
            True if message was sent successfully.
        """
        if self.content_sid_welcome:
            return self.send_content_template(to, self.content_sid_welcome)

        # Fallback to text message with button hints
        return self.send_quick_reply(
            to,
            get_welcome_message_with_buttons(),
            WEATHER_QUICK_REPLIES,
        )

    def send_location_prompt(self, to: str) -> bool:
        """
        Send a message prompting for location selection.

        Args:
            to: Recipient's WhatsApp number.

        Returns:
            True if message was sent successfully.
        """
        if self.content_sid_location:
            return self.send_content_template(to, self.content_sid_location)

        message_text, buttons = get_quick_reply_message("location")
        return self.send_quick_reply(to, message_text, buttons)


# Module-level instance
_interactive_provider: TwilioInteractiveProvider | None = None


def get_interactive_provider() -> TwilioInteractiveProvider:
    """Get or create the interactive provider instance."""
    global _interactive_provider
    if _interactive_provider is None:
        _interactive_provider = TwilioInteractiveProvider()
    return _interactive_provider


def convert_button_to_message(button_payload: str, city: str | None = None) -> str:
    """
    Convert a button payload to a natural language message for processing.

    Args:
        button_payload: The button ID (e.g., "weather_today").
        city: Optional city context.

    Returns:
        Natural language message string.
    """
    params = parse_button_payload(button_payload)
    if not params:
        return "weather"  # Default fallback

    query_type = params.get("query_type", "weather")
    time_ref = params.get("time", "")
    days = params.get("days", "")
    action = params.get("action", "")
    button_city = params.get("city", "")

    # Build natural language message
    if action == "request_location":
        return "share my location"

    if button_city:
        return f"weather in {button_city}"

    location_str = f" in {city}" if city else ""

    if query_type == "weather":
        if time_ref == "today":
            return f"weather{location_str}"
        elif time_ref == "tomorrow":
            return f"weather tomorrow{location_str}"
        return f"weather{location_str}"

    elif query_type == "forecast":
        if time_ref == "weekend":
            return f"forecast this weekend{location_str}"
        elif days:
            return f"{days} day forecast{location_str}"
        elif time_ref:
            return f"forecast {time_ref}{location_str}"
        return f"forecast{location_str}"

    elif query_type == "crop_advice":
        return f"crop advice{location_str}"

    elif query_type == "soil":
        return f"soil moisture{location_str}"

    elif query_type == "seasonal":
        return f"seasonal outlook{location_str}"

    return f"{query_type}{location_str}"


# Contextual quick reply buttons based on query type
CONTEXTUAL_BUTTONS: dict[str, tuple[str, list[dict[str, str]]]] = {
    "weather": (
        "What else would you like to know?",
        [
            {"title": "Tomorrow", "id": "forecast_tomorrow"},
            {"title": "This Week", "id": "forecast_week"},
            {"title": "Farming Advice", "id": "crop_advice"},
        ],
    ),
    "forecast": (
        "Need more info?",
        [
            {"title": "Crop Advice", "id": "crop_advice"},
            {"title": "Soil Moisture", "id": "soil_moisture"},
            {"title": "Different City", "id": "change_location"},
        ],
    ),
    "crop_advice": (
        "More farming info?",
        [
            {"title": "Soil Moisture", "id": "soil_moisture"},
            {"title": "Seasonal Outlook", "id": "seasonal_outlook"},
            {"title": "Weather", "id": "weather_today"},
        ],
    ),
    "soil": (
        "What else?",
        [
            {"title": "Weather", "id": "weather_today"},
            {"title": "Crop Advice", "id": "crop_advice"},
            {"title": "Forecast", "id": "forecast_week"},
        ],
    ),
    "seasonal": (
        "Need more details?",
        [
            {"title": "Weather Now", "id": "weather_today"},
            {"title": "Crop Advice", "id": "crop_advice"},
            {"title": "Different City", "id": "change_location"},
        ],
    ),
    "greeting": (
        "What can I help you with?",
        [
            {"title": "Weather", "id": "weather_today"},
            {"title": "Forecast", "id": "forecast_week"},
            {"title": "Farming Advice", "id": "crop_advice"},
        ],
    ),
    "help": (
        "Quick options:",
        [
            {"title": "Weather", "id": "weather_today"},
            {"title": "Forecast", "id": "forecast_week"},
            {"title": "Farming Advice", "id": "crop_advice"},
        ],
    ),
}

# Buttons with rain condition
RAIN_BUTTONS: list[dict[str, str]] = [
    {"title": "Rain Forecast", "id": "forecast_rain"},
    {"title": "This Week", "id": "forecast_week"},
    {"title": "Farming Advice", "id": "crop_advice"},
]


def get_contextual_buttons(
    query_type: str,
    weather_condition: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """
    Get contextually appropriate quick reply buttons based on previous query.

    Args:
        query_type: The type of query just processed.
        weather_condition: Current weather condition (if available).

    Returns:
        Tuple of (prompt_text, buttons_list).
    """
    # If rain detected in weather, show rain-specific buttons
    if weather_condition:
        condition_lower = weather_condition.lower()
        if any(word in condition_lower for word in ["rain", "shower", "drizzle", "storm"]):
            return ("Rain on the way! Need more info?", RAIN_BUTTONS)

    # Get buttons for query type
    if query_type in CONTEXTUAL_BUTTONS:
        return CONTEXTUAL_BUTTONS[query_type]

    # Default to weather buttons
    return CONTEXTUAL_BUTTONS.get("greeting", ("What can I help with?", WEATHER_QUICK_REPLIES))


def format_buttons_as_text(buttons: list[dict[str, str]]) -> str:
    """
    Format buttons as text hints for display.

    Args:
        buttons: List of button dicts with 'title' keys.

    Returns:
        Formatted string like "[Option 1] [Option 2] [Option 3]"
    """
    return " ".join([f"[{b['title']}]" for b in buttons[:3]])
