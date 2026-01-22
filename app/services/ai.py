"""AI service with Groq integration for NLU and response generation."""

import json
import logging
from typing import Protocol

from groq import AsyncGroq

from app.config import get_settings
from app.models.ai_schemas import (
    AIResponse,
    AgroMetData,
    ForecastData,
    GDDData,
    IntentExtraction,
    QueryType,
    SeasonalForecast,
    SeasonalOutlook,
    TimeReference,
    UserContext,
)
from app.models.schemas import WeatherData

logger = logging.getLogger(__name__)


class AIProvider(Protocol):
    """Protocol for AI providers."""

    async def extract_intent(
        self,
        message: str,
        user_context: UserContext | None = None,
    ) -> IntentExtraction:
        """Extract intent from user message."""
        ...

    async def generate_response(
        self,
        intent: IntentExtraction,
        weather_data: WeatherData | None = None,
        forecast_data: ForecastData | None = None,
        agromet_data: AgroMetData | None = None,
        gdd_data: GDDData | None = None,
        seasonal_data: SeasonalOutlook | None = None,
        user_context: UserContext | None = None,
    ) -> str:
        """Generate a friendly response based on data."""
        ...


INTENT_EXTRACTION_PROMPT = """You are a parser for a Ghanaian agricultural weather chatbot.
Extract structured JSON from user messages.

Query types:
- "weather": current conditions (default for general weather queries)
- "forecast": future weather (hours/days ahead)
- "eto": evapotranspiration query
- "gdd": growing degree days
- "soil": soil moisture
- "seasonal": 3-6 month outlook
- "seasonal_onset": when rainy season starts, onset, beginning of rains
- "seasonal_cessation": when rains end, cessation, end of season
- "dry_spell": dry spell, dry period, drought risk
- "season_length": how long is rainy season, season duration
- "crop_advice": planting/farming advice
- "dekadal": 10-day bulletin
- "help": user needs help/instructions
- "greeting": casual greeting (hi, hello, etc.)

Common Ghana crops: maize, rice, cassava, cocoa, tomato, pepper, yam, groundnut, sorghum, millet, plantain, cowpea

Common Ghana cities: Accra, Kumasi, Tamale, Takoradi, Cape Coast, Sunyani, Ho, Koforidua, Tema, Wa, Bolgatanga

Time references:
- "now"/"today" -> days_ahead: 0
- "tomorrow" -> days_ahead: 1
- "this week" -> days_ahead: 3
- "next week" -> days_ahead: 7

Output ONLY valid JSON (no markdown, no explanation):
{
  "city": "city name or null",
  "query_type": "weather|forecast|eto|gdd|soil|seasonal|seasonal_onset|seasonal_cessation|dry_spell|season_length|crop_advice|dekadal|help|greeting",
  "crop": "crop name or null",
  "time_reference": {"reference": "now|today|tomorrow|this_week", "days_ahead": 0},
  "confidence": 0.8
}

User message: """

RESPONSE_GENERATION_PROMPT = """You are a Ghanaian agricultural weather assistant. Be concise and professional.

CRITICAL RULES:
- Keep responses under 80 words maximum
- Use ONE greeting max (not multiple)
- ALWAYS use these emojis: 🌡️ temp, 💧 humidity/ETO, 💨 wind, ☀️ sunny, ⛅ cloudy, 🌧️ rain, 🌱 crops/GDD, 🪴 soil
- Format data with emojis on separate lines
- Give 1-2 practical tips max, not paragraphs

Example weather format:
☀️ Sunyani weather:
🌡️ 33°C (feels 35°C)
⛅ Overcast clouds
💧 65%  💨 8 km/h

💡 Good for field work!

Context:
{context}

Generate a SHORT response with emojis:"""


class GroqProvider:
    """Groq AI provider using Llama 3.1."""

    # Twi-speaking cities in Ghana (Greater Accra, Ashanti, Central, Eastern, Western)
    TWI_SPEAKING_CITIES = {
        "accra", "tema", "kumasi", "obuasi", "cape coast",
        "koforidua", "takoradi", "sekondi", "sunyani", "nkawkaw",
        "tarkwa", "winneba", "saltpond", "swedru", "techiman"
    }

    def __init__(self) -> None:
        """Initialize Groq client if API key is available."""
        settings = get_settings()
        self.client: AsyncGroq | None = None
        self.ai_enabled = False
        if settings.groq_api_key:
            self.client = AsyncGroq(api_key=settings.groq_api_key)
            self.ai_enabled = True
        self.model = settings.groq_model
        self.timeout = settings.groq_timeout

    def _is_twi_region(self, city: str | None) -> bool:
        """Check if city is in a Twi-speaking region."""
        if not city:
            return True  # Default to Twi for Accra default
        return city.lower() in self.TWI_SPEAKING_CITIES

    def _get_greeting(self, city: str | None) -> str:
        """Get region-appropriate greeting."""
        if self._is_twi_region(city):
            return "How far!"
        return "Hello!"

    def _get_weather_intro(self, city: str | None) -> str:
        """Get region-appropriate weather intro."""
        if self._is_twi_region(city):
            return "Chale! "
        return ""

    async def extract_intent(
        self,
        message: str,
        user_context: UserContext | None = None,
    ) -> IntentExtraction:
        """
        Extract intent from user message using Groq.

        Args:
            message: User's message text.
            user_context: Optional user context for defaults.

        Returns:
            IntentExtraction with parsed data.
        """
        if not self.ai_enabled:
            return self._fallback_intent_extraction(message, user_context)

        try:
            prompt = INTENT_EXTRACTION_PROMPT + f'"{message}"'

            if user_context:
                context_hint = f"\nUser's last location: {user_context.last_city or 'unknown'}"
                if user_context.preferred_crop:
                    context_hint += f", preferred crop: {user_context.preferred_crop}"
                prompt += context_hint

            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.1,
                max_tokens=200,
                timeout=self.timeout,
            )

            response_text = chat_completion.choices[0].message.content.strip()
            return self._parse_intent_response(response_text, message, user_context)

        except Exception as e:
            logger.warning(f"Groq intent extraction failed: {e}, falling back to keyword parsing")
            return self._fallback_intent_extraction(message, user_context)

    def _parse_intent_response(
        self,
        response_text: str,
        original_message: str,
        user_context: UserContext | None = None,
    ) -> IntentExtraction:
        """Parse JSON response from Groq."""
        try:
            # Clean up response if it has markdown code blocks
            if "```" in response_text:
                start = response_text.find("{")
                end = response_text.rfind("}") + 1
                response_text = response_text[start:end]

            data = json.loads(response_text)

            time_ref = data.get("time_reference", {})
            if isinstance(time_ref, str):
                time_ref = {"reference": time_ref, "days_ahead": 0}

            intent = IntentExtraction(
                city=data.get("city"),
                query_type=QueryType(data.get("query_type", "weather")),
                crop=data.get("crop"),
                time_reference=TimeReference(
                    reference=time_ref.get("reference", "now"),
                    days_ahead=time_ref.get("days_ahead", 0),
                ),
                confidence=data.get("confidence", 0.8),
                raw_message=original_message,
            )

            # Use user context defaults if city not specified
            if not intent.city and user_context and user_context.last_city:
                intent.city = user_context.last_city

            if not intent.crop and user_context and user_context.preferred_crop:
                intent.crop = user_context.preferred_crop

            return intent

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse intent JSON: {e}")
            return self._fallback_intent_extraction(original_message, user_context)

    def _fallback_intent_extraction(
        self,
        message: str,
        user_context: UserContext | None = None,
    ) -> IntentExtraction:
        """Fallback keyword-based intent extraction."""
        message_lower = message.lower().strip()

        # Determine query type
        query_type = QueryType.WEATHER
        if any(word in message_lower for word in ["help", "how do i", "how to", "what can"]):
            query_type = QueryType.HELP
        elif any(word in message_lower for word in [" hi ", " hi,", "hi!", "hello", "hey ", "good morning", "good evening"]):
            query_type = QueryType.GREETING
        elif message_lower.strip() == "hi":
            query_type = QueryType.GREETING
        elif any(word in message_lower for word in ["eto", "evapotranspiration", "evaporation"]):
            query_type = QueryType.ETO
        elif any(word in message_lower for word in ["gdd", "degree day", "growth stage"]):
            query_type = QueryType.GDD
        elif any(word in message_lower for word in ["soil", "moisture"]):
            query_type = QueryType.SOIL
        elif any(word in message_lower for word in ["onset", "start of rain", "when does rain start", "beginning of rain", "rainy season start"]):
            query_type = QueryType.SEASONAL_ONSET
        elif any(word in message_lower for word in ["cessation", "end of rain", "when does rain end", "rain stop", "rainy season end"]):
            query_type = QueryType.SEASONAL_CESSATION
        elif any(word in message_lower for word in ["dry spell", "dry period", "drought"]):
            query_type = QueryType.DRY_SPELL
        elif any(word in message_lower for word in ["season length", "how long", "duration of rain", "season duration"]):
            query_type = QueryType.SEASON_LENGTH
        elif any(word in message_lower for word in ["seasonal", "outlook", "3 month", "6 month"]):
            query_type = QueryType.SEASONAL
        elif any(word in message_lower for word in ["advice", "plant", "when to", "should i"]):
            query_type = QueryType.CROP_ADVICE
        elif any(word in message_lower for word in ["dekadal", "bulletin", "10-day", "10 day"]):
            query_type = QueryType.DEKADAL
        elif any(word in message_lower for word in ["forecast", "tomorrow", "next week", "this week"]):
            query_type = QueryType.FORECAST

        # Extract city
        city = self._extract_city_fallback(message)
        if not city and user_context and user_context.last_city:
            city = user_context.last_city

        # Extract crop
        crop = self._extract_crop_fallback(message)
        if not crop and user_context and user_context.preferred_crop:
            crop = user_context.preferred_crop

        # Extract time reference
        time_ref = self._extract_time_fallback(message)

        return IntentExtraction(
            city=city,
            query_type=query_type,
            crop=crop,
            time_reference=time_ref,
            confidence=0.6,
            raw_message=message,
        )

    def _extract_city_fallback(self, message: str) -> str | None:
        """Extract city from message using keywords."""
        message_lower = message.lower()
        ghana_cities = [
            "accra", "kumasi", "tamale", "takoradi", "cape coast",
            "sunyani", "ho", "koforidua", "tema", "wa", "bolgatanga",
            "sekondi", "tarkwa", "obuasi", "techiman", "nkawkaw"
        ]

        for city in ghana_cities:
            if city in message_lower:
                return city.title()

        # Try to extract after prepositions
        prepositions = ["in", "for", "at"]
        for prep in prepositions:
            pattern = f"{prep} "
            if pattern in message_lower:
                start = message_lower.find(pattern) + len(pattern)
                remaining = message[start:].strip()
                words = remaining.split()
                if words:
                    return words[0].strip("?,.")

        return None

    def _extract_crop_fallback(self, message: str) -> str | None:
        """Extract crop from message using keywords."""
        message_lower = message.lower()
        crops = [
            "maize", "corn", "rice", "cassava", "cocoa", "tomato",
            "pepper", "yam", "groundnut", "sorghum", "millet",
            "plantain", "cowpea", "beans"
        ]

        for crop in crops:
            if crop in message_lower:
                # Normalize corn to maize
                return "maize" if crop == "corn" else crop

        return None

    def _extract_time_fallback(self, message: str) -> TimeReference:
        """Extract time reference from message."""
        message_lower = message.lower()

        if "tomorrow" in message_lower:
            return TimeReference(reference="tomorrow", days_ahead=1)
        elif "next week" in message_lower:
            return TimeReference(reference="next_week", days_ahead=7)
        elif "this week" in message_lower:
            return TimeReference(reference="this_week", days_ahead=3)
        elif "today" in message_lower or "now" in message_lower:
            return TimeReference(reference="today", days_ahead=0)

        return TimeReference(reference="now", days_ahead=0)

    async def generate_response(
        self,
        intent: IntentExtraction,
        weather_data: WeatherData | None = None,
        forecast_data: ForecastData | None = None,
        agromet_data: AgroMetData | None = None,
        gdd_data: GDDData | None = None,
        seasonal_data: SeasonalOutlook | None = None,
        seasonal_forecast: SeasonalForecast | None = None,
        user_context: UserContext | None = None,
    ) -> str:
        """
        Generate a friendly response using Groq.

        Args:
            intent: Extracted intent from user message.
            weather_data: Current weather data if available.
            forecast_data: Forecast data if available.
            agromet_data: Agrometeorological data if available.
            gdd_data: Growing degree days data if available.
            seasonal_data: Seasonal outlook if available.
            seasonal_forecast: Ghana-specific seasonal forecast if available.
            user_context: User context for personalization.

        Returns:
            Friendly response string.
        """
        if not self.ai_enabled:
            return self._generate_template_response(
                intent, weather_data, forecast_data, agromet_data, gdd_data,
                seasonal_data, seasonal_forecast
            )

        context = self._build_context(
            intent, weather_data, forecast_data, agromet_data, gdd_data,
            seasonal_data, seasonal_forecast
        )

        try:
            prompt = RESPONSE_GENERATION_PROMPT.format(context=context)

            chat_completion = await self.client.chat.completions.create(
                messages=[
                    {"role": "user", "content": prompt}
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=500,
                timeout=self.timeout,
            )

            return chat_completion.choices[0].message.content.strip()

        except Exception as e:
            logger.warning(f"Groq response generation failed: {e}, using template")
            return self._generate_template_response(
                intent, weather_data, forecast_data, agromet_data, gdd_data,
                seasonal_data, seasonal_forecast
            )

    def _build_context(
        self,
        intent: IntentExtraction,
        weather_data: WeatherData | None = None,
        forecast_data: ForecastData | None = None,
        agromet_data: AgroMetData | None = None,
        gdd_data: GDDData | None = None,
        seasonal_data: SeasonalOutlook | None = None,
        seasonal_forecast: SeasonalForecast | None = None,
    ) -> str:
        """Build context string for AI response generation."""
        context_parts = [f"Query type: {intent.query_type.value}"]
        context_parts.append(f"User asked: {intent.raw_message}")

        # Make query type very clear to AI for targeted responses
        query_descriptions = {
            QueryType.SEASONAL_ONSET: "User wants ONLY onset date information - when rainy season starts",
            QueryType.SEASONAL_CESSATION: "User wants ONLY cessation date information - when rains end",
            QueryType.DRY_SPELL: "User wants ONLY dry spell information - dry periods within season",
            QueryType.SEASON_LENGTH: "User wants ONLY season length information - duration of rainy season",
        }
        if intent.query_type in query_descriptions:
            context_parts.append(f"FOCUS: {query_descriptions[intent.query_type]}")

        if intent.city:
            context_parts.append(f"Location: {intent.city}")
        if intent.crop:
            context_parts.append(f"Crop: {intent.crop}")

        if weather_data:
            context_parts.append(
                f"Current weather in {weather_data.city}: "
                f"{weather_data.temperature:.1f}C, {weather_data.description}, "
                f"humidity {weather_data.humidity}%, wind {weather_data.wind_speed} km/h"
            )

        if forecast_data and forecast_data.periods:
            forecasts = []
            for period in forecast_data.periods[:5]:
                forecasts.append(
                    f"{period.datetime_str}: {period.temperature:.1f}C, {period.description}"
                )
            context_parts.append("Forecast:\n" + "\n".join(forecasts))

        if agromet_data:
            if agromet_data.daily_data:
                today = agromet_data.daily_data[0]
                if today.eto is not None:
                    context_parts.append(f"Today's ETO: {today.eto:.2f}mm")

            if agromet_data.soil_moisture:
                sm = agromet_data.soil_moisture
                context_parts.append(
                    f"Soil moisture: Surface {sm.moisture_0_1cm:.1f}%, "
                    f"Root zone {sm.moisture_9_27cm:.1f}%"
                )

        if gdd_data:
            context_parts.append(
                f"GDD for {gdd_data.crop}: {gdd_data.accumulated_gdd:.0f} "
                f"(current stage: {gdd_data.current_stage})"
            )
            if gdd_data.next_stage:
                context_parts.append(
                    f"Next stage: {gdd_data.next_stage} "
                    f"(need {gdd_data.gdd_to_next_stage:.0f} more GDD)"
                )

        if seasonal_data:
            context_parts.append(
                f"Seasonal outlook: Temperature {seasonal_data.temperature_trend}, "
                f"Precipitation {seasonal_data.precipitation_trend}"
            )
            context_parts.append(f"Summary: {seasonal_data.summary}")

        if seasonal_forecast:
            region_name = "Southern" if seasonal_forecast.region.value == "southern" else "Northern"
            context_parts.append(f"Ghana Region: {region_name} (lat {seasonal_forecast.latitude:.2f})")
            context_parts.append(f"Season Type: {seasonal_forecast.season_type.value}")
            if seasonal_forecast.onset_date:
                context_parts.append(f"Onset: {seasonal_forecast.onset_date} ({seasonal_forecast.onset_status})")
            if seasonal_forecast.cessation_date:
                context_parts.append(f"Cessation: {seasonal_forecast.cessation_date} ({seasonal_forecast.cessation_status})")
            if seasonal_forecast.season_length_days:
                context_parts.append(f"Season length: {seasonal_forecast.season_length_days} days")
            if seasonal_forecast.dry_spells:
                ds = seasonal_forecast.dry_spells
                context_parts.append(f"Early dry spell: {ds.early_dry_spell_days} days ({ds.early_period})")
                context_parts.append(f"Late dry spell: {ds.late_dry_spell_days} days ({ds.late_period})")
            context_parts.append(f"Farming advice: {seasonal_forecast.farming_advice}")

        return "\n".join(context_parts)

    def _get_weather_icon(self, description: str) -> str:
        """Get appropriate weather icon based on description."""
        desc_lower = description.lower()
        if any(word in desc_lower for word in ["rain", "drizzle", "shower"]):
            return "🌧️"
        elif any(word in desc_lower for word in ["cloud", "overcast"]):
            return "⛅"
        elif any(word in desc_lower for word in ["clear", "sunny", "sun"]):
            return "☀️"
        elif any(word in desc_lower for word in ["storm", "thunder"]):
            return "⛈️"
        return "⛅"

    def _get_cessation_start(self, sf: SeasonalForecast) -> str:
        """Get the cessation monitoring start date for display."""
        from app.services.seasonal import get_cessation_start_date
        from datetime import date
        return get_cessation_start_date(sf.region, sf.season_type, date.today().year)

    def _format_onset_response(self, sf: SeasonalForecast) -> str:
        """Format response for onset-only queries."""
        region = "Southern" if sf.region.value == "southern" else "Northern"
        msg = f"🌧️ {region} Ghana - Onset\n\n"

        if sf.onset_date:
            status = "✅ Confirmed" if sf.onset_status == "occurred" else "📅 Expected"
            msg += f"Date: {sf.onset_date} ({status})\n"
        else:
            msg += f"Status: {sf.onset_status.replace('_', ' ').title()}\n"
            msg += f"Typical range: {sf.expected_onset_range}\n"

        # Onset-specific advisory
        msg += "\n📋 Advisory:\n"
        if sf.onset_status == "occurred":
            msg += "• Planting window is open - begin sowing immediately\n"
            msg += "• Apply basal fertilizer at planting\n"
            msg += "• Monitor for early pest emergence"
        elif sf.onset_status == "expected":
            msg += "• Prepare land and acquire inputs now\n"
            msg += "• Have seeds ready for planting\n"
            msg += "• Clear fields and create drainage"
        else:
            msg += "• Too early for planting - continue land preparation\n"
            msg += "• Monitor weather updates regularly\n"
            msg += "• Avoid planting on false starts"
        return msg

    def _format_cessation_response(self, sf: SeasonalForecast) -> str:
        """Format response for cessation-only queries."""
        region = "Southern" if sf.region.value == "southern" else "Northern"
        msg = f"🛑 {region} Ghana - Cessation\n\n"

        if sf.cessation_date:
            status = "✅ Confirmed" if sf.cessation_status == "occurred" else "📅 Expected"
            msg += f"Date: {sf.cessation_date} ({status})\n"
        else:
            msg += f"Status: Monitoring from {self._get_cessation_start(sf)}\n"
            msg += f"Typical range: {sf.expected_cessation_range}\n"

        # Cessation-specific advisory
        msg += "\n📋 Advisory:\n"
        if sf.cessation_status == "occurred":
            msg += "• Rains have ended - begin harvest if mature\n"
            msg += "• Reduce irrigation gradually\n"
            msg += "• Prepare for dry season storage"
        else:
            msg += "• Plan harvest timing before cessation\n"
            msg += "• Ensure crops reach maturity before rains end\n"
            msg += "• Consider early-maturing varieties if late planting"
        return msg

    def _format_dry_spell_response(self, sf: SeasonalForecast) -> str:
        """Format response for dry spell-only queries."""
        region = "Southern" if sf.region.value == "southern" else "Northern"
        msg = f"☀️ {region} Ghana - Dry Spells\n\n"

        if sf.dry_spells:
            msg += f"Early period ({sf.dry_spells.early_period}):\n"
            msg += f"  Longest dry spell: {sf.dry_spells.early_dry_spell_days} days\n\n"
            msg += f"Late period ({sf.dry_spells.late_period}):\n"
            msg += f"  Longest dry spell: {sf.dry_spells.late_dry_spell_days} days\n"

            # Dry spell-specific advisory
            msg += "\n📋 Advisory:\n"
            if sf.dry_spells.early_dry_spell_days > 7:
                msg += "• Early dry spell risk HIGH - mulch to conserve moisture\n"
                msg += "• Consider supplemental irrigation for seedlings\n"
            else:
                msg += "• Early dry spell risk LOW - normal practices apply\n"

            if sf.dry_spells.late_dry_spell_days > 10:
                msg += "• Late dry spell risk HIGH - avoid late planting\n"
                msg += "• Select drought-tolerant varieties"
            else:
                msg += "• Late dry spell risk MODERATE - monitor soil moisture"
        else:
            msg += "Cannot calculate - onset not yet detected\n"
            msg += "\n📋 Advisory:\n"
            msg += "• Check back after rainy season begins"
        return msg

    def _format_season_length_response(self, sf: SeasonalForecast) -> str:
        """Format response for season length-only queries."""
        region = "Southern" if sf.region.value == "southern" else "Northern"
        season = sf.season_type.value.title()
        msg = f"📏 {region} Ghana - {season} Season Length\n\n"

        if sf.season_length_days:
            msg += f"Duration: {sf.season_length_days} days\n"
            if sf.onset_date and sf.cessation_date:
                msg += f"From: {sf.onset_date} to {sf.cessation_date}\n"

            # Season length-specific advisory
            msg += "\n📋 Advisory:\n"
            if sf.season_length_days < 90:
                msg += "• SHORT season - use 90-day maturing varieties\n"
                msg += "• Prioritize quick-maturing crops (cowpea, millet)\n"
                msg += "• Avoid long-season crops this year"
            elif sf.season_length_days < 120:
                msg += "• NORMAL season - standard varieties suitable\n"
                msg += "• Maize (100-110 days) is appropriate\n"
                msg += "• Plan for one cropping cycle"
            else:
                msg += "• LONG season - opportunity for longer varieties\n"
                msg += "• Can consider late planting if needed\n"
                msg += "• Second crop possible in Southern Ghana"
        else:
            msg += "Cannot calculate - need both onset and cessation dates\n"
            msg += "\n📋 Advisory:\n"
            msg += "• Check back as season progresses"
        return msg

    def _generate_template_response(
        self,
        intent: IntentExtraction,
        weather_data: WeatherData | None = None,
        forecast_data: ForecastData | None = None,
        agromet_data: AgroMetData | None = None,
        gdd_data: GDDData | None = None,
        seasonal_data: SeasonalOutlook | None = None,
        seasonal_forecast: SeasonalForecast | None = None,
    ) -> str:
        """Generate template-based response as fallback."""
        city = intent.city

        if intent.query_type == QueryType.GREETING:
            greeting = self._get_greeting(city)
            return (
                f"👋 {greeting} I'm your agri-weather assistant.\n\n"
                "☀️ Weather  💧 ETO  🌱 GDD\n"
                "🪴 Soil  🗓️ Seasonal outlook\n\n"
                "Ask me anything!"
            )

        if intent.query_type == QueryType.HELP:
            return (
                "ℹ️ Commands:\n"
                '☀️ "weather Kumasi"\n'
                '📅 "forecast tomorrow"\n'
                '💧 "ETO today"\n'
                '🌱 "GDD maize"\n'
                '🪴 "soil moisture"'
            )

        # Route to query-specific seasonal responses FIRST
        if intent.query_type == QueryType.SEASONAL_ONSET and seasonal_forecast:
            return self._format_onset_response(seasonal_forecast)

        if intent.query_type == QueryType.SEASONAL_CESSATION and seasonal_forecast:
            return self._format_cessation_response(seasonal_forecast)

        if intent.query_type == QueryType.DRY_SPELL and seasonal_forecast:
            return self._format_dry_spell_response(seasonal_forecast)

        if intent.query_type == QueryType.SEASON_LENGTH and seasonal_forecast:
            return self._format_season_length_response(seasonal_forecast)

        if weather_data:
            intro = self._get_weather_intro(weather_data.city)
            weather_icon = self._get_weather_icon(weather_data.description)
            return (
                f"☀️ {intro}{weather_data.city} weather:\n\n"
                f"🌡️ {weather_data.temperature:.1f}°C (feels {weather_data.feels_like:.1f}°C)\n"
                f"{weather_icon} {weather_data.description.capitalize()}\n"
                f"💧 {weather_data.humidity}%  💨 {weather_data.wind_speed} km/h"
            )

        if forecast_data and forecast_data.periods:
            lines = [f"📅 {forecast_data.city} Forecast\n"]
            for period in forecast_data.periods[:5]:
                weather_icon = self._get_weather_icon(period.description)
                lines.append(
                    f"{period.datetime_str}: {weather_icon} {period.temperature:.1f}°C"
                )
            return "\n".join(lines)

        if agromet_data and agromet_data.daily_data:
            today = agromet_data.daily_data[0]
            msg = f"🌱 Agro Data - {today.date}\n\n"
            if today.eto is not None:
                msg += f"💧 ETO: {today.eto:.2f}mm\n"
            if today.temp_max is not None:
                msg += f"🌡️ {today.temp_min:.1f}° - {today.temp_max:.1f}°C\n"
            if agromet_data.soil_moisture:
                sm = agromet_data.soil_moisture
                msg += f"🪴 Surface: {sm.moisture_0_1cm:.1f}%\n"
                msg += f"🪴 Root zone: {sm.moisture_9_27cm:.1f}%"
            return msg

        if gdd_data:
            msg = f"📈 {gdd_data.crop.title()} GDD\n\n"
            msg += f"Accumulated: {gdd_data.accumulated_gdd:.0f}\n"
            msg += f"Stage: {gdd_data.current_stage}\n"
            if gdd_data.next_stage:
                msg += f"Next: {gdd_data.next_stage} ({gdd_data.gdd_to_next_stage:.0f} away)"
            return msg

        if seasonal_data:
            return (
                "🗓️ Seasonal Outlook\n\n"
                f"🌡️ Temp: {seasonal_data.temperature_trend}\n"
                f"🌧️ Rain: {seasonal_data.precipitation_trend}\n\n"
                f"{seasonal_data.summary}"
            )

        if seasonal_forecast:
            region_name = "Southern" if seasonal_forecast.region.value == "southern" else "Northern"
            season_name = {
                "major": "Major Season",
                "minor": "Minor Season",
                "single": "Single Season",
            }.get(seasonal_forecast.season_type.value, seasonal_forecast.season_type.value)

            msg = f"🌍 {region_name} Ghana - {season_name}\n\n"

            if seasonal_forecast.onset_date:
                onset_emoji = "✅" if seasonal_forecast.onset_status == "occurred" else "📅"
                msg += f"🌧️ Onset: {seasonal_forecast.onset_date} {onset_emoji}\n"

            if seasonal_forecast.cessation_date:
                cess_emoji = "✅" if seasonal_forecast.cessation_status == "occurred" else "📅"
                msg += f"🛑 Cessation: {seasonal_forecast.cessation_date} {cess_emoji}\n"

            if seasonal_forecast.season_length_days:
                msg += f"📏 Length: {seasonal_forecast.season_length_days} days\n"

            if seasonal_forecast.dry_spells:
                ds = seasonal_forecast.dry_spells
                msg += f"\n☀️ Early dry spell: {ds.early_dry_spell_days} days\n"
                msg += f"☀️ Late dry spell: {ds.late_dry_spell_days} days\n"

            msg += f"\n💡 {seasonal_forecast.farming_advice}"
            return msg

        return (
            "I couldn't find that info. "
            "Try asking about weather, forecasts, or farming advice!"
        )

    async def generate_crop_advice(
        self,
        crop: str,
        weather_data: WeatherData | None = None,
        agromet_data: AgroMetData | None = None,
        gdd_data: GDDData | None = None,
        seasonal_data: SeasonalOutlook | None = None,
    ) -> str:
        """
        Generate crop-specific advice using AI.

        Args:
            crop: Crop name.
            weather_data: Current weather data.
            agromet_data: Agrometeorological data.
            gdd_data: GDD data for the crop.
            seasonal_data: Seasonal outlook.

        Returns:
            Crop-specific advice string.
        """
        if not self.ai_enabled:
            return self._get_default_crop_advice(crop)

        context_parts = [f"Generate farming advice for {crop} in Ghana."]

        if weather_data:
            context_parts.append(
                f"Current weather: {weather_data.temperature:.1f}C, "
                f"{weather_data.description}, humidity {weather_data.humidity}%"
            )

        if agromet_data and agromet_data.daily_data:
            today = agromet_data.daily_data[0]
            if today.eto:
                context_parts.append(f"Today's ETO: {today.eto:.2f}mm")

        if gdd_data:
            context_parts.append(
                f"Crop GDD: {gdd_data.accumulated_gdd:.0f}, stage: {gdd_data.current_stage}"
            )

        if seasonal_data:
            context_parts.append(
                f"Seasonal outlook: {seasonal_data.temperature_trend} temps, "
                f"{seasonal_data.precipitation_trend} rainfall"
            )

        try:
            prompt = (
                "You are a Ghanaian agricultural expert. Give practical, "
                "actionable farming advice based on this context:\n\n"
                + "\n".join(context_parts) +
                "\n\nProvide 3-4 specific recommendations in a friendly tone."
            )

            chat_completion = await self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.7,
                max_tokens=400,
                timeout=self.timeout,
            )

            return chat_completion.choices[0].message.content.strip()

        except Exception as e:
            logger.warning(f"Crop advice generation failed: {e}")
            return self._get_default_crop_advice(crop)

    def _get_default_crop_advice(self, crop: str) -> str:
        """Get default crop advice when AI fails."""
        advice = {
            "maize": (
                "🌱 Maize Tips\n"
                "• Plant April-May\n"
                "• Space 75cm x 25cm\n"
                "• NPK at 4 weeks\n"
                "• Watch for armyworm"
            ),
            "rice": (
                "🌱 Rice Tips\n"
                "• Paddy water 5-10cm\n"
                "• Urea at tillering\n"
                "• Weed control in 40 days\n"
                "• Harvest at 80% maturity"
            ),
            "cassava": (
                "🌱 Cassava Tips\n"
                "• Plant at start of rains\n"
                "• Cuttings 25-30cm\n"
                "• Space 1m x 1m\n"
                "• Harvest 9-12 months"
            ),
            "tomato": (
                "🌱 Tomato Tips\n"
                "• Transplant at 4-6 weeks\n"
                "• Stake for support\n"
                "• Water regularly\n"
                "• Watch for early blight"
            ),
        }
        return advice.get(crop, f"🌱 For {crop} advice, consult local extension officers.")


# Singleton instance
_ai_provider: GroqProvider | None = None


def get_ai_provider() -> GroqProvider:
    """Get or create the AI provider instance."""
    global _ai_provider
    if _ai_provider is None:
        _ai_provider = GroqProvider()
    return _ai_provider
