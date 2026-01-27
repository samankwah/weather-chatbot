"""Pydantic models for AI and agrometeorological data."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class QueryType(str, Enum):
    """Types of queries the chatbot can handle."""

    WEATHER = "weather"
    FORECAST = "forecast"
    MARINE = "marine"
    INLAND_WATER = "inland_water"
    ETO = "eto"
    GDD = "gdd"
    SOIL = "soil"
    SEASONAL = "seasonal"
    SEASONAL_ONSET = "seasonal_onset"
    SEASONAL_CESSATION = "seasonal_cessation"
    DRY_SPELL = "dry_spell"
    SEASON_LENGTH = "season_length"
    CROP_ADVICE = "crop_advice"
    DEKADAL = "dekadal"
    HELP = "help"
    GREETING = "greeting"


class GhanaRegion(str, Enum):
    """Ghana rainfall regions based on latitude."""

    SOUTHERN = "southern"  # Below 8°N - bimodal rainfall
    NORTHERN = "northern"  # Above 8°N - unimodal rainfall


class SeasonType(str, Enum):
    """Types of rainfall seasons in Ghana."""

    MAJOR = "major"    # Southern: Feb-Jul
    MINOR = "minor"    # Southern: Aug-Nov
    SINGLE = "single"  # Northern: Mar-Oct


class TimeOfDay(str, Enum):
    """Time of day references."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class TimeReference(BaseModel):
    """Model for time references in user queries."""

    reference: str = "now"  # now, today, tomorrow, this_week, next_week, weekend
    time_of_day: Optional[TimeOfDay] = None
    days_ahead: int = 0
    specific_day: Optional[str] = None  # e.g., "saturday", "monday"
    is_weekend: bool = False
    date_range_start: Optional[int] = None  # days ahead for range start
    date_range_end: Optional[int] = None  # days ahead for range end


class IntentExtraction(BaseModel):
    """Model for AI-extracted intent from user message."""

    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    query_type: QueryType = QueryType.WEATHER
    crop: Optional[str] = None
    time_reference: TimeReference = Field(default_factory=TimeReference)
    confidence: float = 0.8
    raw_message: str = ""


class ConversationTurn(BaseModel):
    """Model for a single turn in conversation history."""

    role: str  # user or assistant
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class PendingClarification(BaseModel):
    """Model for pending location clarification state."""

    original_query: str
    options: list[dict] = Field(default_factory=list)  # List of {place_name, lat, lon, display_name}
    expires_at: datetime


class UserContext(BaseModel):
    """Model for user context/memory storage."""

    user_id: str
    user_name: Optional[str] = None  # WhatsApp ProfileName for personalized greetings
    last_city: Optional[str] = None
    last_latitude: Optional[float] = None
    last_longitude: Optional[float] = None
    preferred_crop: Optional[str] = None
    preferred_language: Optional[str] = None  # e.g., "en", "tw", "ga", "ee", "dag"
    last_query_type: Optional[str] = None  # Track last query for contextual buttons
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    last_interaction: datetime = Field(default_factory=datetime.now)

    # Home location - permanent storage from WhatsApp location share
    home_latitude: Optional[float] = None
    home_longitude: Optional[float] = None
    home_location_name: Optional[str] = None

    # Pending clarification state for ambiguous locations
    pending_clarification: Optional[PendingClarification] = None

    @property
    def has_home_location(self) -> bool:
        """Check if user has a saved home location."""
        return self.home_latitude is not None and self.home_longitude is not None


class ForecastPeriod(BaseModel):
    """Model for a single forecast period."""

    datetime_str: str
    timestamp: int
    temperature: float
    feels_like: float
    temp_min: float
    temp_max: float
    humidity: int
    description: str
    icon: str
    wind_speed: float
    precipitation_probability: Optional[float] = None
    rain_volume: Optional[float] = None


class ForecastData(BaseModel):
    """Model for forecast data."""

    city: str
    country: str
    latitude: float
    longitude: float
    periods: list[ForecastPeriod]


class ForecastResponse(BaseModel):
    """Model for forecast API response."""

    success: bool
    data: Optional[ForecastData] = None
    error_message: Optional[str] = None


class MarineHourlyData(BaseModel):
    """Model for hourly marine or inland water conditions."""

    time: str
    wave_height: Optional[float] = None
    wave_direction: Optional[float] = None
    wave_period: Optional[float] = None
    swell_wave_height: Optional[float] = None
    swell_wave_direction: Optional[float] = None
    swell_wave_period: Optional[float] = None
    wind_wave_height: Optional[float] = None
    wind_wave_direction: Optional[float] = None
    wind_wave_period: Optional[float] = None
    ocean_temperature: Optional[float] = None
    ocean_current_velocity: Optional[float] = None
    wind_speed: Optional[float] = None
    wind_direction: Optional[float] = None
    precipitation_probability: Optional[float] = None
    weathercode: Optional[int] = None


class MarineWindowSummary(BaseModel):
    """Model for summarized 12h/24h marine risk windows."""

    label: str
    start: str
    end: str
    wave_height_max: Optional[float] = None
    wave_height_mean: Optional[float] = None
    wind_speed_max: Optional[float] = None
    precip_probability_max: Optional[float] = None
    ocean_temp_mean: Optional[float] = None
    current_speed_mean: Optional[float] = None
    thunderstorm_risk: bool = False
    sea_state: str = "Unknown"
    likelihood: str = "Low"
    impact: str = "Low"
    risk_label: str = "Low"
    risk_emoji: str = "🟢"


class MarineForecastData(BaseModel):
    """Model for marine and inland water forecast data."""

    latitude: float
    longitude: float
    location_name: str
    timezone: str
    hourly: list[MarineHourlyData] = Field(default_factory=list)
    windows: list[MarineWindowSummary] = Field(default_factory=list)
    source: str
    is_inland: bool = False
    location_note: Optional[str] = None


class MarineForecastResponse(BaseModel):
    """Model for marine forecast API response."""

    success: bool
    data: Optional[MarineForecastData] = None
    error_message: Optional[str] = None


class SoilMoistureData(BaseModel):
    """Model for soil moisture at different depths."""

    moisture_0_1cm: Optional[float] = None  # Surface layer
    moisture_1_3cm: Optional[float] = None
    moisture_3_9cm: Optional[float] = None
    moisture_9_27cm: Optional[float] = None  # Root zone
    moisture_27_81cm: Optional[float] = None  # Deep layer
    timestamp: str = ""


class DailyAgroData(BaseModel):
    """Model for daily agrometeorological data."""

    date: str
    eto: Optional[float] = None  # FAO Penman-Monteith ETo in mm
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    precipitation: Optional[float] = None
    humidity_mean: Optional[float] = None


class AgroMetData(BaseModel):
    """Model for agrometeorological data."""

    latitude: float
    longitude: float
    daily_data: list[DailyAgroData] = Field(default_factory=list)
    soil_moisture: Optional[SoilMoistureData] = None


class AgroMetResponse(BaseModel):
    """Model for agrometeorological API response."""

    success: bool
    data: Optional[AgroMetData] = None
    error_message: Optional[str] = None


class GDDStage(BaseModel):
    """Model for GDD growth stage."""

    stage_name: str
    gdd_required: int
    reached: bool = False


class GDDData(BaseModel):
    """Model for Growing Degree Days calculation."""

    crop: str
    base_temp: float
    accumulated_gdd: float
    current_stage: str
    next_stage: Optional[str] = None
    gdd_to_next_stage: Optional[float] = None
    stages: list[GDDStage] = Field(default_factory=list)


class SeasonalOutlook(BaseModel):
    """Model for seasonal (3-6 month) forecasts."""

    latitude: float
    longitude: float
    forecast_days: int
    temperature_trend: str  # above_normal, normal, below_normal
    precipitation_trend: str  # above_normal, normal, below_normal
    summary: str
    daily_forecasts: list[DailyAgroData] = Field(default_factory=list)


class SeasonalResponse(BaseModel):
    """Model for seasonal forecast API response."""

    success: bool
    data: Optional[SeasonalOutlook] = None
    error_message: Optional[str] = None


class CropInfo(BaseModel):
    """Model for crop information."""

    name: str
    base_temp: float
    gdd_stages: dict[str, int]  # stage_name -> GDD required
    water_needs: str  # low, medium, high
    optimal_soil_moisture: float  # percentage


class AIResponse(BaseModel):
    """Model for AI-generated response."""

    message: str
    query_type: QueryType
    confidence: float = 0.8
    extracted_intent: Optional[IntentExtraction] = None


class DrySpellInfo(BaseModel):
    """Model for dry spell information during a season."""

    early_dry_spell_days: int  # Longest dry period from onset to day 50
    late_dry_spell_days: int   # Longest dry period from day 51 to cessation
    early_period: str          # Date range for early period
    late_period: str           # Date range for late period


class SeasonalForecast(BaseModel):
    """Model for Ghana-specific seasonal forecast with onset/cessation."""

    region: GhanaRegion
    season_type: SeasonType
    onset_date: Optional[str] = None
    onset_status: str  # "occurred", "expected", "not_yet"
    expected_onset_range: Optional[str] = None  # e.g., "Mar 1-15" when not yet detected
    cessation_date: Optional[str] = None
    cessation_status: str  # "occurred", "expected", "not_yet"
    expected_cessation_range: Optional[str] = None  # e.g., "Jul 15-31" when not yet detected
    season_length_days: Optional[int] = None
    dry_spells: Optional[DrySpellInfo] = None
    summary: str
    farming_advice: str
    latitude: float
    longitude: float


class SeasonalForecastResponse(BaseModel):
    """Model for seasonal forecast API response."""

    success: bool
    data: Optional[SeasonalForecast] = None
    error_message: Optional[str] = None
