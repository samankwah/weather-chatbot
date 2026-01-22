"""Tests for webhook endpoint."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.ai_schemas import IntentExtraction, QueryType, UserContext
from app.models.schemas import WeatherData, WeatherResponse
from app.services.weather import parse_weather_response


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check_returns_healthy(self, client: TestClient) -> None:
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data

    def test_root_endpoint(self, client: TestClient) -> None:
        """Root endpoint should return API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "Weather Chatbot API" in data["message"]
        assert "docs" in data
        assert "health" in data


class TestWeatherResponseParsing:
    """Tests for weather API response parsing."""

    def test_parse_weather_response(self, sample_weather_api_response: dict) -> None:
        """Should correctly parse OpenWeatherMap response."""
        result = parse_weather_response(sample_weather_api_response)

        assert result.city == "Accra"
        assert result.country == "GH"
        assert result.temperature == 28.5
        assert result.feels_like == 30.2
        assert result.humidity == 75
        assert result.description == "scattered clouds"
        assert result.wind_speed == 12.5
        assert result.icon == "03d"

    def test_parse_weather_response_with_different_data(self) -> None:
        """Should parse weather response with different values."""
        mock_response = {
            "name": "Kumasi",
            "sys": {"country": "GH"},
            "main": {"temp": 25.0, "feels_like": 27.5, "humidity": 80},
            "weather": [{"description": "light rain", "icon": "10d"}],
            "wind": {"speed": 8.0},
        }

        result = parse_weather_response(mock_response)

        assert result.city == "Kumasi"
        assert result.temperature == 25.0
        assert result.description == "light rain"


class TestWebhookValidation:
    """Tests for webhook request validation."""

    def test_webhook_missing_signature_returns_400(
        self, client: TestClient, sample_twilio_webhook_data: dict
    ) -> None:
        """Webhook should return 400 for missing Twilio signature."""
        response = client.post(
            "/webhook",
            data=sample_twilio_webhook_data,
        )
        assert response.status_code == 400
        assert "signature" in response.json()["detail"].lower()

    def test_webhook_invalid_signature_returns_403(
        self, client: TestClient, sample_twilio_webhook_data: dict
    ) -> None:
        """Webhook should return 403 for invalid Twilio signature."""
        response = client.post(
            "/webhook",
            data=sample_twilio_webhook_data,
            headers={"X-Twilio-Signature": "invalid_signature"},
        )
        assert response.status_code == 403
        assert "invalid" in response.json()["detail"].lower()


class TestWebhookProcessing:
    """Tests for webhook message processing."""

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.get_memory_store")
    @patch("app.routes.webhook.get_ai_provider")
    @patch("app.routes.webhook.get_messaging_provider")
    @patch("app.routes.webhook.get_weather")
    async def test_webhook_processes_weather_request(
        self,
        mock_get_weather: MagicMock,
        mock_get_messaging: MagicMock,
        mock_get_ai: MagicMock,
        mock_get_memory: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_weather_data: WeatherData,
        mock_memory_store: MagicMock,
        mock_ai_provider: AsyncMock,
        mock_messaging_provider: MagicMock,
    ) -> None:
        """Webhook should process weather request and send response."""
        mock_validate.return_value = True
        mock_get_memory.return_value = mock_memory_store
        mock_get_ai.return_value = mock_ai_provider
        mock_get_messaging.return_value = mock_messaging_provider
        mock_get_weather.return_value = WeatherResponse(
            success=True, data=sample_weather_data
        )

        response = client.post(
            "/webhook",
            data={
                "Body": "What's the weather in Accra?",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM12345678901234567890123456789012",
                "AccountSid": "ACtest123456789",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.get_memory_store")
    @patch("app.routes.webhook.get_ai_provider")
    @patch("app.routes.webhook.get_messaging_provider")
    async def test_webhook_handles_greeting(
        self,
        mock_get_messaging: MagicMock,
        mock_get_ai: MagicMock,
        mock_get_memory: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        mock_memory_store: MagicMock,
        mock_messaging_provider: MagicMock,
    ) -> None:
        """Webhook should handle greeting message."""
        mock_validate.return_value = True
        mock_get_memory.return_value = mock_memory_store
        mock_get_messaging.return_value = mock_messaging_provider

        ai_provider = AsyncMock()
        ai_provider.extract_intent = AsyncMock(
            return_value=IntentExtraction(
                query_type=QueryType.GREETING,
                confidence=0.95,
                raw_message="hello",
            )
        )
        ai_provider.generate_response = AsyncMock(
            return_value="Hello! How can I help you today?"
        )
        mock_get_ai.return_value = ai_provider

        response = client.post(
            "/webhook",
            data={
                "Body": "hello",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM12345678901234567890123456789012",
                "AccountSid": "ACtest123456789",
            },
        )

        assert response.status_code == 200
        mock_messaging_provider.send_message.assert_called_once()

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.get_memory_store")
    @patch("app.routes.webhook.get_ai_provider")
    @patch("app.routes.webhook.get_messaging_provider")
    async def test_webhook_handles_help_request(
        self,
        mock_get_messaging: MagicMock,
        mock_get_ai: MagicMock,
        mock_get_memory: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        mock_memory_store: MagicMock,
        mock_messaging_provider: MagicMock,
    ) -> None:
        """Webhook should handle help message."""
        mock_validate.return_value = True
        mock_get_memory.return_value = mock_memory_store
        mock_get_messaging.return_value = mock_messaging_provider

        ai_provider = AsyncMock()
        ai_provider.extract_intent = AsyncMock(
            return_value=IntentExtraction(
                query_type=QueryType.HELP,
                confidence=0.95,
                raw_message="help",
            )
        )
        ai_provider.generate_response = AsyncMock(
            return_value="Here's how to use the bot..."
        )
        mock_get_ai.return_value = ai_provider

        response = client.post(
            "/webhook",
            data={
                "Body": "help",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM12345678901234567890123456789012",
                "AccountSid": "ACtest123456789",
            },
        )

        assert response.status_code == 200


class TestWebhookGPSCoordinates:
    """Tests for webhook GPS coordinate handling."""

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.get_memory_store")
    @patch("app.routes.webhook.get_ai_provider")
    @patch("app.routes.webhook.get_messaging_provider")
    @patch("app.routes.webhook.get_weather_by_coordinates")
    async def test_webhook_handles_gps_location(
        self,
        mock_get_weather_coords: MagicMock,
        mock_get_messaging: MagicMock,
        mock_get_ai: MagicMock,
        mock_get_memory: MagicMock,
        mock_validate: AsyncMock,
        client: TestClient,
        sample_weather_data: WeatherData,
        mock_memory_store: MagicMock,
        mock_ai_provider: AsyncMock,
        mock_messaging_provider: MagicMock,
    ) -> None:
        """Webhook should handle GPS location share."""
        mock_validate.return_value = True
        mock_get_memory.return_value = mock_memory_store
        mock_get_ai.return_value = mock_ai_provider
        mock_get_messaging.return_value = mock_messaging_provider
        mock_get_weather_coords.return_value = WeatherResponse(
            success=True, data=sample_weather_data
        )

        response = client.post(
            "/webhook",
            data={
                "Body": "",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM12345678901234567890123456789012",
                "AccountSid": "ACtest123456789",
                "Latitude": "5.6037",
                "Longitude": "-0.1870",
            },
        )

        assert response.status_code == 200

    def test_webhook_parses_invalid_coordinates_gracefully(
        self, client: TestClient
    ) -> None:
        """Webhook should handle invalid coordinates gracefully."""
        with patch("app.routes.webhook.validate_twilio_request") as mock_validate:
            mock_validate.return_value = True

            with patch("app.routes.webhook.process_message") as mock_process:
                mock_process.return_value = "Weather info"

                with patch(
                    "app.routes.webhook.get_messaging_provider"
                ) as mock_provider:
                    provider = MagicMock()
                    provider.send_message.return_value = True
                    mock_provider.return_value = provider

                    response = client.post(
                        "/webhook",
                        data={
                            "Body": "weather",
                            "From": "whatsapp:+233123456789",
                            "To": "whatsapp:+14155238886",
                            "MessageSid": "SM12345678901234567890123456789012",
                            "AccountSid": "ACtest123456789",
                            "Latitude": "invalid",
                            "Longitude": "also_invalid",
                        },
                    )

                    assert response.status_code == 200


class TestWebhookMessageSending:
    """Tests for webhook message sending."""

    @patch("app.routes.webhook.validate_twilio_request")
    @patch("app.routes.webhook.process_message")
    @patch("app.routes.webhook.get_messaging_provider")
    async def test_webhook_returns_failure_when_send_fails(
        self,
        mock_get_messaging: MagicMock,
        mock_process: AsyncMock,
        mock_validate: AsyncMock,
        client: TestClient,
    ) -> None:
        """Webhook should return failure when message send fails."""
        mock_validate.return_value = True
        mock_process.return_value = "Weather response"

        provider = MagicMock()
        provider.send_message.return_value = False
        mock_get_messaging.return_value = provider

        response = client.post(
            "/webhook",
            data={
                "Body": "weather",
                "From": "whatsapp:+233123456789",
                "To": "whatsapp:+14155238886",
                "MessageSid": "SM12345678901234567890123456789012",
                "AccountSid": "ACtest123456789",
            },
        )

        assert response.status_code == 200
        assert response.json()["success"] is False
        assert "failed" in response.json()["message"].lower()
