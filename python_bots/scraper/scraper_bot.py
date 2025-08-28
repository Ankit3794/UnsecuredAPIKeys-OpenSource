"""
Python API Key Scraper Bot

This module replaces the C# UnsecuredAPIKeys.Bots.Scraper.
It searches for exposed API keys across various platforms (GitHub, GitLab, etc.)
"""
import asyncio
import aiohttp
import structlog
import asyncpg
import re
import base64
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs
import sys
import os

# Add parent directory to path to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from python_backend.app.core.config import settings
from python_backend.app.core.enums import SearchProviderEnum, ApiStatusEnum, ApiTypeEnum
from python_backend.app.models.database import APIKey, RepoReference, SearchQuery, SearchProviderToken

logger = structlog.get_logger()


@dataclass
class ScrapingStats:
    """Statistics for scraping operations"""
    new_keys_found: int = 0
    duplicate_keys_found: int = 0
    total_searched: int = 0
    errors: int = 0


class CircuitBreaker:
    """Circuit breaker for external API calls"""
    
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


class KeySimilarityChecker:
    """Enhanced key similarity checker for duplicate detection"""
    
    SIMILARITY_THRESHOLD = 0.85
    
    @staticmethod
    def are_similar(key1: str, key2: str) -> bool:
        """Check if two keys are similar"""
        if not key1 or not key2:
            return False
        
        if key1.lower() == key2.lower():
            return True
        
        # Calculate Jaccard similarity
        similarity = KeySimilarityChecker._calculate_jaccard_similarity(key1, key2)
        return similarity >= KeySimilarityChecker.SIMILARITY_THRESHOLD
    
    @staticmethod
    def _calculate_jaccard_similarity(str1: str, str2: str) -> float:
        """Calculate Jaccard similarity between two strings"""
        ngrams1 = set(KeySimilarityChecker._get_ngrams(str1, 3))
        ngrams2 = set(KeySimilarityChecker._get_ngrams(str2, 3))
        
        intersection = len(ngrams1.intersection(ngrams2))
        union = len(ngrams1.union(ngrams2))
        
        return intersection / union if union > 0 else 0
    
    @staticmethod
    def _get_ngrams(text: str, n: int) -> List[str]:
        """Get n-grams from text"""
        return [text[i:i+n] for i in range(len(text) - n + 1)]


class APIKeyPatterns:
    """API key pattern matching"""
    
    # Common API key patterns
    PATTERNS = {
        ApiTypeEnum.OPENAI: [
            r'sk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}',
            r'sk-proj-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}',
        ],
        ApiTypeEnum.ANTHROPIC_CLAUDE: [
            r'sk-ant-api03-[A-Za-z0-9_-]{95}',
        ],
        ApiTypeEnum.GITHUB: [
            r'ghp_[A-Za-z0-9]{36}',
            r'github_pat_[A-Za-z0-9_]{82}',
            r'ghs_[A-Za-z0-9]{36}',
            r'ghr_[A-Za-z0-9]{36}',
        ],
        ApiTypeEnum.STRIPE: [
            r'sk_live_[A-Za-z0-9]{24}',
            r'sk_test_[A-Za-z0-9]{24}',
            r'pk_live_[A-Za-z0-9]{24}',
            r'pk_test_[A-Za-z0-9]{24}',
        ],
        ApiTypeEnum.AWS: [
            r'AKIA[0-9A-Z]{16}',
        ],
        ApiTypeEnum.GOOGLE_AI: [
            r'AIza[0-9A-Za-z_-]{35}',
        ],
        ApiTypeEnum.SENDGRID: [
            r'SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}',
        ],
        ApiTypeEnum.TWILIO: [
            r'SK[a-f0-9]{32}',
            r'AC[a-f0-9]{32}',
        ],
    }
    
    @classmethod
    def detect_api_type(cls, api_key: str) -> ApiTypeEnum:
        """Detect API type from key pattern"""
        for api_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, api_key):
                    return api_type
        return ApiTypeEnum.UNKNOWN
    
    @classmethod
    def extract_keys_from_content(cls, content: str) -> List[Tuple[str, ApiTypeEnum]]:
        """Extract API keys from file content"""
        found_keys = []
        
        for api_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    found_keys.append((match, api_type))
        
        return found_keys


class GitHubSearchProvider:
    """GitHub search provider for finding API keys"""
    
    def __init__(self, session: aiohttp.ClientSession, db_pool: asyncpg.Pool):
        self.session = session
        self.db_pool = db_pool
        self.base_url = "https://api.github.com"
        self.circuit_breaker = CircuitBreaker()
    
    async def get_auth_headers(self) -> Dict[str, str]:
        """Get GitHub authentication headers"""
        # Get a valid GitHub token from database
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT "Token" FROM "SearchProviderTokens" WHERE "Provider" = $1 AND "IsActive" = true ORDER BY "LastUsedUTC" NULLS FIRST LIMIT 1',
                SearchProviderEnum.GITHUB.value
            )
            
            if row:
                token = row['Token']
                return {
                    'Authorization': f'token {token}',
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'UnsecuredAPIKeys-Bot/1.0'
                }
        
        raise Exception("No valid GitHub token available")
    
    async def search_code(self, query: str, page: int = 1, per_page: int = 100) -> List[Dict]:
        """Search for code on GitHub"""
        if await self.circuit_breaker.is_circuit_open():
            logger.warning("GitHub circuit breaker is open, skipping search")
            return []
        
        try:
            headers = await self.get_auth_headers()
            params = {
                'q': query,
                'page': page,
                'per_page': per_page,
                'sort': 'indexed'
            }
            
            url = f"{self.base_url}/search/code"
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    await self.circuit_breaker.record_success()
                    return data.get('items', [])
                elif response.status == 403:
                    # Rate limit hit
                    logger.warning("GitHub rate limit hit")
                    await self.circuit_breaker.record_failure()
                    return []
                else:
                    await self.circuit_breaker.record_failure()
                    return []
                    
        except Exception as e:
            logger.error("Error searching GitHub", error=str(e))
            await self.circuit_breaker.record_failure()
            return []
    
    async def get_file_content(self, file_url: str) -> Optional[str]:
        """Get file content from GitHub"""
        try:
            headers = await self.get_auth_headers()
            
            async with self.session.get(file_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data.get('content', '')
                    
                    # Decode base64 content
                    if content:
                        try:
                            decoded = base64.b64decode(content).decode('utf-8')
                            return decoded
                        except Exception:
                            return None
                
                return None
                
        except Exception as e:
            logger.error("Error getting file content", error=str(e))
            return None


class APIKeyScraper:
    """Main API key scraper class"""
    
    def __init__(self):
        self.stats = ScrapingStats()
        self.session: Optional[aiohttp.ClientSession] = None
        self.db_pool: Optional[asyncpg.Pool] = None
        self.github_provider: Optional[GitHubSearchProvider] = None
        self.shutdown_event = asyncio.Event()
        self.known_keys: Set[str] = set()
    
    async def initialize(self):
        """Initialize the scraper"""
        logger.info("Initializing API Key Scraper")
        
        # Create database connection pool
        self.db_pool = await asyncpg.create_pool(
            settings.database_url.replace('+asyncpg', ''),
            min_size=5,
            max_size=20
        )
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        self.session = aiohttp.ClientSession(timeout=timeout)
        
        # Initialize providers
        self.github_provider = GitHubSearchProvider(self.session, self.db_pool)
        
        # Load existing keys to avoid duplicates
        await self.load_existing_keys()
        
        logger.info("API Key Scraper initialized")
    
    async def shutdown(self):
        """Shutdown the scraper"""
        logger.info("Shutting down API Key Scraper")
        self.shutdown_event.set()
        
        if self.session:
            await self.session.close()
        
        if self.db_pool:
            await self.db_pool.close()
        
        logger.info("API Key Scraper shutdown complete")
    
    async def load_existing_keys(self):
        """Load existing API keys to avoid duplicates"""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch('SELECT "ApiKey" FROM "APIKeys"')
            self.known_keys = {row['ApiKey'] for row in rows}
        
        logger.info(f"Loaded {len(self.known_keys)} existing keys")
    
    async def run_scraping_loop(self):
        """Main scraping loop"""
        logger.info("Starting scraping loop")
        
        while not self.shutdown_event.is_set():
            try:
                # Get enabled search queries
                queries = await self.get_search_queries()
                
                if not queries:
                    logger.debug("No search queries enabled, sleeping...")
                    await asyncio.sleep(300)  # 5 minutes
                    continue
                
                # Process each query
                for query_data in queries:
                    if self.shutdown_event.is_set():
                        break
                    
                    await self.process_search_query(query_data)
                    
                    # Brief pause between queries
                    await asyncio.sleep(10)
                
                # Log progress
                logger.info("Scraping progress",
                           new_keys=self.stats.new_keys_found,
                           duplicates=self.stats.duplicate_keys_found,
                           total_searched=self.stats.total_searched,
                           errors=self.stats.errors)
                
                # Longer pause between full cycles
                await asyncio.sleep(300)  # 5 minutes
                
            except Exception as e:
                logger.error("Error in scraping loop", error=str(e))
                await asyncio.sleep(600)  # Wait longer on error
    
    async def get_search_queries(self) -> List[Dict]:
        """Get enabled search queries from database"""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                'SELECT "Id", "Query", "Provider" FROM "SearchQueries" WHERE "IsEnabled" = true'
            )
            return [dict(row) for row in rows]
    
    async def process_search_query(self, query_data: Dict):
        """Process a single search query"""
        query_id = query_data['Id']
        query_text = query_data['Query']
        provider = SearchProviderEnum(query_data['Provider'])
        
        logger.info(f"Processing query: {query_text} on {provider.name}")
        
        try:
            if provider == SearchProviderEnum.GITHUB:
                await self.search_github(query_id, query_text)
            else:
                logger.warning(f"Unsupported provider: {provider.name}")
            
            # Update last search time
            await self.update_query_last_search(query_id)
            
        except Exception as e:
            logger.error(f"Error processing query {query_id}", error=str(e))
            self.stats.errors += 1
    
    async def search_github(self, query_id: int, query_text: str):
        """Search GitHub for API keys"""
        page = 1
        max_pages = 10  # Limit to avoid hitting rate limits
        
        while page <= max_pages:
            if self.shutdown_event.is_set():
                break
            
            results = await self.github_provider.search_code(query_text, page=page)
            
            if not results:
                break
            
            # Process each search result
            for result in results:
                if self.shutdown_event.is_set():
                    break
                
                await self.process_search_result(query_id, result, SearchProviderEnum.GITHUB)
            
            page += 1
            self.stats.total_searched += len(results)
            
            # Rate limiting pause
            await asyncio.sleep(2)
    
    async def process_search_result(self, query_id: int, result: Dict, provider: SearchProviderEnum):
        """Process a single search result"""
        try:
            # Extract file information
            file_url = result.get('url')  # API URL for file content
            html_url = result.get('html_url')  # Web URL
            file_name = result.get('name')
            file_path = result.get('path')
            
            # Repository information
            repo_info = result.get('repository', {})
            repo_url = repo_info.get('html_url')
            repo_name = repo_info.get('name')
            repo_owner = repo_info.get('owner', {}).get('login')
            repo_id = repo_info.get('id')
            repo_description = repo_info.get('description')
            
            # Get file content
            content = await self.github_provider.get_file_content(file_url)
            if not content:
                return
            
            # Extract API keys from content
            found_keys = APIKeyPatterns.extract_keys_from_content(content)
            
            for api_key, api_type in found_keys:
                await self.process_found_key(
                    api_key, api_type, query_id, provider,
                    repo_url, repo_name, repo_owner, repo_id, repo_description,
                    html_url, file_name, file_path, content
                )
            
        except Exception as e:
            logger.error("Error processing search result", error=str(e))
            self.stats.errors += 1
    
    async def process_found_key(self, api_key: str, api_type: ApiTypeEnum, query_id: int,
                               provider: SearchProviderEnum, repo_url: str, repo_name: str,
                               repo_owner: str, repo_id: int, repo_description: str,
                               file_url: str, file_name: str, file_path: str, content: str):
        """Process a found API key"""
        try:
            # Check if key already exists or is similar to existing ones
            if api_key in self.known_keys:
                self.stats.duplicate_keys_found += 1
                return
            
            # Check for similar keys
            for known_key in self.known_keys:
                if KeySimilarityChecker.are_similar(api_key, known_key):
                    self.stats.duplicate_keys_found += 1
                    return
            
            # Extract context around the key
            context = self.extract_context(content, api_key)
            line_number = self.get_line_number(content, api_key)
            
            # Save new API key
            key_id = await self.save_api_key(api_key, api_type, provider)
            
            # Save repository reference
            await self.save_repo_reference(
                key_id, query_id, repo_url, repo_name, repo_owner, repo_id,
                repo_description, file_url, file_name, file_path, context, line_number
            )
            
            # Add to known keys
            self.known_keys.add(api_key)
            self.stats.new_keys_found += 1
            
            logger.info(f"Found new {api_type.name} key in {repo_owner}/{repo_name}")
            
        except Exception as e:
            logger.error("Error processing found key", error=str(e))
            self.stats.errors += 1
    
    async def save_api_key(self, api_key: str, api_type: ApiTypeEnum, provider: SearchProviderEnum) -> int:
        """Save API key to database"""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                '''INSERT INTO "APIKeys" 
                   ("ApiKey", "Status", "ApiType", "SearchProvider", "FirstFoundUTC", "LastFoundUTC", "TimesDisplayed", "ErrorCount")
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                   RETURNING "Id"''',
                api_key,
                ApiStatusEnum.UNVERIFIED.value,
                api_type.value,
                provider.value,
                datetime.utcnow(),
                datetime.utcnow(),
                0,
                0
            )
            return row['Id']
    
    async def save_repo_reference(self, key_id: int, query_id: int, repo_url: str,
                                 repo_name: str, repo_owner: str, repo_id: int,
                                 repo_description: str, file_url: str, file_name: str,
                                 file_path: str, context: str, line_number: int):
        """Save repository reference to database"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                '''INSERT INTO "RepoReferences"
                   ("APIKeyId", "RepoURL", "RepoOwner", "RepoName", "RepoDescription", "RepoId",
                    "FileURL", "FileName", "FilePath", "CodeContext", "LineNumber", 
                    "SearchQueryId", "FoundUTC", "Provider")
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)''',
                key_id, repo_url, repo_owner, repo_name, repo_description, repo_id,
                file_url, file_name, file_path, context, line_number,
                query_id, datetime.utcnow(), "GitHub"
            )
    
    async def update_query_last_search(self, query_id: int):
        """Update last search time for query"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                'UPDATE "SearchQueries" SET "LastSearchUTC" = $1 WHERE "Id" = $2',
                datetime.utcnow(),
                query_id
            )
    
    def extract_context(self, content: str, api_key: str, context_lines: int = 3) -> str:
        """Extract context around the API key"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            if api_key in line:
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                return '\n'.join(lines[start:end])
        
        return ""
    
    def get_line_number(self, content: str, api_key: str) -> int:
        """Get line number where API key appears"""
        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            if api_key in line:
                return i + 1
        
        return 0


async def main():
    """Main entry point for the scraper bot"""
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
    
    logger.info("Starting UnsecuredAPIKeys Python Scraper Bot")
    
    scraper = APIKeyScraper()
    
    try:
        await scraper.initialize()
        await scraper.run_scraping_loop()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error("Fatal error in scraper", error=str(e))
    finally:
        await scraper.shutdown()


if __name__ == "__main__":
    asyncio.run(main())