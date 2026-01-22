"""Multi-language localization service for Ghanaian languages."""

from datetime import datetime
from enum import Enum
from typing import Optional


class Language(str, Enum):
    """Supported languages for the chatbot."""

    ENGLISH = "en"
    TWI = "tw"      # Akan/Twi - Greater Accra, Ashanti, Central, Eastern
    GA = "ga"       # Ga - Greater Accra (Accra, Tema)
    EWE = "ee"      # Ewe - Volta Region
    DAGBANI = "dag"  # Dagbani - Northern Region
    HAUSA = "ha"    # Hausa - Northern Ghana (trade language)


# Greetings by language and time of day
GREETINGS: dict[Language, dict[str, str]] = {
    Language.ENGLISH: {
        "hello": "Hello!",
        "good_morning": "Good morning!",
        "good_afternoon": "Good afternoon!",
        "good_evening": "Good evening!",
        "goodbye": "Goodbye!",
        "thank_you": "Thank you!",
        "welcome": "Welcome!",
    },
    Language.TWI: {
        "hello": "Akwaaba!",  # Welcome
        "good_morning": "Maakye!",
        "good_afternoon": "Maaha!",
        "good_evening": "Maadwo!",
        "goodbye": "Nante yie!",  # Walk well
        "thank_you": "Medaase!",
        "welcome": "Akwaaba!",
    },
    Language.GA: {
        "hello": "Ojekoo!",
        "good_morning": "Ojaadoo!",  # Good morning
        "good_afternoon": "Ojuunoo!",  # Good afternoon
        "good_evening": "Ojuunoo!",  # Good evening (same as afternoon)
        "goodbye": "Oyiwala doon!",  # Safe journey
        "thank_you": "Oyiwala doon!",
        "welcome": "Ojekoo!",
    },
    Language.EWE: {
        "hello": "Woezor!",  # Welcome
        "good_morning": "Ndi na mi!",
        "good_afternoon": "Ndo na mi!",
        "good_evening": "Fie na mi!",
        "goodbye": "Mia dogo!",
        "thank_you": "Akpe!",
        "welcome": "Woezor!",
    },
    Language.DAGBANI: {
        "hello": "Despa!",  # Hello
        "good_morning": "Dasuba!",  # Good morning
        "good_afternoon": "Antire!",  # Good afternoon
        "good_evening": "Aniwula!",  # Good evening
        "goodbye": "Naawuni sagdi!",
        "thank_you": "Naawuni sagdi!",
        "welcome": "Despa!",
    },
    Language.HAUSA: {
        "hello": "Sannu!",
        "good_morning": "Ina kwana!",
        "good_afternoon": "Ina wuni!",
        "good_evening": "Ina yini!",
        "goodbye": "Sai anjima!",
        "thank_you": "Na gode!",
        "welcome": "Maraba!",
    },
}

# Weather-related phrases by language
WEATHER_PHRASES: dict[Language, dict[str, str]] = {
    Language.ENGLISH: {
        "sunny": "Sunny",
        "cloudy": "Cloudy",
        "rainy": "Rainy",
        "hot": "Hot",
        "cool": "Cool",
        "humid": "Humid",
        "windy": "Windy",
        "weather_in": "Weather in",
        "forecast_for": "Forecast for",
        "temperature": "Temperature",
        "humidity": "Humidity",
        "wind": "Wind",
    },
    Language.TWI: {
        "sunny": "Owia rebɔ",  # Sun is shining
        "cloudy": "Wim ayɛ kusuu",  # Sky is dark
        "rainy": "Osuo retɔ",  # Rain is falling
        "hot": "Ahuhuro",
        "cool": "Awɔw",
        "humid": "Nsuo wɔ wim",  # Moisture in air
        "windy": "Mframa rebɔ",  # Wind is blowing
        "weather_in": "Wim tebea wɔ",
        "forecast_for": "Wim tebea a ɛbɛba",
        "temperature": "Ahuhuro",
        "humidity": "Nsuo wɔ wim",
        "wind": "Mframa",
    },
    Language.GA: {
        "sunny": "Hwɛ le ba",  # Sun is coming
        "cloudy": "Mlitso le ba",  # Clouds coming
        "rainy": "Nuu le nu",  # Rain is falling
        "hot": "Lɛ sho",  # It's hot
        "cool": "Lɛ gbee",  # It's cool
        "humid": "Nuu ni",
        "windy": "Efɔ",
        "weather_in": "Hewale ni",
        "forecast_for": "Hewale ba",
        "temperature": "Hewale",
        "humidity": "Nuu ni",
        "wind": "Efɔ",
    },
    Language.EWE: {
        "sunny": "Ɣe le dɔm",  # Sun is hot
        "cloudy": "Aliwo le dzim",  # Clouds in sky
        "rainy": "Tsi dzɔ",  # Rain has come
        "hot": "Dzɔ",  # Hot
        "cool": "Fa",  # Cool
        "humid": "Tsi le yam",
        "windy": "Ya le fɔm",  # Wind is blowing
        "weather_in": "Yame le",
        "forecast_for": "Yame",
        "temperature": "Dzɔdzɔ",
        "humidity": "Tsi",
        "wind": "Ya",
    },
    Language.DAGBANI: {
        "sunny": "Wuntaŋa yɛla",  # Sun matters
        "cloudy": "Saŋa mali",  # Clouds present
        "rainy": "Saa niŋ",  # Rain falling
        "hot": "Gurli",  # Hot
        "cool": "Nyɛm",  # Cool
        "humid": "Kom ni",
        "windy": "Puuni",  # Windy
        "weather_in": "Saŋa ka",
        "forecast_for": "Saŋa",
        "temperature": "Gurli",
        "humidity": "Kom",
        "wind": "Puuni",
    },
    Language.HAUSA: {
        "sunny": "Rana tana haskaka",  # Sun is shining
        "cloudy": "Girgije",  # Cloudy
        "rainy": "Ruwan sama",  # Rain
        "hot": "Zafi",  # Hot
        "cool": "Sanyi",  # Cool
        "humid": "Rigar iska",
        "windy": "Iska",  # Wind
        "weather_in": "Yanayi a",
        "forecast_for": "Hasashen yanayi",
        "temperature": "Zafin iska",
        "humidity": "Rigar iska",
        "wind": "Iska",
    },
}

# Tips and advice in local languages
TIPS: dict[Language, dict[str, str]] = {
    Language.ENGLISH: {
        "stay_hydrated": "Stay hydrated!",
        "carry_umbrella": "Carry an umbrella!",
        "good_for_farming": "Good day for farming!",
        "avoid_fieldwork": "Avoid fieldwork in peak heat.",
        "protect_crops": "Protect your crops from rain.",
    },
    Language.TWI: {
        "stay_hydrated": "Nom nsuo!",  # Drink water
        "carry_umbrella": "Fa kyinii!",  # Take umbrella
        "good_for_farming": "Ɛda pa ma afuom adwuma!",
        "avoid_fieldwork": "Mfa ahuhuro mu nkɔ afuom.",
        "protect_crops": "Bɔ w'afuom nnua ho ban.",
    },
    Language.GA: {
        "stay_hydrated": "Nu nuu!",  # Drink water
        "carry_umbrella": "Tse kyinii!",
        "good_for_farming": "Gbɛjɛ nyɔŋmɔ agbo!",
        "avoid_fieldwork": "Mba hwɛ shi agbo ni.",
        "protect_crops": "Kɛ naami shi.",
    },
    Language.EWE: {
        "stay_hydrated": "No tsi!",  # Drink water
        "carry_umbrella": "Tsɔ agbale!",
        "good_for_farming": "Ŋkeke nyui na agbledede!",
        "avoid_fieldwork": "Megayi agble o le dzɔ me.",
        "protect_crops": "Dzɔ ame le wò nu dzi.",
    },
    Language.DAGBANI: {
        "stay_hydrated": "Nyu kom!",  # Drink water
        "carry_umbrella": "Di laŋ!",
        "good_for_farming": "Dabisili bee suhudoo!",
        "avoid_fieldwork": "Da saa ka gurli.",
        "protect_crops": "Che ni bindirigu.",
    },
    Language.HAUSA: {
        "stay_hydrated": "Sha ruwa!",  # Drink water
        "carry_umbrella": "Ɗauki laima!",
        "good_for_farming": "Kyakkyawan rana don noma!",
        "avoid_fieldwork": "Ka guji aikin gona a lokacin zafi.",
        "protect_crops": "Ka kare amfanin gonarka.",
    },
}

# City to language mapping (regional defaults)
CITY_LANGUAGE_MAP: dict[str, Language] = {
    # Greater Accra - Ga (but Twi widely spoken)
    "accra": Language.GA,
    "tema": Language.GA,
    "madina": Language.GA,
    "ashaiman": Language.GA,
    "kasoa": Language.TWI,  # More Twi speakers

    # Ashanti Region - Twi
    "kumasi": Language.TWI,
    "obuasi": Language.TWI,
    "mampong": Language.TWI,
    "ejisu": Language.TWI,
    "bekwai": Language.TWI,
    "konongo": Language.TWI,

    # Central Region - Twi/Fante (using Twi as base)
    "cape coast": Language.TWI,
    "winneba": Language.TWI,
    "saltpond": Language.TWI,
    "mankessim": Language.TWI,
    "elmina": Language.TWI,

    # Eastern Region - Twi
    "koforidua": Language.TWI,
    "nkawkaw": Language.TWI,
    "suhum": Language.TWI,
    "akosombo": Language.TWI,
    "akim oda": Language.TWI,

    # Western Region - Twi
    "takoradi": Language.TWI,
    "sekondi": Language.TWI,
    "tarkwa": Language.TWI,
    "axim": Language.TWI,

    # Volta Region - Ewe
    "ho": Language.EWE,
    "hohoe": Language.EWE,
    "keta": Language.EWE,
    "aflao": Language.EWE,
    "kpando": Language.EWE,

    # Northern Region - Dagbani
    "tamale": Language.DAGBANI,
    "yendi": Language.DAGBANI,
    "savelugu": Language.DAGBANI,
    "bimbilla": Language.DAGBANI,

    # Upper East - Hausa widely used
    "bolgatanga": Language.HAUSA,
    "navrongo": Language.HAUSA,
    "bawku": Language.HAUSA,

    # Upper West
    "wa": Language.DAGBANI,

    # Brong-Ahafo - Twi
    "sunyani": Language.TWI,
    "techiman": Language.TWI,
    "berekum": Language.TWI,
    "wenchi": Language.TWI,
}


def detect_language_from_city(city: str | None) -> Language:
    """
    Detect the appropriate language based on city/region.

    Args:
        city: City name (case-insensitive).

    Returns:
        Detected Language enum, defaults to English.
    """
    if not city:
        return Language.ENGLISH

    city_lower = city.lower().strip()
    return CITY_LANGUAGE_MAP.get(city_lower, Language.ENGLISH)


def get_time_based_greeting_key() -> str:
    """
    Get the appropriate greeting key based on current time.

    Returns:
        Greeting key: "good_morning", "good_afternoon", or "good_evening".
    """
    current_hour = datetime.now().hour

    if 5 <= current_hour < 12:
        return "good_morning"
    elif 12 <= current_hour < 17:
        return "good_afternoon"
    else:
        return "good_evening"


def get_greeting(
    language: Language,
    time_of_day: str | None = None,
) -> str:
    """
    Get a greeting in the specified language.

    Args:
        language: Target language.
        time_of_day: Optional time key ("morning", "afternoon", "evening").
                     If None, auto-detects based on current time.

    Returns:
        Greeting string in the specified language.
    """
    # Map time_of_day strings to greeting keys
    time_key_map = {
        "morning": "good_morning",
        "afternoon": "good_afternoon",
        "evening": "good_evening",
        "night": "good_evening",
    }

    if time_of_day:
        greeting_key = time_key_map.get(time_of_day.lower(), "hello")
    else:
        greeting_key = get_time_based_greeting_key()

    greetings = GREETINGS.get(language, GREETINGS[Language.ENGLISH])
    return greetings.get(greeting_key, greetings["hello"])


def get_localized_greeting(
    city: str | None = None,
    preferred_language: str | None = None,
    time_of_day: str | None = None,
) -> str:
    """
    Get a localized greeting based on city or user preference.

    Args:
        city: City name for regional language detection.
        preferred_language: User's preferred language code.
        time_of_day: Optional time of day.

    Returns:
        Localized greeting string.
    """
    # User preference takes priority
    if preferred_language:
        try:
            language = Language(preferred_language)
        except ValueError:
            language = detect_language_from_city(city)
    else:
        language = detect_language_from_city(city)

    return get_greeting(language, time_of_day)


def get_weather_phrase(
    phrase_key: str,
    language: Language = Language.ENGLISH,
) -> str:
    """
    Get a weather-related phrase in the specified language.

    Args:
        phrase_key: Key for the phrase (e.g., "sunny", "rainy").
        language: Target language.

    Returns:
        Localized weather phrase.
    """
    phrases = WEATHER_PHRASES.get(language, WEATHER_PHRASES[Language.ENGLISH])
    return phrases.get(phrase_key, phrase_key.title())


def get_tip(
    tip_key: str,
    language: Language = Language.ENGLISH,
) -> str:
    """
    Get a tip/advice in the specified language.

    Args:
        tip_key: Key for the tip (e.g., "stay_hydrated", "carry_umbrella").
        language: Target language.

    Returns:
        Localized tip string.
    """
    tips = TIPS.get(language, TIPS[Language.ENGLISH])
    return tips.get(tip_key, tips.get("stay_hydrated", "Stay safe!"))


def get_localized_weather_intro(
    city: str,
    preferred_language: str | None = None,
) -> str:
    """
    Get a localized weather introduction for a city.

    Args:
        city: City name.
        preferred_language: User's preferred language code.

    Returns:
        Localized intro like "Maakye! 🌤️ Kumasi weather..."
    """
    if preferred_language:
        try:
            language = Language(preferred_language)
        except ValueError:
            language = detect_language_from_city(city)
    else:
        language = detect_language_from_city(city)

    greeting = get_greeting(language)
    weather_in = get_weather_phrase("weather_in", language)

    return f"{greeting} {weather_in} {city.title()}..."


def format_localized_response(
    city: str,
    temperature: float,
    description: str,
    humidity: int,
    wind_speed: float,
    tip: str,
    preferred_language: str | None = None,
    condition_emoji: str = "🌡️",
) -> str:
    """
    Format a complete localized weather response.

    Args:
        city: City name.
        temperature: Temperature in Celsius.
        description: Weather description.
        humidity: Humidity percentage.
        wind_speed: Wind speed in km/h.
        tip: Weather tip (in English, will be translated).
        preferred_language: User's preferred language code.
        condition_emoji: Weather condition emoji.

    Returns:
        Fully formatted, localized weather response.
    """
    if preferred_language:
        try:
            language = Language(preferred_language)
        except ValueError:
            language = detect_language_from_city(city)
    else:
        language = detect_language_from_city(city)

    greeting = get_greeting(language)
    temp_word = get_weather_phrase("temperature", language)
    humidity_word = get_weather_phrase("humidity", language)
    wind_word = get_weather_phrase("wind", language)

    # Build response
    response = f"{greeting}\n\n"
    response += f"{condition_emoji} *{city.title()}*\n\n"
    response += f"🌡️ {temp_word}: {temperature:.0f}°C\n"
    response += f"💧 {humidity_word}: {humidity}%\n"
    response += f"💨 {wind_word}: {wind_speed:.0f} km/h\n\n"
    response += f"_💡 {tip}_"

    return response


# Language names for display
LANGUAGE_NAMES: dict[Language, str] = {
    Language.ENGLISH: "English",
    Language.TWI: "Twi (Akan)",
    Language.GA: "Ga",
    Language.EWE: "Ewe",
    Language.DAGBANI: "Dagbani",
    Language.HAUSA: "Hausa",
}


def get_language_options() -> list[dict[str, str]]:
    """
    Get list of available languages for user selection.

    Returns:
        List of dicts with 'code' and 'name' keys.
    """
    return [
        {"code": lang.value, "name": name}
        for lang, name in LANGUAGE_NAMES.items()
    ]
