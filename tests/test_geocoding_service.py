"""Tests for geocoding service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.geocoding import (
    GeocodingResponse,
    GeocodingResult,
    calculate_confidence,
    format_clarification_question,
    geocode_location,
    reverse_geocode,
    should_ask_clarification,
)


class TestConfidenceCalculation:
    """Tests for confidence score calculation."""

    def test_village_gets_high_confidence(self) -> None:
        """Village-type places should get higher confidence."""
        result = {
            "importance": 0.5,
            "boundingbox": ["5.55", "5.56", "-0.20", "-0.19"],  # Small bbox
            "type": "village",
            "class": "place",
        }
        confidence = calculate_confidence(result)
        assert confidence >= 0.7

    def test_city_gets_moderate_confidence(self) -> None:
        """City-type places should get moderate confidence."""
        result = {
            "importance": 0.7,
            "boundingbox": ["5.50", "5.70", "-0.30", "-0.10"],  # Medium bbox
            "type": "city",
            "class": "place",
        }
        confidence = calculate_confidence(result)
        assert 0.5 <= confidence <= 0.85

    def test_region_gets_lower_confidence(self) -> None:
        """Region-type places should get lower confidence."""
        result = {
            "importance": 0.3,
            "boundingbox": ["5.00", "7.00", "-1.00", "0.50"],  # Large bbox
            "type": "administrative",
            "class": "boundary",
        }
        confidence = calculate_confidence(result)
        assert confidence <= 0.6

    def test_high_importance_boosts_confidence(self) -> None:
        """High importance score should boost confidence."""
        result = {
            "importance": 1.0,
            "boundingbox": ["5.55", "5.56", "-0.20", "-0.19"],
            "type": "town",
            "class": "place",
        }
        confidence = calculate_confidence(result)
        assert confidence >= 0.8

    def test_confidence_clamped_to_bounds(self) -> None:
        """Confidence should be clamped between 0.0 and 1.0."""
        # Very high scores
        result = {
            "importance": 1.0,
            "boundingbox": ["5.55", "5.551", "-0.20", "-0.199"],  # Tiny bbox
            "type": "village",
            "class": "place",
        }
        confidence = calculate_confidence(result)
        assert confidence <= 1.0

        # Very low scores
        low_result = {
            "importance": 0.0,
            "type": "country",
            "class": "boundary",
        }
        low_confidence = calculate_confidence(low_result)
        assert low_confidence >= 0.0


class TestClarificationLogic:
    """Tests for clarification decision logic."""

    def test_should_clarify_low_confidence(self) -> None:
        """Should ask for clarification when confidence is low."""
        response = GeocodingResponse(
            success=True,
            results=[
                GeocodingResult(
                    place_name="Assin",
                    latitude=5.5,
                    longitude=-0.5,
                    confidence=0.5,  # Below threshold
                    place_type="administrative",
                    original_query="Assin",
                    display_name="Assin, Ghana",
                )
            ],
            best_match=GeocodingResult(
                place_name="Assin",
                latitude=5.5,
                longitude=-0.5,
                confidence=0.5,
                place_type="administrative",
                original_query="Assin",
                display_name="Assin, Ghana",
            ),
        )
        assert should_ask_clarification(response) is True

    def test_should_not_clarify_high_confidence(self) -> None:
        """Should not ask for clarification when confidence is high."""
        response = GeocodingResponse(
            success=True,
            results=[
                GeocodingResult(
                    place_name="Tema",
                    latitude=5.67,
                    longitude=0.0,
                    confidence=0.9,  # Above threshold
                    place_type="city",
                    original_query="Tema",
                    display_name="Tema, Ghana",
                )
            ],
            best_match=GeocodingResult(
                place_name="Tema",
                latitude=5.67,
                longitude=0.0,
                confidence=0.9,
                place_type="city",
                original_query="Tema",
                display_name="Tema, Ghana",
            ),
        )
        assert should_ask_clarification(response) is False

    def test_should_clarify_multiple_similar_results(self) -> None:
        """Should ask for clarification when multiple results have similar confidence."""
        response = GeocodingResponse(
            success=True,
            results=[
                GeocodingResult(
                    place_name="Assin Fosu",
                    latitude=5.5,
                    longitude=-0.5,
                    confidence=0.75,
                    place_type="town",
                    original_query="Assin",
                    display_name="Assin Fosu, Central Region, Ghana",
                ),
                GeocodingResult(
                    place_name="Assin North",
                    latitude=5.6,
                    longitude=-0.4,
                    confidence=0.72,  # Similar confidence
                    place_type="administrative",
                    original_query="Assin",
                    display_name="Assin North District, Ghana",
                ),
            ],
            best_match=GeocodingResult(
                place_name="Assin Fosu",
                latitude=5.5,
                longitude=-0.5,
                confidence=0.75,
                place_type="town",
                original_query="Assin",
                display_name="Assin Fosu, Central Region, Ghana",
            ),
        )
        assert should_ask_clarification(response) is True


class TestClarificationFormatting:
    """Tests for clarification question formatting."""

    def test_format_empty_results(self) -> None:
        """Should format message for empty results."""
        response = GeocodingResponse(success=False, results=[])
        message = format_clarification_question(response)
        assert "couldn't find" in message.lower()
        assert "location" in message.lower()

    def test_format_multiple_results(self) -> None:
        """Should format numbered list for multiple results."""
        response = GeocodingResponse(
            success=True,
            results=[
                GeocodingResult(
                    place_name="Assin Fosu",
                    latitude=5.5,
                    longitude=-0.5,
                    confidence=0.75,
                    place_type="town",
                    original_query="Assin",
                    display_name="Assin Fosu, Central Region, Ghana",
                ),
                GeocodingResult(
                    place_name="Assin North",
                    latitude=5.6,
                    longitude=-0.4,
                    confidence=0.72,
                    place_type="administrative",
                    original_query="Assin",
                    display_name="Assin North District, Central Region, Ghana",
                ),
            ],
        )
        message = format_clarification_question(response)
        assert "1." in message
        assert "2." in message
        assert "Assin Fosu" in message
        assert "which one" in message.lower()


class TestGeocodeLocation:
    """Tests for geocode_location function."""

    @pytest.mark.asyncio
    @patch("app.services.geocoding.get_http_client")
    async def test_geocode_location_success(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return geocoded location on success."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "lat": "5.6037",
                "lon": "-0.1870",
                "name": "Accra",
                "importance": 0.8,
                "type": "city",
                "class": "place",
                "boundingbox": ["5.5", "5.7", "-0.3", "-0.1"],
                "display_name": "Accra, Greater Accra, Ghana",
                "address": {"city": "Accra", "state": "Greater Accra", "country": "Ghana"},
            }
        ]
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        # Clear cache to ensure fresh request
        from app.services.geocoding import _geocoding_cache
        _geocoding_cache.clear()

        result = await geocode_location("Accra")

        assert result.success is True
        assert result.best_match is not None
        assert result.best_match.latitude == 5.6037
        assert result.best_match.longitude == -0.1870

    @pytest.mark.asyncio
    @patch("app.services.geocoding.get_http_client")
    async def test_geocode_location_not_found(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return error when location not found."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # Empty results
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        # Clear cache
        from app.services.geocoding import _geocoding_cache
        _geocoding_cache.clear()

        result = await geocode_location("XYZNonexistentPlace123")

        assert result.success is False
        assert "couldn't find" in result.error_message.lower()

    @pytest.mark.asyncio
    @patch("app.services.geocoding.get_http_client")
    async def test_geocode_location_api_error(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should handle API errors gracefully."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        # Clear cache
        from app.services.geocoding import _geocoding_cache
        _geocoding_cache.clear()

        result = await geocode_location("Accra")

        assert result.success is False
        assert "unavailable" in result.error_message.lower()

    @pytest.mark.asyncio
    @patch("app.services.geocoding.get_http_client")
    async def test_geocode_location_timeout(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should handle timeout gracefully."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_get_client.return_value = mock_client

        # Clear cache
        from app.services.geocoding import _geocoding_cache
        _geocoding_cache.clear()

        result = await geocode_location("Accra")

        assert result.success is False
        assert "too long" in result.error_message.lower()


class TestReverseGeocode:
    """Tests for reverse_geocode function."""

    @pytest.mark.asyncio
    @patch("app.services.geocoding.get_http_client")
    async def test_reverse_geocode_success(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return place name on success."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "display_name": "Tema, Greater Accra, Ghana",
            "address": {
                "city": "Tema",
                "state": "Greater Accra",
                "country": "Ghana",
            },
        }
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        # Clear cache
        from app.services.geocoding import _geocoding_cache
        _geocoding_cache.clear()

        result = await reverse_geocode(5.67, 0.0)

        assert result is not None
        assert "Tema" in result

    @pytest.mark.asyncio
    @patch("app.services.geocoding.get_http_client")
    async def test_reverse_geocode_error(
        self,
        mock_get_client: MagicMock,
    ) -> None:
        """Should return None on error."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_client.return_value = mock_client

        # Clear cache
        from app.services.geocoding import _geocoding_cache
        _geocoding_cache.clear()

        result = await reverse_geocode(5.67, 0.0)

        assert result is None
