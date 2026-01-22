"""Pytest configuration and fixtures for weather chatbot tests."""

from datetime import datetime
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.ai_schemas import (
    AgroMetData,
    ConversationTurn,
    DailyAgroData,
    DrySpellInfo,
    ForecastData,
    ForecastPeriod,
    GDDData,
    GDDStage,
    GhanaRegion,
    IntentExtraction,
    QueryType,
    SeasonalForecast,
    SeasonType,
    SoilMoistureData,
    TimeReference,
    UserContext,
)
from app.models.schemas import WeatherData, WeatherResponse


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create test client for FastAPI app."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings object."""
    settings = MagicMock()
    settings.twilio_account_sid = "ACtest123456789"
    settings.twilio_auth_token = "test_auth_token"
    settings.twilio_whatsapp_number = "+14155238886"
    settings.twilio_whatsapp_from = "whatsapp:+14155238886"
    settings.weather_api_key = "test_weather_key"
    settings.weather_api_url = "https://api.openweathermap.org/data/2.5/weather"
    settings.weather_forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
    settings.groq_api_key = "test_groq_key"
    settings.groq_model = "llama-3.1-8b-instant"
    settings.groq_timeout = 10.0
    settings.open_meteo_base_url = "https://api.open-meteo.com/v1"
    settings.open_meteo_forecast_days = 16
    settings.memory_ttl_seconds = 3600
    settings.default_city = "Accra"
    settings.default_country = "Ghana"
    settings.default_latitude = 5.6037
    settings.default_longitude = -0.1870
    settings.default_location = "Accra,Ghana"
    return settings


@pytest.fixture
def sample_weather_data() -> WeatherData:
    """Create sample weather data."""
    return WeatherData(
        city="Accra",
        country="GH",
        temperature=30.5,
        feels_like=32.0,
        humidity=75,
        description="scattered clouds",
        wind_speed=5.5,
        icon="03d",
    )


@pytest.fixture
def sample_weather_api_response() -> dict:
    """Sample OpenWeatherMap API response."""
    return {
        "coord": {"lon": -0.1969, "lat": 5.556},
        "weather": [
            {
                "id": 802,
                "main": "Clouds",
                "description": "scattered clouds",
                "icon": "03d",
            }
        ],
        "base": "stations",
        "main": {
            "temp": 28.5,
            "feels_like": 30.2,
            "temp_min": 28.0,
            "temp_max": 29.0,
            "pressure": 1012,
            "humidity": 75,
        },
        "visibility": 10000,
        "wind": {"speed": 12.5, "deg": 220},
        "clouds": {"all": 40},
        "dt": 1699012345,
        "sys": {
            "type": 1,
            "id": 1234,
            "country": "GH",
            "sunrise": 1698990000,
            "sunset": 1699032000,
        },
        "timezone": 0,
        "id": 2306104,
        "name": "Accra",
        "cod": 200,
    }


@pytest.fixture
def sample_open_meteo_response() -> dict:
    """Create sample Open-Meteo API response."""
    return {
        "daily": {
            "time": ["2024-01-21", "2024-01-22", "2024-01-23"],
            "et0_fao_evapotranspiration": [4.5, 5.0, 4.8],
            "temperature_2m_max": [32.0, 33.0, 31.5],
            "temperature_2m_min": [24.0, 25.0, 23.5],
            "precipitation_sum": [0.0, 5.2, 0.0],
        },
        "hourly": {
            "time": ["2024-01-21T12:00"] * 24,
            "soil_moisture_0_to_1cm": [0.35] * 24,
            "soil_moisture_1_to_3cm": [0.38] * 24,
            "soil_moisture_3_to_9cm": [0.40] * 24,
            "soil_moisture_9_to_27cm": [0.42] * 24,
            "soil_moisture_27_to_81cm": [0.45] * 24,
            "relative_humidity_2m": [70] * 24,
        },
    }


@pytest.fixture
def sample_twilio_webhook_data() -> dict:
    """Sample Twilio webhook form data."""
    return {
        "MessageSid": "SM12345678901234567890123456789012",
        "AccountSid": "ACtest123456789",
        "From": "whatsapp:+233201234567",
        "To": "whatsapp:+14155238886",
        "Body": "weather",
        "NumMedia": "0",
        "ProfileName": "Test User",
    }


@pytest.fixture
def sample_user_context() -> UserContext:
    """Create sample user context."""
    return UserContext(
        user_id="whatsapp:+233201234567",
        last_city="Accra",
        last_latitude=5.6037,
        last_longitude=-0.1870,
        preferred_crop="maize",
        conversation_history=[
            ConversationTurn(
                role="user",
                content="What's the weather in Accra?",
                timestamp=datetime.now(),
            ),
            ConversationTurn(
                role="assistant",
                content="The weather in Accra is sunny with 30°C",
                timestamp=datetime.now(),
            ),
        ],
        last_interaction=datetime.now(),
    )


@pytest.fixture
def sample_intent() -> IntentExtraction:
    """Create sample intent extraction."""
    return IntentExtraction(
        city="Accra",
        query_type=QueryType.WEATHER,
        crop=None,
        time_reference=TimeReference(reference="now", days_ahead=0),
        confidence=0.9,
        raw_message="What's the weather in Accra?",
    )


@pytest.fixture
def sample_forecast_data() -> ForecastData:
    """Create sample forecast data."""
    return ForecastData(
        city="Accra",
        country="GH",
        latitude=5.6037,
        longitude=-0.1870,
        periods=[
            ForecastPeriod(
                datetime_str="2024-01-21 12:00",
                timestamp=1705838400,
                temperature=30.0,
                feels_like=32.0,
                temp_min=28.0,
                temp_max=32.0,
                humidity=70,
                description="scattered clouds",
                icon="03d",
                wind_speed=5.0,
                precipitation_probability=20.0,
            ),
            ForecastPeriod(
                datetime_str="2024-01-22 12:00",
                timestamp=1705924800,
                temperature=31.0,
                feels_like=33.0,
                temp_min=29.0,
                temp_max=33.0,
                humidity=65,
                description="few clouds",
                icon="02d",
                wind_speed=4.5,
                precipitation_probability=10.0,
            ),
        ],
    )


@pytest.fixture
def sample_agromet_data() -> AgroMetData:
    """Create sample agrometeorological data."""
    return AgroMetData(
        latitude=5.6037,
        longitude=-0.1870,
        daily_data=[
            DailyAgroData(
                date="2024-01-21",
                eto=4.5,
                temp_max=32.0,
                temp_min=24.0,
                precipitation=0.0,
                humidity_mean=70,
            ),
            DailyAgroData(
                date="2024-01-22",
                eto=5.0,
                temp_max=33.0,
                temp_min=25.0,
                precipitation=5.2,
                humidity_mean=75,
            ),
        ],
        soil_moisture=SoilMoistureData(
            moisture_0_1cm=35.0,
            moisture_1_3cm=38.0,
            moisture_3_9cm=40.0,
            moisture_9_27cm=42.0,
            moisture_27_81cm=45.0,
            timestamp="2024-01-21T12:00",
        ),
    )


@pytest.fixture
def sample_gdd_data() -> GDDData:
    """Create sample GDD data."""
    return GDDData(
        crop="maize",
        base_temp=10.0,
        accumulated_gdd=450.0,
        current_stage="v6_vegetative",
        next_stage="tasseling",
        gdd_to_next_stage=400.0,
        stages=[
            GDDStage(stage_name="germination", gdd_required=50, reached=True),
            GDDStage(stage_name="v6_vegetative", gdd_required=200, reached=True),
            GDDStage(stage_name="tasseling", gdd_required=850, reached=False),
        ],
    )


@pytest.fixture
def sample_seasonal_forecast() -> SeasonalForecast:
    """Create sample seasonal forecast."""
    return SeasonalForecast(
        region=GhanaRegion.SOUTHERN,
        season_type=SeasonType.MAJOR,
        onset_date="2024-03-15",
        onset_status="occurred",
        expected_onset_range="Mar 1 - Apr 15",
        cessation_date="2024-07-20",
        cessation_status="expected",
        expected_cessation_range="Jul 15 - Aug 15",
        season_length_days=127,
        dry_spells=DrySpellInfo(
            early_dry_spell_days=5,
            late_dry_spell_days=8,
            early_period="Mar 15 - May 04",
            late_period="May 05 - Jul 20",
        ),
        summary="Southern Ghana - Major Season. Onset: March 15 (confirmed)",
        farming_advice="Rains have started - ideal time for planting!",
        latitude=5.6037,
        longitude=-0.1870,
    )


@pytest.fixture
def mock_request_validator():
    """Create mock Twilio request validator that always passes."""
    with patch("app.routes.webhook.RequestValidator") as mock:
        mock.return_value.validate.return_value = True
        yield mock


@pytest.fixture
def mock_memory_store():
    """Create mock memory store."""
    store = MagicMock()
    store.get_context.return_value = None
    store.get_or_create_context.return_value = UserContext(
        user_id="whatsapp:+233201234567"
    )
    store.update_context.return_value = UserContext(user_id="whatsapp:+233201234567")
    store.add_user_message.return_value = UserContext(user_id="whatsapp:+233201234567")
    store.add_assistant_message.return_value = UserContext(
        user_id="whatsapp:+233201234567"
    )
    return store


@pytest.fixture
def mock_ai_provider():
    """Create mock AI provider."""
    provider = AsyncMock()
    provider.extract_intent = AsyncMock(
        return_value=IntentExtraction(
            city="Accra",
            query_type=QueryType.WEATHER,
            confidence=0.9,
            raw_message="What's the weather?",
        )
    )
    provider.generate_response = AsyncMock(
        return_value="The weather in Accra is sunny with 30°C"
    )
    return provider


@pytest.fixture
def mock_messaging_provider():
    """Create mock messaging provider."""
    provider = MagicMock()
    provider.send_message.return_value = True
    return provider


def create_mock_httpx_response(
    status_code: int = 200,
    json_data: dict | None = None,
) -> MagicMock:
    """Helper to create mock httpx responses."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    if json_data:
        response.json.return_value = json_data
    return response
