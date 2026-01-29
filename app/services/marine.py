"""Marine and inland water forecast service using Open-Meteo APIs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cachetools import TTLCache

from app.config import get_settings
from app.models.ai_schemas import (
    MarineForecastData,
    MarineForecastResponse,
    MarineHourlyData,
    MarineWindowSummary,
    QueryType,
)
from app.services.weather import get_http_client

logger = logging.getLogger(__name__)

ACCRA_FALLBACK = (5.6037, -0.187, "Accra Offshore")

MARINE_LOCATIONS: dict[str, tuple[float, float, str]] = {
    "accra": (5.6037, -0.187, "Accra Offshore"),
    "tema": (5.67, 0.0, "Tema Offshore"),
    "east coast": (5.67, 0.1, "East Coast Offshore"),
    "keta": (5.916, 0.99, "Keta Coast"),
    "cape coast": (5.1053, -1.2466, "Cape Coast"),
    "takoradi": (4.9, -1.77, "Takoradi Coast"),
    "sekondi": (4.94, -1.75, "Sekondi Coast"),
    "west coast": (4.9, -2.2, "West Coast Offshore"),
}

INLAND_WATER_LOCATIONS: dict[str, tuple[float, float, str]] = {
    "lake volta": (6.3, 0.05, "Lake Volta (Akosombo)"),
    "akosombo": (6.3, 0.05, "Akosombo (Lake Volta)"),
    "kpong": (6.1, 0.1, "Kpong (Lower Volta)"),
    "volta": (6.3, 0.05, "Lake Volta (Akosombo)"),
}

MARINE_KEYWORDS = [
    "marine", "sea", "ocean", "wave", "swell", "tide", "offshore",
    "coastal", "coast", "sea conditions", "fishing", "canoe", "boat",
]

INLAND_KEYWORDS = [
    "inland water", "lake", "lagoon", "river", "volta", "akosombo", "kpong",
]

# Cache marine data for 30 minutes
marine_cache: TTLCache = TTLCache(maxsize=100, ttl=1800)


@dataclass
class WaterLocation:
    latitude: float
    longitude: float
    name: str
    is_inland: bool
    note: str | None = None


def detect_water_query(message: str) -> QueryType | None:
    """Detect marine or inland water intent from a message."""
    message_lower = message.lower()
    if any(keyword in message_lower for keyword in INLAND_KEYWORDS):
        return QueryType.INLAND_WATER
    if any(keyword in message_lower for keyword in MARINE_KEYWORDS):
        return QueryType.MARINE
    return None


def resolve_water_location(
    message: str,
    intent_city: str | None,
    latitude: float | None,
    longitude: float | None,
    query_type: QueryType,
) -> WaterLocation:
    """Resolve water location using presets, GPS, or fallback."""
    if latitude is not None and longitude is not None:
        return WaterLocation(
            latitude=latitude,
            longitude=longitude,
            name="Shared location",
            is_inland=query_type == QueryType.INLAND_WATER,
        )

    message_lower = message.lower()
    is_inland = query_type == QueryType.INLAND_WATER
    lookup = INLAND_WATER_LOCATIONS if is_inland else MARINE_LOCATIONS

    for key, (lat, lon, name) in lookup.items():
        if key in message_lower:
            return WaterLocation(latitude=lat, longitude=lon, name=name, is_inland=is_inland)

    if intent_city:
        city_key = intent_city.lower()
        if city_key in lookup:
            lat, lon, name = lookup[city_key]
            return WaterLocation(latitude=lat, longitude=lon, name=name, is_inland=is_inland)

    # Fallback to Accra offshore (or Lake Volta for inland queries)
    if is_inland:
        lat, lon, name = INLAND_WATER_LOCATIONS["lake volta"]
        note = "Using Lake Volta (Akosombo). Reply with your lake/river area for a local update."
        return WaterLocation(latitude=lat, longitude=lon, name=name, is_inland=True, note=note)

    lat, lon, name = ACCRA_FALLBACK
    note = "Using Accra coast. Reply with your coastal area for a local update."
    return WaterLocation(latitude=lat, longitude=lon, name=name, is_inland=False, note=note)


async def get_marine_forecast(
    location: WaterLocation,
    hours: int = 48,
) -> MarineForecastResponse:
    """Fetch and summarize marine/inland water forecast."""
    cache_key = f"marine:{location.latitude:.3f},{location.longitude:.3f}:{hours}:{location.is_inland}"
    if cache_key in marine_cache:
        return marine_cache[cache_key]

    settings = get_settings()
    client = await get_http_client()
    tz = "Africa/Accra"

    marine_params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "hourly": ",".join(
            [
                "wave_height", "wave_direction", "wave_period",
                "swell_wave_height", "swell_wave_direction", "swell_wave_period",
                "wind_wave_height", "wind_wave_direction", "wind_wave_period",
                "sea_surface_temperature", "ocean_current_velocity",
                "sea_level_height_msl",
            ]
        ),
        "timezone": tz,
    }

    weather_params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "hourly": ",".join(
            [
                "wind_speed_10m", "wind_direction_10m",
                "precipitation_probability", "weathercode",
                "visibility",
            ]
        ),
        "timezone": tz,
        "forecast_days": 3,
    }

    try:
        marine_resp = await client.get(settings.open_meteo_marine_url, params=marine_params)
        weather_resp = await client.get(f"{settings.open_meteo_base_url}/forecast", params=weather_params)

        if marine_resp.status_code != 200 and weather_resp.status_code != 200:
            return MarineForecastResponse(
                success=False,
                error_message=(
                    "I'm having trouble getting marine data right now. "
                    "Please try again later or check GMet updates."
                ),
            )

        marine_json = marine_resp.json() if marine_resp.status_code == 200 else {}
        weather_json = weather_resp.json() if weather_resp.status_code == 200 else {}

        hourly = _merge_hourly_data(marine_json, weather_json)
        hourly = _filter_next_hours(hourly, hours)

        if not hourly:
            return MarineForecastResponse(
                success=False,
                error_message=(
                    "Marine data is temporarily unavailable for this location. "
                    "Please try again soon."
                ),
            )

        windows = _summarize_windows(hourly, location.is_inland)
        data = MarineForecastData(
            latitude=location.latitude,
            longitude=location.longitude,
            location_name=location.name,
            timezone=tz,
            hourly=hourly,
            windows=windows,
            source="Open-Meteo marine model (ECMWF-derived)",
            is_inland=location.is_inland,
            location_note=location.note,
        )

        result = MarineForecastResponse(success=True, data=data)
        marine_cache[cache_key] = result
        return result

    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Marine forecast error: {exc}")
        return MarineForecastResponse(
            success=False,
            error_message="Marine service error. Please try again later.",
        )


def format_marine_response(data: MarineForecastData) -> str:
    """Create a WhatsApp-friendly marine/inland water forecast response."""
    if not data.windows:
        return (
            "I couldn't summarize the marine conditions right now. "
            "Please try again later."
        )

    # Use 24h window for primary display (more representative)
    window = data.windows[1] if len(data.windows) > 1 else data.windows[0]

    # Header
    header_type = "Inland Water" if data.is_inland else "Marine Forecast"
    header = f"🌊 {header_type} - {data.location_name}\n"

    # Risk summary line
    summary = f"{window.risk_emoji} {window.risk_label}: {window.sea_state} "
    summary += "surface\n" if data.is_inland else "seas\n"

    # Location note if present
    if data.location_note:
        summary += f"{data.location_note}\n"

    # Get human-readable descriptions
    wind_name, _ = describe_wind_speed(window.wind_speed_max)
    wind_kmh = format_wind_kmh(window.wind_speed_max)

    # Conditions section with actual values
    conditions = "\n📊 Conditions:\n"

    # Waves (marine only) - show actual value with description
    if not data.is_inland:
        wave_desc, _ = describe_wave_height(window.wave_height_max)
        wave_val = f"{window.wave_height_max:.1f}m" if window.wave_height_max else "N/A"
        conditions += f"• Waves: {wave_val} ({wave_desc.lower()})\n"
    else:
        # Inland water - show surface description
        if window.wave_height_max is None:
            surface_desc, _ = describe_inland_surface(window.wind_speed_max)
        else:
            surface_desc, _ = describe_wave_height(window.wave_height_max)
        conditions += f"• Surface: {surface_desc.lower()}\n"

    # Wind
    conditions += f"• Wind: {wind_kmh} {wind_name.lower()}\n"

    # Current (if available)
    if window.current_speed_mean is not None:
        conditions += f"• Current: {format_current(window.current_speed_mean)}\n"

    # Sea temperature (if available)
    if window.ocean_temp_mean is not None:
        conditions += f"• Sea Temp: {window.ocean_temp_mean:.0f}°C\n"

    # Visibility (if available)
    if window.visibility_min is not None:
        conditions += f"• Visibility: {format_visibility(window.visibility_min)}\n"

    # Tide/sea level (marine only, if available)
    if window.sea_level_mean is not None and not data.is_inland:
        conditions += f"• Tide: {format_sea_level(window.sea_level_mean)}\n"

    # Rain only if significant (>=30%)
    if window.precip_probability_max and window.precip_probability_max >= 30:
        conditions += f"• Rain: {window.precip_probability_max:.0f}% chance\n"

    # Safety section (max 3 tips)
    advisories = generate_water_advisory(window, data.is_inland)[:3]
    safety = "\n📋 Safety:\n"
    for advice in advisories:
        safety += f"• {advice}\n"

    return f"{header}{summary}{conditions}{safety}".rstrip("\n")


def _merge_hourly_data(marine_json: dict, weather_json: dict) -> list[MarineHourlyData]:
    """Merge marine and weather hourly data by timestamp."""
    marine_hourly = marine_json.get("hourly", {})
    weather_hourly = weather_json.get("hourly", {})

    # Build weather lookup by timestamp for proper alignment
    weather_times = weather_hourly.get("time", [])
    weather_by_time: dict[str, int] = {t: i for i, t in enumerate(weather_times)}

    # Helper to get weather data by timestamp
    def _get_weather_at(key: str, time_str: str) -> float | None:
        idx = weather_by_time.get(time_str)
        if idx is None:
            return None
        return _get_at(weather_hourly, key, idx)

    times = marine_hourly.get("time") or weather_hourly.get("time") or []
    hourly: list[MarineHourlyData] = []
    for idx, time_str in enumerate(times):
        hourly.append(
            MarineHourlyData(
                time=time_str,
                wave_height=_get_at(marine_hourly, "wave_height", idx),
                wave_direction=_get_at(marine_hourly, "wave_direction", idx),
                wave_period=_get_at(marine_hourly, "wave_period", idx),
                swell_wave_height=_get_at(marine_hourly, "swell_wave_height", idx),
                swell_wave_direction=_get_at(marine_hourly, "swell_wave_direction", idx),
                swell_wave_period=_get_at(marine_hourly, "swell_wave_period", idx),
                wind_wave_height=_get_at(marine_hourly, "wind_wave_height", idx),
                wind_wave_direction=_get_at(marine_hourly, "wind_wave_direction", idx),
                wind_wave_period=_get_at(marine_hourly, "wind_wave_period", idx),
                ocean_temperature=_get_at(marine_hourly, "sea_surface_temperature", idx),
                ocean_current_velocity=_get_at(marine_hourly, "ocean_current_velocity", idx),
                wind_speed=_get_weather_at("wind_speed_10m", time_str),
                wind_direction=_get_weather_at("wind_direction_10m", time_str),
                precipitation_probability=_get_weather_at("precipitation_probability", time_str),
                weathercode=_get_weather_at("weathercode", time_str),
                visibility=_get_weather_at("visibility", time_str),
                sea_level=_get_at(marine_hourly, "sea_level_height_msl", idx),
            )
        )
    return hourly


def _filter_next_hours(hourly: list[MarineHourlyData], hours: int) -> list[MarineHourlyData]:
    """Return hourly data for the next N hours."""
    if not hourly:
        return []

    tz = ZoneInfo("Africa/Accra")
    now = datetime.now(tz)
    end = now + timedelta(hours=hours)
    filtered: list[MarineHourlyData] = []

    for item in hourly:
        dt = datetime.fromisoformat(item.time)
        dt = dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)
        if now <= dt <= end:
            filtered.append(item)

    return filtered if filtered else hourly[:hours]


def _summarize_windows(hourly: list[MarineHourlyData], is_inland: bool) -> list[MarineWindowSummary]:
    """Create 12h and 24h summaries."""
    tz = ZoneInfo("Africa/Accra")
    now = datetime.now(tz)
    windows = []
    for hours, label in [(12, "Next 12h"), (24, "Next 24h")]:
        end = now + timedelta(hours=hours)
        window_data = [
            item for item in hourly
            if now <= _parse_time(item.time, tz) <= end
        ]
        windows.append(_summarize_window(window_data, label, is_inland))
    return windows


def _summarize_window(
    hourly: list[MarineHourlyData],
    label: str,
    is_inland: bool,
) -> MarineWindowSummary:
    """Summarize a window of hourly marine data."""
    tz = ZoneInfo("Africa/Accra")
    if not hourly:
        return MarineWindowSummary(
            label=label,
            start=datetime.now(tz).isoformat(),
            end=datetime.now(tz).isoformat(),
            wave_height_max=None,
            wave_height_mean=None,
            wind_speed_max=None,
            precip_probability_max=None,
            ocean_temp_mean=None,
            current_speed_mean=None,
            thunderstorm_risk=False,
            sea_state="Unknown",
            likelihood="Low",
            impact="Low",
            risk_label="Low",
            risk_emoji="🟢",
            visibility_min=None,
            sea_level_mean=None,
        )

    wave_heights = [h.wave_height for h in hourly if h.wave_height is not None]
    wind_speeds = [h.wind_speed for h in hourly if h.wind_speed is not None]
    precip_probs = [h.precipitation_probability for h in hourly if h.precipitation_probability is not None]
    ocean_temps = [h.ocean_temperature for h in hourly if h.ocean_temperature is not None]
    currents = [h.ocean_current_velocity for h in hourly if h.ocean_current_velocity is not None]
    weathercodes = [h.weathercode for h in hourly if h.weathercode is not None]
    visibilities = [h.visibility for h in hourly if h.visibility is not None]
    sea_levels = [h.sea_level for h in hourly if h.sea_level is not None]

    wave_max = max(wave_heights) if wave_heights else None
    wave_mean = sum(wave_heights) / len(wave_heights) if wave_heights else None
    wind_max = max(wind_speeds) if wind_speeds else None
    precip_max = max(precip_probs) if precip_probs else None
    ocean_mean = sum(ocean_temps) / len(ocean_temps) if ocean_temps else None
    current_mean = sum(currents) / len(currents) if currents else None
    visibility_min = min(visibilities) if visibilities else None
    sea_level_mean = sum(sea_levels) / len(sea_levels) if sea_levels else None
    thunderstorm = any(code in (95, 96, 99) for code in weathercodes)

    sea_state = classify_sea_state(wave_max, wind_max, is_inland)
    likelihood = classify_likelihood(precip_max, wave_max, wind_max, thunderstorm)
    impact = classify_impact(wave_max, wind_max, thunderstorm, is_inland)
    risk_label, risk_emoji = map_risk(likelihood, impact)

    return MarineWindowSummary(
        label=label,
        start=_parse_time(hourly[0].time, tz).isoformat(),
        end=_parse_time(hourly[-1].time, tz).isoformat(),
        wave_height_max=wave_max,
        wave_height_mean=wave_mean,
        wind_speed_max=wind_max,
        precip_probability_max=precip_max,
        ocean_temp_mean=ocean_mean,
        current_speed_mean=current_mean,
        thunderstorm_risk=thunderstorm,
        sea_state=sea_state,
        likelihood=likelihood,
        impact=impact,
        risk_label=risk_label,
        risk_emoji=risk_emoji,
        visibility_min=visibility_min,
        sea_level_mean=sea_level_mean,
    )


def classify_sea_state(
    wave_height: float | None,
    wind_speed: float | None = None,
    is_inland: bool = False,
) -> str:
    """Classify sea state from wave height, or wind for inland water."""
    # For marine or when wave data exists, use wave height
    if wave_height is not None:
        if wave_height < 1.0:
            return "Calm"
        if wave_height < 1.5:
            return "Moderate"
        if wave_height < 2.5:
            return "Rough"
        return "Very rough"

    # For inland water without wave data, estimate from wind
    if is_inland and wind_speed is not None:
        if wind_speed < 5.5:
            return "Calm"
        if wind_speed < 10.5:
            return "Moderate"
        if wind_speed < 14.0:
            return "Rough"
        return "Very rough"

    return "Unknown"


def classify_likelihood(
    precip_max: float | None,
    wave_max: float | None,
    wind_max: float | None,
    thunderstorm: bool,
) -> str:
    """Classify likelihood based on precipitation/waves/wind."""
    if thunderstorm or (precip_max is not None and precip_max >= 60):
        return "High"
    if precip_max is not None and precip_max >= 40:
        return "Medium"
    if wave_max is not None and wave_max >= 1.5:
        return "High"
    if wind_max is not None and wind_max >= 12:
        return "High"
    if wave_max is not None and wave_max >= 1.0:
        return "Medium"
    if wind_max is not None and wind_max >= 8:
        return "Medium"
    return "Low"


def classify_impact(
    wave_max: float | None,
    wind_max: float | None,
    thunderstorm: bool,
    is_inland: bool,
) -> str:
    """Classify impact based on wave, wind, and storms."""
    if thunderstorm:
        return "High"
    if wave_max is not None and wave_max >= 1.5:
        return "High"
    if wind_max is not None and wind_max >= 12:
        return "High"
    if wave_max is not None and wave_max >= 1.0:
        return "Medium"
    if wind_max is not None and wind_max >= 8:
        return "Medium"
    if is_inland and wind_max is not None and wind_max >= 6:
        return "Medium"
    return "Low"


def map_risk(likelihood: str, impact: str) -> tuple[str, str]:
    """Map likelihood/impact to a risk label and emoji."""
    if impact == "Low" and likelihood == "Low":
        return "Low", "🟢"
    if impact == "High" and likelihood in ("Medium", "High"):
        return "Take Action", "🔴"
    if impact == "Medium" and likelihood == "High":
        return "Take Action", "🔴"
    return "Be Aware", "🟡"


# Human-readable wave height descriptions: (min_m, max_m, description, safety_note)
WAVE_HEIGHT_DESCRIPTIONS: list[tuple[float, float, str, str]] = [
    (0.0, 0.25, "Flat, glassy water", "ideal for all boats"),
    (0.25, 0.5, "Small ripples", "safe for small boats"),
    (0.5, 1.0, "Small waves (ankle to knee high)", "safe for canoes"),
    (1.0, 1.5, "Moderate waves (knee to waist high)", "caution for small boats"),
    (1.5, 2.0, "Rough waves (waist to chest high)", "small boats should avoid"),
    (2.0, 2.5, "Large waves (chest high+)", "dangerous for small craft"),
    (2.5, float("inf"), "Very large waves", "stay on shore"),
]

# Wind descriptions based on simplified Beaufort scale: (min_ms, max_ms, name, effect)
WIND_DESCRIPTIONS: list[tuple[float, float, str, str]] = [
    (0.0, 1.5, "Calm", "Smoke rises straight up"),
    (1.5, 5.5, "Light breeze", "Leaves rustle, felt on face"),
    (5.5, 8.0, "Gentle breeze", "Flags flutter, small waves"),
    (8.0, 10.5, "Moderate breeze", "Dust and paper blow"),
    (10.5, 14.0, "Fresh breeze", "Small trees sway"),
    (14.0, 17.0, "Strong breeze", "Large branches move"),
    (17.0, float("inf"), "Near gale", "Whole trees sway, dangerous"),
]

# Sea state explanations differentiated by water type
SEA_STATE_EXPLANATIONS: dict[str, dict[str, str]] = {
    "Calm": {
        "marine": "Smooth waters, safe for all vessels. Ideal fishing conditions.",
        "inland": "Lake surface like glass. Perfect for boating and fishing.",
    },
    "Moderate": {
        "marine": "Some waves present. Small boats can operate with care.",
        "inland": "Choppy surface with small waves. Stay near shore.",
    },
    "Rough": {
        "marine": "Significant waves. Only experienced fishermen in sturdy boats.",
        "inland": "Strong winds creating waves. Delay crossings if possible.",
    },
    "Very rough": {
        "marine": "Dangerous conditions. All small craft should remain on shore.",
        "inland": "Hazardous conditions. Do not go on the water.",
    },
    "Unknown": {
        "marine": "Conditions uncertain. Exercise caution.",
        "inland": "Conditions uncertain. Exercise caution.",
    },
}


def describe_wave_height(height_meters: float | None) -> tuple[str, str]:
    """Return human-readable wave description and safety note."""
    if height_meters is None:
        return "Unknown wave conditions", "check local reports"
    for min_h, max_h, description, safety in WAVE_HEIGHT_DESCRIPTIONS:
        if min_h <= height_meters < max_h:
            return description, safety
    # Fallback for very large waves
    return "Very large waves", "stay on shore"


def describe_inland_surface(wind_speed_ms: float | None) -> tuple[str, str]:
    """Estimate inland water surface conditions from wind speed."""
    if wind_speed_ms is None:
        return "Unknown surface conditions", "check local reports"
    # Estimate lake surface based on wind (simplified Beaufort for lakes)
    if wind_speed_ms < 1.5:
        return "Calm, glassy surface", "ideal for all boats"
    if wind_speed_ms < 5.5:
        return "Light ripples", "safe for small boats"
    if wind_speed_ms < 8.0:
        return "Small wavelets", "safe for canoes"
    if wind_speed_ms < 10.5:
        return "Choppy with small waves", "caution for small boats"
    if wind_speed_ms < 14.0:
        return "Moderate chop", "small boats should stay near shore"
    return "Rough surface with whitecaps", "delay crossings if possible"


def describe_wind_speed(speed_ms: float | None) -> tuple[str, str]:
    """Return wind name and effect description from m/s speed."""
    if speed_ms is None:
        return "Unknown wind", "check local conditions"
    for min_s, max_s, name, effect in WIND_DESCRIPTIONS:
        if min_s <= speed_ms < max_s:
            return name, effect
    return "Near gale", "Whole trees sway, dangerous"


def format_wind_kmh(speed_ms: float | None) -> str:
    """Convert m/s to km/h string for display."""
    if speed_ms is None:
        return "N/A"
    kmh = speed_ms * 3.6
    return f"{kmh:.0f} km/h"


def format_visibility(meters: float | None) -> str:
    """Format visibility in km with description."""
    if meters is None:
        return "N/A"
    km = meters / 1000
    if km >= 10:
        return "10+ km (clear)"
    if km >= 5:
        return f"{km:.0f} km (good)"
    if km >= 1:
        return f"{km:.1f} km (moderate)"
    return f"{meters:.0f}m (poor)"


def format_sea_level(meters: float | None) -> str:
    """Format sea level relative to normal."""
    if meters is None:
        return "N/A"
    if abs(meters) < 0.1:
        return "normal"
    sign = "+" if meters > 0 else ""
    return f"{sign}{meters:.1f}m"


def format_current(ms: float | None) -> str:
    """Format ocean current speed."""
    if ms is None:
        return "N/A"
    if ms < 0.1:
        return "calm"
    return f"{ms:.1f} m/s"


def get_sea_state_explanation(sea_state: str, is_inland: bool) -> str:
    """Return practical explanation for a sea state."""
    water_type = "inland" if is_inland else "marine"
    explanations = SEA_STATE_EXPLANATIONS.get(sea_state, SEA_STATE_EXPLANATIONS["Unknown"])
    return explanations.get(water_type, explanations["marine"])


def generate_water_advisory(window: MarineWindowSummary, is_inland: bool) -> list[str]:
    """Generate 2-4 actionable advisory bullets based on conditions."""
    advisories: list[str] = []
    risk = window.risk_label
    precip = window.precip_probability_max

    # Primary advice based on risk level
    if window.thunderstorm_risk:
        advisories.append("Avoid water entirely - thunderstorm risk")
        advisories.append("Seek shelter immediately if on water")
    elif risk == "Take Action":
        advisories.append("Stay on shore - conditions too dangerous")
        advisories.append("Do not launch boats today")
    elif risk == "Be Aware":
        if is_inland:
            advisories.append("Stay close to shore")
            advisories.append("Experienced boaters only with caution")
        else:
            advisories.append("Experienced fishermen can go out with caution")
            advisories.append("Stay within sight of shore")
            advisories.append("Expect moderate rocking - secure all gear")
    else:  # Low risk
        if is_inland:
            advisories.append("Good conditions for boating and fishing")
            advisories.append("Safe to launch canoes and small boats")
        else:
            advisories.append("Good conditions for fishing")
            advisories.append("Safe to launch canoes")

    # Weather-related advice
    if precip is not None and precip >= 50:
        advisories.append("Plan to return before afternoon rains")
    elif precip is not None and precip >= 30:
        advisories.append("Bring waterproof gear - rain possible")

    # Limit to 4 advisories max
    return advisories[:4]


def format_maybe(value: float | None, suffix: str) -> str:
    """Format numeric value with suffix."""
    if value is None:
        return "N/A"
    return f"{value:.1f}{suffix}"


def format_percent(value: float | None) -> str:
    """Format percent value."""
    if value is None:
        return "N/A"
    return f"{value:.0f}%"


def format_range(value: float | None, max_value: float | None) -> str:
    """Format range for table display."""
    if value is None and max_value is None:
        return "N/A"
    if max_value is None:
        return f"{value:.1f}" if value is not None else "N/A"
    if value is None:
        return f"{max_value:.1f}"
    return f"{value:.1f}-{max_value:.1f}"


def _parse_time(time_str: str, tz: ZoneInfo) -> datetime:
    dt = datetime.fromisoformat(time_str)
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)


def _get_at(source: dict, key: str, index: int) -> float | None:
    values = source.get(key, [])
    if index < len(values):
        return values[index]
    return None
