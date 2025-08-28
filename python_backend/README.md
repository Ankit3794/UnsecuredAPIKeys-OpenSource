# UnsecuredAPIKeys Python Backend

This directory contains the Python FastAPI backend that replaces the original C# .NET WebAPI.

## Architecture

The Python backend is designed to be a drop-in replacement for the C# backend while maintaining:
- **Same API endpoints** - All REST endpoints match the original C# API
- **Same database schema** - Uses the existing PostgreSQL database without changes
- **Same functionality** - All features including Discord auth, PayPal integration, rate limiting
- **WebSocket support** - Replaces SignalR with native WebSocket support

## Project Structure

```
python_backend/
├── app/
│   ├── controllers/          # API route handlers (replaces C# Controllers)
│   │   ├── api_controller.py
│   │   ├── discord_auth_controller.py
│   │   ├── paypal_controller.py
│   │   └── status_controller.py
│   ├── models/               # Database models (replaces C# Entity Framework)
│   │   └── database.py
│   ├── schemas/              # Pydantic schemas for API validation
│   │   └── api_schemas.py
│   ├── services/             # Business logic services
│   │   ├── display_count_service.py
│   │   └── websocket_service.py
│   ├── middleware/           # Custom middleware
│   │   ├── rate_limit.py
│   │   └── referrer_check.py
│   ├── core/                 # Core configuration and utilities
│   │   ├── config.py
│   │   ├── database.py
│   │   └── enums.py
│   └── main.py              # FastAPI application entry point
├── alembic/                 # Database migrations
├── requirements.txt         # Python dependencies
├── run_dev.py              # Development server
└── .env.example            # Environment configuration template
```

## Technology Stack

- **FastAPI** - Modern, fast web framework for building APIs
- **SQLAlchemy** - Python ORM (replaces Entity Framework)
- **Alembic** - Database migration tool (replaces EF migrations)
- **AsyncPG** - Async PostgreSQL driver
- **Pydantic** - Data validation using Python type annotations
- **WebSockets** - Real-time communication (replaces SignalR)
- **Structlog** - Structured logging

## Installation & Setup

1. **Install Python dependencies:**
   ```bash
   cd python_backend
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Initialize database:**
   ```bash
   alembic upgrade head
   ```

4. **Run development server:**
   ```bash
   python run_dev.py
   ```

The API will be available at `http://localhost:8000`

## API Endpoints

All endpoints maintain compatibility with the original C# API:

### Core API (`/API/`)
- `GET /API/GetRandomKey` - Get random valid API key
- `GET /API/GetAllValidKeys` - Get paginated list of valid keys
- `GET /API/GetStats` - Get API key statistics
- `GET /API/GetKeyTypes` - Get key counts by type
- `POST /API/TrackIssueSubmission` - Track issue submissions
- `POST /API/TrackDonationClick` - Track donation clicks
- `GET /API/GetDonationStats` - Get donation statistics
- `POST /API/webhook/key-fixed` - Handle key fixed webhooks

### Discord Auth (`/discordauth/`)
- `GET /discordauth/login` - Get Discord OAuth URL
- `POST /discordauth/callback` - Handle OAuth callback
- `GET /discordauth/user/{discord_id}` - Get user info
- `POST /discordauth/refresh-membership/{discord_id}` - Refresh membership

### PayPal (`/api/paypal/`)
- `POST /api/paypal/ipn` - Handle PayPal IPN notifications

### Status (`/status/`)
- `GET /status/health` - Health check endpoint
- `GET /status/` - Basic status

### WebSocket (`/ws`)
- Real-time updates for statistics and events

## Key Features

### Rate Limiting
- IP-based rate limiting with Redis backend (in-memory fallback)
- Different limits for regular users vs Discord server members
- Configurable limits per endpoint

### Authentication
- Discord OAuth2 integration
- JWT token support for authenticated requests
- Server membership verification

### Real-time Updates
- WebSocket support for live statistics
- Event broadcasting for key displays and updates
- Active user tracking

### Monitoring & Observability
- Structured logging with contextual information
- Health check endpoints
- Request/response tracking

## Database Compatibility

The Python backend uses the **same PostgreSQL database** as the C# version:
- All table names and column names match exactly
- Foreign key relationships preserved
- Indexes and constraints maintained
- No data migration required

## Configuration

Environment variables (see `.env.example`):
- `DATABASE_URL` - PostgreSQL connection string
- `DISCORD_CLIENT_ID/SECRET` - Discord OAuth credentials
- `PAYPAL_*` - PayPal integration settings
- `RATE_LIMIT_*` - Rate limiting configuration
- `ALLOWED_ORIGINS` - CORS configuration

## Development

### Code Style
- Python 3.11+ required
- Type hints throughout
- Async/await for database operations
- Structured logging with context

### Testing
```bash
# Run tests (when implemented)
pytest
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## Deployment

The Python backend can be deployed using:
- **Docker** - Containerized deployment
- **Systemd** - Direct service deployment
- **Cloud platforms** - AWS, GCP, Azure

Example Docker deployment:
```dockerfile
FROM python:3.11-slim
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Migration from C#

This Python backend provides:
✅ **100% API compatibility** - All endpoints work identically
✅ **Same database** - No schema changes required  
✅ **Same features** - Discord auth, PayPal, rate limiting, etc.
✅ **WebSocket support** - Replaces SignalR functionality
✅ **Performance** - FastAPI provides excellent performance
✅ **Modern stack** - Python 3.11+ with async support

The migration is transparent to the frontend - the Next.js UI requires no changes.