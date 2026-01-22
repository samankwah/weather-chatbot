"""Tests for AI service (intent extraction and response generation)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.ai_schemas import (
    IntentExtraction,
    QueryType,
    TimeReference,
    UserContext,
)
from app.models.schemas import WeatherData
from app.services.ai import GroqProvider, get_ai_provider


class TestFallbackIntentExtraction:
    """Tests for keyword-based fallback intent extraction."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.provider = GroqProvider()
        self.provider.ai_enabled = False  # Force fallback mode

    def test_extract_weather_intent(self) -> None:
        """Should extract weather intent from message."""
        intent = self.provider._fallback_intent_extraction("What's the weather?")
        assert intent.query_type == QueryType.WEATHER

    def test_extract_forecast_intent_tomorrow(self) -> None:
        """Should extract forecast intent for tomorrow."""
        intent = self.provider._fallback_intent_extraction(
            "What's the forecast for tomorrow?"
        )
        assert intent.query_type == QueryType.FORECAST
        assert intent.time_reference.days_ahead == 1

    def test_extract_forecast_intent_next_week(self) -> None:
        """Should extract forecast intent for next week."""
        intent = self.provider._fallback_intent_extraction("forecast next week")
        assert intent.query_type == QueryType.FORECAST
        assert intent.time_reference.days_ahead == 7

    def test_extract_greeting_intent(self) -> None:
        """Should extract greeting intent."""
        intent = self.provider._fallback_intent_extraction("hello")
        assert intent.query_type == QueryType.GREETING

        intent = self.provider._fallback_intent_extraction("hi")
        assert intent.query_type == QueryType.GREETING

        intent = self.provider._fallback_intent_extraction("good morning")
        assert intent.query_type == QueryType.GREETING

    def test_extract_help_intent(self) -> None:
        """Should extract help intent."""
        intent = self.provider._fallback_intent_extraction("help")
        assert intent.query_type == QueryType.HELP

        intent = self.provider._fallback_intent_extraction("how do I use this?")
        assert intent.query_type == QueryType.HELP

    def test_extract_eto_intent(self) -> None:
        """Should extract ETO intent."""
        intent = self.provider._fallback_intent_extraction("What is the ETO today?")
        assert intent.query_type == QueryType.ETO

        intent = self.provider._fallback_intent_extraction("evapotranspiration rate")
        assert intent.query_type == QueryType.ETO

    def test_extract_gdd_intent(self) -> None:
        """Should extract GDD intent."""
        intent = self.provider._fallback_intent_extraction("What's the GDD for maize?")
        assert intent.query_type == QueryType.GDD

        intent = self.provider._fallback_intent_extraction("degree days for my crop")
        assert intent.query_type == QueryType.GDD

    def test_extract_soil_intent(self) -> None:
        """Should extract soil moisture intent."""
        intent = self.provider._fallback_intent_extraction("soil moisture level")
        assert intent.query_type == QueryType.SOIL

    def test_extract_seasonal_onset_intent(self) -> None:
        """Should extract seasonal onset intent."""
        intent = self.provider._fallback_intent_extraction(
            "When does the rainy season start?"
        )
        assert intent.query_type == QueryType.SEASONAL_ONSET

        intent = self.provider._fallback_intent_extraction("onset date")
        assert intent.query_type == QueryType.SEASONAL_ONSET

    def test_extract_seasonal_cessation_intent(self) -> None:
        """Should extract seasonal cessation intent."""
        intent = self.provider._fallback_intent_extraction("When does rain end?")
        assert intent.query_type == QueryType.SEASONAL_CESSATION

        intent = self.provider._fallback_intent_extraction("cessation date")
        assert intent.query_type == QueryType.SEASONAL_CESSATION

    def test_extract_dry_spell_intent(self) -> None:
        """Should extract dry spell intent."""
        intent = self.provider._fallback_intent_extraction("dry spell forecast")
        assert intent.query_type == QueryType.DRY_SPELL

        intent = self.provider._fallback_intent_extraction("drought risk")
        assert intent.query_type == QueryType.DRY_SPELL

    def test_extract_crop_advice_intent(self) -> None:
        """Should extract crop advice intent."""
        intent = self.provider._fallback_intent_extraction("When should I plant maize?")
        assert intent.query_type == QueryType.CROP_ADVICE


class TestCityExtraction:
    """Tests for city name extraction."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.provider = GroqProvider()
        self.provider.ai_enabled = False

    def test_extract_known_ghana_city(self) -> None:
        """Should extract known Ghana cities."""
        city = self.provider._extract_city_fallback("weather in Kumasi")
        assert city == "Kumasi"

        city = self.provider._extract_city_fallback("temperature in Tamale")
        assert city == "Tamale"

    def test_extract_city_with_preposition(self) -> None:
        """Should extract city after preposition."""
        city = self.provider._extract_city_fallback("weather for Accra")
        assert city == "Accra"

        city = self.provider._extract_city_fallback("forecast at Cape Coast")
        assert city == "Cape Coast"

    def test_extract_lowercase_city(self) -> None:
        """Should handle lowercase city names."""
        city = self.provider._extract_city_fallback("weather in accra")
        assert city == "Accra"

    def test_no_city_in_message(self) -> None:
        """Should return None when no city found."""
        city = self.provider._extract_city_fallback("what's the weather?")
        assert city is None


class TestCropExtraction:
    """Tests for crop name extraction."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.provider = GroqProvider()
        self.provider.ai_enabled = False

    def test_extract_maize(self) -> None:
        """Should extract maize crop."""
        crop = self.provider._extract_crop_fallback("GDD for maize")
        assert crop == "maize"

    def test_extract_corn_as_maize(self) -> None:
        """Should normalize corn to maize."""
        crop = self.provider._extract_crop_fallback("GDD for corn")
        assert crop == "maize"

    def test_extract_rice(self) -> None:
        """Should extract rice crop."""
        crop = self.provider._extract_crop_fallback("advice for rice farming")
        assert crop == "rice"

    def test_extract_cassava(self) -> None:
        """Should extract cassava crop."""
        crop = self.provider._extract_crop_fallback("planting cassava")
        assert crop == "cassava"

    def test_no_crop_in_message(self) -> None:
        """Should return None when no crop found."""
        crop = self.provider._extract_crop_fallback("what's the weather?")
        assert crop is None


class TestTimeReferenceExtraction:
    """Tests for time reference extraction."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.provider = GroqProvider()
        self.provider.ai_enabled = False

    def test_extract_today(self) -> None:
        """Should extract today reference."""
        time_ref = self.provider._extract_time_fallback("weather today")
        assert time_ref.reference == "today"
        assert time_ref.days_ahead == 0

    def test_extract_tomorrow(self) -> None:
        """Should extract tomorrow reference."""
        time_ref = self.provider._extract_time_fallback("forecast tomorrow")
        assert time_ref.reference == "tomorrow"
        assert time_ref.days_ahead == 1

    def test_extract_this_week(self) -> None:
        """Should extract this week reference."""
        time_ref = self.provider._extract_time_fallback("forecast this week")
        assert time_ref.reference == "this_week"
        assert time_ref.days_ahead == 3

    def test_extract_next_week(self) -> None:
        """Should extract next week reference."""
        time_ref = self.provider._extract_time_fallback("weather next week")
        assert time_ref.reference == "next_week"
        assert time_ref.days_ahead == 7

    def test_default_to_now(self) -> None:
        """Should default to now when no time reference."""
        time_ref = self.provider._extract_time_fallback("weather in Accra")
        assert time_ref.reference == "now"
        assert time_ref.days_ahead == 0


class TestUserContextIntegration:
    """Tests for intent extraction with user context."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.provider = GroqProvider()
        self.provider.ai_enabled = False

    def test_uses_context_city_when_not_in_message(self) -> None:
        """Should use context city when not specified in message."""
        context = UserContext(user_id="test", last_city="Kumasi")
        intent = self.provider._fallback_intent_extraction("what's the weather?", context)
        assert intent.city == "Kumasi"

    def test_uses_context_crop_when_not_in_message(self) -> None:
        """Should use context crop when not specified in message."""
        context = UserContext(user_id="test", preferred_crop="rice")
        intent = self.provider._fallback_intent_extraction("GDD calculation", context)
        assert intent.crop == "rice"

    def test_message_city_overrides_context(self) -> None:
        """Message city should override context city."""
        context = UserContext(user_id="test", last_city="Kumasi")
        intent = self.provider._fallback_intent_extraction(
            "weather in Tamale", context
        )
        assert intent.city == "Tamale"


class TestTemplateResponseGeneration:
    """Tests for template-based response generation."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.provider = GroqProvider()
        self.provider.ai_enabled = False

    def test_generate_greeting_response(self) -> None:
        """Should generate greeting response."""
        intent = IntentExtraction(
            query_type=QueryType.GREETING, raw_message="hello"
        )
        response = self.provider._generate_template_response(intent)
        assert "assistant" in response.lower() or "help" in response.lower()

    def test_generate_help_response(self) -> None:
        """Should generate help response."""
        intent = IntentExtraction(query_type=QueryType.HELP, raw_message="help")
        response = self.provider._generate_template_response(intent)
        assert "weather" in response.lower()

    def test_generate_weather_response(self) -> None:
        """Should generate weather response with data."""
        intent = IntentExtraction(
            query_type=QueryType.WEATHER,
            city="Accra",
            raw_message="weather in Accra",
        )
        weather_data = WeatherData(
            city="Accra",
            country="GH",
            temperature=30.5,
            feels_like=32.0,
            humidity=75,
            description="scattered clouds",
            wind_speed=5.5,
            icon="03d",
        )
        response = self.provider._generate_template_response(
            intent, weather_data=weather_data
        )
        assert "Accra" in response
        assert "30.5" in response
        assert "75" in response

    def test_generate_fallback_response(self) -> None:
        """Should generate fallback response when no data."""
        intent = IntentExtraction(
            query_type=QueryType.WEATHER, raw_message="weather"
        )
        response = self.provider._generate_template_response(intent)
        assert "couldn't" in response.lower() or "try" in response.lower()


class TestTwiRegionDetection:
    """Tests for Twi-speaking region detection."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.provider = GroqProvider()

    def test_accra_is_twi_region(self) -> None:
        """Accra should be in Twi region."""
        assert self.provider._is_twi_region("Accra") is True
        assert self.provider._is_twi_region("accra") is True

    def test_kumasi_is_twi_region(self) -> None:
        """Kumasi should be in Twi region."""
        assert self.provider._is_twi_region("Kumasi") is True

    def test_tamale_is_not_twi_region(self) -> None:
        """Tamale should not be in Twi region."""
        assert self.provider._is_twi_region("Tamale") is False

    def test_none_defaults_to_twi(self) -> None:
        """None should default to Twi region."""
        assert self.provider._is_twi_region(None) is True

    def test_get_greeting_twi_region(self) -> None:
        """Should get Twi greeting for Twi region."""
        greeting = self.provider._get_greeting("Accra")
        assert greeting == "How far!"

    def test_get_greeting_non_twi_region(self) -> None:
        """Should get standard greeting for non-Twi region."""
        greeting = self.provider._get_greeting("Tamale")
        assert greeting == "Hello!"


class TestWeatherIconSelection:
    """Tests for weather icon selection."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.provider = GroqProvider()

    def test_rain_icon(self) -> None:
        """Should return rain icon for rain description."""
        assert self.provider._get_weather_icon("light rain") == "🌧️"
        assert self.provider._get_weather_icon("heavy drizzle") == "🌧️"

    def test_cloud_icon(self) -> None:
        """Should return cloud icon for cloudy description."""
        assert self.provider._get_weather_icon("scattered clouds") == "⛅"
        assert self.provider._get_weather_icon("overcast") == "⛅"

    def test_sun_icon(self) -> None:
        """Should return sun icon for clear description."""
        assert self.provider._get_weather_icon("clear sky") == "☀️"
        assert self.provider._get_weather_icon("sunny") == "☀️"

    def test_storm_icon(self) -> None:
        """Should return storm icon for storm description."""
        assert self.provider._get_weather_icon("thunderstorm") == "⛈️"

    def test_default_cloud_icon(self) -> None:
        """Should default to cloud icon."""
        assert self.provider._get_weather_icon("unknown") == "⛅"


class TestAIProviderSingleton:
    """Tests for AI provider singleton."""

    def test_get_ai_provider_returns_instance(self) -> None:
        """Should return GroqProvider instance."""
        provider = get_ai_provider()
        assert isinstance(provider, GroqProvider)

    def test_get_ai_provider_returns_same_instance(self) -> None:
        """Should return same instance on multiple calls."""
        provider1 = get_ai_provider()
        provider2 = get_ai_provider()
        assert provider1 is provider2
