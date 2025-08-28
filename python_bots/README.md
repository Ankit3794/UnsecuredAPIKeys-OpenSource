# UnsecuredAPIKeys Python Bots

This directory contains Python implementations of the API key discovery and verification bots that replace the original C# bots.

## Bots Overview

### Scraper Bot (`scraper/scraper_bot.py`)
Replaces `UnsecuredAPIKeys.Bots.Scraper` - Searches for exposed API keys across various platforms:

**Features:**
- **GitHub Search Integration** - Uses GitHub Code Search API to find exposed keys
- **Pattern Matching** - Detects various API key formats (OpenAI, Anthropic, GitHub, Stripe, AWS, etc.)
- **Duplicate Detection** - Advanced similarity checking to avoid duplicate keys
- **Circuit Breaker** - Handles API rate limits and failures gracefully
- **Database Integration** - Stores found keys and repository references
- **Extensible** - Easy to add new search providers (GitLab, Bitbucket, etc.)

**Supported Key Types:**
- OpenAI (sk-*, sk-proj-*)
- Anthropic Claude (sk-ant-api03-*)
- GitHub (ghp_*, github_pat_*, ghs_*, ghr_*)
- Stripe (sk_live_*, sk_test_*, pk_live_*, pk_test_*)
- AWS (AKIA*)
- Google AI (AIza*)
- SendGrid (SG.*)
- Twilio (SK*, AC*)

### Verifier Bot (`verifier/verifier_bot.py`)
Replaces `UnsecuredAPIKeys.Bots.Verifier` - Validates discovered API keys:

**Features:**
- **Multi-Provider Verification** - Tests keys against their respective APIs
- **Circuit Breaker Protection** - Prevents cascading failures
- **Caching** - Avoids re-verifying recently checked keys
- **Batch Processing** - Efficient concurrent verification
- **Status Tracking** - Updates key validity status in database
- **Resource Monitoring** - Monitors memory usage and throttles if needed

**Supported Verifications:**
- **OpenAI** - Tests against `/v1/models` endpoint
- **Anthropic** - Tests against `/v1/messages` endpoint
- **GitHub** - Tests against `/user` endpoint
- **Stripe** - Tests against `/v1/account` endpoint
- **Format Validation** - Basic pattern validation for other types

## Installation & Setup

1. **Install dependencies:**
   ```bash
   cd python_bots
   pip install -r requirements.txt
   ```

2. **Configure database connection:**
   - Set `DATABASE_URL` environment variable or update settings in the bot files
   - Ensure the PostgreSQL database is accessible and contains the required tables

3. **Configure search provider tokens:**
   - Add GitHub tokens to the `SearchProviderTokens` table
   - Ensure tokens have appropriate permissions for code search

## Running the Bots

### Scraper Bot
```bash
cd python_bots
python run_scraper.py
```

### Verifier Bot
```bash
cd python_bots
python run_verifier.py
```

### Running Both (recommended)
```bash
# Terminal 1 - Scraper
python run_scraper.py

# Terminal 2 - Verifier  
python run_verifier.py
```

## Architecture

### Scraper Bot Flow
1. **Query Management** - Loads enabled search queries from database
2. **Platform Search** - Executes searches on GitHub (extensible to other platforms)
3. **Content Analysis** - Downloads file content and extracts API keys using regex patterns
4. **Duplicate Detection** - Uses Jaccard similarity to identify similar/duplicate keys
5. **Database Storage** - Stores new keys and repository references
6. **Rate Limiting** - Respects API rate limits with circuit breakers

### Verifier Bot Flow
1. **Batch Loading** - Gets unverified or stale keys from database
2. **Provider Detection** - Determines verification method based on key type
3. **API Testing** - Makes test requests to provider APIs
4. **Status Update** - Updates key status (Valid/Invalid/Error) in database
5. **Caching** - Caches results to avoid redundant verification
6. **Circuit Breaking** - Handles provider failures gracefully

## Key Features

### Circuit Breaker Pattern
Both bots implement circuit breakers to handle:
- API rate limits
- Network failures
- Provider outages
- Cascading failures

### Duplicate Detection
Advanced similarity checking using:
- Exact string matching
- Jaccard similarity with n-grams
- Configurable similarity threshold
- Memory-efficient known key tracking

### Resource Management
- Memory usage monitoring
- Concurrent request limiting
- Adaptive batch sizing
- Graceful degradation under load

### Error Handling
- Comprehensive exception handling
- Structured logging with context
- Automatic retry with backoff
- Graceful shutdown handling

## Configuration

### Environment Variables
```bash
# Database connection
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db

# Optional: Custom settings
SCRAPER_BATCH_SIZE=50
VERIFIER_BATCH_SIZE=50
MAX_CONCURRENT_REQUESTS=10
```

### Database Requirements
The bots require the following tables (created by the main backend):
- `APIKeys` - Stores discovered API keys
- `RepoReferences` - Stores repository/file references
- `SearchQueries` - Defines search queries to execute
- `SearchProviderTokens` - Stores API tokens for search providers

## Monitoring & Logging

Both bots provide structured logging with:
- **Progress Statistics** - Keys found, verified, errors
- **Performance Metrics** - Request timing, memory usage
- **Error Tracking** - Detailed error context
- **Circuit Breaker Status** - Provider health monitoring

Example log output:
```
2024-01-01 12:00:00 [INFO] Scraping progress new_keys=42 duplicates=15 total_searched=1000 errors=2
2024-01-01 12:01:00 [INFO] Verification progress processed=50 valid=30 invalid=18 skipped=2
```

## Production Deployment

### Systemd Services
Create service files for production deployment:

**scraper.service:**
```ini
[Unit]
Description=UnsecuredAPIKeys Scraper Bot
After=network.target

[Service]
Type=simple
User=apikeys
WorkingDirectory=/opt/unsecuredapikeys/python_bots
ExecStart=/usr/bin/python3 run_scraper.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**verifier.service:**
```ini
[Unit]
Description=UnsecuredAPIKeys Verifier Bot
After=network.target

[Service]
Type=simple
User=apikeys
WorkingDirectory=/opt/unsecuredapikeys/python_bots
ExecStart=/usr/bin/python3 run_verifier.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Docker Deployment
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run both bots
CMD ["sh", "-c", "python run_scraper.py & python run_verifier.py & wait"]
```

## Extending the Bots

### Adding New Search Providers
1. Create a new provider class (e.g., `GitLabSearchProvider`)
2. Implement search and content retrieval methods
3. Add provider support to `APIKeyScraper.process_search_query`
4. Update database enum for new provider

### Adding New API Key Types
1. Add patterns to `APIKeyPatterns.PATTERNS`
2. Implement verification method in `APIKeyVerifier.perform_verification`
3. Update enum definitions

### Custom Verification Logic
Extend `perform_verification` method:
```python
async def verify_custom_api(self, api_key: str) -> bool:
    """Custom API verification logic"""
    try:
        # Implement custom verification
        headers = {'Authorization': f'Bearer {api_key}'}
        async with self.session.get('https://api.custom.com/status', headers=headers) as response:
            return response.status == 200
    except Exception:
        return False
```

## Migration from C#

The Python bots provide **100% functional compatibility** with the original C# bots:

✅ **Same database schema** - No database changes required  
✅ **Same search logic** - Identical pattern matching and duplicate detection  
✅ **Same verification methods** - API-compatible verification approaches  
✅ **Enhanced features** - Better error handling, monitoring, and extensibility  
✅ **Performance** - Async Python provides excellent concurrent performance  

The migration is transparent - existing data and workflows continue unchanged.