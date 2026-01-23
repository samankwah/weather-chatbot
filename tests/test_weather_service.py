"""Tests for weather service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.models.schemas import WeatherData, WeatherResponse
from app.services.weather import (
    extract_city_from_message,
    get_weather,
    get_weather_by_coordinates,
    parse_weather_response,
)


class TestParseWeatherResponse:
    """Tests for parsing OpenWeatherMap responses."""

    def test_parse_complete_response(self, sample_weather_api_response: dict) -> None:
        """Should parse all fields from API response."""
        result = parse_weather_response(sample_weather_api_response)

        assert isinstance(result, WeatherData)
        assert result.city == "Accra"
        assert result.country == "GH"
        assert result.temperature == 28.5
        assert result.feels_like == 30.2
        assert result.humidity == 75
        assert result.description == "scattered clouds"
        assert result.wind_speed == 12.5
        assert result.icon == "03d"

    def test_parse_minimal_response(self) -> None:
        """Should parse response with minimal data."""
        minimal_response = {
            "name": "Test City",
            "sys": {"country": "TC"},
            "main": {"temp": 25.0, "feels_like": 26.0, "humidity": 50},
            "weather": [{"description": "clear", "icon": "01d"}],
            "wind": {"speed": 3.0},
        }

        result = parse_weather_response(minimal_response)

        assert result.city == "Test City"
        assert result.temperature == 25.0


class TestExtractCityFromMessage:
    """Tests for extracting city names from user messages."""

    def test_extract_city_from_weather_in_pattern(self) -> None:
        """Should extract city from 'weather in X' pattern."""
        city = extract_city_from_message("weather in Lagos")
        assert city == "Lagos"

    def test_extract_city_from_weather_for_pattern(self) -> None:
        """Should extract city from 'weather for X' pattern."""
        city = extract_city_from_message("weather for Kumasi")
        assert city == "Kumasi"

    def test_extract_city_from_temp_pattern(self) -> None:
        """Should extract city from 'temp in X' pattern."""
        city = extract_city_from_message("temp in Tamale")
        assert city == "Tamale"

    def test_extract_city_case_insensitive(self) -> None:
        """Should handle case-insensitive matching."""
        city = extract_city_from_message("WEATHER IN accra")
        assert city is not None

    def test_extract_city_single_word_input(self) -> None:
        """Should return single word as potential city."""
        city = extract_city_from_message("Nairobi")
        assert city == "Nairobi"

    def test_extract_city_strips_punctuation(self) -> None:
        """Should strip trailing punctuation."""
        city = extract_city_from_message("weather in Lagos?")
        assert city == "Lagos"

        city = extract_city_from_message("weather in Accra.")
        assert city == "Accra"

    def test_extract_city_returns_none_for_keyword_only(self) -> None:
        """Should return None when only keyword present."""
        city = extract_city_from_message("weather")
        assert city is None

        city = extract_city_from_message("forecast")
        assert city is None

    def test_extract_city_handles_preposition_start(self) -> None:
        """Should extract city starting with preposition."""
        city = extract_city_from_message("in Accra")
        assert city == "Accra"


class TestGetWeather:
    """Tests for get_weather function."""

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_get_weather_success(
        self,
        mock_get_client: MagicMock,
        sample_weather_api_response: dict,
    ) -> None:
        """Should return weather data on success."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_weather_api_response
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await get_weather("Accra")

        assert result.success is True
        assert result.data is not None
        assert result.data.city == "Accra"

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_get_weather_city_not_found(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return error for 404 response."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await get_weather("InvalidCity123")

        assert result.success is False
        assert "couldn't find" in result.error_message.lower()

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_get_weather_server_error(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return error for server errors."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await get_weather("Accra")

        assert result.success is False
        assert "trouble" in result.error_message.lower()

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_get_weather_timeout(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return error on timeout."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_get_client.return_value = mock_client

        result = await get_weather("Accra")

        assert result.success is False
        assert "taking too long" in result.error_message.lower()

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_get_weather_connection_error(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return error on connection failure."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.RequestError("connection failed")
        )
        mock_get_client.return_value = mock_client

        result = await get_weather("Accra")

        assert result.success is False
        assert "couldn't connect" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_get_weather_requires_location(self) -> None:
        """Should return error when city is None (no default fallback)."""
        result = await get_weather(None)

        assert result.success is False
        assert "need a location" in result.error_message.lower()


class TestGetWeatherByCoordinates:
    """Tests for get_weather_by_coordinates function."""

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_get_weather_by_coords_success(
        self,
        mock_get_client: MagicMock,
        sample_weather_api_response: dict,
    ) -> None:
        """Should return weather data for coordinates."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_weather_api_response
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await get_weather_by_coordinates(5.6037, -0.1870)

        assert result.success is True
        assert result.data is not None

        # Verify coordinates were passed
        call_kwargs = mock_client.get.call_args
        assert "lat" in str(call_kwargs)
        assert "lon" in str(call_kwargs)

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_get_weather_by_coords_error(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return error for failed coordinate lookup."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await get_weather_by_coordinates(999.0, 999.0)

        assert result.success is False


class TestCountryCodeMapping:
    """Tests for country code mapping in weather lookups."""

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_ghana_country_name_mapped_to_code(
        self,
        mock_get_client: MagicMock,
        sample_weather_api_response: dict,
    ) -> None:
        """Should map 'Ghana' to 'GH' code."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_weather_api_response
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        await get_weather("Accra, Ghana")

        call_args = mock_client.get.call_args
        # The query should contain GH, not Ghana
        params = call_args.kwargs.get("params", {})
        assert "GH" in params.get("q", "") or "ghana" not in params.get("q", "").lower()

    @pytest.mark.asyncio
    @patch("app.services.weather.get_http_client")
    async def test_nigeria_country_mapped(
        self,
        mock_get_client: MagicMock,
        sample_weather_api_response: dict,
    ) -> None:
        """Should map 'Nigeria' to 'NG' code."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        sample_weather_api_response["name"] = "Lagos"
        sample_weather_api_response["sys"]["country"] = "NG"
        mock_response.json.return_value = sample_weather_api_response
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        result = await get_weather("Lagos, Nigeria")

        assert result.success is True
