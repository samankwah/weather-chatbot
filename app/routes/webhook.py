"""Twilio webhook endpoint for WhatsApp messages."""

import logging

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
from app.services.memory import get_memory_store
from app.services.messaging import get_messaging_provider
from app.services.seasonal import get_seasonal_forecast
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
        x_twilio_signature: Twilio request signature.

    Returns:
        WebhookResponse indicating success or failure.
    """
    await validate_twilio_request(request, x_twilio_signature)

    # Parse coordinates if shared
    lat: float | None = None
    lon: float | None = None
    if Latitude and Longitude:
        try:
            lat = float(Latitude)
            lon = float(Longitude)
        except ValueError:
            pass

    response_message = await process_message(Body, From, lat, lon)

    messaging_provider = get_messaging_provider()
    sent = messaging_provider.send_message(From, response_message)

    return WebhookResponse(
        success=sent,
        message="Message sent" if sent else "Failed to send message",
    )


async def process_message(
    message: str,
    user_id: str,
    latitude: float | None = None,
    longitude: float | None = None,
) -> str:
    """
    Process user message using AI and route to appropriate service.

    Args:
        message: User's message text.
        user_id: User's WhatsApp number.
        latitude: GPS latitude (from location share).
        longitude: GPS longitude (from location share).

    Returns:
        Response message string.
    """
    settings = get_settings()
    memory_store = get_memory_store()
    ai_provider = get_ai_provider()

    # Get or create user context
    user_context = memory_store.get_or_create_context(user_id)

    # Update context with location if shared
    if latitude is not None and longitude is not None:
        memory_store.update_context(
            user_id,
            latitude=latitude,
            longitude=longitude,
        )
        user_context = memory_store.get_context(user_id)

    # Add user message to conversation history
    memory_store.add_user_message(user_id, message)

    # Extract intent using AI
    intent = await ai_provider.extract_intent(message, user_context)

    # Resolve location - use shared coords, then intent city, then user context, then defaults
    final_lat = latitude
    final_lon = longitude

    if final_lat is None or final_lon is None:
        if user_context and user_context.last_latitude and user_context.last_longitude:
            final_lat = user_context.last_latitude
            final_lon = user_context.last_longitude
        else:
            final_lat = settings.default_latitude
            final_lon = settings.default_longitude

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
            weather_data = await _get_weather_data(intent, latitude, longitude)
            if weather_data:
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
            weather_data = await _get_weather_data(intent, latitude, longitude)
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
    )

    # Add response to conversation history
    memory_store.add_assistant_message(user_id, response)

    # Update user city if extracted
    if intent.city:
        memory_store.update_context(user_id, city=intent.city)

    return response


async def _get_weather_data(
    intent: IntentExtraction,
    latitude: float | None,
    longitude: float | None,
) -> WeatherData | None:
    """Get current weather data based on intent and location."""
    settings = get_settings()

    # Try coordinates first
    if latitude is not None and longitude is not None:
        response = await get_weather_by_coordinates(latitude, longitude)
        if response.success and response.data:
            return response.data

    # Try city from intent
    if intent.city:
        response = await get_weather(intent.city)
        if response.success and response.data:
            return response.data

    # Fall back to default
    response = await get_weather(settings.default_location)
    return response.data if response.success else None


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
