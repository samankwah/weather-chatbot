"""Text normalization service for handling slang, typos, and Ghanaian Pidgin."""

import re
from difflib import SequenceMatcher
from typing import Optional


# Ghanaian Pidgin, abbreviations, and common slang
SLANG_DICTIONARY: dict[str, str] = {
    # Abbreviations
    "tmrw": "tomorrow",
    "2moro": "tomorrow",
    "2morow": "tomorrow",
    "2morrow": "tomorrow",
    "wknd": "weekend",
    "wkd": "weekend",
    "nxt": "next",
    "wk": "week",
    "hr": "hour",
    "hrs": "hours",
    "min": "minutes",
    "mins": "minutes",
    "temp": "temperature",
    "temps": "temperatures",
    "wthr": "weather",
    "weathr": "weather",
    "pls": "please",
    "plz": "please",
    "thx": "thanks",
    "thnx": "thanks",
    "tnx": "thanks",
    "u": "you",
    "r": "are",
    "wat": "what",
    "wats": "what is",
    "whts": "what is",
    "hw": "how",
    "abt": "about",
    "cld": "could",
    "shld": "should",
    "wld": "would",
    "b4": "before",
    "4cast": "forecast",
    "4": "for",
    "2day": "today",
    "2nite": "tonight",
    "2night": "tonight",
    "2gether": "together",
    "bcz": "because",
    "bcs": "because",
    "bcoz": "because",
    "cuz": "because",
    "cos": "because",
    "dis": "this",
    "dat": "that",
    "dem": "them",
    "wen": "when",
    "whr": "where",
    "yr": "your",
    "gd": "good",
    "gud": "good",
    "mornin": "morning",
    "morn": "morning",
    "evenin": "evening",
    "evnin": "evening",
    "nite": "night",
    "aft": "afternoon",
    "aftnoon": "afternoon",

    # Ghanaian Pidgin
    "wey": "what is",
    "de": "the",
    "dey": "is",
    "deh": "is",
    "wetin": "what is",
    "abeg": "please",
    "abi": "or",
    "how far": "hello",
    "howfar": "hello",
    "chale": "friend",
    "charley": "friend",
    "charlie": "friend",
    "gyimi": "silly",
    "wahala": "problem",
    "na": "is",
    "sef": "even",
    "saf": "even",
    "e be": "it is",
    "e dey": "it is",
    "make i": "let me",
    "wey dey": "that is",
    "no be": "is not",
    "masa": "please",
    "paaa": "very",
    "too much": "very",
    "plenty": "a lot",
    "small small": "gradually",
    "sharp": "okay",
    "sharp sharp": "immediately",
    "yawa": "trouble",
    "kai": "wow",
    "eiii": "wow",
    "herh": "wow",
    "omo": "wow",
    "make": "let",
    "i go": "i will",
    "you go": "you will",
    "e go": "it will",
    "no worry": "don't worry",
    "no vex": "don't be angry",
    "i wan": "i want",
    "i dey": "i am",
    "we dey": "we are",
    "e good": "it is good",
    "e bad": "it is bad",

    # Weather-specific pidgin
    "sun dey": "it is sunny",
    "rain dey": "it is raining",
    "rain dey fall": "it is raining",
    "e go rain": "will it rain",
    "rain go fall": "will it rain",
    "weather set": "weather is good",
    "weather dey nice": "weather is nice",
    "sky dey dark": "it is cloudy",
    "sun dey shine": "it is sunny",
    "e dey hot": "it is hot",
    "e dey cold": "it is cold",
    "wind dey blow": "it is windy",

    # Question patterns
    "how weather": "what is the weather",
    "wetin be weather": "what is the weather",
    "how e dey": "how is it",
    "how weather be": "what is the weather",

    # Time expressions (pidgin)
    "for morning": "in the morning",
    "for evening": "in the evening",
    "for night": "at night",
    "dis time": "now",
    "dat time": "then",
    "wey dey come": "upcoming",
    "next tym": "next time",

    # Farming-related pidgin
    "plant time": "planting season",
    "ground wet": "soil is moist",
    "ground dry": "soil is dry",
    "when make i plant": "when should i plant",
    "i fit plant": "can i plant",

    # Location expressions
    "for my side": "in my area",
    "for here": "here",
    "for there": "there",
    "my area": "my location",
}

# Common crop name typos and corrections
CROP_CORRECTIONS: dict[str, str] = {
    "maze": "maize",
    "maiz": "maize",
    "mais": "maize",
    "corn": "maize",
    "kasava": "cassava",
    "cassva": "cassava",
    "casava": "cassava",
    "kassava": "cassava",
    "cocao": "cocoa",
    "cacao": "cocoa",
    "coca": "cocoa",
    "plaintain": "plantain",
    "plantian": "plantain",
    "plantin": "plantain",
    "platain": "plantain",
    "groundnuts": "groundnut",
    "groundnt": "groundnut",
    "groudnut": "groundnut",
    "g-nut": "groundnut",
    "gnut": "groundnut",
    "sorgum": "sorghum",
    "sorgh": "sorghum",
    "millet": "millet",
    "millit": "millet",
    "milt": "millet",
    "tomatoe": "tomato",
    "tomatoes": "tomato",
    "tomatoe": "tomato",
    "tomatos": "tomato",
    "pepper": "pepper",
    "peper": "pepper",
    "peppa": "pepper",
    "ric": "rice",
    "rce": "rice",
    "ryse": "rice",
    "yams": "yam",
    "yamm": "yam",
    "cowpeas": "cowpea",
    "cowpea": "cowpea",
    "cowp": "cowpea",
    "cow pea": "cowpea",
    "beans": "cowpea",
    "bean": "cowpea",
    "okra": "okra",
    "okro": "okra",
    "kontomire": "cocoyam",
    "kontomere": "cocoyam",
    "cocoyam": "cocoyam",
    "coco yam": "cocoyam",
    "taro": "cocoyam",
    "ginger": "ginger",
    "gingr": "ginger",
    "onion": "onion",
    "onions": "onion",
    "onin": "onion",
    "garlic": "garlic",
    "galic": "garlic",
    "watermelon": "watermelon",
    "water melon": "watermelon",
    "water-melon": "watermelon",
    "melon": "watermelon",
    "pineapple": "pineapple",
    "pine apple": "pineapple",
    "pine-apple": "pineapple",
    "pawpaw": "pawpaw",
    "papaya": "pawpaw",
    "paw paw": "pawpaw",
    "mango": "mango",
    "mangoes": "mango",
    "mangos": "mango",
    "orange": "orange",
    "oranges": "orange",
    "banana": "banana",
    "bananas": "banana",
    "bannana": "banana",
}

# Common Ghana city name typos and corrections
CITY_CORRECTIONS: dict[str, str] = {
    # Accra variations
    "accara": "accra",
    "acra": "accra",
    "accraa": "accra",
    "akra": "accra",
    "accrah": "accra",
    "acc": "accra",

    # Kumasi variations
    "kumassi": "kumasi",
    "kumase": "kumasi",
    "kumassy": "kumasi",
    "kumsi": "kumasi",
    "ksi": "kumasi",
    "kumashi": "kumasi",

    # Tamale variations
    "tamalle": "tamale",
    "tamal": "tamale",
    "tamali": "tamale",
    "tamalee": "tamale",
    "tml": "tamale",

    # Takoradi variations
    "takordi": "takoradi",
    "tacradi": "takoradi",
    "tadi": "takoradi",
    "sekondi-takoradi": "takoradi",
    "secondi": "sekondi",
    "sekodi": "sekondi",

    # Cape Coast variations
    "capecoast": "cape coast",
    "cape-coast": "cape coast",
    "capecost": "cape coast",
    "cape": "cape coast",
    "oguaa": "cape coast",

    # Bolgatanga variations
    "bolga": "bolgatanga",
    "bolg": "bolgatanga",
    "bolgat": "bolgatanga",
    "bolgatang": "bolgatanga",

    # Sunyani variations
    "sunyan": "sunyani",
    "sunyane": "sunyani",
    "sunyanyi": "sunyani",

    # Ho variations
    "hoo": "ho",

    # Koforidua variations
    "kofridua": "koforidua",
    "kofridwa": "koforidua",
    "koforidwa": "koforidua",
    "kofor": "koforidua",

    # Tema variations
    "temma": "tema",
    "teme": "tema",
    "temah": "tema",

    # Wa variations
    "waa": "wa",

    # Other cities
    "techman": "techiman",
    "techimann": "techiman",
    "nkwkw": "nkawkaw",
    "obuassi": "obuasi",
    "tarkwaa": "tarkwa",
    "winnaba": "winneba",
    "winniba": "winneba",
    "sweduro": "swedru",
    "saltpon": "saltpond",
    "ashaiman": "ashaiman",
    "ashaimen": "ashaiman",
    "kasoa": "kasoa",
    "madinna": "madina",
    "madna": "madina",
    "dansoman": "dansoman",
    "labade": "labadi",
    "labone": "labone",
    "osu": "osu",
    "kaneshie": "kaneshie",
    "kaneshi": "kaneshie",
    "circle": "kwame nkrumah circle",
}

# Ghana city names for validation
GHANA_CITIES: set[str] = {
    "accra", "kumasi", "tamale", "takoradi", "cape coast",
    "sunyani", "ho", "koforidua", "tema", "wa", "bolgatanga",
    "sekondi", "tarkwa", "obuasi", "techiman", "nkawkaw",
    "winneba", "saltpond", "swedru", "ashaiman", "kasoa",
    "madina", "dansoman", "labadi", "labone", "osu",
    "kaneshie", "kwame nkrumah circle", "legon", "east legon",
    "spintex", "airport", "dzorwulu", "achimota", "tesano",
    "adenta", "dodowa", "somanya", "akosombo", "kpong",
    "nsawam", "asamankese", "oda", "akim oda", "suhum",
    "begoro", "mpraeso", "aburi", "mampong", "akuapem",
    "axim", "half assini", "bibiani", "sefwi", "wassa",
    "assin fosu", "agona swedru", "elmina", "saltpond",
    "anomabu", "mankessim", "dunkwa", "prestea", "bogoso",
    "ahafo", "kenyasi", "bechem", "dormaa", "berekum",
    "wenchi", "navrongo", "bawku", "zebilla", "walewale",
    "yendi", "bimbilla", "salaga", "damango", "sawla",
    "bole", "tumu", "lawra", "jirapa", "nandom",
}

# Common Ghana crops for validation
GHANA_CROPS: set[str] = {
    "maize", "rice", "cassava", "cocoa", "tomato", "pepper",
    "yam", "groundnut", "sorghum", "millet", "plantain",
    "cowpea", "okra", "cocoyam", "ginger", "onion", "garlic",
    "watermelon", "pineapple", "pawpaw", "mango", "orange",
    "banana", "shea", "cashew", "oil palm", "coconut",
    "sugarcane", "cotton", "kenaf", "tobacco", "coffee",
}


def normalize_message(message: str) -> str:
    """
    Normalize a user message by converting slang, fixing typos.

    Args:
        message: Raw user message.

    Returns:
        Normalized message text.
    """
    if not message:
        return message

    # Convert to lowercase for processing
    normalized = message.lower().strip()

    # Replace slang terms (use word boundaries)
    for slang, replacement in SLANG_DICTIONARY.items():
        # Handle multi-word slang (like "how far")
        if " " in slang:
            normalized = normalized.replace(slang, replacement)
        else:
            # Use word boundary matching for single words
            pattern = r'\b' + re.escape(slang) + r'\b'
            normalized = re.sub(pattern, replacement, normalized)

    # Fix crop typos
    for typo, correction in CROP_CORRECTIONS.items():
        pattern = r'\b' + re.escape(typo) + r'\b'
        normalized = re.sub(pattern, correction, normalized)

    # Fix city typos
    for typo, correction in CITY_CORRECTIONS.items():
        pattern = r'\b' + re.escape(typo) + r'\b'
        normalized = re.sub(pattern, correction, normalized)

    return normalized


def fuzzy_match_city(
    input_city: str,
    threshold: float = 0.7,
) -> Optional[str]:
    """
    Fuzzy match a city name against known Ghana cities.

    Args:
        input_city: User-provided city name.
        threshold: Minimum similarity ratio (0.0 to 1.0).

    Returns:
        Matched city name or None if no match found.
    """
    if not input_city:
        return None

    input_lower = input_city.lower().strip()

    # Direct match check
    if input_lower in GHANA_CITIES:
        return input_lower.title()

    # Check city corrections first
    if input_lower in CITY_CORRECTIONS:
        corrected = CITY_CORRECTIONS[input_lower]
        return corrected.title()

    # Fuzzy matching
    best_match: Optional[str] = None
    best_ratio: float = 0.0

    for city in GHANA_CITIES:
        ratio = SequenceMatcher(None, input_lower, city).ratio()
        if ratio > best_ratio and ratio >= threshold:
            best_ratio = ratio
            best_match = city

    return best_match.title() if best_match else None


def fuzzy_match_crop(
    input_crop: str,
    threshold: float = 0.7,
) -> Optional[str]:
    """
    Fuzzy match a crop name against known Ghana crops.

    Args:
        input_crop: User-provided crop name.
        threshold: Minimum similarity ratio (0.0 to 1.0).

    Returns:
        Matched crop name or None if no match found.
    """
    if not input_crop:
        return None

    input_lower = input_crop.lower().strip()

    # Direct match check
    if input_lower in GHANA_CROPS:
        return input_lower

    # Check crop corrections first
    if input_lower in CROP_CORRECTIONS:
        return CROP_CORRECTIONS[input_lower]

    # Fuzzy matching
    best_match: Optional[str] = None
    best_ratio: float = 0.0

    for crop in GHANA_CROPS:
        ratio = SequenceMatcher(None, input_lower, crop).ratio()
        if ratio > best_ratio and ratio >= threshold:
            best_ratio = ratio
            best_match = crop

    return best_match


def extract_normalized_entities(message: str) -> dict[str, Optional[str]]:
    """
    Extract and normalize city and crop entities from a message.

    Args:
        message: User message (may contain slang/typos).

    Returns:
        Dict with 'city' and 'crop' keys (values may be None).
    """
    normalized = normalize_message(message)
    words = normalized.split()

    city: Optional[str] = None
    crop: Optional[str] = None

    # Look for cities - check multi-word cities first
    for multi_word_city in ["cape coast", "kwame nkrumah circle", "east legon"]:
        if multi_word_city in normalized:
            city = multi_word_city.title()
            break

    # Check single words for city matches
    if not city:
        for word in words:
            clean_word = word.strip("?,.")
            if clean_word in GHANA_CITIES:
                city = clean_word.title()
                break
            elif clean_word in CITY_CORRECTIONS:
                city = CITY_CORRECTIONS[clean_word].title()
                break

    # Fuzzy match if no exact match found
    if not city:
        for word in words:
            clean_word = word.strip("?,.")
            if len(clean_word) >= 3:  # Minimum 3 chars for fuzzy matching
                fuzzy_city = fuzzy_match_city(clean_word)
                if fuzzy_city:
                    city = fuzzy_city
                    break

    # Look for crops
    for word in words:
        clean_word = word.strip("?,.")
        if clean_word in GHANA_CROPS:
            crop = clean_word
            break
        elif clean_word in CROP_CORRECTIONS:
            crop = CROP_CORRECTIONS[clean_word]
            break

    # Fuzzy match crop if no exact match
    if not crop:
        for word in words:
            clean_word = word.strip("?,.")
            if len(clean_word) >= 3:
                fuzzy_crop = fuzzy_match_crop(clean_word)
                if fuzzy_crop:
                    crop = fuzzy_crop
                    break

    return {"city": city, "crop": crop}


# Complex query patterns for natural language parsing
# Each pattern is: (regex_pattern, extraction_dict)
# extraction_dict can have special keys ending in "_group" to extract from regex groups
COMPLEX_QUERY_PATTERNS: list[tuple[str, dict[str, str | int]]] = [
    # "how's the weather looking this weekend in Kumasi?"
    (r"how.*weather.*look.*weekend.*in\s+(\w+)", {"time": "weekend", "city_group": 1}),
    (r"how.*weather.*weekend.*in\s+(\w+)", {"time": "weekend", "city_group": 1}),

    # "will it rain tomorrow morning in Accra?"
    (r"will.*rain.*tomorrow.*morning.*in\s+(\w+)", {"query": "forecast", "time": "tomorrow morning", "city_group": 1}),
    (r"will.*rain.*tomorrow.*in\s+(\w+)", {"query": "forecast", "time": "tomorrow", "city_group": 1}),
    (r"will.*rain.*in\s+(\w+)", {"query": "forecast", "city_group": 1}),

    # "what's the forecast for next week?"
    (r"forecast.*for.*next\s+week", {"query": "forecast", "time": "next_week"}),
    (r"forecast.*next\s+week", {"query": "forecast", "time": "next_week"}),

    # "should I plant maize this week?"
    (r"should.*plant\s+(\w+).*this\s+week", {"query": "crop_advice", "crop_group": 1, "time": "this_week"}),
    (r"when.*plant\s+(\w+)", {"query": "crop_advice", "crop_group": 1}),

    # Pidgin patterns
    (r"e\s+go\s+rain.*for\s+(\w+)", {"query": "forecast", "city_group": 1}),
    (r"e\s+go\s+rain.*(\w+)", {"query": "forecast", "city_group": 1}),
    (r"rain\s+go\s+fall.*for\s+(\w+)", {"query": "forecast", "city_group": 1}),
    (r"weather.*for\s+(\w+).*tomorrow", {"query": "forecast", "city_group": 1, "time": "tomorrow"}),
    (r"weather.*for\s+(\w+)", {"query": "weather", "city_group": 1}),
]


def parse_complex_query(message: str) -> dict[str, str | None]:
    """
    Parse complex natural language queries to extract intent.

    Args:
        message: User message (may be normalized).

    Returns:
        Dict with extracted parameters (query, time, city, crop) or empty dict.
    """
    normalized = normalize_message(message)

    for pattern, extraction in COMPLEX_QUERY_PATTERNS:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            result: dict[str, str | None] = {}
            for key, value in extraction.items():
                if key.endswith("_group") and isinstance(value, int):
                    # Extract from regex group
                    base_key = key.replace("_group", "")
                    try:
                        extracted = match.group(value)
                        # Try to match the extracted value to a known city
                        if base_key == "city":
                            matched_city = fuzzy_match_city(extracted)
                            result[base_key] = matched_city if matched_city else extracted.title()
                        elif base_key == "crop":
                            matched_crop = fuzzy_match_crop(extracted)
                            result[base_key] = matched_crop if matched_crop else extracted.lower()
                        else:
                            result[base_key] = extracted
                    except IndexError:
                        pass
                else:
                    result[key] = str(value)
            return result

    return {}
