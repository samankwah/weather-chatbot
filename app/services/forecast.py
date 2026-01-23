"""Extended forecast service using OpenWeatherMap and Open-Meteo."""

import logging
from datetime import datetime

import httpx
from cachetools import TTLCache

from app.config import get_settings
from app.models.ai_schemas import (
    ForecastData,
    ForecastPeriod,
    ForecastResponse,
    TimeReference,
)
from app.services.weather import get_http_client

logger = logging.getLogger(__name__)

# Cache forecast data for 30 minutes
forecast_cache: TTLCache = TTLCache(maxsize=100, ttl=1800)


async def get_forecast(
    city: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> ForecastResponse:
    """
    Get 5-day forecast from OpenWeatherMap.

    Prefers coordinates for accurate location-specific forecasts.
    Falls back to city name if coordinates not available.

    Args:
        city: City name (fallback if coordinates not provided).
        latitude: Latitude coordinate (preferred).
        longitude: Longitude coordinate (preferred).

    Returns:
        ForecastResponse with forecast data or error.
    """
    settings = get_settings()

    # Require either coordinates or city name
    if latitude is None or longitude is None:
        if not city:
            return ForecastResponse(
                success=False,
                error_message=(
                    "I need your location to provide a forecast. "
                    "Please share your location or specify a place name."
                ),
            )

    # Build cache key
    if latitude is not None and longitude is not None:
        cache_key = f"forecast:coords:{latitude:.4f},{longitude:.4f}"
    else:
        cache_key = f"forecast:city:{city.lower()}"

    if cache_key in forecast_cache:
        return forecast_cache[cache_key]

    # Build request params - prefer coordinates
    params = {
        "appid": settings.weather_api_key,
        "units": "metric",
    }

    if latitude is not None and longitude is not None:
        params["lat"] = latitude
        params["lon"] = longitude
    else:
        params["q"] = city

    try:
        client = await get_http_client()
        response = await client.get(
            settings.weather_forecast_url,
            params=params,
        )

        if response.status_code == 404:
            return ForecastResponse(
                success=False,
                error_message=f"Could not find forecast for the specified location.",
            )

        if response.status_code != 200:
            return ForecastResponse(
                success=False,
                error_message="Unable to fetch forecast data. Please try again.",
            )

        data = response.json()
        forecast_data = _parse_owm_forecast(data)
        result = ForecastResponse(success=True, data=forecast_data)
        forecast_cache[cache_key] = result
        return result

    except httpx.TimeoutException:
        return ForecastResponse(
            success=False,
            error_message="Forecast service timeout. Please try again.",
        )
    except httpx.RequestError as e:
        logger.error(f"Forecast request error: {e}")
        return ForecastResponse(
            success=False,
            error_message="Could not connect to forecast service.",
        )


async def get_extended_forecast(
    latitude: float,
    longitude: float,
    days: int = 16,
) -> ForecastResponse:
    """
    Get extended forecast (up to 16 days) from Open-Meteo.

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        days: Number of days to forecast (max 16).

    Returns:
        ForecastResponse with extended forecast data.
    """
    settings = get_settings()
    cache_key = f"extended:{latitude:.4f},{longitude:.4f}:{days}"

    if cache_key in forecast_cache:
        return forecast_cache[cache_key]

    forecast_days = min(days, settings.open_meteo_forecast_days)

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,weathercode",
        "timezone": "Africa/Accra",
        "forecast_days": forecast_days,
    }

    try:
        client = await get_http_client()
        response = await client.get(
            f"{settings.open_meteo_base_url}/forecast",
            params=params,
        )

        if response.status_code != 200:
            return ForecastResponse(
                success=False,
                error_message="Unable to fetch extended forecast.",
            )

        data = response.json()
        forecast_data = _parse_open_meteo_forecast(data, latitude, longitude)
        result = ForecastResponse(success=True, data=forecast_data)
        forecast_cache[cache_key] = result
        return result

    except httpx.TimeoutException:
        return ForecastResponse(
            success=False,
            error_message="Extended forecast service timeout.",
        )
    except httpx.RequestError as e:
        logger.error(f"Extended forecast request error: {e}")
        return ForecastResponse(
            success=False,
            error_message="Could not connect to extended forecast service.",
        )


def _parse_owm_forecast(data: dict) -> ForecastData:
    """Parse OpenWeatherMap 5-day forecast response."""
    periods = []

    for item in data.get("list", []):
        period = ForecastPeriod(
            datetime_str=item["dt_txt"],
            timestamp=item["dt"],
            temperature=item["main"]["temp"],
            feels_like=item["main"]["feels_like"],
            temp_min=item["main"]["temp_min"],
            temp_max=item["main"]["temp_max"],
            humidity=item["main"]["humidity"],
            description=item["weather"][0]["description"],
            icon=item["weather"][0]["icon"],
            wind_speed=item["wind"]["speed"],
            precipitation_probability=item.get("pop", 0) * 100,
            rain_volume=item.get("rain", {}).get("3h", 0),
        )
        periods.append(period)

    city_data = data.get("city", {})
    return ForecastData(
        city=city_data.get("name", "Unknown"),
        country=city_data.get("country", ""),
        latitude=city_data.get("coord", {}).get("lat", 0),
        longitude=city_data.get("coord", {}).get("lon", 0),
        periods=periods,
    )


def _parse_open_meteo_forecast(
    data: dict,
    latitude: float,
    longitude: float,
) -> ForecastData:
    """Parse Open-Meteo forecast response."""
    periods = []
    daily = data.get("daily", {})

    dates = daily.get("time", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    precip_prob = daily.get("precipitation_probability_max", [])
    precip_sum = daily.get("precipitation_sum", [])
    weather_codes = daily.get("weathercode", [])

    for i, date in enumerate(dates):
        avg_temp = (temp_max[i] + temp_min[i]) / 2 if i < len(temp_max) and i < len(temp_min) else 0
        description = _weather_code_to_description(weather_codes[i] if i < len(weather_codes) else 0)
        icon = _weather_code_to_icon(weather_codes[i] if i < len(weather_codes) else 0)

        period = ForecastPeriod(
            datetime_str=date,
            timestamp=int(datetime.fromisoformat(date).timestamp()),
            temperature=avg_temp,
            feels_like=avg_temp,
            temp_min=temp_min[i] if i < len(temp_min) else 0,
            temp_max=temp_max[i] if i < len(temp_max) else 0,
            humidity=0,  # Not available in daily Open-Meteo
            description=description,
            icon=icon,
            wind_speed=0,  # Not requested
            precipitation_probability=precip_prob[i] if i < len(precip_prob) else None,
            rain_volume=precip_sum[i] if i < len(precip_sum) else None,
        )
        periods.append(period)

    return ForecastData(
        city="Location",  # Open-Meteo doesn't return city name
        country="",
        latitude=latitude,
        longitude=longitude,
        periods=periods,
    )


def _weather_code_to_description(code: int) -> str:
    """Convert WMO weather code to description."""
    descriptions = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Foggy",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Slight rain showers",
        81: "Moderate rain showers",
        82: "Violent rain showers",
        95: "Thunderstorm",
        96: "Thunderstorm with slight hail",
        99: "Thunderstorm with heavy hail",
    }
    return descriptions.get(code, "Unknown")


def _weather_code_to_icon(code: int) -> str:
    """Convert WMO weather code to OpenWeatherMap-style icon code."""
    icon_map = {
        0: "01d",  # Clear
        1: "01d",  # Mainly clear
        2: "02d",  # Partly cloudy
        3: "04d",  # Overcast
        45: "50d",  # Fog
        48: "50d",  # Fog
        51: "09d",  # Drizzle
        53: "09d",
        55: "09d",
        61: "10d",  # Rain
        63: "10d",
        65: "10d",
        71: "13d",  # Snow
        73: "13d",
        75: "13d",
        80: "09d",  # Rain showers
        81: "09d",
        82: "09d",
        95: "11d",  # Thunderstorm
        96: "11d",
        99: "11d",
    }
    return icon_map.get(code, "01d")


def extract_forecast_for_time(
    forecast_data: ForecastData,
    time_ref: TimeReference,
) -> list[ForecastPeriod]:
    """
    Extract forecast periods matching a time reference.

    Args:
        forecast_data: Full forecast data.
        time_ref: Time reference to filter by.

    Returns:
        List of matching forecast periods.
    """
    if not forecast_data.periods:
        return []

    now = datetime.now()
    target_date = now.date()

    if time_ref.days_ahead > 0:
        from datetime import timedelta
        target_date = (now + timedelta(days=time_ref.days_ahead)).date()

    matching = []
    for period in forecast_data.periods:
        try:
            # Handle both timestamp and datetime string
            if "-" in period.datetime_str:
                period_date = datetime.fromisoformat(period.datetime_str).date()
            else:
                period_date = datetime.fromtimestamp(period.timestamp).date()

            if period_date == target_date:
                matching.append(period)
        except (ValueError, TypeError):
            continue

    # If looking for "this week" or "next week", return more periods
    if time_ref.reference in ["this_week", "next_week"]:
        from datetime import timedelta
        start_date = target_date
        end_date = start_date + timedelta(days=7)

        matching = []
        for period in forecast_data.periods:
            try:
                if "-" in period.datetime_str:
                    period_date = datetime.fromisoformat(period.datetime_str).date()
                else:
                    period_date = datetime.fromtimestamp(period.timestamp).date()

                if start_date <= period_date <= end_date:
                    matching.append(period)
            except (ValueError, TypeError):
                continue

    return matching


def summarize_daily_forecast(periods: list[ForecastPeriod]) -> dict:
    """
    Summarize multiple forecast periods into a daily summary.

    Args:
        periods: List of forecast periods for a day.

    Returns:
        Dictionary with daily summary.
    """
    if not periods:
        return {}

    temps = [p.temperature for p in periods]
    temp_maxs = [p.temp_max for p in periods]
    temp_mins = [p.temp_min for p in periods]

    # Most common description
    descriptions = [p.description for p in periods]
    most_common_desc = max(set(descriptions), key=descriptions.count)

    # Max precipitation probability
    precip_probs = [p.precipitation_probability for p in periods if p.precipitation_probability]
    max_precip_prob = max(precip_probs) if precip_probs else 0

    return {
        "date": periods[0].datetime_str.split()[0] if " " in periods[0].datetime_str else periods[0].datetime_str,
        "temp_avg": sum(temps) / len(temps),
        "temp_max": max(temp_maxs),
        "temp_min": min(temp_mins),
        "description": most_common_desc,
        "precipitation_probability": max_precip_prob,
    }
