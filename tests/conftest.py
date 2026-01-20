"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings object."""
    settings = MagicMock()
    settings.twilio_account_sid = "test_account_sid"
    settings.twilio_auth_token = "test_auth_token"
    settings.twilio_whatsapp_number = "+14155238886"
    settings.twilio_whatsapp_from = "whatsapp:+14155238886"
    settings.weather_api_key = "test_weather_key"
    settings.weather_api_url = "https://api.openweathermap.org/data/2.5/weather"
    settings.default_city = "Accra"
    settings.default_country = "Ghana"
    settings.default_location = "Accra,Ghana"
    return settings


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
def sample_twilio_webhook_data() -> dict:
    """Sample Twilio webhook form data."""
    return {
        "MessageSid": "SM123456789abcdef",
        "AccountSid": "AC123456789abcdef",
        "From": "whatsapp:+233201234567",
        "To": "whatsapp:+14155238886",
        "Body": "weather",
        "NumMedia": "0",
        "ProfileName": "Test User",
    }
