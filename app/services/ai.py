"""AI service with Groq integration for NLU and response generation."""

import json
import logging
from datetime import date, datetime
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
    TimeOfDay,
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


INTENT_EXTRACTION_PROMPT = """You are an expert NLU parser for a Ghanaian agricultural weather chatbot.

═══════════════════════════════════════════════════════════════════════════════
SECTION 1: PRE-PROCESSING NOTE
═══════════════════════════════════════════════════════════════════════════════
Messages are ALREADY NORMALIZED before reaching you:
- Pidgin English converted to standard English (e.g., "wetin be weather" → "what is the weather")
- Slang normalized (e.g., "2moro" → "tomorrow", "d weather" → "the weather")
- Typos corrected where possible

DO NOT re-interpret or second-guess normalized text. Process it as standard English.

═══════════════════════════════════════════════════════════════════════════════
SECTION 2: ROLE & CRITICAL RULES
═══════════════════════════════════════════════════════════════════════════════
Your task: Extract structured intent as JSON from user messages.

CRITICAL RULES:
1. Output ONLY valid JSON - no markdown, no explanation, no text before/after
2. Use EXACT values from allowed lists (cities, crops, query_types)
3. Never invent cities or crops not in the lists
4. When uncertain, lower the confidence score rather than guessing

═══════════════════════════════════════════════════════════════════════════════
SECTION 3: QUERY TYPE DECISION TREE (Check in this priority order)
═══════════════════════════════════════════════════════════════════════════════
1. GREETING → "greeting"
   Triggers: hi, hello, hey, good morning/afternoon/evening, how are you

2. HELP REQUEST → "help"
   Triggers: help, how do I, how to use, what can you do, instructions

3. SEASONAL-SPECIFIC (check keywords carefully):
   - "onset", "start of rain", "when does rain begin" → "seasonal_onset"
   - "cessation", "end of rain", "when do rains stop" → "seasonal_cessation"
   - "dry spell", "drought risk", "dry period" → "dry_spell"
   - "season length", "how long is season", "duration" → "season_length"
   - "seasonal outlook", "3-month", "6-month forecast" → "seasonal"

4. AGRO-METEOROLOGICAL:
   - "GDD", "degree days", "growth stage", "accumulation" → "gdd"
   - "soil moisture", "soil water", "soil condition" → "soil"
   - "ETO", "evapotranspiration", "water loss" → "eto"
   - "dekadal", "10-day bulletin", "bulletin" → "dekadal"

5. CROP-RELATED → "crop_advice"
   Triggers: when to plant, planting advice, should I plant, crop recommendation

6. FUTURE WEATHER → "forecast"
   Triggers: tomorrow, next week, this week, weekend, will it rain, future dates

7. CURRENT WEATHER → "weather" (DEFAULT)
   Triggers: weather now, current conditions, what's the weather, temperature today

═══════════════════════════════════════════════════════════════════════════════
SECTION 4: ENTITY EXTRACTION
═══════════════════════════════════════════════════════════════════════════════
GHANA_CITIES (use exact spelling, title case):
Accra, Kumasi, Tamale, Takoradi, Cape Coast, Sunyani, Ho, Koforidua,
Tema, Wa, Bolgatanga, Sekondi, Tarkwa, Obuasi, Techiman, Nkawkaw

CROPS (use lowercase):
maize, rice, cassava, cocoa, tomato, pepper, yam, groundnut,
sorghum, millet, plantain, cowpea

TIME PARSING:
- "now", "today", "currently" → reference: "now", days_ahead: 0
- "tomorrow" → reference: "tomorrow", days_ahead: 1
- "this week" → reference: "this_week", days_ahead: 3
- "next week" → reference: "next_week", days_ahead: 7
- "weekend", "Saturday" → reference: "weekend", days_ahead: (calculate to next Saturday)
- Specific day names → calculate days_ahead from current day

TIME OF DAY (optional, include when mentioned):
- "morning", "AM", "dawn" → time_of_day: "morning"
- "afternoon", "midday", "noon" → time_of_day: "afternoon"
- "evening", "dusk" → time_of_day: "evening"
- "night", "tonight" → time_of_day: "night"

═══════════════════════════════════════════════════════════════════════════════
SECTION 5: DISAMBIGUATION RULES
═══════════════════════════════════════════════════════════════════════════════
- Message mentions BOTH current AND future → use "forecast"
- City unclear but crop mentioned → city: null (let system use default)
- Time unclear for weather query → default to "now"
- Just a city name alone (e.g., "Kumasi") → treat as "weather" for that city
- "Season" without specifics → use "seasonal"
- Mentions "rain" in future tense → "forecast", not "seasonal_onset"
- Unknown city name → city: null, DO NOT invent or guess
- Unknown crop name → crop: null, DO NOT invent or guess
- Out-of-domain request (bank balance, news, etc.) → query_type: "help"

═══════════════════════════════════════════════════════════════════════════════
SECTION 6: CONFIDENCE SCORING
═══════════════════════════════════════════════════════════════════════════════
0.90-1.00: Clear, unambiguous query with explicit entities
0.70-0.89: Minor ambiguity (e.g., time unclear, common phrasing)
0.50-0.69: Multiple valid interpretations possible
Below 0.50: Cannot determine intent → use query_type: "help"

Confidence adjustments:
- Subtract 0.1 if city is missing
- Subtract 0.1 if time reference is ambiguous
- Subtract 0.15 if query type could be multiple things
- Add 0.05 if message is a complete, well-formed question

═══════════════════════════════════════════════════════════════════════════════
SECTION 7: EXAMPLES (Diverse Cases)
═══════════════════════════════════════════════════════════════════════════════

BASIC QUERIES:
Input: "What's the weather in Kumasi?"
Output: {"city": "Kumasi", "query_type": "weather", "crop": null, "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.95}

Input: "Will it rain tomorrow in Accra?"
Output: {"city": "Accra", "query_type": "forecast", "crop": null, "time_reference": {"reference": "tomorrow", "days_ahead": 1}, "confidence": 0.92}

Input: "Hello"
Output: {"city": null, "query_type": "greeting", "crop": null, "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.98}

SEASONAL QUERIES:
Input: "When does the rainy season start in Tamale?"
Output: {"city": "Tamale", "query_type": "seasonal_onset", "crop": null, "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.92}

Input: "How long will the rains last this year?"
Output: {"city": null, "query_type": "season_length", "crop": null, "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.85}

AGRICULTURAL QUERIES:
Input: "Check maize GDD in Kumasi"
Output: {"city": "Kumasi", "query_type": "gdd", "crop": "maize", "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.93}

Input: "Soil moisture for my rice field"
Output: {"city": null, "query_type": "soil", "crop": "rice", "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.88}

MULTI-ENTITY QUERIES:
Input: "Maize planting conditions in Kumasi tomorrow morning"
Output: {"city": "Kumasi", "query_type": "crop_advice", "crop": "maize", "time_reference": {"reference": "tomorrow", "days_ahead": 1, "time_of_day": "morning"}, "confidence": 0.91}

EDGE CASES - Ambiguous/Incomplete:
Input: "The weather"
Output: {"city": null, "query_type": "weather", "crop": null, "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.65}

Input: "Tell me about things"
Output: {"city": null, "query_type": "help", "crop": null, "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.45}

OUT-OF-DOMAIN (should redirect to help):
Input: "What is my account balance?"
Output: {"city": null, "query_type": "help", "crop": null, "time_reference": {"reference": "now", "days_ahead": 0}, "confidence": 0.40}

NEGATIVE EXAMPLES (DO NOT output like these):
❌ WRONG: {"city": "Lagos", ...} - Lagos is not in GHANA_CITIES list
❌ WRONG: {"city": "kumasi", ...} - Should be "Kumasi" (title case)
❌ WRONG: {"crop": "wheat", ...} - wheat is not in CROPS list
❌ WRONG: {"query_type": "rain", ...} - "rain" is not a valid query_type
❌ WRONG: {"confidence": "high", ...} - confidence must be a number 0.0-1.0

═══════════════════════════════════════════════════════════════════════════════
SECTION 8: STRICT OUTPUT SCHEMA
═══════════════════════════════════════════════════════════════════════════════
{
  "city": "<string from GHANA_CITIES | null>",
  "query_type": "<weather|forecast|eto|gdd|soil|seasonal|seasonal_onset|seasonal_cessation|dry_spell|season_length|crop_advice|dekadal|help|greeting>",
  "crop": "<string from CROPS | null>",
  "time_reference": {
    "reference": "<now|today|tomorrow|this_week|next_week|weekend>",
    "days_ahead": <integer 0-14>,
    "time_of_day": "<morning|afternoon|evening|night | null>"
  },
  "confidence": <float 0.0-1.0>
}

Output ONLY the JSON object. No other text.

User message: """

RESPONSE_GENERATION_PROMPT = """You are a Ghanaian agricultural meteorologist advising farmers via WhatsApp.

═══════════════════════════════════════════════════════════════════════════════
ROLE & EXPERTISE
═══════════════════════════════════════════════════════════════════════════════
You specialize in:
- Crop-weather relationships for West African agriculture
- Ghana's bimodal (south) and unimodal (north) rainfall patterns
- Climate-smart farming practices
- Translating technical data into actionable farmer advice

Persona: Professional but approachable. You understand smallholder farming challenges.

═══════════════════════════════════════════════════════════════════════════════
GHANA CROP CALENDAR REFERENCE
═══════════════════════════════════════════════════════════════════════════════
SOUTHERN GHANA (Major Season - April to July):
- Maize: Plant March-April, harvest July-August
- Rice (rain-fed): Plant April-May
- Tomato: Plant Feb-March for major season

SOUTHERN GHANA (Minor Season - September to November):
- Maize: Plant August-September
- Vegetables: September-December (dry season production)

NORTHERN GHANA (Single Season - May to October):
- Maize: Plant May-June, harvest September-October
- Sorghum/Millet: Plant June-July
- Rice: Plant June-July

YEAR-ROUND:
- Cassava: Plant at start of rains, harvest 9-12 months later
- Plantain: Plant at start of rains

═══════════════════════════════════════════════════════════════════════════════
DATA USAGE PRIORITY
═══════════════════════════════════════════════════════════════════════════════
When multiple data types are available, prioritize in this order:

1. GDD (Growing Degree Days) → Growth stage guidance
   - Use to advise on crop development timing
   - "Your maize has accumulated X GDD, indicating [stage]"

2. Soil Moisture → Irrigation and planting readiness
   - Surface moisture: planting/germination decisions
   - Root zone moisture: irrigation needs

3. Current Weather → Immediate conditions
   - Temperature, humidity for daily planning
   - Precipitation for spray/harvest timing

4. Seasonal Outlook → Long-term planning
   - Onset/cessation for planting windows
   - Dry spell risk for variety selection

CRITICAL: If data is missing, work with what's available. NEVER invent numbers.
Say "data not available" rather than guessing values.

═══════════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT & CONSTRAINTS
═══════════════════════════════════════════════════════════════════════════════
- Maximum 80 words (STRICT - count before outputting)
- WhatsApp markdown: *bold* for headers, _italic_ for tips/advice
- Emojis: 🌡️ temp, 💧 humidity/water, 💨 wind, ☀️ sunny, ⛅ cloudy, 🌧️ rain, 🌱 crops, 🪴 soil, ⛈️ storm, 📊 data
- ONE actionable tip in italics at the end
- Do NOT repeat the user's question
- One greeting maximum (only if appropriate)

STRUCTURE:
1. Header: Location + condition/topic emoji
2. Key data: 2-3 most relevant metrics
3. Tip: One practical, actionable recommendation in _italics_

═══════════════════════════════════════════════════════════════════════════════
FEW-SHOT EXAMPLES
═══════════════════════════════════════════════════════════════════════════════

EXAMPLE 1 - Good Planting Conditions:
Context: Kumasi, maize query, soil moisture 65%, temp 28°C, recent rain
Response:
🌱 *Maize Planting - Kumasi*
🪴 Soil moisture: 65% (excellent)
🌡️ Temp: 28°C | 💧 Humidity: 72%
Recent rain has prepared the soil well.

_💡 Plant within 3 days while moisture is optimal. Apply basal fertilizer at planting._

EXAMPLE 2 - Adverse Weather Advisory:
Context: Tamale, forecast shows 5+ days no rain, temp 35°C
Response:
⚠️ *Dry Spell Alert - Tamale*
☀️ No rain expected for 5+ days
🌡️ High temps: 34-36°C

_💡 Mulch around crops to conserve soil moisture. Irrigate seedlings in early morning._

EXAMPLE 3 - Data-Sparse Response:
Context: User asks about GDD but no GDD data available
Response:
📊 *GDD Data - Accra*
GDD data currently unavailable for your location.

Based on planting date and current temps (29°C avg), maize typically reaches tasseling at 50-55 days.

_💡 Monitor for silk emergence as indicator of growth stage._

═══════════════════════════════════════════════════════════════════════════════
SELF-VERIFICATION CHECKLIST (Apply before outputting)
═══════════════════════════════════════════════════════════════════════════════
Before generating your response, verify:
[ ] Under 80 words? (Count carefully)
[ ] WhatsApp markdown used? (*bold*, _italic_)
[ ] Exactly ONE tip in italics?
[ ] No invented/fabricated data?
[ ] Actionable and specific to Ghana context?

═══════════════════════════════════════════════════════════════════════════════
AVOID
═══════════════════════════════════════════════════════════════════════════════
- Data dumps without interpretation
- Generic advice ("Have a nice day", "Stay safe")
- Repeating the user's question verbatim
- Multiple greetings
- Advice not relevant to Ghana agriculture
- Making up numbers when data is unavailable

═══════════════════════════════════════════════════════════════════════════════
CONTEXT PROVIDED
═══════════════════════════════════════════════════════════════════════════════
{context}

Generate your response now:"""

# Dynamic weather emoji maps with day/night variants and tips
WEATHER_EMOJI_MAP: dict[str, dict[str, str]] = {
    "clear": {
        "day": "☀️",
        "night": "🌙",
        "tip": "Perfect weather for outdoor activities!",
    },
    "clouds": {
        "day": "⛅",
        "night": "☁️",
        "tip": "Good working weather - not too hot!",
    },
    "overcast": {
        "day": "☁️",
        "night": "☁️",
        "tip": "Comfortable conditions for fieldwork.",
    },
    "rain": {
        "day": "🌧️",
        "night": "🌧️",
        "tip": "Grab an umbrella! Good for natural irrigation.",
    },
    "drizzle": {
        "day": "🌦️",
        "night": "🌧️",
        "tip": "Light rain - might clear up soon.",
    },
    "thunderstorm": {
        "day": "⛈️",
        "night": "⛈️",
        "tip": "Stay indoors! Avoid open fields.",
    },
    "snow": {
        "day": "❄️",
        "night": "❄️",
        "tip": "Unusual for Ghana - check conditions!",
    },
    "mist": {
        "day": "🌫️",
        "night": "🌫️",
        "tip": "Low visibility - drive carefully.",
    },
    "fog": {
        "day": "🌫️",
        "night": "🌫️",
        "tip": "Dense fog - wait for it to lift.",
    },
    "haze": {
        "day": "😶‍🌫️",
        "night": "😶‍🌫️",
        "tip": "Harmattan haze - protect your skin!",
    },
    "dust": {
        "day": "💨",
        "night": "💨",
        "tip": "Harmattan dust! Cover nose and mouth.",
    },
    "sand": {
        "day": "💨",
        "night": "💨",
        "tip": "Sandy winds - protect crops if possible.",
    },
    "smoke": {
        "day": "🌫️",
        "night": "🌫️",
        "tip": "Smoky air - limit outdoor exposure.",
    },
}

# Temperature emoji thresholds (min_temp, max_temp) -> emoji
TEMP_EMOJI_MAP: list[tuple[tuple[int, int], str, str]] = [
    ((0, 15), "🥶", "Very cool - rare for Ghana!"),
    ((15, 25), "😊", "Pleasant temperature."),
    ((25, 30), "🌡️", "Warm and comfortable."),
    ((30, 35), "🥵", "Hot! Stay hydrated."),
    ((35, 40), "🔥", "Very hot! Limit outdoor work."),
    ((40, 50), "🔥🔥", "Extreme heat! Stay indoors if possible."),
]

# Humidity emoji thresholds
HUMIDITY_EMOJI_MAP: list[tuple[tuple[int, int], str, str]] = [
    ((0, 30), "💨", "Dry air - irrigate crops."),
    ((30, 50), "💧", "Comfortable humidity."),
    ((50, 70), "💧💧", "Moderate humidity - good for most crops."),
    ((70, 85), "💦", "High humidity - great for transplanting!"),
    ((85, 100), "💦💦", "Very humid - watch for fungal issues."),
]

# Weather condition to emoji + display name mapping
CONDITION_DISPLAY_MAP: dict[str, tuple[str, str]] = {
    "clear": ("☀️", "Sunny"),
    "sunny": ("☀️", "Sunny"),
    "clouds": ("🌤️", "Partly Cloudy"),
    "few clouds": ("🌤️", "Partly Cloudy"),
    "scattered clouds": ("🌤️", "Partly Cloudy"),
    "broken clouds": ("☁️", "Cloudy"),
    "overcast": ("🌥️", "Overcast"),
    "overcast clouds": ("🌥️", "Overcast"),
    "rain": ("🌧️", "Rainy"),
    "light rain": ("🌦️", "Light Rain"),
    "moderate rain": ("🌧️", "Rainy"),
    "heavy rain": ("🌧️", "Heavy Rain"),
    "shower": ("🌧️", "Showers"),
    "drizzle": ("🌧️", "Drizzle"),
    "thunderstorm": ("⛈️", "Thunderstorm"),
    "mist": ("🌫️", "Misty"),
    "fog": ("🌫️", "Foggy"),
    "haze": ("😶‍🌫️", "Hazy"),
    "dust": ("💨", "Dusty"),
    "harmattan": ("😶‍🌫️", "Harmattan"),
    "smoke": ("🌫️", "Smoky"),
}

# General tips (for weather/forecast queries - NO farming)
GENERAL_TIPS: dict[str, list[str]] = {
    "hot": [
        "Stay hydrated and seek shade during peak hours!",
        "Hot day ahead - drink plenty of water!",
        "Keep cool and avoid prolonged sun exposure!",
    ],
    "rain": [
        "Carry an umbrella - rain expected!",
        "Rain on the way - stay dry!",
        "Showers expected - plan indoor activities!",
    ],
    "thunderstorm": [
        "Stay indoors - thunderstorms expected!",
        "Avoid open areas during the storm!",
        "Seek shelter - lightning risk!",
    ],
    "sunny": [
        "Perfect weather for outdoor activities!",
        "Great day to be outside!",
        "Enjoy the sunshine!",
    ],
    "cloudy": [
        "Comfortable weather - not too hot!",
        "Pleasant conditions today!",
        "Nice day ahead!",
    ],
    "humid": [
        "Humid today - stay cool!",
        "Sticky weather - stay hydrated!",
    ],
    "harmattan": [
        "Harmattan season - protect your skin!",
        "Dry dusty winds - cover nose and mouth!",
    ],
}

# Farming tips (ONLY for agro/crop queries)
FARMING_TIPS: dict[str, list[str]] = {
    "high_humidity": [
        "Great conditions for transplanting seedlings!",
        "Good moisture for young plants!",
    ],
    "low_humidity": [
        "Consider irrigation - soil drying out.",
        "Water crops in early morning or evening.",
    ],
    "rain_expected": [
        "Hold off on spraying - rain will wash it away.",
        "Natural watering on the way - save irrigation!",
    ],
    "sunny_dry": [
        "Good day for harvesting or drying crops.",
        "Ideal for post-harvest drying!",
    ],
    "very_hot": [
        "Avoid fieldwork during peak heat - early morning best.",
        "Protect workers from heat stress!",
    ],
    "good_planting": [
        "Good conditions for planting!",
        "Favorable weather for sowing seeds!",
    ],
}


def get_personalized_greeting(user_name: str | None) -> str:
    """
    Get personalized greeting with user's name.

    Args:
        user_name: User's WhatsApp profile name.

    Returns:
        Personalized greeting string.
    """
    if user_name:
        # Get first name only if full name provided
        first_name = user_name.split()[0] if " " in user_name else user_name
        return f"Hi {first_name}! 👋"
    return "Hello! 👋"


def get_condition_display(description: str, is_daytime: bool = True) -> tuple[str, str]:
    """
    Get emoji and display name for weather condition.

    Args:
        description: Weather description from API.
        is_daytime: Whether it's daytime.

    Returns:
        Tuple of (emoji, display_name).
    """
    desc_lower = description.lower()

    # Check for exact or partial matches
    for condition, (emoji, display_name) in CONDITION_DISPLAY_MAP.items():
        if condition in desc_lower:
            # Night variant for clear sky
            if condition in ("clear", "sunny") and not is_daytime:
                return ("🌙", "Clear Night")
            return (emoji, display_name)

    # Default fallback
    return ("🌡️", description.title())


def get_general_tip(
    temperature: float,
    humidity: int,
    description: str,
) -> str:
    """
    Get general lifestyle tip based on weather conditions.
    NO farming tips - for weather/forecast queries only.

    Args:
        temperature: Temperature in Celsius.
        humidity: Humidity percentage.
        description: Weather description.

    Returns:
        General weather tip string.
    """
    import random
    desc_lower = description.lower()

    # Check conditions in priority order
    if "thunder" in desc_lower or "storm" in desc_lower:
        return random.choice(GENERAL_TIPS["thunderstorm"])
    elif "rain" in desc_lower or "shower" in desc_lower or "drizzle" in desc_lower:
        return random.choice(GENERAL_TIPS["rain"])
    elif temperature >= 33:
        return random.choice(GENERAL_TIPS["hot"])
    elif "haze" in desc_lower or "dust" in desc_lower or "harmattan" in desc_lower:
        return random.choice(GENERAL_TIPS["harmattan"])
    elif humidity >= 80:
        return random.choice(GENERAL_TIPS["humid"])
    elif "clear" in desc_lower or "sunny" in desc_lower:
        return random.choice(GENERAL_TIPS["sunny"])
    else:
        return random.choice(GENERAL_TIPS["cloudy"])


def get_farming_tip(
    temperature: float,
    humidity: int,
    description: str,
) -> str:
    """
    Get farming-specific tip based on weather conditions.
    ONLY for agro/crop queries.

    Args:
        temperature: Temperature in Celsius.
        humidity: Humidity percentage.
        description: Weather description.

    Returns:
        Farming tip string.
    """
    import random
    desc_lower = description.lower()

    # Check conditions in priority order
    if "rain" in desc_lower or "shower" in desc_lower:
        return random.choice(FARMING_TIPS["rain_expected"])
    elif temperature >= 35:
        return random.choice(FARMING_TIPS["very_hot"])
    elif humidity >= 75:
        return random.choice(FARMING_TIPS["high_humidity"])
    elif humidity <= 40:
        return random.choice(FARMING_TIPS["low_humidity"])
    elif "clear" in desc_lower or "sunny" in desc_lower:
        return random.choice(FARMING_TIPS["sunny_dry"])
    else:
        return random.choice(FARMING_TIPS["good_planting"])


def get_dynamic_emojis(
    weather_description: str,
    temperature: float,
    humidity: int,
    is_daytime: bool = True,
) -> dict[str, str]:
    """
    Get dynamic emojis and tips based on weather conditions.

    Args:
        weather_description: Weather description text.
        temperature: Temperature in Celsius.
        humidity: Humidity percentage.
        is_daytime: Whether it's daytime (affects emoji choice).

    Returns:
        Dict with 'condition_emoji', 'condition_tip', 'temp_emoji',
        'temp_tip', 'humidity_emoji', 'humidity_tip' keys.
    """
    result = {
        "condition_emoji": "🌡️",
        "condition_tip": "Check local conditions.",
        "temp_emoji": "🌡️",
        "temp_tip": "Typical temperature.",
        "humidity_emoji": "💧",
        "humidity_tip": "Normal humidity.",
    }

    # Match weather condition
    desc_lower = weather_description.lower()
    time_key = "day" if is_daytime else "night"

    for condition, data in WEATHER_EMOJI_MAP.items():
        if condition in desc_lower:
            result["condition_emoji"] = data[time_key]
            result["condition_tip"] = data["tip"]
            break

    # Match temperature
    for (min_temp, max_temp), emoji, tip in TEMP_EMOJI_MAP:
        if min_temp <= temperature < max_temp:
            result["temp_emoji"] = emoji
            result["temp_tip"] = tip
            break

    # Match humidity
    for (min_hum, max_hum), emoji, tip in HUMIDITY_EMOJI_MAP:
        if min_hum <= humidity < max_hum:
            result["humidity_emoji"] = emoji
            result["humidity_tip"] = tip
            break

    return result


def is_daytime_now() -> bool:
    """Check if it's daytime in Ghana (WAT timezone, roughly 6 AM - 6 PM)."""
    current_hour = datetime.now().hour
    # Ghana is in GMT, adjust if needed
    return 6 <= current_hour < 18


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
        """Extract time reference from message with enhanced parsing."""
        message_lower = message.lower()
        today = date.today()
        today_weekday = today.weekday()  # Monday = 0, Sunday = 6

        # Day name mapping
        day_names = {
            "monday": 0, "mon": 0,
            "tuesday": 1, "tue": 1, "tues": 1,
            "wednesday": 2, "wed": 2, "weds": 2,
            "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
            "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6,
        }

        # Extract time of day
        time_of_day: TimeOfDay | None = None
        if any(word in message_lower for word in ["morning", "mornin", "am", "dawn", "sunrise"]):
            time_of_day = TimeOfDay.MORNING
        elif any(word in message_lower for word in ["afternoon", "midday", "noon", "pm"]):
            time_of_day = TimeOfDay.AFTERNOON
        elif any(word in message_lower for word in ["evening", "evenin", "dusk", "sunset"]):
            time_of_day = TimeOfDay.EVENING
        elif any(word in message_lower for word in ["night", "nite", "tonight", "midnight"]):
            time_of_day = TimeOfDay.NIGHT

        # Check for weekend
        if any(word in message_lower for word in ["weekend", "wknd", "wkd"]):
            # Calculate days to Saturday
            days_to_saturday = (5 - today_weekday) % 7
            if days_to_saturday == 0 and today_weekday == 5:
                days_to_saturday = 0  # Today is Saturday
            elif today_weekday == 6:
                days_to_saturday = 6  # Today is Sunday, next Saturday

            return TimeReference(
                reference="weekend",
                time_of_day=time_of_day,
                days_ahead=days_to_saturday,
                specific_day="saturday",
                is_weekend=True,
                date_range_start=days_to_saturday,
                date_range_end=days_to_saturday + 1,  # Saturday and Sunday
            )

        # Check for specific day names with "next" prefix
        for day_name, day_num in day_names.items():
            if f"next {day_name}" in message_lower:
                # Calculate days ahead (always next week's occurrence)
                days_ahead = (day_num - today_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7  # Same day next week
                else:
                    days_ahead += 7  # Next week's occurrence

                return TimeReference(
                    reference="next_week",
                    time_of_day=time_of_day,
                    days_ahead=days_ahead,
                    specific_day=day_name.split()[0] if " " not in day_name else day_name,
                    is_weekend=day_num in (5, 6),
                )

        # Check for specific day names (this week)
        for day_name, day_num in day_names.items():
            if day_name in message_lower:
                # Calculate days ahead
                days_ahead = (day_num - today_weekday) % 7
                if days_ahead == 0 and day_num != today_weekday:
                    days_ahead = 7  # Same day name but means next week

                return TimeReference(
                    reference="this_week",
                    time_of_day=time_of_day,
                    days_ahead=days_ahead,
                    specific_day=day_name,
                    is_weekend=day_num in (5, 6),
                )

        # Standard time references
        if "tomorrow" in message_lower or "tmrw" in message_lower or "2moro" in message_lower:
            return TimeReference(
                reference="tomorrow",
                time_of_day=time_of_day,
                days_ahead=1,
            )
        elif "next week" in message_lower:
            return TimeReference(
                reference="next_week",
                time_of_day=time_of_day,
                days_ahead=7,
            )
        elif "this week" in message_lower:
            return TimeReference(
                reference="this_week",
                time_of_day=time_of_day,
                days_ahead=3,
            )
        elif "today" in message_lower or "now" in message_lower or "2day" in message_lower:
            return TimeReference(
                reference="today",
                time_of_day=time_of_day,
                days_ahead=0,
            )
        elif "tonight" in message_lower or "2nite" in message_lower:
            return TimeReference(
                reference="today",
                time_of_day=TimeOfDay.NIGHT,
                days_ahead=0,
            )

        # Default - include time of day if extracted
        return TimeReference(
            reference="now",
            time_of_day=time_of_day,
            days_ahead=0,
        )

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
        skip_greeting: bool = False,
    ) -> str:
        """
        Generate a friendly response using template format.

        For weather and forecast queries, ALWAYS uses the template format
        to ensure consistent, professional output. AI is only used for
        complex queries like crop advice.

        Args:
            intent: Extracted intent from user message.
            weather_data: Current weather data if available.
            forecast_data: Forecast data if available.
            agromet_data: Agrometeorological data if available.
            gdd_data: Growing degree days data if available.
            seasonal_data: Seasonal outlook if available.
            seasonal_forecast: Ghana-specific seasonal forecast if available.
            user_context: User context for personalization.
            skip_greeting: If True, omit the greeting (for follow-up queries).

        Returns:
            Friendly response string.
        """
        # ALWAYS use template for weather/forecast/greeting/help - consistent format
        template_query_types = (
            QueryType.WEATHER,
            QueryType.FORECAST,
            QueryType.GREETING,
            QueryType.HELP,
            QueryType.ETO,
            QueryType.GDD,
            QueryType.SOIL,
            QueryType.SEASONAL,
            QueryType.SEASONAL_ONSET,
            QueryType.SEASONAL_CESSATION,
            QueryType.DRY_SPELL,
            QueryType.SEASON_LENGTH,
            QueryType.DEKADAL,
        )

        if intent.query_type in template_query_types:
            return self._generate_template_response(
                intent, weather_data, forecast_data, agromet_data, gdd_data,
                seasonal_data, seasonal_forecast, user_context, skip_greeting
            )

        # Use AI only for complex queries (crop advice)
        if not self.ai_enabled:
            return self._generate_template_response(
                intent, weather_data, forecast_data, agromet_data, gdd_data,
                seasonal_data, seasonal_forecast, user_context, skip_greeting
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
                seasonal_data, seasonal_forecast, user_context, skip_greeting
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
        user_context: UserContext | None = None,
        skip_greeting: bool = False,
    ) -> str:
        """Generate template-based response as fallback."""
        city = intent.city

        # Get personalized greeting (conditionally for follow-up queries)
        user_name = user_context.user_name if user_context else None
        if skip_greeting:
            greeting = ""
        else:
            greeting = get_personalized_greeting(user_name) + "\n\n"

        # Determine if this is an agro query (for tip selection)
        is_agro_query = intent.query_type in (
            QueryType.CROP_ADVICE, QueryType.SOIL, QueryType.ETO,
            QueryType.GDD, QueryType.SEASONAL, QueryType.DEKADAL,
            QueryType.SEASONAL_ONSET, QueryType.SEASONAL_CESSATION,
            QueryType.DRY_SPELL, QueryType.SEASON_LENGTH,
        )

        if intent.query_type == QueryType.GREETING:
            return (
                f"{greeting}"
                "I'm your weather assistant. I can help with:\n"
                "☀️ Weather  📅 Forecasts  🌱 Farming advice\n\n"
                "What would you like to know?"
            )

        if intent.query_type == QueryType.HELP:
            return (
                f"{greeting}"
                "ℹ️ *How to use:*\n"
                '☀️ "weather in Kumasi"\n'
                '📅 "forecast for tomorrow"\n'
                '🌱 "crop advice for maize"\n'
                '🪴 "soil moisture"\n\n'
                "Just ask naturally!"
            )

        # Route to query-specific seasonal responses FIRST
        if intent.query_type == QueryType.SEASONAL_ONSET and seasonal_forecast:
            return f"{greeting}" + self._format_onset_response(seasonal_forecast)

        if intent.query_type == QueryType.SEASONAL_CESSATION and seasonal_forecast:
            return f"{greeting}" + self._format_cessation_response(seasonal_forecast)

        if intent.query_type == QueryType.DRY_SPELL and seasonal_forecast:
            return f"{greeting}" + self._format_dry_spell_response(seasonal_forecast)

        if intent.query_type == QueryType.SEASON_LENGTH and seasonal_forecast:
            return f"{greeting}" + self._format_season_length_response(seasonal_forecast)

        if weather_data:
            # Get condition emoji and display name
            condition_emoji, condition_name = get_condition_display(
                weather_data.description, is_daytime_now()
            )

            # Get appropriate tip based on query type
            if is_agro_query:
                tip = get_farming_tip(
                    weather_data.temperature,
                    weather_data.humidity,
                    weather_data.description,
                )
            else:
                tip = get_general_tip(
                    weather_data.temperature,
                    weather_data.humidity,
                    weather_data.description,
                )

            return (
                f"{greeting}"
                f"{condition_emoji} *{condition_name}* in {weather_data.city}\n"
                f"{weather_data.temperature:.0f}°C (feels like {weather_data.feels_like:.0f}°C)\n"
                f"💧 Humidity: {weather_data.humidity}%\n"
                f"🌬️ Wind: {weather_data.wind_speed:.0f} km/h\n\n"
                f"_💡 {tip}_"
            )

        if forecast_data and forecast_data.periods:
            lines = [f"{greeting}📅 *Forecast* for {forecast_data.city}\n"]
            for period in forecast_data.periods[:5]:
                condition_emoji, _ = get_condition_display(period.description)
                lines.append(
                    f"*{period.datetime_str}:* {condition_emoji} {period.temperature:.0f}°C - {period.description.capitalize()}"
                )

            # Add general tip for forecast
            first_period = forecast_data.periods[0]
            tip = get_general_tip(
                first_period.temperature,
                first_period.humidity,
                first_period.description,
            )
            lines.append(f"\n_💡 {tip}_")
            return "\n".join(lines)

        if agromet_data and agromet_data.daily_data:
            today = agromet_data.daily_data[0]
            msg = f"{greeting}🌱 *Agro Data* - {today.date}\n\n"
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
            msg = f"{greeting}📈 *{gdd_data.crop.title()} GDD*\n\n"
            msg += f"Accumulated: {gdd_data.accumulated_gdd:.0f}\n"
            msg += f"Stage: {gdd_data.current_stage}\n"
            if gdd_data.next_stage:
                msg += f"Next: {gdd_data.next_stage} ({gdd_data.gdd_to_next_stage:.0f} away)"
            return msg

        if seasonal_data:
            return (
                f"{greeting}"
                "🗓️ *Seasonal Outlook*\n\n"
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

            msg = f"{greeting}🌍 *{region_name} Ghana* - {season_name}\n\n"

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

            msg += f"\n_💡 {seasonal_forecast.farming_advice}_"
            return msg

        return (
            f"{greeting}"
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
