"""Weather API integration service."""

import httpx
from cachetools import TTLCache

from app.config import get_settings
from app.models.schemas import LocationInput, WeatherData, WeatherResponse

# Cache weather data for 5 minutes (300 seconds) to reduce API calls
weather_cache: TTLCache = TTLCache(maxsize=100, ttl=300)

# Singleton HTTP client (initialized lazily)
_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create the singleton HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def close_http_client() -> None:
    """Close the HTTP client (call on app shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def get_weather(city: str | None = None) -> WeatherResponse:
    """
    Fetch weather data for a given city.

    Note: This function is deprecated. Prefer get_weather_by_coordinates()
    for location-specific accuracy. This function is kept for backward
    compatibility with city name lookups.

    Args:
        city: City name to get weather for. Required.
              Supports "City, Country" format (e.g., "Kade, Ghana" or "Kade, GH").

    Returns:
        WeatherResponse with weather data or error message.
    """
    if not city:
        return WeatherResponse(
            success=False,
            error_message=(
                "I need a location to provide weather. "
                "Please share your location or specify a place name."
            ),
        )

    settings = get_settings()
    location = city
    cache_key = f"city:{location.lower()}"

    if cache_key in weather_cache:
        return weather_cache[cache_key]

    # Parse city and country if provided (e.g., "Kade, Ghana" or "Kade, GH")
    query = location
    if "," in location:
        parts = [p.strip() for p in location.split(",", 1)]
        city_name = parts[0]
        country = parts[1] if len(parts) > 1 else ""
        # Convert common country names to ISO codes for Ghana region
        country_map = {
            "ghana": "GH", "nigeria": "NG", "kenya": "KE",
            "south africa": "ZA", "egypt": "EG", "morocco": "MA",
        }
        country_code = country_map.get(country.lower(), country.upper())
        query = f"{city_name},{country_code}" if country_code else city_name

    params = {
        "q": query,
        "appid": settings.weather_api_key,
        "units": "metric",
    }

    try:
        client = await get_http_client()
        response = await client.get(
            settings.weather_api_url,
            params=params,
        )

        if response.status_code == 404:
            return WeatherResponse(
                success=False,
                error_message=f"I couldn't find weather data for '{location}'. "
                "Please check the spelling or try adding the country "
                "(e.g., 'Kade, Ghana' or 'Lagos, Nigeria').",
            )

        if response.status_code != 200:
            return WeatherResponse(
                success=False,
                error_message="I'm having trouble getting weather data right now. "
                "Please try again in a moment.",
            )

        data = response.json()
        weather_data = parse_weather_response(data)
        result = WeatherResponse(success=True, data=weather_data)
        weather_cache[cache_key] = result
        return result

    except httpx.TimeoutException:
        return WeatherResponse(
            success=False,
            error_message="The weather service is taking too long to respond. "
            "Please try again.",
        )
    except httpx.RequestError:
        return WeatherResponse(
            success=False,
            error_message="I couldn't connect to the weather service. "
            "Please try again later.",
        )


async def get_weather_by_coordinates(
    latitude: float,
    longitude: float,
) -> WeatherResponse:
    """
    Fetch weather data for given GPS coordinates.

    Args:
        latitude: GPS latitude coordinate.
        longitude: GPS longitude coordinate.

    Returns:
        WeatherResponse with weather data or error message.
    """
    settings = get_settings()
    cache_key = f"coords:{latitude:.4f},{longitude:.4f}"

    if cache_key in weather_cache:
        return weather_cache[cache_key]

    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": settings.weather_api_key,
        "units": "metric",
    }

    try:
        client = await get_http_client()
        response = await client.get(
            settings.weather_api_url,
            params=params,
        )

        if response.status_code != 200:
            return WeatherResponse(
                success=False,
                error_message="I'm having trouble getting weather data right now. "
                "Please try again in a moment.",
            )

        data = response.json()
        weather_data = parse_weather_response(data)
        result = WeatherResponse(success=True, data=weather_data)
        weather_cache[cache_key] = result
        return result

    except httpx.TimeoutException:
        return WeatherResponse(
            success=False,
            error_message="The weather service is taking too long to respond. "
            "Please try again.",
        )
    except httpx.RequestError:
        return WeatherResponse(
            success=False,
            error_message="I couldn't connect to the weather service. "
            "Please try again later.",
        )


async def get_weather_for_location(location: LocationInput) -> WeatherResponse:
    """
    Fetch weather data for a LocationInput.

    IMPORTANT: This function now requires coordinates. City-name-only lookups
    are no longer supported to ensure location-specific accuracy.

    Args:
        location: LocationInput with coordinates (required).

    Returns:
        WeatherResponse with weather data or error message.
    """
    if not location.has_coordinates:
        return WeatherResponse(
            success=False,
            error_message=(
                "I need your location to provide accurate weather. "
                "Please share your location using WhatsApp's location button "
                "(tap the paperclip icon and select Location), "
                "or tell me a specific place name."
            ),
        )
    return await get_weather_by_coordinates(
        location.latitude,
        location.longitude,
    )


def parse_weather_response(data: dict) -> WeatherData:
    """
    Parse OpenWeatherMap API response into WeatherData model.

    Args:
        data: Raw API response dictionary.

    Returns:
        WeatherData model with parsed values.
    """
    return WeatherData(
        city=data["name"],
        country=data["sys"]["country"],
        temperature=data["main"]["temp"],
        feels_like=data["main"]["feels_like"],
        humidity=data["main"]["humidity"],
        description=data["weather"][0]["description"],
        wind_speed=data["wind"]["speed"],
        icon=data["weather"][0]["icon"],
    )


def extract_city_from_message(message: str) -> str | None:
    """
    Extract city name from user message.

    Args:
        message: User's WhatsApp message text.

    Returns:
        City name if found, None to use default.
    """
    message_lower = message.lower().strip()

    weather_keywords = ["weather", "temperature", "temp", "forecast"]
    prepositions = ["in", "for", "at"]

    for keyword in weather_keywords:
        if keyword in message_lower:
            for prep in prepositions:
                pattern = f"{keyword} {prep} "
                if pattern in message_lower:
                    start_index = message_lower.find(pattern) + len(pattern)
                    city = message[start_index:].strip()
                    city = city.split("?")[0].strip()
                    city = city.split(".")[0].strip()
                    if city:
                        return city

    for prep in prepositions:
        pattern = f"{prep} "
        if message_lower.startswith(pattern):
            city = message[len(pattern):].strip()
            if city:
                return city

    if message_lower not in weather_keywords and len(message.split()) <= 3:
        if not any(kw in message_lower for kw in weather_keywords):
            return message.strip()

    return None
