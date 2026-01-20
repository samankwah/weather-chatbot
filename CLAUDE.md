# Weather Chatbot - Development Guidelines

## Project Overview
WhatsApp-based weather chatbot for Accra, Ghana users. Uses Twilio Sandbox initially, designed for future Meta Cloud API migration.

## Tech Stack
- Python 3.11+
- FastAPI (async web framework)
- Twilio SDK (WhatsApp messaging)
- requests (weather API calls)
- pydantic-settings (configuration management)
- python-dotenv (environment variables)

## Code Style
- Use type hints on all functions
- Async/await for I/O operations
- Pydantic models for request/response validation
- Keep functions small and focused (<30 lines)
- Descriptive variable names, no abbreviations

## Project Structure
```
weather-chatbot/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry
│   ├── config.py            # Settings with pydantic-settings
│   ├── routes/
│   │   └── webhook.py       # Twilio webhook endpoint
│   ├── services/
│   │   ├── weather.py       # Weather API integration
│   │   └── messaging.py     # Message formatting & sending
│   └── models/
│       └── schemas.py       # Pydantic models
├── tests/
├── .env.example
├── requirements.txt
└── CLAUDE.md
```

## Environment Variables
- TWILIO_ACCOUNT_SID
- TWILIO_AUTH_TOKEN
- TWILIO_WHATSAPP_NUMBER
- WEATHER_API_KEY
- WEATHER_API_URL

## Conventions
- Weather units: Metric (Celsius, km/h)
- Default location: Accra, Ghana
- Response tone: Friendly, conversational
- Error messages: Helpful, non-technical

## Messaging Provider Abstraction
Design messaging service with interface pattern to allow swapping Twilio for Meta Cloud API without changing business logic.
