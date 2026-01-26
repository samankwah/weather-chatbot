"""Twilio webhook endpoint for WhatsApp messages."""

import logging
from datetime import datetime

from fastapi import APIRouter, Form, Header, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.models.ai_schemas import (
    AgroMetData,
    ForecastData,
    GDDData,
    IntentExtraction,
    QueryType,
    SeasonalForecast,
    SeasonalOutlook,
    UserContext,
)
from app.models.schemas import WebhookResponse, WeatherData
from app.services.ai import get_ai_provider
from app.services.agromet import (
    get_accumulated_gdd,
    get_agromet_data,
    get_crop_info,
    get_irrigation_advice,
    get_seasonal_outlook,
)
from app.services.forecast import get_extended_forecast, get_forecast
from app.services.interactive import (
    convert_button_to_message,
    parse_button_payload,
)
from app.services.localization import get_localized_greeting
from app.services.memory import get_memory_store
from app.services.messaging import (
    get_complexity_for_query,
    get_messaging_provider,
    simulate_typing_delay,
)
from app.services.location import (
    create_pending_clarification,
    get_location_prompt_message,
    handle_clarification_response,
    resolve_location,
)
from app.services.normalizer import (
    extract_normalized_entities,
    fuzzy_match_city,
    normalize_message,
    parse_complex_query,
)
from app.services.seasonal import get_seasonal_forecast
from app.services.transcription import get_transcription_provider
from app.services.weather import get_weather, get_weather_by_coordinates

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limiter - 20 requests per minute per IP
limiter = Limiter(key_func=get_remote_address)


async def validate_twilio_request(
    request: Request,
    x_twilio_signature: str | None = Header(default=None),
) -> bool:
    """
    Validate that the request came from Twilio.

    Args:
        request: FastAPI request object.
        x_twilio_signature: Twilio signature header.

    Returns:
        True if request is valid.

    Raises:
        HTTPException: If validation fails.
    """
    if not x_twilio_signature:
        raise HTTPException(status_code=400, detail="Missing Twilio signature")

    settings = get_settings()
    validator = RequestValidator(settings.twilio_auth_token)

    url = str(request.url)
    form_data = await request.form()
    params = {key: value for key, value in form_data.items()}

    if not validator.validate(url, params, x_twilio_signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    return True


@router.post("/webhook", response_model=WebhookResponse)
@limiter.limit("20/minute")
async def twilio_webhook(
    request: Request,
    Body: str = Form(default=""),
    From: str = Form(...),
    To: str = Form(...),
    MessageSid: str = Form(...),
    AccountSid: str = Form(...),
    NumMedia: int = Form(default=0),
    ProfileName: str | None = Form(default=None),
    Latitude: str | None = Form(default=None),
    Longitude: str | None = Form(default=None),
    ButtonPayload: str | None = Form(default=None),
    MediaUrl0: str | None = Form(default=None),
    MediaContentType0: str | None = Form(default=None),
    x_twilio_signature: str | None = Header(default=None),
) -> WebhookResponse:
    """
    Handle incoming WhatsApp messages from Twilio.

    Args:
        request: FastAPI request object.
        Body: Message content.
        From: Sender's WhatsApp number.
        To: Recipient's WhatsApp number.
        MessageSid: Twilio message SID.
        AccountSid: Twilio account SID.
        NumMedia: Number of media attachments.
        ProfileName: Sender's WhatsApp profile name.
        Latitude: GPS latitude (when user shares location).
        Longitude: GPS longitude (when user shares location).
        ButtonPayload: Payload from interactive button clicks.
        MediaUrl0: URL of the first media attachment.
        MediaContentType0: Content type of the first media attachment.
        x_twilio_signature: Twilio request signature.

    Returns:
        WebhookResponse indicating success or failure.
    """
    # TODO: Re-enable for production
    # await validate_twilio_request(request, x_twilio_signature)

    settings = get_settings()

    # DEBUG: Log media parameters to diagnose voice message handling
    logger.info(f"Webhook received - NumMedia: {NumMedia}, MediaUrl0: {MediaUrl0}, MediaContentType0: {MediaContentType0}")

    # Parse coordinates if shared
    lat: float | None = None
    lon: float | None = None
    if Latitude and Longitude:
        try:
            lat = float(Latitude)
            lon = float(Longitude)
        except ValueError:
            pass

    # Handle voice message transcription
    message_to_process = Body
    if NumMedia > 0 and MediaUrl0 and MediaContentType0:
        # Check if it's an audio message (voice note)
        if MediaContentType0.startswith("audio/"):
            logger.info(f"Received voice message from {From}: {MediaContentType0}")
            transcription_provider = get_transcription_provider()

            # Twilio media URLs require authentication
            twilio_auth = (settings.twilio_account_sid, settings.twilio_auth_token)

            result = await transcription_provider.transcribe_audio(
                audio_url=MediaUrl0,
                auth=twilio_auth,
            )

            if result.success and result.text:
                message_to_process = result.text
                logger.info(f"Voice transcription: '{result.text[:100]}...'")
            else:
                # Transcription failed - send helpful error message
                messaging_provider = get_messaging_provider()
                error_response = (
                    "🎤 I received your voice message but couldn't transcribe it. "
                    "Please try again or send a text message instead.\n\n"
                    "You can ask things like:\n"
                    "• What's the weather in Accra?\n"
                    "• Will it rain tomorrow?\n"
                    "• Weather forecast for Kumasi"
                )
                messaging_provider.send_message(From, error_response)
                return WebhookResponse(
                    success=False,
                    message=f"Transcription failed: {result.error}",
                )
        else:
            # Non-audio media (image, video, etc.)
            logger.info(f"Received non-audio media from {From}: {MediaContentType0}")
            # If there's text with the media, use that
            if not Body:
                messaging_provider = get_messaging_provider()
                messaging_provider.send_message(
                    From,
                    "I can only process voice messages and text. "
                    "Please send me a text or voice message about the weather!",
                )
                return WebhookResponse(
                    success=True,
                    message="Non-audio media received",
                )

    # Handle button payload - convert to natural language message
    if ButtonPayload:
        # Get user's last city for context
        memory_store = get_memory_store()
        user_context = memory_store.get_context(From)
        last_city = user_context.last_city if user_context else None
        message_to_process = convert_button_to_message(ButtonPayload, last_city)
        logger.info(f"Button payload '{ButtonPayload}' converted to: '{message_to_process}'")

    response_message, query_type = await process_message(
        message_to_process, From, lat, lon, ProfileName
    )

    # Simulate typing delay for more natural UX
    complexity = get_complexity_for_query(query_type)
    await simulate_typing_delay(len(response_message), complexity)

    messaging_provider = get_messaging_provider()
    sent = messaging_provider.send_message(From, response_message)

    return WebhookResponse(
        success=sent,
        message="Message sent" if sent else "Failed to send message",
    )


def is_follow_up_query(user_context: UserContext) -> bool:
    """
    Check if this is a follow-up query within the conversation session.

    A query is considered a follow-up if:
    1. There's a previous interaction within the last 5 minutes
    2. There's at least one previous exchange in conversation history

    Args:
        user_context: User's conversation context.

    Returns:
        True if this is a follow-up query, False otherwise.
    """
    if not user_context.last_interaction:
        return False

    # Check if last interaction was within 5 minutes
    time_since_last = datetime.now() - user_context.last_interaction
    if time_since_last.total_seconds() > 300:  # 5 minutes
        return False

    # Check if there's conversation history (at least one exchange)
    return len(user_context.conversation_history) >= 2


async def process_message(
    message: str,
    user_id: str,
    latitude: float | None = None,
    longitude: float | None = None,
    profile_name: str | None = None,
) -> tuple[str, str]:
    """
    Process user message using AI and route to appropriate service.

    Args:
        message: User's message text.
        user_id: User's WhatsApp number.
        latitude: GPS latitude (from location share).
        longitude: GPS longitude (from location share).
        profile_name: User's WhatsApp profile name.

    Returns:
        Tuple of (response_message, query_type).
    """
    memory_store = get_memory_store()
    ai_provider = get_ai_provider()

    # Get or create user context
    user_context = memory_store.get_or_create_context(user_id)

    # Detect if this is a follow-up query (for omitting greeting)
    skip_greeting = is_follow_up_query(user_context)

    # Update context with profile name if available
    if profile_name and (not user_context.user_name or user_context.user_name != profile_name):
        memory_store.update_context(user_id, user_name=profile_name)
        user_context = memory_store.get_context(user_id)

    # Handle WhatsApp location share - store as home location
    if latitude is not None and longitude is not None:
        from app.services.geocoding import reverse_geocode
        location_name = await reverse_geocode(latitude, longitude)
        memory_store.set_home_location(user_id, latitude, longitude, location_name)
        user_context = memory_store.get_context(user_id)
        logger.info(f"Saved home location for {user_id}: {location_name} ({latitude}, {longitude})")

    # Check for pending clarification response (user selecting option 1, 2, 3)
    pending_clarification = memory_store.get_pending_clarification(user_id)
    if pending_clarification:
        resolved_location = handle_clarification_response(message, pending_clarification)
        if resolved_location:
            # User selected a valid option - clear clarification and proceed
            memory_store.clear_pending_clarification(user_id)
            # Fetch weather for the selected location
            weather_response = await get_weather_by_coordinates(
                resolved_location.latitude,
                resolved_location.longitude,
            )
            if weather_response.success and weather_response.data:
                memory_store.add_user_message(user_id, message)
                # Generate AI response for the weather data
                clarification_intent = IntentExtraction(
                    query_type=QueryType.WEATHER,
                    city=resolved_location.city,
                )
                response = await ai_provider.generate_response(
                    intent=clarification_intent,
                    weather_data=weather_response.data,
                    user_context=user_context,
                )
                memory_store.add_assistant_message(user_id, response)
                if resolved_location.city:
                    memory_store.update_context(user_id, city=resolved_location.city)
                return response, QueryType.WEATHER.value
            else:
                return (
                    f"I found {resolved_location.city}, but couldn't get the weather. "
                    "Please try again.",
                    "weather",
                )

    # Add user message to conversation history
    memory_store.add_user_message(user_id, message)

    # --- TEXT NORMALIZATION ---
    # Normalize slang, typos, and Ghanaian Pidgin before processing
    normalized_message = normalize_message(message)
    logger.debug(f"Normalized message: '{message}' -> '{normalized_message}'")

    # Try complex query pattern matching first
    complex_params = parse_complex_query(normalized_message)
    if complex_params:
        logger.debug(f"Complex query detected: {complex_params}")

    # Extract normalized entities (city, crop) with fuzzy matching
    entities = extract_normalized_entities(normalized_message)
    if entities.get("city"):
        logger.debug(f"Extracted city: {entities['city']}")
    if entities.get("crop"):
        logger.debug(f"Extracted crop: {entities['crop']}")

    # Extract intent using AI (with normalized message)
    intent = await ai_provider.extract_intent(normalized_message, user_context)

    # Override intent with complex query params if found
    if complex_params:
        if complex_params.get("city") and not intent.city:
            intent.city = complex_params["city"]
        if complex_params.get("crop") and not intent.crop:
            intent.crop = complex_params["crop"]

    # Use fuzzy-matched entities as fallback
    if not intent.city and entities.get("city"):
        intent.city = entities["city"]
    if not intent.crop and entities.get("crop"):
        intent.crop = entities["crop"]

    # Only apply fuzzy matching for known corrections (typos, abbreviations)
    # Skip similarity-based matching - let geocoding handle unknown cities
    # This prevents incorrect matches like "Goaso" -> "Bogoso"
    if intent.city:
        from app.services.normalizer import CITY_CORRECTIONS, GHANA_CITIES
        input_lower = intent.city.lower().strip()
        # Only correct if it's a known typo/correction or exact match
        if input_lower in CITY_CORRECTIONS:
            intent.city = CITY_CORRECTIONS[input_lower].title()
        elif input_lower in GHANA_CITIES:
            intent.city = input_lower.title()

    # --- LOCATION RESOLUTION ---
    # Resolve location using geocoding with priority:
    # 1. GPS coordinates from WhatsApp location share
    # 2. Geocoded city name from user's message
    # 3. Stored home location from context
    # 4. Prompt user to share location
    location_result = await resolve_location(
        intent_city=intent.city,
        latitude=latitude,
        longitude=longitude,
        user_context=user_context,
    )

    # Handle location prompt (new user with no location)
    if location_result.needs_location_prompt:
        response = location_result.clarification_message or get_location_prompt_message()
        memory_store.add_assistant_message(user_id, response)
        return response, "location_prompt"

    # Handle location clarification (ambiguous place name)
    if location_result.needs_clarification:
        # Store pending clarification state
        if location_result.clarification_options:
            pending = create_pending_clarification(
                intent.city or "unknown",
                location_result.clarification_options,
            )
            memory_store.set_pending_clarification(user_id, pending)
        response = location_result.clarification_message or "Please select a location."
        memory_store.add_assistant_message(user_id, response)
        return response, "location_clarification"

    # Use resolved location coordinates
    final_lat = location_result.location.latitude if location_result.location else None
    final_lon = location_result.location.longitude if location_result.location else None
    resolved_city = location_result.location.city if location_result.location else None

    # Update intent city with resolved name if we geocoded it
    if resolved_city and not intent.city:
        intent.city = resolved_city

    # Route based on query type and fetch data
    weather_data: WeatherData | None = None
    forecast_data: ForecastData | None = None
    agromet_data: AgroMetData | None = None
    gdd_data: GDDData | None = None
    seasonal_data: SeasonalOutlook | None = None
    seasonal_forecast_data: SeasonalForecast | None = None

    try:
        if intent.query_type == QueryType.GREETING:
            pass  # No data needed for greeting

        elif intent.query_type == QueryType.HELP:
            pass  # No data needed for help

        elif intent.query_type == QueryType.WEATHER:
            weather_data = await _get_weather_data(intent, final_lat, final_lon)
            if weather_data:
                # Use the user's requested/geocoded city name, not the API's nearest city
                if resolved_city:
                    weather_data.city = resolved_city
                memory_store.update_context(user_id, city=weather_data.city)

        elif intent.query_type == QueryType.FORECAST:
            forecast_data = await _get_forecast_data(intent, final_lat, final_lon)

        elif intent.query_type == QueryType.ETO:
            agromet_response = await get_agromet_data(final_lat, final_lon, 7)
            if agromet_response.success and agromet_response.data:
                agromet_data = agromet_response.data

        elif intent.query_type == QueryType.GDD:
            crop = intent.crop or "maize"
            gdd_data = await get_accumulated_gdd(final_lat, final_lon, crop)
            if crop and crop != "maize":
                memory_store.update_context(user_id, crop=crop)

        elif intent.query_type == QueryType.SOIL:
            agromet_response = await get_agromet_data(final_lat, final_lon, 1)
            if agromet_response.success and agromet_response.data:
                agromet_data = agromet_response.data

        elif intent.query_type == QueryType.SEASONAL:
            seasonal_response = await get_seasonal_outlook(final_lat, final_lon)
            if seasonal_response.success and seasonal_response.data:
                seasonal_data = seasonal_response.data

        elif intent.query_type in [
            QueryType.SEASONAL_ONSET,
            QueryType.SEASONAL_CESSATION,
            QueryType.DRY_SPELL,
            QueryType.SEASON_LENGTH,
        ]:
            # Ghana-specific seasonal forecast with onset/cessation/dry spells
            seasonal_forecast_response = await get_seasonal_forecast(final_lat, final_lon)
            if seasonal_forecast_response.success and seasonal_forecast_response.data:
                seasonal_forecast_data = seasonal_forecast_response.data

        elif intent.query_type == QueryType.CROP_ADVICE:
            # Get comprehensive data for crop advice
            weather_data = await _get_weather_data(intent, final_lat, final_lon)
            if weather_data and resolved_city:
                weather_data.city = resolved_city
            agromet_response = await get_agromet_data(final_lat, final_lon, 7)
            if agromet_response.success and agromet_response.data:
                agromet_data = agromet_response.data
            if intent.crop:
                gdd_data = await get_accumulated_gdd(final_lat, final_lon, intent.crop)
            seasonal_response = await get_seasonal_outlook(final_lat, final_lon)
            if seasonal_response.success and seasonal_response.data:
                seasonal_data = seasonal_response.data

        elif intent.query_type == QueryType.DEKADAL:
            # Dekadal bulletins are typically from GMet - return info message
            agromet_response = await get_agromet_data(final_lat, final_lon, 10)
            if agromet_response.success and agromet_response.data:
                agromet_data = agromet_response.data

    except Exception as e:
        logger.error(f"Error fetching data for {intent.query_type}: {e}")

    # Generate AI response
    response = await ai_provider.generate_response(
        intent=intent,
        weather_data=weather_data,
        forecast_data=forecast_data,
        agromet_data=agromet_data,
        gdd_data=gdd_data,
        seasonal_data=seasonal_data,
        seasonal_forecast=seasonal_forecast_data,
        user_context=user_context,
        skip_greeting=skip_greeting,
    )

    # Add response to conversation history
    memory_store.add_assistant_message(user_id, response)

    # Update user city if extracted
    if intent.city:
        memory_store.update_context(user_id, city=intent.city)

    return response, intent.query_type.value


async def _get_weather_data(
    intent: IntentExtraction,
    latitude: float | None,
    longitude: float | None,
) -> WeatherData | None:
    """
    Get current weather data based on resolved coordinates.

    Note: This function now prioritizes coordinates over city names
    to ensure location-specific accuracy.
    """
    # Use resolved coordinates (required for accurate weather)
    if latitude is not None and longitude is not None:
        response = await get_weather_by_coordinates(latitude, longitude)
        if response.success and response.data:
            return response.data

    # Fallback to city name lookup (less accurate but better than nothing)
    if intent.city:
        response = await get_weather(intent.city)
        if response.success and response.data:
            return response.data

    # No location available
    return None


async def _get_forecast_data(
    intent: IntentExtraction,
    latitude: float,
    longitude: float,
) -> ForecastData | None:
    """Get forecast data based on intent time reference."""
    days_ahead = intent.time_reference.days_ahead

    if days_ahead <= 5:
        # Use OpenWeatherMap 5-day forecast
        response = await get_forecast(
            city=intent.city,
            latitude=latitude,
            longitude=longitude,
        )
    else:
        # Use Open-Meteo extended forecast
        response = await get_extended_forecast(latitude, longitude, days=days_ahead + 2)

    return response.data if response.success else None
