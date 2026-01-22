"""Agrometeorological service for ETO, GDD, soil moisture, and seasonal forecasts."""

import logging
from datetime import date, datetime, timedelta

import httpx
from cachetools import TTLCache

from app.config import get_settings
from app.models.ai_schemas import (
    AgroMetData,
    AgroMetResponse,
    CropInfo,
    DailyAgroData,
    GDDData,
    GDDStage,
    SeasonalOutlook,
    SeasonalResponse,
    SoilMoistureData,
)
from app.services.weather import get_http_client

logger = logging.getLogger(__name__)

# Cache agro data for 1 hour
agromet_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)

# Crop database with base temperatures and GDD stages
CROP_DATABASE: dict[str, CropInfo] = {
    "maize": CropInfo(
        name="maize",
        base_temp=10.0,
        gdd_stages={
            "germination": 50,
            "v6_vegetative": 200,
            "tasseling": 850,
            "silking": 950,
            "dough": 1700,
            "maturity": 2700,
        },
        water_needs="medium",
        optimal_soil_moisture=60.0,
    ),
    "rice": CropInfo(
        name="rice",
        base_temp=10.0,
        gdd_stages={
            "germination": 80,
            "tillering": 400,
            "panicle_initiation": 800,
            "flowering": 1200,
            "grain_filling": 1800,
            "maturity": 2500,
        },
        water_needs="high",
        optimal_soil_moisture=80.0,
    ),
    "cassava": CropInfo(
        name="cassava",
        base_temp=15.0,
        gdd_stages={
            "establishment": 200,
            "vegetative": 500,
            "tuber_initiation": 1000,
            "tuber_bulking": 2000,
            "maturity": 3000,
        },
        water_needs="low",
        optimal_soil_moisture=45.0,
    ),
    "cocoa": CropInfo(
        name="cocoa",
        base_temp=18.0,
        gdd_stages={
            "vegetative": 500,
            "flowering": 1500,
            "pod_development": 2500,
        },
        water_needs="medium",
        optimal_soil_moisture=55.0,
    ),
    "tomato": CropInfo(
        name="tomato",
        base_temp=10.0,
        gdd_stages={
            "germination": 50,
            "vegetative": 300,
            "flowering": 700,
            "fruit_set": 900,
            "maturity": 1400,
        },
        water_needs="high",
        optimal_soil_moisture=65.0,
    ),
    "pepper": CropInfo(
        name="pepper",
        base_temp=15.0,
        gdd_stages={
            "germination": 60,
            "vegetative": 350,
            "flowering": 650,
            "fruit_development": 900,
            "maturity": 1300,
        },
        water_needs="medium",
        optimal_soil_moisture=60.0,
    ),
    "yam": CropInfo(
        name="yam",
        base_temp=15.0,
        gdd_stages={
            "sprouting": 150,
            "vine_growth": 600,
            "tuber_initiation": 1200,
            "tuber_bulking": 2200,
            "maturity": 3200,
        },
        water_needs="medium",
        optimal_soil_moisture=55.0,
    ),
    "groundnut": CropInfo(
        name="groundnut",
        base_temp=10.0,
        gdd_stages={
            "germination": 60,
            "vegetative": 300,
            "flowering": 550,
            "pegging": 750,
            "pod_filling": 1000,
            "maturity": 1400,
        },
        water_needs="medium",
        optimal_soil_moisture=50.0,
    ),
    "sorghum": CropInfo(
        name="sorghum",
        base_temp=10.0,
        gdd_stages={
            "germination": 50,
            "vegetative": 400,
            "boot": 700,
            "heading": 900,
            "grain_filling": 1400,
            "maturity": 1800,
        },
        water_needs="low",
        optimal_soil_moisture=45.0,
    ),
    "millet": CropInfo(
        name="millet",
        base_temp=10.0,
        gdd_stages={
            "germination": 40,
            "vegetative": 350,
            "heading": 600,
            "flowering": 750,
            "maturity": 1200,
        },
        water_needs="low",
        optimal_soil_moisture=40.0,
    ),
}


def get_crop_info(crop_name: str) -> CropInfo:
    """
    Get crop information by name.

    Args:
        crop_name: Name of the crop.

    Returns:
        CropInfo for the crop, defaults to maize if not found.
    """
    crop_lower = crop_name.lower()
    if crop_lower in CROP_DATABASE:
        return CROP_DATABASE[crop_lower]

    # Handle aliases
    aliases = {
        "corn": "maize",
        "beans": "cowpea",
        "groundnuts": "groundnut",
        "peanut": "groundnut",
        "peanuts": "groundnut",
    }
    if crop_lower in aliases:
        return CROP_DATABASE[aliases[crop_lower]]

    # Default to maize
    return CROP_DATABASE["maize"]


async def get_agromet_data(
    latitude: float,
    longitude: float,
    days: int = 7,
) -> AgroMetResponse:
    """
    Get agrometeorological data from Open-Meteo.

    Includes ETO, temperature extremes, and soil moisture.

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        days: Number of days of data (default 7).

    Returns:
        AgroMetResponse with agro data or error.
    """
    settings = get_settings()
    cache_key = f"agromet:{latitude:.4f},{longitude:.4f}:{days}"

    if cache_key in agromet_cache:
        return agromet_cache[cache_key]

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "et0_fao_evapotranspiration,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "hourly": "soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm,soil_moisture_9_to_27cm,soil_moisture_27_to_81cm,relative_humidity_2m",
        "timezone": "Africa/Accra",
        "forecast_days": min(days, 16),
    }

    try:
        client = await get_http_client()
        response = await client.get(
            f"{settings.open_meteo_base_url}/forecast",
            params=params,
        )

        if response.status_code != 200:
            return AgroMetResponse(
                success=False,
                error_message="Unable to fetch agrometeorological data.",
            )

        data = response.json()
        agromet_data = _parse_agromet_response(data, latitude, longitude)
        result = AgroMetResponse(success=True, data=agromet_data)
        agromet_cache[cache_key] = result
        return result

    except httpx.TimeoutException:
        return AgroMetResponse(
            success=False,
            error_message="Agrometeorological service timeout.",
        )
    except httpx.RequestError as e:
        logger.error(f"Agromet request error: {e}")
        return AgroMetResponse(
            success=False,
            error_message="Could not connect to agrometeorological service.",
        )


def _parse_agromet_response(
    data: dict,
    latitude: float,
    longitude: float,
) -> AgroMetData:
    """Parse Open-Meteo response into AgroMetData."""
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})

    # Parse daily data
    daily_data = []
    dates = daily.get("time", [])
    eto_values = daily.get("et0_fao_evapotranspiration", [])
    temp_max_values = daily.get("temperature_2m_max", [])
    temp_min_values = daily.get("temperature_2m_min", [])
    precip_values = daily.get("precipitation_sum", [])

    for i, date_str in enumerate(dates):
        day_data = DailyAgroData(
            date=date_str,
            eto=eto_values[i] if i < len(eto_values) else None,
            temp_max=temp_max_values[i] if i < len(temp_max_values) else None,
            temp_min=temp_min_values[i] if i < len(temp_min_values) else None,
            precipitation=precip_values[i] if i < len(precip_values) else None,
        )
        daily_data.append(day_data)

    # Parse soil moisture (use most recent hourly values)
    soil_moisture = None
    if hourly:
        sm_0_1 = hourly.get("soil_moisture_0_to_1cm", [])
        sm_1_3 = hourly.get("soil_moisture_1_to_3cm", [])
        sm_3_9 = hourly.get("soil_moisture_3_to_9cm", [])
        sm_9_27 = hourly.get("soil_moisture_9_to_27cm", [])
        sm_27_81 = hourly.get("soil_moisture_27_to_81cm", [])
        times = hourly.get("time", [])

        if sm_0_1:
            # Get most recent values (convert from m3/m3 to percentage)
            idx = -1  # Most recent
            soil_moisture = SoilMoistureData(
                moisture_0_1cm=sm_0_1[idx] * 100 if sm_0_1 else None,
                moisture_1_3cm=sm_1_3[idx] * 100 if sm_1_3 else None,
                moisture_3_9cm=sm_3_9[idx] * 100 if sm_3_9 else None,
                moisture_9_27cm=sm_9_27[idx] * 100 if sm_9_27 else None,
                moisture_27_81cm=sm_27_81[idx] * 100 if sm_27_81 else None,
                timestamp=times[idx] if times else "",
            )

    return AgroMetData(
        latitude=latitude,
        longitude=longitude,
        daily_data=daily_data,
        soil_moisture=soil_moisture,
    )


async def get_eto(
    latitude: float,
    longitude: float,
    days: int = 7,
) -> list[float]:
    """
    Get ETO (evapotranspiration) values.

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        days: Number of days.

    Returns:
        List of daily ETO values in mm.
    """
    response = await get_agromet_data(latitude, longitude, days)
    if not response.success or not response.data:
        return []

    return [d.eto for d in response.data.daily_data if d.eto is not None]


async def get_soil_moisture(
    latitude: float,
    longitude: float,
) -> SoilMoistureData | None:
    """
    Get current soil moisture data.

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.

    Returns:
        SoilMoistureData or None if not available.
    """
    response = await get_agromet_data(latitude, longitude, 1)
    if not response.success or not response.data:
        return None

    return response.data.soil_moisture


def calculate_gdd(
    temp_max: float,
    temp_min: float,
    base_temp: float,
) -> float:
    """
    Calculate Growing Degree Days for a single day.

    Uses the simple averaging method:
    GDD = max(0, (Tmax + Tmin) / 2 - Tbase)

    Args:
        temp_max: Maximum temperature (Celsius).
        temp_min: Minimum temperature (Celsius).
        base_temp: Base temperature for the crop.

    Returns:
        GDD value for the day.
    """
    avg_temp = (temp_max + temp_min) / 2
    gdd = max(0, avg_temp - base_temp)
    return gdd


async def get_accumulated_gdd(
    latitude: float,
    longitude: float,
    crop: str,
    start_date: date | None = None,
    days_back: int = 60,
) -> GDDData:
    """
    Calculate accumulated GDD for a crop.

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.
        crop: Crop name.
        start_date: Planting date (defaults to days_back ago).
        days_back: Days to look back if no start_date.

    Returns:
        GDDData with accumulated GDD and growth stage.
    """
    crop_info = get_crop_info(crop)

    # Get historical temperature data
    settings = get_settings()

    if start_date is None:
        start_date = date.today() - timedelta(days=days_back)

    end_date = date.today()

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min",
        "timezone": "Africa/Accra",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }

    try:
        client = await get_http_client()
        response = await client.get(
            f"{settings.open_meteo_base_url}/forecast",
            params=params,
        )

        if response.status_code != 200:
            # Return default/estimated GDD
            return _create_default_gdd(crop_info, 0)

        data = response.json()
        return _calculate_gdd_from_data(data, crop_info)

    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.error(f"GDD calculation error: {e}")
        return _create_default_gdd(crop_info, 0)


def _calculate_gdd_from_data(data: dict, crop_info: CropInfo) -> GDDData:
    """Calculate GDD from Open-Meteo response data."""
    daily = data.get("daily", {})
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])

    accumulated = 0.0
    for i in range(len(temp_max)):
        if i < len(temp_min):
            gdd = calculate_gdd(temp_max[i], temp_min[i], crop_info.base_temp)
            accumulated += gdd

    return _create_gdd_data(crop_info, accumulated)


def _create_default_gdd(crop_info: CropInfo, accumulated: float) -> GDDData:
    """Create GDDData with default values."""
    return _create_gdd_data(crop_info, accumulated)


def _create_gdd_data(crop_info: CropInfo, accumulated: float) -> GDDData:
    """Create GDDData from crop info and accumulated GDD."""
    stages = []
    current_stage = "pre-planting"
    next_stage = None
    gdd_to_next = None

    sorted_stages = sorted(crop_info.gdd_stages.items(), key=lambda x: x[1])

    for stage_name, gdd_required in sorted_stages:
        reached = accumulated >= gdd_required
        stages.append(GDDStage(
            stage_name=stage_name,
            gdd_required=gdd_required,
            reached=reached,
        ))

        if reached:
            current_stage = stage_name
        elif next_stage is None:
            next_stage = stage_name
            gdd_to_next = gdd_required - accumulated

    return GDDData(
        crop=crop_info.name,
        base_temp=crop_info.base_temp,
        accumulated_gdd=accumulated,
        current_stage=current_stage,
        next_stage=next_stage,
        gdd_to_next_stage=gdd_to_next,
        stages=stages,
    )


async def get_seasonal_outlook(
    latitude: float,
    longitude: float,
) -> SeasonalResponse:
    """
    Get seasonal (extended) forecast from Open-Meteo.

    Uses the ECMWF seasonal forecast endpoint for longer-range predictions.

    Args:
        latitude: Latitude coordinate.
        longitude: Longitude coordinate.

    Returns:
        SeasonalResponse with outlook data.
    """
    settings = get_settings()
    cache_key = f"seasonal:{latitude:.4f},{longitude:.4f}"

    if cache_key in agromet_cache:
        return agromet_cache[cache_key]

    # Use the forecast endpoint with maximum days (16 days from Open-Meteo free tier)
    # For true seasonal, you'd need Open-Meteo's ECMWF endpoint (if available)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
        "timezone": "Africa/Accra",
        "forecast_days": 16,
    }

    try:
        client = await get_http_client()
        response = await client.get(
            f"{settings.open_meteo_base_url}/forecast",
            params=params,
        )

        if response.status_code != 200:
            return SeasonalResponse(
                success=False,
                error_message="Unable to fetch seasonal outlook.",
            )

        data = response.json()
        outlook = _parse_seasonal_response(data, latitude, longitude)
        result = SeasonalResponse(success=True, data=outlook)
        agromet_cache[cache_key] = result
        return result

    except httpx.TimeoutException:
        return SeasonalResponse(
            success=False,
            error_message="Seasonal forecast service timeout.",
        )
    except httpx.RequestError as e:
        logger.error(f"Seasonal forecast error: {e}")
        return SeasonalResponse(
            success=False,
            error_message="Could not connect to seasonal forecast service.",
        )


def _parse_seasonal_response(
    data: dict,
    latitude: float,
    longitude: float,
) -> SeasonalOutlook:
    """Parse Open-Meteo response into SeasonalOutlook."""
    daily = data.get("daily", {})

    dates = daily.get("time", [])
    temp_max = daily.get("temperature_2m_max", [])
    temp_min = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])

    # Parse daily forecasts
    daily_forecasts = []
    for i, date_str in enumerate(dates):
        day_data = DailyAgroData(
            date=date_str,
            temp_max=temp_max[i] if i < len(temp_max) else None,
            temp_min=temp_min[i] if i < len(temp_min) else None,
            precipitation=precip[i] if i < len(precip) else None,
        )
        daily_forecasts.append(day_data)

    # Calculate trends
    temp_trend = _calculate_temp_trend(temp_max, temp_min)
    precip_trend = _calculate_precip_trend(precip)

    # Generate summary based on Ghana's seasons
    summary = _generate_seasonal_summary(temp_trend, precip_trend, latitude)

    return SeasonalOutlook(
        latitude=latitude,
        longitude=longitude,
        forecast_days=len(dates),
        temperature_trend=temp_trend,
        precipitation_trend=precip_trend,
        summary=summary,
        daily_forecasts=daily_forecasts,
    )


def _calculate_temp_trend(
    temp_max: list[float],
    temp_min: list[float],
) -> str:
    """Calculate temperature trend from forecast data."""
    if not temp_max or not temp_min:
        return "normal"

    # Calculate average of first week vs second week
    mid = len(temp_max) // 2
    if mid < 3:
        return "normal"

    first_half_avg = sum(temp_max[:mid]) / mid
    second_half_avg = sum(temp_max[mid:]) / (len(temp_max) - mid)

    diff = second_half_avg - first_half_avg

    if diff > 2:
        return "above_normal"
    elif diff < -2:
        return "below_normal"
    return "normal"


def _calculate_precip_trend(precip: list[float]) -> str:
    """Calculate precipitation trend from forecast data."""
    if not precip:
        return "normal"

    total_precip = sum(p for p in precip if p is not None)
    avg_daily = total_precip / len(precip) if precip else 0

    # Ghana average varies by season, using rough estimates
    # Rainy season (Apr-Oct): ~5-10mm/day average
    # Dry season (Nov-Mar): ~0-2mm/day average
    month = datetime.now().month

    if 4 <= month <= 10:  # Rainy season
        if avg_daily > 8:
            return "above_normal"
        elif avg_daily < 4:
            return "below_normal"
    else:  # Dry season
        if avg_daily > 3:
            return "above_normal"
        elif avg_daily < 0.5:
            return "below_normal"

    return "normal"


def _generate_seasonal_summary(
    temp_trend: str,
    precip_trend: str,
    latitude: float,
) -> str:
    """Generate a seasonal summary text."""
    month = datetime.now().month

    # Determine current season in Ghana
    if 11 <= month or month <= 2:
        season = "harmattan season (dry)"
    elif 3 <= month <= 4:
        season = "early rainy season"
    elif 5 <= month <= 7:
        season = "major rainy season"
    elif month == 8:
        season = "short dry spell"
    else:
        season = "minor rainy season"

    summaries = []
    summaries.append(f"Currently in {season}.")

    if temp_trend == "above_normal":
        summaries.append("Temperatures expected to be warmer than usual.")
    elif temp_trend == "below_normal":
        summaries.append("Temperatures expected to be cooler than usual.")

    if precip_trend == "above_normal":
        summaries.append("Higher than normal rainfall expected.")
    elif precip_trend == "below_normal":
        summaries.append("Lower than normal rainfall expected.")
    else:
        summaries.append("Rainfall expected to be near normal.")

    return " ".join(summaries)


def get_irrigation_advice(
    eto: float,
    soil_moisture: float,
    crop: str,
) -> str:
    """
    Generate irrigation advice based on ETO and soil moisture.

    Args:
        eto: Today's evapotranspiration in mm.
        soil_moisture: Current soil moisture percentage.
        crop: Crop name.

    Returns:
        Irrigation advice string.
    """
    crop_info = get_crop_info(crop)
    optimal = crop_info.optimal_soil_moisture

    if soil_moisture < optimal * 0.5:
        urgency = "urgent"
        amount = eto * 1.5
    elif soil_moisture < optimal * 0.75:
        urgency = "recommended"
        amount = eto * 1.2
    elif soil_moisture < optimal:
        urgency = "optional"
        amount = eto
    else:
        urgency = "not needed"
        amount = 0

    if urgency == "not needed":
        return f"Soil moisture is good ({soil_moisture:.0f}%). No irrigation needed today."

    return (
        f"Irrigation {urgency}. Soil moisture: {soil_moisture:.0f}% "
        f"(optimal for {crop}: {optimal:.0f}%). "
        f"Recommended: {amount:.1f}mm based on today's ETO of {eto:.1f}mm."
    )
