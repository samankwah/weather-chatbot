"""Ghana-specific seasonal forecast service with onset, cessation, and dry spell calculations."""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import httpx

from app.models.ai_schemas import (
    DrySpellInfo,
    GhanaRegion,
    SeasonalForecast,
    SeasonalForecastResponse,
    SeasonType,
)

logger = logging.getLogger(__name__)

# Open-Meteo API endpoints
HISTORICAL_API_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"

# Ghana region latitude threshold
LATITUDE_THRESHOLD = 8.0

# Season start dates (month, day)
SEASON_START_DATES = {
    (GhanaRegion.SOUTHERN, SeasonType.MAJOR): (2, 1),    # Feb 1
    (GhanaRegion.SOUTHERN, SeasonType.MINOR): (8, 15),   # Aug 15
    (GhanaRegion.NORTHERN, SeasonType.SINGLE): (3, 15),  # Mar 15
}

# Cessation start dates (month, day)
CESSATION_START_DATES = {
    (GhanaRegion.SOUTHERN, SeasonType.MAJOR): (7, 1),    # Jul 1
    (GhanaRegion.SOUTHERN, SeasonType.MINOR): (10, 1),   # Oct 1
    (GhanaRegion.NORTHERN, SeasonType.SINGLE): (10, 1),  # Oct 1
}

# Onset criteria
ONSET_CRITERIA = {
    (GhanaRegion.SOUTHERN, SeasonType.MAJOR): {
        "min_rainfall_mm": 20,
        "max_days_for_rainfall": 3,
        "max_dry_spell_days": 10,
        "validation_period_days": 30,
    },
    (GhanaRegion.SOUTHERN, SeasonType.MINOR): {
        "min_rainfall_mm": 20,
        "max_days_for_rainfall": 3,
        "max_dry_spell_days": 15,
        "validation_period_days": 30,
    },
    (GhanaRegion.NORTHERN, SeasonType.SINGLE): {
        "min_rainfall_mm": 20,
        "max_days_for_rainfall": 3,
        "max_dry_spell_days": 10,
        "validation_period_days": 30,
    },
}

# Soil water balance constants
SOIL_WATER_CAPACITY_MM = 70  # Initial soil water capacity
DEFAULT_ETO_MM_PER_DAY = 4   # Default evapotranspiration rate

# Expected onset date ranges by region and season type
EXPECTED_ONSET_RANGES = {
    (GhanaRegion.SOUTHERN, SeasonType.MAJOR): "Mar 1 - Apr 15",
    (GhanaRegion.SOUTHERN, SeasonType.MINOR): "Sep 1 - Sep 30",
    (GhanaRegion.NORTHERN, SeasonType.SINGLE): "Apr 15 - May 15",
}

# Expected cessation date ranges by region and season type
EXPECTED_CESSATION_RANGES = {
    (GhanaRegion.SOUTHERN, SeasonType.MAJOR): "Jul 15 - Aug 15",
    (GhanaRegion.SOUTHERN, SeasonType.MINOR): "Nov 15 - Dec 15",
    (GhanaRegion.NORTHERN, SeasonType.SINGLE): "Oct 15 - Nov 15",
}


def get_expected_onset_info(region: GhanaRegion, season_type: SeasonType) -> str:
    """
    Return typical onset date range when onset hasn't been detected yet.

    Args:
        region: Ghana region (SOUTHERN or NORTHERN).
        season_type: Type of season.

    Returns:
        String with expected onset date range.
    """
    return EXPECTED_ONSET_RANGES.get(
        (region, season_type),
        "Mar 1 - Apr 30",  # Default fallback
    )


def get_expected_cessation_info(region: GhanaRegion, season_type: SeasonType) -> str:
    """
    Return typical cessation date range when cessation hasn't been detected yet.

    Args:
        region: Ghana region (SOUTHERN or NORTHERN).
        season_type: Type of season.

    Returns:
        String with expected cessation date range.
    """
    return EXPECTED_CESSATION_RANGES.get(
        (region, season_type),
        "Oct 15 - Nov 15",  # Default fallback
    )


def get_cessation_start_date(region: GhanaRegion, season_type: SeasonType, year: int) -> str:
    """
    Get the date when cessation monitoring begins for a region/season.

    Args:
        region: Ghana region.
        season_type: Season type.
        year: Year for the date.

    Returns:
        Formatted date string (e.g., "Jul 1").
    """
    cess_month, cess_day = CESSATION_START_DATES.get(
        (region, season_type),
        (10, 1),
    )
    return date(year, cess_month, cess_day).strftime("%b %d")


def get_region(latitude: float) -> GhanaRegion:
    """
    Determine Ghana region based on latitude.

    Args:
        latitude: Location latitude.

    Returns:
        GhanaRegion.SOUTHERN if lat < 8.0, else NORTHERN.
    """
    if latitude < LATITUDE_THRESHOLD:
        return GhanaRegion.SOUTHERN
    return GhanaRegion.NORTHERN


def get_current_season_type(region: GhanaRegion, current_date: date) -> SeasonType:
    """
    Determine which season type applies based on region and date.

    Args:
        region: Ghana region (SOUTHERN or NORTHERN).
        current_date: Current date to check.

    Returns:
        SeasonType for the current period.
    """
    if region == GhanaRegion.NORTHERN:
        return SeasonType.SINGLE

    # Southern Ghana has two seasons
    month = current_date.month

    # Minor season: Aug 15 to Nov 30 (roughly)
    if month >= 8 and month <= 11:
        return SeasonType.MINOR

    # Major season: Feb 1 to Jul 31
    return SeasonType.MAJOR


async def get_historical_rainfall(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """
    Fetch daily rainfall data from Open-Meteo historical API.

    Args:
        latitude: Location latitude.
        longitude: Location longitude.
        start_date: Start date for data.
        end_date: End date for data.

    Returns:
        List of dicts with 'date', 'precipitation', and 'eto' keys.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": "precipitation_sum,et0_fao_evapotranspiration",
        "timezone": "Africa/Accra",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(HISTORICAL_API_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        precipitation = daily.get("precipitation_sum", [])
        eto = daily.get("et0_fao_evapotranspiration", [])

        result = []
        for i, date_str in enumerate(dates):
            result.append({
                "date": date_str,
                "precipitation": precipitation[i] if i < len(precipitation) else 0,
                "eto": eto[i] if i < len(eto) else DEFAULT_ETO_MM_PER_DAY,
            })
        return result

    except Exception as e:
        logger.error(f"Failed to fetch historical rainfall: {e}")
        return []


async def get_forecast_rainfall(
    latitude: float,
    longitude: float,
    days: int = 16,
) -> list[dict]:
    """
    Fetch forecast rainfall data from Open-Meteo forecast API.

    Args:
        latitude: Location latitude.
        longitude: Location longitude.
        days: Number of forecast days.

    Returns:
        List of dicts with 'date', 'precipitation', and 'eto' keys.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "precipitation_sum,et0_fao_evapotranspiration",
        "forecast_days": days,
        "timezone": "Africa/Accra",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(FORECAST_API_URL, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        precipitation = daily.get("precipitation_sum", [])
        eto = daily.get("et0_fao_evapotranspiration", [])

        result = []
        for i, date_str in enumerate(dates):
            result.append({
                "date": date_str,
                "precipitation": precipitation[i] if i < len(precipitation) else 0,
                "eto": eto[i] if i < len(eto) else DEFAULT_ETO_MM_PER_DAY,
            })
        return result

    except Exception as e:
        logger.error(f"Failed to fetch forecast rainfall: {e}")
        return []


def check_onset_criteria(
    rainfall_data: list[dict],
    start_index: int,
    region: GhanaRegion,
    season_type: SeasonType,
) -> bool:
    """
    Check if onset criteria are met at a given starting index.

    Args:
        rainfall_data: List of daily rainfall data.
        start_index: Index to check for onset.
        region: Ghana region.
        season_type: Type of season.

    Returns:
        True if onset criteria are met.
    """
    criteria = ONSET_CRITERIA.get((region, season_type), ONSET_CRITERIA[(GhanaRegion.SOUTHERN, SeasonType.MAJOR)])

    min_rainfall = criteria["min_rainfall_mm"]
    max_days = criteria["max_days_for_rainfall"]
    max_dry_spell = criteria["max_dry_spell_days"]
    validation_period = criteria["validation_period_days"]

    # Check if we have enough data
    if start_index + validation_period > len(rainfall_data):
        return False

    # Check if >= min_rainfall in <= max_days
    cumulative_rain = 0
    for i in range(max_days):
        if start_index + i < len(rainfall_data):
            precip = rainfall_data[start_index + i].get("precipitation") or 0
            cumulative_rain += precip

    if cumulative_rain < min_rainfall:
        return False

    # Check for dry spells in the validation period
    current_dry_spell = 0
    max_observed_dry_spell = 0

    for i in range(validation_period):
        if start_index + i >= len(rainfall_data):
            break
        precip = rainfall_data[start_index + i].get("precipitation") or 0
        if precip < 1:  # Consider < 1mm as dry day
            current_dry_spell += 1
            max_observed_dry_spell = max(max_observed_dry_spell, current_dry_spell)
        else:
            current_dry_spell = 0

    if max_observed_dry_spell > max_dry_spell:
        return False

    return True


def calculate_onset_date(
    rainfall_data: list[dict],
    region: GhanaRegion,
    season_type: SeasonType,
    season_start_date: date,
) -> tuple[Optional[str], str]:
    """
    Calculate onset date based on Ghana criteria.

    Args:
        rainfall_data: List of daily rainfall data.
        region: Ghana region.
        season_type: Type of season.
        season_start_date: Date when season can potentially start.

    Returns:
        Tuple of (onset_date or None, status).
    """
    if not rainfall_data:
        return None, "not_yet"

    # Find the index corresponding to season start date
    start_index = 0
    for i, day_data in enumerate(rainfall_data):
        day_date = date.fromisoformat(day_data["date"])
        if day_date >= season_start_date:
            start_index = i
            break

    # Search for onset from start date onwards
    for i in range(start_index, len(rainfall_data) - 30):
        if check_onset_criteria(rainfall_data, i, region, season_type):
            onset_date_str = rainfall_data[i]["date"]
            # Determine if this is historical or forecast
            onset_date = date.fromisoformat(onset_date_str)
            today = date.today()
            if onset_date <= today:
                return onset_date_str, "occurred"
            else:
                return onset_date_str, "expected"

    return None, "not_yet"


def calculate_cessation_date(
    rainfall_data: list[dict],
    region: GhanaRegion,
    season_type: SeasonType,
    cessation_start_date: date,
) -> tuple[Optional[str], str]:
    """
    Calculate cessation date using soil water balance model.

    Soil water balance:
    - Start with 70mm soil water capacity
    - Daily: add rainfall, subtract ETO (default 4mm/day)
    - Cessation = when soil water reaches 0

    Args:
        rainfall_data: List of daily rainfall data with 'precipitation' and 'eto'.
        region: Ghana region.
        season_type: Type of season.
        cessation_start_date: Date when cessation calculation begins.

    Returns:
        Tuple of (cessation_date or None, status).
    """
    if not rainfall_data:
        return None, "not_yet"

    # Find the index corresponding to cessation start date
    start_index = 0
    for i, day_data in enumerate(rainfall_data):
        day_date = date.fromisoformat(day_data["date"])
        if day_date >= cessation_start_date:
            start_index = i
            break

    # Initialize soil water balance
    soil_water = SOIL_WATER_CAPACITY_MM

    for i in range(start_index, len(rainfall_data)):
        day_data = rainfall_data[i]
        precipitation = day_data.get("precipitation") or 0
        eto = day_data.get("eto") or DEFAULT_ETO_MM_PER_DAY

        # Update soil water balance
        soil_water = min(soil_water + precipitation - eto, SOIL_WATER_CAPACITY_MM)
        soil_water = max(soil_water, 0)

        if soil_water <= 0:
            cessation_date_str = day_data["date"]
            cessation_date = date.fromisoformat(cessation_date_str)
            today = date.today()
            if cessation_date <= today:
                return cessation_date_str, "occurred"
            else:
                return cessation_date_str, "expected"

    return None, "not_yet"


def calculate_dry_spells(
    rainfall_data: list[dict],
    onset_date_str: Optional[str],
    cessation_date_str: Optional[str],
) -> Optional[DrySpellInfo]:
    """
    Calculate early and late dry spells within the growing season.

    Early: Longest consecutive dry days from onset to day 50
    Late: Longest consecutive dry days from day 51 to cessation

    Args:
        rainfall_data: List of daily rainfall data.
        onset_date_str: Onset date string (ISO format).
        cessation_date_str: Cessation date string (ISO format).

    Returns:
        DrySpellInfo or None if data insufficient.
    """
    if not onset_date_str or not rainfall_data:
        return None

    onset_date = date.fromisoformat(onset_date_str)
    cessation_date = date.fromisoformat(cessation_date_str) if cessation_date_str else None

    # Find onset index
    onset_index = None
    for i, day_data in enumerate(rainfall_data):
        if day_data["date"] == onset_date_str:
            onset_index = i
            break

    if onset_index is None:
        return None

    # Early period: onset to day 50
    early_end_index = min(onset_index + 50, len(rainfall_data))

    # Late period: day 51 to cessation (or end of data)
    late_start_index = onset_index + 50
    late_end_index = len(rainfall_data)

    if cessation_date_str:
        for i, day_data in enumerate(rainfall_data):
            if day_data["date"] == cessation_date_str:
                late_end_index = i + 1
                break

    def find_longest_dry_spell(data: list[dict], start: int, end: int) -> int:
        max_dry = 0
        current_dry = 0
        for i in range(start, min(end, len(data))):
            precip = data[i].get("precipitation") or 0
            if precip < 1:  # Dry day
                current_dry += 1
                max_dry = max(max_dry, current_dry)
            else:
                current_dry = 0
        return max_dry

    early_dry = find_longest_dry_spell(rainfall_data, onset_index, early_end_index)
    late_dry = find_longest_dry_spell(rainfall_data, late_start_index, late_end_index)

    # Calculate periods for display
    early_start = onset_date
    early_end = early_start + timedelta(days=50)
    late_start = early_end + timedelta(days=1)
    late_end = cessation_date if cessation_date else late_start + timedelta(days=60)

    return DrySpellInfo(
        early_dry_spell_days=early_dry,
        late_dry_spell_days=late_dry,
        early_period=f"{early_start.strftime('%b %d')} - {early_end.strftime('%b %d')}",
        late_period=f"{late_start.strftime('%b %d')} - {late_end.strftime('%b %d')}",
    )


def generate_farming_advice(
    region: GhanaRegion,
    season_type: SeasonType,
    onset_status: str,
    cessation_status: str,
    dry_spells: Optional[DrySpellInfo],
) -> str:
    """
    Generate farming advice based on seasonal forecast.

    Args:
        region: Ghana region.
        season_type: Type of season.
        onset_status: Onset status (occurred, expected, not_yet).
        cessation_status: Cessation status.
        dry_spells: Dry spell information.

    Returns:
        Farming advice string.
    """
    advice_parts = []

    if onset_status == "occurred":
        advice_parts.append("Rains have started - ideal time for planting!")
    elif onset_status == "expected":
        advice_parts.append("Prepare your land now - rains expected soon.")
    else:
        advice_parts.append("Monitor conditions - season hasn't started yet.")

    if dry_spells:
        if dry_spells.early_dry_spell_days > 7:
            advice_parts.append(f"Watch for early dry spells ({dry_spells.early_dry_spell_days} days expected).")
        if dry_spells.late_dry_spell_days > 10:
            advice_parts.append("Plan for late-season moisture stress.")

    if region == GhanaRegion.NORTHERN:
        advice_parts.append("Single season - plan full crop cycle carefully.")
    elif season_type == SeasonType.MINOR:
        advice_parts.append("Minor season - consider quick-maturing varieties.")

    return " ".join(advice_parts)


def generate_summary(
    region: GhanaRegion,
    season_type: SeasonType,
    onset_date_str: Optional[str],
    onset_status: str,
    cessation_date_str: Optional[str],
    cessation_status: str,
    season_length: Optional[int],
) -> str:
    """
    Generate human-readable summary of seasonal forecast.

    Args:
        region: Ghana region.
        season_type: Type of season.
        onset_date_str: Onset date (ISO format).
        onset_status: Onset status.
        cessation_date_str: Cessation date (ISO format).
        cessation_status: Cessation status.
        season_length: Season length in days.

    Returns:
        Summary string.
    """
    region_name = "Southern" if region == GhanaRegion.SOUTHERN else "Northern"
    season_name = {
        SeasonType.MAJOR: "Major Season",
        SeasonType.MINOR: "Minor Season",
        SeasonType.SINGLE: "Single Season",
    }[season_type]

    parts = [f"{region_name} Ghana - {season_name}"]

    if onset_date_str:
        onset_date = date.fromisoformat(onset_date_str)
        onset_str = onset_date.strftime("%B %d")
        if onset_status == "occurred":
            parts.append(f"Onset: {onset_str} (confirmed)")
        else:
            parts.append(f"Onset: {onset_str} (forecast)")
    else:
        parts.append("Onset: Not yet detected")

    if cessation_date_str:
        cessation_date = date.fromisoformat(cessation_date_str)
        cess_str = cessation_date.strftime("%B %d")
        if cessation_status == "occurred":
            parts.append(f"Cessation: {cess_str} (confirmed)")
        else:
            parts.append(f"Cessation: {cess_str} (forecast)")
    else:
        parts.append("Cessation: TBD")

    if season_length:
        parts.append(f"Season length: {season_length} days")

    return ". ".join(parts)


async def get_seasonal_forecast(
    latitude: float,
    longitude: float,
) -> SeasonalForecastResponse:
    """
    Get Ghana-specific seasonal forecast with onset, cessation, and dry spells.

    Args:
        latitude: Location latitude.
        longitude: Location longitude.

    Returns:
        SeasonalForecastResponse with forecast data.
    """
    try:
        today = date.today()
        region = get_region(latitude)
        season_type = get_current_season_type(region, today)

        # Get season start/cessation dates for current year
        start_month, start_day = SEASON_START_DATES.get(
            (region, season_type),
            (2, 1),
        )
        cess_month, cess_day = CESSATION_START_DATES.get(
            (region, season_type),
            (10, 1),
        )

        season_start_date = date(today.year, start_month, start_day)
        cessation_start_date = date(today.year, cess_month, cess_day)

        # Fetch historical data from season start to today
        historical_data = []
        if season_start_date < today:
            # Use yesterday as end date to ensure data is available
            end_date = today - timedelta(days=1)
            historical_data = await get_historical_rainfall(
                latitude, longitude, season_start_date, end_date
            )

        # Fetch forecast data
        forecast_data = await get_forecast_rainfall(latitude, longitude, 16)

        # Combine historical and forecast data
        all_data = historical_data + forecast_data

        # Remove duplicates (keep historical for overlapping dates)
        seen_dates = set()
        combined_data = []
        for day in all_data:
            if day["date"] not in seen_dates:
                combined_data.append(day)
                seen_dates.add(day["date"])

        # Sort by date
        combined_data.sort(key=lambda x: x["date"])

        # Calculate onset
        onset_date_str, onset_status = calculate_onset_date(
            combined_data, region, season_type, season_start_date
        )

        # Calculate cessation
        cessation_date_str, cessation_status = calculate_cessation_date(
            combined_data, region, season_type, cessation_start_date
        )

        # Calculate season length
        season_length: Optional[int] = None
        if onset_date_str and cessation_date_str:
            onset_dt = date.fromisoformat(onset_date_str)
            cess_dt = date.fromisoformat(cessation_date_str)
            season_length = (cess_dt - onset_dt).days

        # Calculate dry spells
        dry_spells = calculate_dry_spells(combined_data, onset_date_str, cessation_date_str)

        # Generate summary and advice
        summary = generate_summary(
            region, season_type,
            onset_date_str, onset_status,
            cessation_date_str, cessation_status,
            season_length,
        )

        farming_advice = generate_farming_advice(
            region, season_type, onset_status, cessation_status, dry_spells
        )

        # Get expected ranges for when dates are not yet detected
        expected_onset_range = get_expected_onset_info(region, season_type)
        expected_cessation_range = get_expected_cessation_info(region, season_type)

        forecast = SeasonalForecast(
            region=region,
            season_type=season_type,
            onset_date=onset_date_str,
            onset_status=onset_status,
            expected_onset_range=expected_onset_range,
            cessation_date=cessation_date_str,
            cessation_status=cessation_status,
            expected_cessation_range=expected_cessation_range,
            season_length_days=season_length,
            dry_spells=dry_spells,
            summary=summary,
            farming_advice=farming_advice,
            latitude=latitude,
            longitude=longitude,
        )

        return SeasonalForecastResponse(success=True, data=forecast)

    except Exception as e:
        logger.error(f"Failed to get seasonal forecast: {e}")
        return SeasonalForecastResponse(
            success=False,
            error_message=f"Failed to calculate seasonal forecast: {str(e)}",
        )
