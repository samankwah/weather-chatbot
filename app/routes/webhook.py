"""Twilio webhook endpoint for WhatsApp messages."""

from fastapi import APIRouter, Form, Header, HTTPException, Request
from twilio.request_validator import RequestValidator

from app.config import get_settings
from app.models.schemas import LocationInput, WebhookResponse
from app.services.location import parse_webhook_location
from app.services.messaging import (
    format_error_message,
    format_help_message,
    format_weather_message,
    get_messaging_provider,
)
from app.services.weather import get_weather_for_location

router = APIRouter()


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

    response_message = await process_message(Body, Latitude, Longitude)

    messaging_provider = get_messaging_provider()
    sent = messaging_provider.send_message(From, response_message)

    return WebhookResponse(
        success=sent,
        message="Message sent" if sent else "Failed to send message",
    )


async def process_message(
    message: str,
    latitude: str | None = None,
    longitude: str | None = None,
) -> str:
    """
    Process user message and generate appropriate response.

    Args:
        message: User's message text.
        latitude: GPS latitude string (from location share).
        longitude: GPS longitude string (from location share).

    Returns:
        Response message string.
    """
    message_lower = message.strip().lower()
    help_triggers = ["hi", "hello", "help", "start", "hey"]

    if message_lower in help_triggers:
        return format_help_message()

    location = parse_webhook_location(latitude, longitude, message)
    weather_response = await get_weather_for_location(location)

    if weather_response.success and weather_response.data:
        return format_weather_message(weather_response.data)

    if weather_response.error_message:
        return format_error_message(weather_response.error_message)

    return format_help_message()
