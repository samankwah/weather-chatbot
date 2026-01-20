# Weather Chatbot

WhatsApp-based weather chatbot for Accra, Ghana users. Built with FastAPI and Twilio, designed for easy migration to Meta Cloud API.

## Features

- Get current weather for any city
- **GPS location sharing** - Share your WhatsApp location for precise weather
- Default location: Accra, Ghana
- Friendly, conversational responses
- Metric units (Celsius, km/h)
- Provider-agnostic messaging architecture (Twilio/Meta Cloud API ready)

## Prerequisites

- Python 3.11+
- Twilio account with WhatsApp Sandbox enabled
- OpenWeatherMap API key (free tier available)
- ngrok (for local development)

## Installation

1. Clone the repository:
```bash
cd weather-chatbot
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your credentials
```

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TWILIO_ACCOUNT_SID` | Your Twilio Account SID | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Your Twilio Auth Token | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp Sandbox number | `+14155238886` |
| `WEATHER_API_KEY` | OpenWeatherMap API key | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `WEATHER_API_URL` | Weather API endpoint URL | `https://api.openweathermap.org/data/2.5/weather` |
| `DEFAULT_CITY` | Default city for weather | `Accra` |
| `DEFAULT_COUNTRY` | Default country | `Ghana` |

### Getting API Keys

**Twilio:**
1. Sign up at [twilio.com](https://www.twilio.com)
2. Find your Account SID and Auth Token in the Console Dashboard
3. Enable WhatsApp Sandbox in Messaging > Try it out > Send a WhatsApp message

**OpenWeatherMap:**
1. Sign up at [openweathermap.org](https://openweathermap.org/api)
2. Generate an API key (free tier: 1,000 calls/day)

## Running the Application

### Local Development

Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

### Exposing to Internet (for Twilio Webhook)

Twilio needs a public URL to send webhooks. Use ngrok to expose your local server:

```bash
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`). This URL changes each time you restart ngrok (unless you have a paid plan).

## Twilio Sandbox Configuration

1. Go to [Twilio Console](https://console.twilio.com)
2. Navigate to **Messaging > Try it out > Send a WhatsApp message**
3. Follow instructions to join the Sandbox:
   - Send the join code (e.g., `join <word>-<word>`) to the Sandbox number via WhatsApp
4. In Sandbox settings, configure the webhook:
   - **When a message comes in**: `https://your-ngrok-url.ngrok.io/webhook`
   - **Method**: POST
5. Save the configuration

**Important:** Update the webhook URL every time you restart ngrok with a new URL.

## Usage

Send messages to your Twilio Sandbox WhatsApp number:

### Text Messages

| Message | Response |
|---------|----------|
| `weather` | Current weather in Accra (default) |
| `weather in Lagos` | Current weather in Lagos |
| `weather for Kumasi` | Current weather in Kumasi |
| `temperature at Nairobi` | Current weather in Nairobi |
| `Accra` | Current weather in Accra |
| `hello` or `help` | Usage instructions |

### GPS Location Sharing

Share your WhatsApp location for weather at your exact coordinates:

1. Open chat with the Sandbox number
2. Tap the attachment icon (📎)
3. Select **Location**
4. Choose **Send Your Current Location** or pick a location on the map
5. Receive weather for those exact coordinates

**Example response:**
```
🌤️ Weather in Accra

🌡️ Temperature: 28°C (Feels like 31°C)
☁️ Conditions: Scattered clouds
💧 Humidity: 74%
💨 Wind: 4.5 km/h

Stay cool! ☀️
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API information and status |
| `/health` | GET | Health check endpoint |
| `/webhook` | POST | Twilio webhook for incoming messages |
| `/docs` | GET | Swagger/OpenAPI documentation |
| `/redoc` | GET | ReDoc API documentation |

### Webhook Parameters

The `/webhook` endpoint accepts these Twilio form parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `Body` | string | Message text content |
| `From` | string | Sender's WhatsApp number |
| `To` | string | Recipient (your Twilio number) |
| `MessageSid` | string | Unique message identifier |
| `AccountSid` | string | Twilio account identifier |
| `Latitude` | string | GPS latitude (location shares) |
| `Longitude` | string | GPS longitude (location shares) |
| `ProfileName` | string | Sender's WhatsApp name |

## Testing

Run the test suite with pytest:

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=app

# Run specific test file
pytest tests/test_webhook.py -v
pytest tests/test_weather.py -v
pytest tests/test_location.py -v
```

### Test Coverage

- **test_webhook.py** - Webhook endpoint, message processing, Twilio validation
- **test_weather.py** - Weather API integration, response formatting
- **test_location.py** - Location parsing, GPS coordinates, city extraction

## Project Structure

```
weather-chatbot/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI entry point, routers, CORS
│   ├── config.py               # pydantic-settings, env vars
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic models
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── weather.py          # OpenWeatherMap API (city + coordinates)
│   │   ├── location.py         # Location parsing (GPS + text)
│   │   └── messaging.py        # Provider abstraction (Twilio/Meta)
│   │
│   └── routes/
│       ├── __init__.py
│       └── webhook.py          # POST /webhook endpoint
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Fixtures, mocks
│   ├── test_webhook.py
│   ├── test_weather.py
│   └── test_location.py
│
├── .env.example
├── requirements.txt
├── CLAUDE.md
└── README.md
```

### Architecture

```
WhatsApp → Twilio → POST /webhook → location.py → weather.py → messaging.py → WhatsApp
```

**Data Flow:**
1. User sends message/location via WhatsApp
2. Twilio forwards to `/webhook` endpoint
3. `location.py` parses GPS coordinates or extracts city from text
4. `weather.py` fetches weather from OpenWeatherMap API
5. `messaging.py` formats response and sends via Twilio
6. User receives weather update in WhatsApp

## Deployment

### Recommended Platforms

- **Render** - Easy Python deployment with free tier
- **Railway** - Simple deployment with environment variable management
- **Fly.io** - Edge deployment with generous free tier
- **Heroku** - Classic platform with straightforward deployment

### Deployment Steps

1. Push your code to a Git repository
2. Connect your deployment platform to the repository
3. Set all environment variables in your platform's dashboard
4. Deploy the application
5. Update Twilio webhook URL to your production URL (e.g., `https://your-app.onrender.com/webhook`)

### Production Considerations

- Use a process manager (gunicorn with uvicorn workers)
- Enable HTTPS (handled by most platforms)
- Set up monitoring and logging
- Consider rate limiting for the webhook endpoint

```bash
# Example production command
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## Troubleshooting

### Common Issues

**"Missing Twilio signature" error:**
- Ensure the `X-Twilio-Signature` header is being forwarded
- Check that your `TWILIO_AUTH_TOKEN` is correct

**"Invalid Twilio signature" error:**
- Verify the webhook URL matches exactly (including https://)
- Ensure ngrok URL is current and hasn't expired

**Weather not found:**
- Check city name spelling
- OpenWeatherMap may not recognize all cities - try larger nearby cities

**ngrok connection issues:**
- Restart ngrok and update Twilio webhook URL
- Check if local server is running on port 8000

### Debug Mode

Enable detailed logging by running:
```bash
uvicorn app.main:app --reload --log-level debug
```

## Future Enhancements

- [ ] Meta Cloud API integration (production WhatsApp)
- [ ] Weather forecasts (5-day outlook)
- [ ] Multiple language support
- [ ] Weather alerts and notifications
- [ ] Conversation history and preferences
- [ ] Air quality index information

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests (`pytest tests/ -v`)
5. Submit a pull request
