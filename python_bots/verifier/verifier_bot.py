"""
Python API Key Verifier Bot

This module replaces the C# UnsecuredAPIKeys.Bots.Verifier.
It verifies the validity of discovered API keys using various provider-specific validation methods.
"""
import asyncio
import aiohttp
import structlog
import asyncpg
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import sys
import os

# Add parent directory to path to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_backend.app.core.config import settings
from python_backend.app.core.enums import ApiStatusEnum, ApiTypeEnum
from python_backend.app.models.database import APIKey, Proxy

logger = structlog.get_logger()


@dataclass
class CounterState:
    """State tracking for verification progress"""
    valid_count: int = 0
    invalid_count: int = 0
    skipped_count: int = 0
    processed_count: int = 0
    circuit_breaker_tripped_count: int = 0


class SimpleCircuitBreaker:
    """Circuit breaker implementation for handling API failures"""
    
    def __init__(self, threshold: int = 5, retry_timeout: int = 30):
        self.threshold = threshold
        self.retry_timeout = timedelta(seconds=retry_timeout)
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.is_open = False
        self._lock = asyncio.Lock()
    
    async def is_circuit_open(self) -> bool:
        """Check if circuit breaker is open"""
        async with self._lock:
            if not self.is_open:
                return False
            
            if self.last_failure_time and datetime.utcnow() - self.last_failure_time >= self.retry_timeout:
                self.is_open = False
                self.failure_count = 0
                return False
            
            return True
    
    async def record_success(self):
        """Record successful operation"""
        async with self._lock:
            self.failure_count = 0
            self.is_open = False
    
    async def record_failure(self):
        """Record failed operation"""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()
            if self.failure_count >= self.threshold:
                self.is_open = True


class ProviderCircuitBreakers:
    """Per-provider circuit breaker management"""
    
    def __init__(self, logger=None):
        self.breakers: Dict[str, SimpleCircuitBreaker] = {}
        self.logger = logger
    
    def get_breaker(self, provider_name: str) -> SimpleCircuitBreaker:
        """Get or create circuit breaker for provider"""
        if provider_name not in self.breakers:
            if self.logger:
                self.logger.info(f"Creating circuit breaker for provider {provider_name}")
            self.breakers[provider_name] = SimpleCircuitBreaker(5, 30)
        return self.breakers[provider_name]
    
    async def get_tripped_count(self) -> int:
        """Get count of tripped circuit breakers"""
        count = 0
        for breaker in self.breakers.values():
            if await breaker.is_circuit_open():
                count += 1
        return count


class ResourceMonitor:
    """Simple resource monitoring"""
    
    @staticmethod
    def get_memory_usage() -> int:
        """Get current memory usage in bytes"""
        import psutil
        process = psutil.Process()
        return process.memory_info().rss
    
    @staticmethod
    def should_throttle() -> bool:
        """Check if we should throttle operations due to resource usage"""
        try:
            memory_usage = ResourceMonitor.get_memory_usage()
            return memory_usage > 1024 * 1024 * 1024  # 1GB threshold
        except:
            return False


class CacheManager:
    """Simple in-memory cache with size limits"""
    
    def __init__(self, max_size: int = 10000, expiry_seconds: int = 3600):
        self.cache: Dict[str, Tuple[any, datetime]] = {}
        self.max_size = max_size
        self.expiry = timedelta(seconds=expiry_seconds)
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[any]:
        """Get value from cache"""
        async with self._lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if datetime.utcnow() - timestamp < self.expiry:
                    return value
                else:
                    del self.cache[key]
            return None
    
    async def set(self, key: str, value: any):
        """Set value in cache"""
        async with self._lock:
            # Clean expired entries if cache is full
            if len(self.cache) >= self.max_size:
                await self._cleanup_expired()
                
                # If still full, remove oldest entries
                if len(self.cache) >= self.max_size:
                    sorted_items = sorted(self.cache.items(), key=lambda x: x[1][1])
                    for k, _ in sorted_items[:len(sorted_items)//2]:
                        del self.cache[k]
            
            self.cache[key] = (value, datetime.utcnow())
    
    async def _cleanup_expired(self):
        """Remove expired entries"""
        now = datetime.utcnow()
        expired_keys = [
            key for key, (_, timestamp) in self.cache.items()
            if now - timestamp >= self.expiry
        ]
        for key in expired_keys:
            del self.cache[key]


class APIKeyVerifier:
    """Main API key verification class"""
    
    def __init__(self):
        self.counter = CounterState()
        self.circuit_breakers = ProviderCircuitBreakers(logger)
        self.cache = CacheManager()
        self.session: Optional[aiohttp.ClientSession] = None
        self.db_pool: Optional[asyncpg.Pool] = None
        self.shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """Initialize the verifier"""
        logger.info("Initializing API Key Verifier")
        
        # Create database connection pool
        self.db_pool = await asyncpg.create_pool(
            settings.database_url.replace('+asyncpg', ''),
            min_size=5,
            max_size=20
        )
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        logger.info("API Key Verifier initialized")
    
    async def shutdown(self):
        """Shutdown the verifier"""
        logger.info("Shutting down API Key Verifier")
        self.shutdown_event.set()
        
        if self.session:
            await self.session.close()
        
        if self.db_pool:
            await self.db_pool.close()
        
        logger.info("API Key Verifier shutdown complete")
    
    async def run_verification_loop(self):
        """Main verification loop"""
        logger.info("Starting verification loop")
        
        while not self.shutdown_event.is_set():
            try:
                # Get batch of unverified keys
                batch = await self.get_verification_batch()
                
                if not batch:
                    logger.debug("No keys to verify, sleeping...")
                    await asyncio.sleep(30)
                    continue
                
                # Process batch
                await self.process_batch(batch)
                
                # Log progress
                logger.info("Verification progress",
                           processed=self.counter.processed_count,
                           valid=self.counter.valid_count,
                           invalid=self.counter.invalid_count,
                           skipped=self.counter.skipped_count)
                
                # Brief pause between batches
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error("Error in verification loop", error=str(e))
                await asyncio.sleep(60)  # Wait longer on error
    
    async def get_verification_batch(self, batch_size: int = 50) -> List[Dict]:
        """Get batch of API keys to verify"""
        async with self.db_pool.acquire() as conn:
            query = """
                SELECT "Id", "ApiKey", "ApiType", "Status"
                FROM "APIKeys"
                WHERE "Status" = $1 OR ("Status" = $2 AND "LastCheckedUTC" < $3)
                ORDER BY "Id"
                LIMIT $4
            """
            
            # Check unverified keys and keys not checked in last 24 hours
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            rows = await conn.fetch(
                query,
                ApiStatusEnum.UNVERIFIED.value,
                ApiStatusEnum.VALID.value,
                cutoff_time,
                batch_size
            )
            
            return [dict(row) for row in rows]
    
    async def process_batch(self, batch: List[Dict]):
        """Process a batch of API keys"""
        tasks = []
        
        for key_data in batch:
            task = asyncio.create_task(self.verify_api_key(key_data))
            tasks.append(task)
        
        # Process with concurrency limit
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent verifications
        
        async def bounded_verify(key_data):
            async with semaphore:
                return await self.verify_api_key(key_data)
        
        tasks = [bounded_verify(key_data) for key_data in batch]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def verify_api_key(self, key_data: Dict) -> bool:
        """Verify a single API key"""
        key_id = key_data['Id']
        api_key = key_data['ApiKey']
        api_type = ApiTypeEnum(key_data['ApiType'])
        
        try:
            # Check circuit breaker for this provider
            provider_name = api_type.name
            breaker = self.circuit_breakers.get_breaker(provider_name)
            
            if await breaker.is_circuit_open():
                logger.debug(f"Circuit breaker open for {provider_name}, skipping key {key_id}")
                self.counter.skipped_count += 1
                return False
            
            # Check cache first
            cache_key = f"verify:{api_key}"
            cached_result = await self.cache.get(cache_key)
            if cached_result is not None:
                await self.update_key_status(key_id, cached_result)
                self.counter.processed_count += 1
                return cached_result == ApiStatusEnum.VALID
            
            # Perform actual verification
            is_valid = await self.perform_verification(api_key, api_type)
            
            # Update status based on result
            if is_valid:
                new_status = ApiStatusEnum.VALID
                self.counter.valid_count += 1
                await breaker.record_success()
            else:
                new_status = ApiStatusEnum.INVALID
                self.counter.invalid_count += 1
            
            # Cache result
            await self.cache.set(cache_key, new_status)
            
            # Update database
            await self.update_key_status(key_id, new_status)
            self.counter.processed_count += 1
            
            logger.debug(f"Verified key {key_id}: {new_status.name}")
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying key {key_id}", error=str(e))
            
            # Record failure for circuit breaker
            provider_name = api_type.name if 'api_type' in locals() else "unknown"
            breaker = self.circuit_breakers.get_breaker(provider_name)
            await breaker.record_failure()
            
            # Mark as error
            await self.update_key_status(key_id, ApiStatusEnum.ERROR)
            self.counter.processed_count += 1
            return False
    
    async def perform_verification(self, api_key: str, api_type: ApiTypeEnum) -> bool:
        """Perform actual API key verification based on type"""
        try:
            if api_type == ApiTypeEnum.OPENAI:
                return await self.verify_openai_key(api_key)
            elif api_type == ApiTypeEnum.ANTHROPIC_CLAUDE:
                return await self.verify_anthropic_key(api_key)
            elif api_type == ApiTypeEnum.GITHUB:
                return await self.verify_github_key(api_key)
            elif api_type == ApiTypeEnum.STRIPE:
                return await self.verify_stripe_key(api_key)
            else:
                # For unknown types, perform basic format validation
                return len(api_key.strip()) > 10
                
        except Exception as e:
            logger.error(f"Verification failed for {api_type.name}", error=str(e))
            return False
    
    async def verify_openai_key(self, api_key: str) -> bool:
        """Verify OpenAI API key"""
        try:
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            async with self.session.get('https://api.openai.com/v1/models', headers=headers) as response:
                return response.status == 200
                
        except Exception:
            return False
    
    async def verify_anthropic_key(self, api_key: str) -> bool:
        """Verify Anthropic API key"""
        try:
            headers = {
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'Content-Type': 'application/json'
            }
            
            # Use a minimal request to test the key
            data = {
                'model': 'claude-3-haiku-20240307',
                'max_tokens': 1,
                'messages': [{'role': 'user', 'content': 'Hi'}]
            }
            
            async with self.session.post('https://api.anthropic.com/v1/messages', 
                                       headers=headers, json=data) as response:
                return response.status in [200, 400]  # 400 might be insufficient credits
                
        except Exception:
            return False
    
    async def verify_github_key(self, api_key: str) -> bool:
        """Verify GitHub API key"""
        try:
            headers = {
                'Authorization': f'token {api_key}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            async with self.session.get('https://api.github.com/user', headers=headers) as response:
                return response.status == 200
                
        except Exception:
            return False
    
    async def verify_stripe_key(self, api_key: str) -> bool:
        """Verify Stripe API key"""
        try:
            # Basic format check for Stripe keys
            if not (api_key.startswith('sk_') or api_key.startswith('pk_') or api_key.startswith('rk_')):
                return False
            
            # For Stripe, we can try to retrieve account info
            headers = {
                'Authorization': f'Bearer {api_key}'
            }
            
            async with self.session.get('https://api.stripe.com/v1/account', headers=headers) as response:
                return response.status == 200
                
        except Exception:
            return False
    
    async def update_key_status(self, key_id: int, status: ApiStatusEnum):
        """Update API key status in database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                'UPDATE "APIKeys" SET "Status" = $1, "LastCheckedUTC" = $2 WHERE "Id" = $3',
                status.value,
                datetime.utcnow(),
                key_id
            )


async def main():
    """Main entry point for the verifier bot"""
    # Setup logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logger.info("Starting UnsecuredAPIKeys Python Verifier Bot")
    
    verifier = APIKeyVerifier()
    
    try:
        await verifier.initialize()
        await verifier.run_verification_loop()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error("Fatal error in verifier", error=str(e))
    finally:
        await verifier.shutdown()


if __name__ == "__main__":
    asyncio.run(main())