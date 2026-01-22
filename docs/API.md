# API Reference

## Overview

The Weather Chatbot API provides endpoints for WhatsApp messaging integration via Twilio.

**Base URL**: `http://localhost:8000` (development) or your production URL

## Endpoints

### GET /

Returns API information and status.

**Response**:
```json
{
  "message": "Weather Chatbot API",
  "docs": "/docs",
  "health": "/health"
}
```

### GET /health

Enhanced health check with service status.

**Response**:
```json
{
  "status": "healthy",
  "service": "weather-chatbot",
  "version": "2.0.0",
  "timestamp": "2024-01-21T12:00:00Z",
  "services": {
    "redis": "healthy",
    "groq_ai": "configured",
    "openweathermap": "configured"
  }
}
```

**Service Status Values**:
- `redis`: `healthy`, `unhealthy`, or `disabled`
- `groq_ai`: `configured` or `not_configured`
- `openweathermap`: `configured` or `not_configured`

### POST /webhook

Twilio WhatsApp webhook endpoint. Rate limited to 20 requests/minute per IP.

**Headers**:
| Header | Required | Description |
|--------|----------|-------------|
| `X-Twilio-Signature` | Yes | Twilio request signature for validation |
| `Content-Type` | Yes | `application/x-www-form-urlencoded` |

**Form Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `Body` | string | No | Message text content |
| `From` | string | Yes | Sender's WhatsApp number (e.g., `whatsapp:+233...`) |
| `To` | string | Yes | Recipient Twilio number |
| `MessageSid` | string | Yes | Unique message identifier |
| `AccountSid` | string | Yes | Twilio account identifier |
| `NumMedia` | int | No | Number of media attachments |
| `ProfileName` | string | No | Sender's WhatsApp display name |
| `Latitude` | string | No | GPS latitude (location shares) |
| `Longitude` | string | No | GPS longitude (location shares) |

**Response**:
```json
{
  "success": true,
  "message": "Message sent successfully"
}
```

**Error Responses**:

- **400 Bad Request** - Missing Twilio signature
```json
{
  "detail": "Missing Twilio signature"
}
```

- **403 Forbidden** - Invalid Twilio signature
```json
{
  "detail": "Invalid Twilio signature"
}
```

- **429 Too Many Requests** - Rate limit exceeded
```json
{
  "detail": "Rate limit exceeded: 20 per 1 minute"
}
```

## Message Processing

### Supported Query Types

The AI processes messages and extracts these query types:

| Query Type | Example Messages |
|------------|------------------|
| `WEATHER` | "What's the weather?", "Weather in Accra" |
| `FORECAST` | "Forecast tomorrow", "Weather next week" |
| `ETO` | "Evapotranspiration", "ETO today" |
| `GDD` | "GDD for maize", "Degree days" |
| `SOIL` | "Soil moisture", "Soil conditions" |
| `SEASONAL_ONSET` | "When does rain start?", "Onset date" |
| `SEASONAL_CESSATION` | "When does rain end?", "Cessation" |
| `DRY_SPELL` | "Dry spell forecast", "Drought risk" |
| `CROP_ADVICE` | "Should I plant?", "Planting advice" |
| `HELP` | "Help", "How do I use this?" |
| `GREETING` | "Hello", "Hi", "Good morning" |

### Location Handling

The API handles location in two ways:

1. **GPS Coordinates** - When user shares WhatsApp location
   - `Latitude` and `Longitude` parameters are used
   - Most accurate weather data

2. **City Name** - Extracted from message text
   - "Weather in Accra" → `Accra`
   - "Kumasi forecast" → `Kumasi`

### User Context

The API maintains user context (last city, preferred crop, conversation history):
- In-memory store: Development (default)
- Redis store: Production (`USE_REDIS=true`)
- Context TTL: 1 hour (configurable)

## Authentication

The webhook validates all requests using Twilio's request signature:

1. Twilio signs requests with your Auth Token
2. API recomputes signature using URL + parameters
3. Request is rejected if signatures don't match

**Security Notes**:
- Never expose your `TWILIO_AUTH_TOKEN`
- Always use HTTPS in production
- The signature validation can be disabled for testing (not recommended)

## Rate Limiting

The webhook endpoint is rate limited:
- **Limit**: 20 requests per minute per IP
- **Response**: 429 status code with retry information

## Error Handling

All errors return JSON with a `detail` field:

```json
{
  "detail": "Error description"
}
```

Common error scenarios:
- Invalid/missing Twilio signature
- Rate limit exceeded
- Weather API unavailable
- Invalid location

## OpenAPI Documentation

Interactive API documentation available at:
- Swagger UI: `/docs`
- ReDoc: `/redoc`
