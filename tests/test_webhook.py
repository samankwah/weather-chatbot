"""Tests for webhook endpoint and services."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import WeatherData, WeatherResponse
from app.services.location import extract_city_from_text
from app.services.messaging import format_weather_message, format_help_message
from app.services.weather import parse_weather_response


client = TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check_returns_healthy(self) -> None:
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_root_endpoint(self) -> None:
        """Root endpoint should return API info."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Weather Chatbot API" in response.json()["message"]


class TestMessageExtraction:
    """Tests for city extraction from messages."""

    def test_extract_city_from_weather_in_pattern(self) -> None:
        """Should extract city from 'weather in X' pattern."""
        city = extract_city_from_text("weather in Lagos")
        assert city == "Lagos"

    def test_extract_city_from_weather_for_pattern(self) -> None:
        """Should extract city from 'weather for X' pattern."""
        city = extract_city_from_text("weather for Kumasi")
        assert city == "Kumasi"

    def test_extract_city_single_word(self) -> None:
        """Should return single word as city name."""
        city = extract_city_from_text("Nairobi")
        assert city == "Nairobi"

    def test_extract_city_returns_none_for_keyword_only(self) -> None:
        """Should return None for weather keyword alone."""
        city = extract_city_from_text("weather")
        assert city is None


class TestWeatherResponseParsing:
    """Tests for weather API response parsing."""

    def test_parse_weather_response(self) -> None:
        """Should correctly parse OpenWeatherMap response."""
        mock_response = {
            "name": "Accra",
            "sys": {"country": "GH"},
            "main": {"temp": 28.5, "feels_like": 30.2, "humidity": 75},
            "weather": [{"description": "scattered clouds", "icon": "03d"}],
            "wind": {"speed": 12.5},
        }

        result = parse_weather_response(mock_response)

        assert result.city == "Accra"
        assert result.country == "GH"
        assert result.temperature == 28.5
        assert result.feels_like == 30.2
        assert result.humidity == 75
        assert result.description == "scattered clouds"
        assert result.wind_speed == 12.5


class TestMessageFormatting:
    """Tests for message formatting functions."""

    def test_format_weather_message(self) -> None:
        """Should format weather data into readable message."""
        weather_data = WeatherData(
            city="Accra",
            country="GH",
            temperature=28.5,
            feels_like=30.2,
            humidity=75,
            description="scattered clouds",
            wind_speed=12.5,
            icon="03d",
        )

        message = format_weather_message(weather_data)

        assert "Accra" in message
        assert "28.5°C" in message
        assert "75%" in message

    def test_format_help_message(self) -> None:
        """Should return help message with instructions."""
        message = format_help_message()

        assert "weather" in message.lower()
        assert "Accra" in message


class TestWebhookEndpoint:
    """Tests for Twilio webhook endpoint."""

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.get_messaging_provider")
    @patch("app.routes.webhook.get_weather_for_location")
    def test_webhook_processes_weather_request(
        self,
        mock_get_weather: MagicMock,
        mock_get_provider: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """Webhook should process weather request and send response."""
        mock_validate.return_value = True

        mock_provider = MagicMock()
        mock_provider.send_message.return_value = True
        mock_get_provider.return_value = mock_provider

        mock_get_weather.return_value = WeatherResponse(
            success=True,
            data=WeatherData(
                city="Accra",
                country="GH",
                temperature=28.5,
                feels_like=30.2,
                humidity=75,
                description="clear sky",
                wind_speed=10.0,
                icon="01d",
            ),
        )

        response = client.post(
            "/webhook",
            data={
                "Body": "weather",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM123456789",
                "AccountSid": "AC123456789",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.get_messaging_provider")
    def test_webhook_handles_help_request(
        self,
        mock_get_provider: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """Webhook should return help message for help trigger."""
        mock_validate.return_value = True

        mock_provider = MagicMock()
        mock_provider.send_message.return_value = True
        mock_get_provider.return_value = mock_provider

        response = client.post(
            "/webhook",
            data={
                "Body": "hello",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM123456789",
                "AccountSid": "AC123456789",
            },
        )

        assert response.status_code == 200
        mock_provider.send_message.assert_called_once()
