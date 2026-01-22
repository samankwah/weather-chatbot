# AI Agro-Weather Chatbot for Ghana Farmers

<<<<<<< HEAD
An AI-powered WhatsApp chatbot providing agricultural weather information for farmers in Ghana. Uses natural language processing to understand queries and provides weather forecasts, crop advice, and Ghana-specific seasonal information including onset/cessation predictions.
=======
WhatsApp-based weather chatbot for GMet. Built with FastAPI and Twilio, designed for easy migration to Meta Cloud API.
>>>>>>> 0b8ed1d82eb90c0e7d97675cc81ba9464a8d24e5

## Features

### Weather & Forecasts
- **Current Weather**: Real-time weather conditions for any Ghana city
- **Weather Forecasts**: 5-16 day weather forecasts
- **GPS Location**: Share WhatsApp location for precise weather at your coordinates

### Agricultural Data
- **Evapotranspiration (ETO)**: Daily ETO values for irrigation planning
- **Growing Degree Days (GDD)**: Crop growth stage tracking for maize, rice, cassava, and more
- **Soil Moisture**: Current soil moisture at various depths
- **Crop Advice**: AI-generated farming recommendations

### Ghana-Specific Seasonal Forecasts
- **Onset Detection**: When the rainy season starts (using GMet criteria)
- **Cessation Prediction**: When rains will end (soil water balance model)
- **Dry Spell Analysis**: Early and late season dry spell predictions
- **Season Length**: Duration of the growing season

### Regional Support
- **Southern Ghana** (below 8°N): Bimodal rainfall (Major: Mar-Jul, Minor: Sep-Nov)
- **Northern Ghana** (above 8°N): Unimodal rainfall (Apr-Oct)

## Tech Stack

- **Framework**: FastAPI (Python 3.11+)
- **Messaging**: Twilio WhatsApp API
- **AI/NLU**: Groq (Llama 3.1-8B)
- **Weather Data**: OpenWeatherMap + Open-Meteo
- **Storage**: Redis (production) / In-memory (development)
- **Rate Limiting**: slowapi (20 req/min per IP)

## Quick Start

### Prerequisites

- Python 3.11+
- Twilio account with WhatsApp Sandbox
- OpenWeatherMap API key
- Groq API key (optional, for AI features)

### Local Development

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd weather-chatbot
   python -m venv venv
   source venv/bin/activate  # Windows: .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Run the application**:
   ```bash
   uvicorn app.main:app --reload
   ```

4. **Expose with ngrok** (for Twilio webhook):
   ```bash
   ngrok http 8000
   ```

5. **Configure Twilio**:
   - Go to Twilio Console > Messaging > WhatsApp Sandbox
   - Set webhook URL to: `https://your-ngrok-url.ngrok.io/webhook`

### Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up --build

# Services:
# - API: http://localhost:8000
# - Redis: localhost:6379
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TWILIO_ACCOUNT_SID` | Twilio Account SID | Yes |
| `TWILIO_AUTH_TOKEN` | Twilio Auth Token | Yes |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp number | Yes |
| `WEATHER_API_KEY` | OpenWeatherMap API key | Yes |
| `GROQ_API_KEY` | Groq API key for AI | No |
| `USE_REDIS` | Enable Redis storage (`true`/`false`) | No |
| `REDIS_URL` | Redis connection URL | No |

See `.env.example` for all options.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API information |
| `/health` | GET | Health check with service status |
| `/webhook` | POST | Twilio WhatsApp webhook (rate limited) |
| `/docs` | GET | OpenAPI documentation |

## Example Queries

Users can send messages like:
- "What's the weather in Accra?"
- "Forecast for Kumasi tomorrow"
- "When does the rainy season start?"
- "GDD for maize"
- "Soil moisture level"
- "Should I plant now?"
- "Dry spell forecast"
- "How long is the growing season?"

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html

# Run specific test file
pytest tests/test_seasonal_service.py -v
```

## Project Structure

```
weather-chatbot/
├── app/
│   ├── main.py              # FastAPI app, rate limiting, health check
│   ├── config.py            # Settings management
│   ├── logging_config.py    # Structured JSON logging
│   ├── routes/
│   │   └── webhook.py       # Twilio webhook (rate limited)
│   ├── services/
│   │   ├── ai.py            # Groq AI/NLU service
│   │   ├── agromet.py       # ETO, GDD, soil moisture
│   │   ├── forecast.py      # Weather forecasts
│   │   ├── memory.py        # Redis/in-memory user context
│   │   ├── messaging.py     # Message formatting
│   │   ├── seasonal.py      # Ghana seasonal forecasts
│   │   └── weather.py       # Current weather
│   └── models/
│       ├── schemas.py       # Core Pydantic models
│       └── ai_schemas.py    # AI/agricultural models
├── tests/
│   ├── conftest.py          # Test fixtures
│   ├── test_webhook.py      # Endpoint tests
│   ├── test_ai_service.py   # AI/NLU tests
│   ├── test_seasonal_service.py  # Ghana seasonal tests
│   ├── test_weather_service.py   # Weather API tests
│   └── test_memory_service.py    # Context storage tests
├── docs/
│   ├── API.md               # API reference
│   └── DEPLOYMENT.md        # Deployment guide
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Ghana Seasonal Forecasting

### Onset Detection (GMet Criteria)
- 20mm rainfall accumulated in 3 consecutive days
- No dry spell > 10 days in the following 30 days

### Cessation Detection (Soil Water Balance)
- Starts with 70mm soil water capacity
- Subtracts daily ETO (~4mm/day)
- Cessation when soil water reaches 0

### Dry Spell Analysis
- **Early period**: Onset to Day 50
- **Late period**: Day 51 to Cessation

## Deployment

See `docs/DEPLOYMENT.md` for detailed deployment instructions for:
- Render
- Railway
- Fly.io
- AWS/GCP

### Production Checklist

- [ ] Set all environment variables
- [ ] Enable Redis (`USE_REDIS=true`)
- [ ] Configure Twilio webhook URL
- [ ] Set up monitoring/logging
- [ ] Enable HTTPS

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests
4. Run `pytest tests/ -v`
5. Submit a pull request
