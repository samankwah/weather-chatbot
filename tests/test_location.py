"""Tests for location parsing service."""

import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import LocationInput, WeatherData, WeatherResponse
from app.services.location import extract_city_from_text, parse_webhook_location


client = TestClient(app)


class TestParseWebhookLocation:
    """Tests for parse_webhook_location function."""

    def test_parse_valid_coordinates(self) -> None:
        """Should parse valid latitude and longitude."""
        result = parse_webhook_location("5.5600", "-0.1900", "")

        assert result.has_coordinates is True
        assert result.latitude == 5.56
        assert result.longitude == -0.19
        assert result.city is None

    def test_parse_coordinates_with_body(self) -> None:
        """Should prioritize coordinates over body text."""
        result = parse_webhook_location("5.5600", "-0.1900", "Lagos")

        assert result.has_coordinates is True
        assert result.latitude == 5.56
        assert result.longitude == -0.19

    def test_parse_invalid_latitude(self) -> None:
        """Should fall back to city when latitude is invalid."""
        result = parse_webhook_location("invalid", "-0.1900", "Accra")

        assert result.has_coordinates is False
        assert result.city == "Accra"

    def test_parse_missing_longitude(self) -> None:
        """Should fall back to city when longitude is missing."""
        result = parse_webhook_location("5.5600", None, "Kumasi")

        assert result.has_coordinates is False
        assert result.city == "Kumasi"

    def test_parse_missing_both_coordinates(self) -> None:
        """Should extract city from body when no coordinates."""
        result = parse_webhook_location(None, None, "weather in Lagos")

        assert result.has_coordinates is False
        assert result.city == "Lagos"

    def test_parse_empty_body_no_coordinates(self) -> None:
        """Should return None city when no coordinates and empty body."""
        result = parse_webhook_location(None, None, "weather")

        assert result.has_coordinates is False
        assert result.city is None


class TestExtractCityFromText:
    """Tests for extract_city_from_text function."""

    def test_extract_city_from_weather_in_pattern(self) -> None:
        """Should extract city from 'weather in X' pattern."""
        city = extract_city_from_text("weather in Lagos")
        assert city == "Lagos"

    def test_extract_city_from_weather_for_pattern(self) -> None:
        """Should extract city from 'weather for X' pattern."""
        city = extract_city_from_text("weather for Kumasi")
        assert city == "Kumasi"

    def test_extract_city_from_temp_in_pattern(self) -> None:
        """Should extract city from 'temp in X' pattern."""
        city = extract_city_from_text("temp in Nairobi")
        assert city == "Nairobi"

    def test_extract_city_from_temperature_at_pattern(self) -> None:
        """Should extract city from 'temperature at X' pattern."""
        city = extract_city_from_text("temperature at Cape Town")
        assert city == "Cape Town"

    def test_extract_single_city_name(self) -> None:
        """Should return single word as city name."""
        city = extract_city_from_text("Nairobi")
        assert city == "Nairobi"

    def test_extract_multi_word_city(self) -> None:
        """Should return multi-word city name."""
        city = extract_city_from_text("New York")
        assert city == "New York"

    def test_extract_returns_none_for_keyword_only(self) -> None:
        """Should return None for weather keyword alone."""
        city = extract_city_from_text("weather")
        assert city is None

    def test_extract_strips_question_marks(self) -> None:
        """Should strip question marks from city names."""
        city = extract_city_from_text("weather in Lagos?")
        assert city == "Lagos"

    def test_extract_strips_periods(self) -> None:
        """Should strip periods from city names."""
        city = extract_city_from_text("weather in Accra.")
        assert city == "Accra"

    def test_extract_handles_whitespace(self) -> None:
        """Should handle extra whitespace."""
        city = extract_city_from_text("  weather in   Lagos  ")
        assert city == "Lagos"


class TestLocationInput:
    """Tests for LocationInput model."""

    def test_has_coordinates_true(self) -> None:
        """Should return True when coordinates are set."""
        location = LocationInput(latitude=5.56, longitude=-0.19)
        assert location.has_coordinates is True

    def test_has_coordinates_false_missing_lat(self) -> None:
        """Should return False when latitude is missing."""
        location = LocationInput(longitude=-0.19)
        assert location.has_coordinates is False

    def test_has_coordinates_false_missing_lon(self) -> None:
        """Should return False when longitude is missing."""
        location = LocationInput(latitude=5.56)
        assert location.has_coordinates is False

    def test_has_coordinates_false_city_only(self) -> None:
        """Should return False when only city is set."""
        location = LocationInput(city="Accra")
        assert location.has_coordinates is False


class TestWebhookWithLocation:
    """Tests for webhook endpoint with location data."""

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.get_messaging_provider")
    @patch("app.routes.webhook.get_weather_for_location")
    def test_webhook_handles_location_share(
        self,
        mock_get_weather: MagicMock,
        mock_get_provider: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """Webhook should process GPS location and return weather."""
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
                "Body": "",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM123456789",
                "AccountSid": "AC123456789",
                "Latitude": "5.5600",
                "Longitude": "-0.1900",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_get_weather.assert_called_once()

        call_args = mock_get_weather.call_args[0][0]
        assert call_args.latitude == 5.56
        assert call_args.longitude == -0.19

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.get_messaging_provider")
    @patch("app.routes.webhook.get_weather_for_location")
    def test_webhook_falls_back_to_text(
        self,
        mock_get_weather: MagicMock,
        mock_get_provider: MagicMock,
        mock_validate: MagicMock,
    ) -> None:
        """Webhook should fall back to text parsing when no coordinates."""
        mock_validate.return_value = True

        mock_provider = MagicMock()
        mock_provider.send_message.return_value = True
        mock_get_provider.return_value = mock_provider

        mock_get_weather.return_value = WeatherResponse(
            success=True,
            data=WeatherData(
                city="Lagos",
                country="NG",
                temperature=30.0,
                feels_like=32.0,
                humidity=80,
                description="partly cloudy",
                wind_speed=8.0,
                icon="02d",
            ),
        )

        response = client.post(
            "/webhook",
            data={
                "Body": "weather in Lagos",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM123456789",
                "AccountSid": "AC123456789",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

        call_args = mock_get_weather.call_args[0][0]
        assert call_args.city == "Lagos"
        assert call_args.has_coordinates is False
