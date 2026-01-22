# Deployment Guide

## Table of Contents

- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [Cloud Deployment](#cloud-deployment)
  - [Render](#render)
  - [Railway](#railway)
  - [Fly.io](#flyio)
- [Twilio Setup](#twilio-setup)
- [Production Checklist](#production-checklist)

## Local Development

### Prerequisites

- Python 3.11+
- ngrok (for Twilio webhook)
- Redis (optional, for persistent storage)

### Setup

1. **Create virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your credentials
```

4. **Start the server**:
```bash
uvicorn app.main:app --reload
```

5. **Expose with ngrok**:
```bash
ngrok http 8000
```

6. **Configure Twilio webhook** with ngrok URL (see [Twilio Setup](#twilio-setup))

### Running with Redis

```bash
# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Set environment variables
export USE_REDIS=true
export REDIS_URL=redis://localhost:6379

# Start the app
uvicorn app.main:app --reload
```

## Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Build and start services
docker-compose up --build

# Run in background
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

**Services**:
- API: http://localhost:8000
- Redis: localhost:6379

### Using Docker Only

```bash
# Build image
docker build -t weather-chatbot .

# Run container
docker run -d \
  --name weather-chatbot \
  -p 8000:8000 \
  --env-file .env \
  weather-chatbot
```

## Cloud Deployment

### Render

1. **Create a new Web Service** at [render.com](https://render.com)

2. **Configure**:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

3. **Environment Variables** (in Render dashboard):
```
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_WHATSAPP_NUMBER=+14155238886
WEATHER_API_KEY=xxxxxxxx
GROQ_API_KEY=xxxxxxxx
```

4. **Add Redis** (Render Redis):
   - Create a Redis instance
   - Add connection string as `REDIS_URL`
   - Set `USE_REDIS=true`

5. **Update Twilio webhook** to your Render URL

### Railway

1. **Create project** at [railway.app](https://railway.app)

2. **Deploy from GitHub**:
   - Connect your repository
   - Railway auto-detects Python

3. **Add Redis**:
   - Add Redis plugin
   - Connection string auto-configured as `REDIS_URL`

4. **Environment Variables**:
```
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_WHATSAPP_NUMBER=+14155238886
WEATHER_API_KEY=xxxxxxxx
GROQ_API_KEY=xxxxxxxx
USE_REDIS=true
```

5. **Generate domain** and update Twilio webhook

### Fly.io

1. **Install flyctl**:
```bash
curl -L https://fly.io/install.sh | sh
```

2. **Launch app**:
```bash
fly launch
```

3. **Create fly.toml** (auto-generated or customize):
```toml
app = "weather-chatbot"

[build]
  dockerfile = "Dockerfile"

[env]
  PORT = "8080"

[[services]]
  internal_port = 8080
  protocol = "tcp"

  [[services.ports]]
    handlers = ["http"]
    port = 80

  [[services.ports]]
    handlers = ["tls", "http"]
    port = 443
```

4. **Set secrets**:
```bash
fly secrets set TWILIO_ACCOUNT_SID=ACxxxxxxxx
fly secrets set TWILIO_AUTH_TOKEN=xxxxxxxx
fly secrets set TWILIO_WHATSAPP_NUMBER=+14155238886
fly secrets set WEATHER_API_KEY=xxxxxxxx
fly secrets set GROQ_API_KEY=xxxxxxxx
```

5. **Add Redis**:
```bash
fly redis create
fly secrets set REDIS_URL=<redis-url>
fly secrets set USE_REDIS=true
```

6. **Deploy**:
```bash
fly deploy
```

## Twilio Setup

### WhatsApp Sandbox (Development)

1. Go to [Twilio Console](https://console.twilio.com)
2. Navigate to **Messaging > Try it out > Send a WhatsApp message**
3. Join the Sandbox:
   - Send the join code to the Sandbox number
   - Example: `join <word>-<word>` to `+14155238886`
4. Configure webhook:
   - **When a message comes in**: `https://your-app-url/webhook`
   - **HTTP Method**: POST
5. Save configuration

### WhatsApp Business API (Production)

1. Apply for WhatsApp Business API access
2. Complete Facebook Business verification
3. Set up Message Templates for outbound messages
4. Configure webhook URL
5. Implement template messaging for notifications

## Production Checklist

### Security

- [ ] Use HTTPS (enforced by most platforms)
- [ ] Set strong `TWILIO_AUTH_TOKEN`
- [ ] Enable Twilio signature validation
- [ ] Don't expose API keys in logs

### Performance

- [ ] Enable Redis (`USE_REDIS=true`)
- [ ] Configure appropriate worker count
- [ ] Set up connection pooling

### Monitoring

- [ ] Check `/health` endpoint regularly
- [ ] Set up alerting on errors
- [ ] Monitor rate limit hits

### Configuration

```bash
# Recommended production settings
USE_REDIS=true
REDIS_URL=<your-redis-url>
MEMORY_TTL_SECONDS=3600
```

### Worker Configuration

For production with gunicorn:
```bash
gunicorn app.main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:$PORT \
  --access-logfile - \
  --error-logfile -
```

### Health Check

Verify deployment:
```bash
curl https://your-app-url/health
```

Expected response:
```json
{
  "status": "healthy",
  "services": {
    "redis": "healthy",
    "groq_ai": "configured",
    "openweathermap": "configured"
  }
}
```

### End-to-End Test

1. Send "hello" to your WhatsApp number
2. Should receive greeting response
3. Send "weather in Accra"
4. Should receive weather data

## Troubleshooting

### Common Issues

**"Missing Twilio signature"**
- Ensure `X-Twilio-Signature` header is forwarded
- Check reverse proxy configuration

**"Invalid Twilio signature"**
- Verify `TWILIO_AUTH_TOKEN` is correct
- Ensure webhook URL matches exactly (including https)

**Redis connection failed**
- Check `REDIS_URL` format
- Verify Redis is running and accessible
- Check network/firewall rules

**Rate limit exceeded**
- Check for duplicate requests
- Increase rate limit if needed
- Implement retry with backoff

### Logs

```bash
# Docker
docker-compose logs -f api

# Render
# View in Render dashboard

# Railway
railway logs

# Fly.io
fly logs
```
