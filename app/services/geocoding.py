"""Geocoding service using OpenStreetMap Nominatim API."""

import asyncio
import logging
from datetime import datetime, timedelta

import httpx
from cachetools import TTLCache
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)

# Cache geocoding results for 24 hours
_geocoding_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)

# Rate limiting: track last request time
_last_request_time: datetime | None = None
_rate_limit_lock = asyncio.Lock()

# Singleton HTTP client
_http_client: httpx.AsyncClient | None = None


class GeocodingResult(BaseModel):
    """Model for a single geocoding result."""

    place_name: str
    latitude: float
    longitude: float
    confidence: float  # 0.0 to 1.0
    place_type: str
    bounding_box: tuple[float, float, float, float] | None = None
    original_query: str
    display_name: str  # Full display name from Nominatim


class GeocodingResponse(BaseModel):
    """Model for geocoding API response."""

    success: bool
    results: list[GeocodingResult] = []
    best_match: GeocodingResult | None = None
    needs_clarification: bool = False
    clarification_options: list[str] = []
    error_message: str | None = None


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


async def _rate_limit() -> None:
    """Enforce Nominatim rate limit of 1 request per second."""
    global _last_request_time
    async with _rate_limit_lock:
        if _last_request_time is not None:
            elapsed = datetime.now() - _last_request_time
            if elapsed < timedelta(seconds=1):
                await asyncio.sleep(1 - elapsed.total_seconds())
        _last_request_time = datetime.now()


def calculate_confidence(result: dict) -> float:
    """
    Calculate confidence score for a geocoding result.

    Based on:
    - Nominatim's importance score (0-1)
    - Bounding box size (smaller = more precise)
    - Place type (village/hamlet > town > city > region)

    Args:
        result: Raw Nominatim API result dictionary.

    Returns:
        Confidence score from 0.0 to 1.0.
    """
    base = 0.5

    # Add importance score contribution (0-0.2)
    importance = float(result.get("importance", 0))
    base += importance * 0.2

    # Add bounding box bonus based on area size
    bbox = result.get("boundingbox", [])
    if len(bbox) == 4:
        try:
            lat_diff = abs(float(bbox[1]) - float(bbox[0]))
            lon_diff = abs(float(bbox[3]) - float(bbox[2]))
            area = lat_diff * lon_diff

            # Smaller areas = higher confidence
            if area < 0.01:  # Very small - village level
                base += 0.2
            elif area < 0.1:  # Small - town level
                base += 0.15
            elif area < 1.0:  # Medium - city level
                base += 0.1
            # Large areas (regions) get no bonus
        except (ValueError, IndexError):
            pass

    # Add type bonus
    place_type = result.get("type", "").lower()
    place_class = result.get("class", "").lower()

    # Specific place types boost confidence
    if place_type in ("village", "hamlet", "neighbourhood"):
        base += 0.1
    elif place_type in ("town", "suburb"):
        base += 0.05
    elif place_type in ("city", "municipality"):
        base += 0.0
    elif place_type in ("administrative", "state", "region", "country"):
        base -= 0.1

    # Place class adjustments
    if place_class == "place":
        base += 0.05
    elif place_class in ("boundary", "administrative"):
        base -= 0.05

    # Clamp to 0.0-1.0
    return max(0.0, min(1.0, base))


def should_ask_clarification(response: GeocodingResponse) -> bool:
    """
    Determine if we should ask the user for clarification.

    Returns True if:
    - Best match confidence is below threshold (0.7)
    - Multiple results have similar confidence scores

    Args:
        response: GeocodingResponse with results.

    Returns:
        True if clarification is needed.
    """
    settings = get_settings()
    threshold = settings.geocoding_confidence_threshold

    if not response.success or not response.best_match:
        return True

    # Low confidence on best match
    if response.best_match.confidence < threshold:
        return True

    # Multiple results with similar confidence
    if len(response.results) > 1:
        best_conf = response.best_match.confidence
        similar_results = [
            r for r in response.results
            if r.place_name != response.best_match.place_name
            and abs(r.confidence - best_conf) < 0.15
        ]
        if similar_results:
            return True

    return False


def format_clarification_question(response: GeocodingResponse) -> str:
    """
    Format a user-friendly clarification question.

    Args:
        response: GeocodingResponse with ambiguous results.

    Returns:
        Formatted question string with numbered options.
    """
    if not response.results:
        return (
            "I couldn't find that location. "
            "Please share your location using WhatsApp's location button "
            "(tap the paperclip icon and select Location)."
        )

    query = response.results[0].original_query if response.results else "that place"

    lines = [f'I found several places called "{query}":']
    for i, result in enumerate(response.results[:5], 1):
        # Extract region from display name
        display_parts = result.display_name.split(", ")
        if len(display_parts) > 2:
            region = ", ".join(display_parts[1:3])
        else:
            region = display_parts[-1] if len(display_parts) > 1 else ""

        lines.append(f"{i}. {result.place_name}, {region}")

    lines.append("\nWhich one? Reply with the number.")
    return "\n".join(lines)


async def geocode_location(
    query: str,
    country_bias: str | None = None,
) -> GeocodingResponse:
    """
    Geocode a place name to coordinates using Nominatim.

    Args:
        query: Place name to geocode (e.g., "Kade", "Assin Fosu, Ghana").
        country_bias: Country to bias results towards (default: from settings).

    Returns:
        GeocodingResponse with results and confidence scores.
    """
    settings = get_settings()
    country_bias = country_bias or settings.default_country_bias

    # Check cache first
    cache_key = f"{query.lower()}:{country_bias.lower()}"
    if cache_key in _geocoding_cache:
        logger.debug(f"Geocoding cache hit for '{query}'")
        return _geocoding_cache[cache_key]

    # Build Nominatim request parameters
    params = {
        "q": query,
        "format": "json",
        "limit": 5,
        "addressdetails": 1,
    }

    # Add country code bias if specified
    if country_bias:
        country_codes = {
            "ghana": "gh",
            "nigeria": "ng",
            "kenya": "ke",
            "south africa": "za",
            "egypt": "eg",
            "morocco": "ma",
        }
        code = country_codes.get(country_bias.lower(), country_bias.lower())
        if len(code) == 2:
            params["countrycodes"] = code

    headers = {"User-Agent": settings.nominatim_user_agent}

    try:
        # Enforce rate limit
        await _rate_limit()

        client = await get_http_client()
        response = await client.get(
            f"{settings.nominatim_base_url}/search",
            params=params,
            headers=headers,
        )

        if response.status_code != 200:
            logger.error(f"Nominatim API error: {response.status_code}")
            return GeocodingResponse(
                success=False,
                error_message="Geocoding service temporarily unavailable.",
            )

        data = response.json()

        if not data:
            # Try again without country bias
            if country_bias:
                params.pop("countrycodes", None)
                await _rate_limit()
                response = await client.get(
                    f"{settings.nominatim_base_url}/search",
                    params=params,
                    headers=headers,
                )
                data = response.json() if response.status_code == 200 else []

        if not data:
            return GeocodingResponse(
                success=False,
                needs_clarification=True,
                error_message=f"I couldn't find '{query}'. "
                "Please check the spelling or share your location.",
            )

        # Parse results
        results: list[GeocodingResult] = []
        for item in data:
            try:
                bbox = None
                if "boundingbox" in item and len(item["boundingbox"]) == 4:
                    bbox = (
                        float(item["boundingbox"][0]),
                        float(item["boundingbox"][1]),
                        float(item["boundingbox"][2]),
                        float(item["boundingbox"][3]),
                    )

                # Extract clean place name from address
                address = item.get("address", {})
                place_name = (
                    address.get("village")
                    or address.get("town")
                    or address.get("city")
                    or address.get("municipality")
                    or address.get("suburb")
                    or item.get("name", query)
                )

                result = GeocodingResult(
                    place_name=place_name,
                    latitude=float(item["lat"]),
                    longitude=float(item["lon"]),
                    confidence=calculate_confidence(item),
                    place_type=item.get("type", "unknown"),
                    bounding_box=bbox,
                    original_query=query,
                    display_name=item.get("display_name", place_name),
                )
                results.append(result)
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse geocoding result: {e}")
                continue

        if not results:
            return GeocodingResponse(
                success=False,
                needs_clarification=True,
                error_message=f"I couldn't find '{query}'. "
                "Please check the spelling or share your location.",
            )

        # Sort by confidence
        results.sort(key=lambda r: r.confidence, reverse=True)
        best_match = results[0]

        geocoding_response = GeocodingResponse(
            success=True,
            results=results,
            best_match=best_match,
            needs_clarification=should_ask_clarification(
                GeocodingResponse(
                    success=True,
                    results=results,
                    best_match=best_match,
                )
            ),
            clarification_options=[
                f"{r.place_name}, {r.display_name.split(', ')[1] if ', ' in r.display_name else ''}"
                for r in results[:5]
            ],
        )

        # Cache the response
        _geocoding_cache[cache_key] = geocoding_response
        logger.debug(
            f"Geocoded '{query}' -> {best_match.place_name} "
            f"({best_match.latitude}, {best_match.longitude}) "
            f"confidence={best_match.confidence:.2f}"
        )

        return geocoding_response

    except httpx.TimeoutException:
        logger.error(f"Geocoding timeout for '{query}'")
        return GeocodingResponse(
            success=False,
            error_message="The geocoding service is taking too long. "
            "Please try again or share your location.",
        )
    except httpx.RequestError as e:
        logger.error(f"Geocoding request error for '{query}': {e}")
        return GeocodingResponse(
            success=False,
            error_message="I couldn't connect to the geocoding service. "
            "Please try again or share your location.",
        )


async def reverse_geocode(
    latitude: float,
    longitude: float,
) -> str | None:
    """
    Reverse geocode coordinates to a place name.

    Args:
        latitude: GPS latitude.
        longitude: GPS longitude.

    Returns:
        Place name string or None if failed.
    """
    settings = get_settings()
    cache_key = f"reverse:{latitude:.4f},{longitude:.4f}"

    if cache_key in _geocoding_cache:
        return _geocoding_cache[cache_key]

    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "json",
        "addressdetails": 1,
    }
    headers = {"User-Agent": settings.nominatim_user_agent}

    try:
        await _rate_limit()
        client = await get_http_client()
        response = await client.get(
            f"{settings.nominatim_base_url}/reverse",
            params=params,
            headers=headers,
        )

        if response.status_code != 200:
            return None

        data = response.json()
        address = data.get("address", {})

        # Get the most specific place name
        place_name = (
            address.get("village")
            or address.get("town")
            or address.get("city")
            or address.get("suburb")
            or address.get("municipality")
            or address.get("state")
            or data.get("display_name", "").split(",")[0]
        )

        # Add region/country for context
        region = address.get("state") or address.get("region")
        country = address.get("country")

        if region and region != place_name:
            place_name = f"{place_name}, {region}"
        elif country:
            place_name = f"{place_name}, {country}"

        _geocoding_cache[cache_key] = place_name
        return place_name

    except Exception as e:
        logger.error(f"Reverse geocoding error: {e}")
        return None
