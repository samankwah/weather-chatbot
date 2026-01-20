"""Location parsing service for WhatsApp messages."""

from app.models.schemas import LocationInput


def parse_webhook_location(
    latitude: str | None,
    longitude: str | None,
    body: str,
) -> LocationInput:
    """
    Parse location from Twilio webhook data.

    Checks for GPS coordinates first (from WhatsApp location share),
    then falls back to extracting city from text message.

    Args:
        latitude: Latitude string from Twilio webhook (or None).
        longitude: Longitude string from Twilio webhook (or None).
        body: Message body text.

    Returns:
        LocationInput with either coordinates or city name.
    """
    if latitude and longitude:
        try:
            lat = float(latitude)
            lon = float(longitude)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return LocationInput(latitude=lat, longitude=lon)
        except ValueError:
            pass

    city = extract_city_from_text(body)
    if city and len(city) > 100:
        city = city[:100]
    return LocationInput(city=city)


def extract_city_from_text(message: str) -> str | None:
    """
    Extract city name from user message text.

    Supports patterns like:
    - "weather in Lagos"
    - "weather for Kumasi"
    - "temperature at Nairobi"
    - Single city name like "Accra"

    Args:
        message: User's WhatsApp message text.

    Returns:
        City name if found, None to use default location.
    """
    # Normalize whitespace
    normalized = " ".join(message.split())
    message_lower = normalized.lower()

    weather_keywords = ["weather", "temperature", "temp", "forecast"]
    prepositions = ["in", "for", "at"]

    for keyword in weather_keywords:
        if keyword in message_lower:
            for prep in prepositions:
                pattern = f"{keyword} {prep} "
                if pattern in message_lower:
                    start_index = message_lower.find(pattern) + len(pattern)
                    city = normalized[start_index:].strip()
                    city = city.split("?")[0].strip()
                    city = city.split(".")[0].strip()
                    if city:
                        return city

    for prep in prepositions:
        pattern = f"{prep} "
        if message_lower.startswith(pattern):
            city = normalized[len(pattern):].strip()
            if city:
                return city

    if message_lower not in weather_keywords and len(normalized.split()) <= 3:
        if not any(kw in message_lower for kw in weather_keywords):
            return normalized.strip()

    return None
