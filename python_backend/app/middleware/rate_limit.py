from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List
import asyncio
import structlog

logger = structlog.get_logger()


class RateLimitStore:
    """In-memory rate limit store (should use Redis in production)"""
    
    def __init__(self):
        self.requests: Dict[str, List[datetime]] = defaultdict(list)
        self.lock = asyncio.Lock()
    
    async def is_rate_limited(self, key: str, limit: int, window_minutes: int) -> tuple[bool, int]:
        """Check if key is rate limited and return remaining requests"""
        async with self.lock:
            now = datetime.utcnow()
            window_start = now - timedelta(minutes=window_minutes)
            
            # Clean old requests
            self.requests[key] = [req_time for req_time in self.requests[key] if req_time > window_start]
            
            # Check if limit exceeded
            current_count = len(self.requests[key])
            
            if current_count >= limit:
                return True, 0
            
            # Add current request
            self.requests[key].append(now)
            remaining = limit - (current_count + 1)
            
            return False, remaining
    
    async def cleanup_old_entries(self):
        """Cleanup old entries periodically"""
        async with self.lock:
            now = datetime.utcnow()
            cutoff = now - timedelta(hours=24)  # Remove entries older than 24 hours
            
            keys_to_remove = []
            for key, requests in self.requests.items():
                self.requests[key] = [req_time for req_time in requests if req_time > cutoff]
                if not self.requests[key]:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.requests[key]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware matching C# rate limiting functionality"""
    
    def __init__(self, app):
        super().__init__(app)
        self.store = RateLimitStore()
        self.default_limit = 5
        self.default_window = 60
        self.server_member_limit = 20
        self.site_creator_limit = 999999
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_task())
    
    async def dispatch(self, request: Request, call_next):
        # Get rate limit config for this endpoint
        limit, window = self._get_rate_limit_config(request)
        
        if limit is None:
            # No rate limiting for this endpoint
            response = await call_next(request)
            return response
        
        # Get client identifier
        client_id = self._get_client_id(request)
        
        # Check rate limit
        is_limited, remaining = await self.store.is_rate_limited(
            f"{client_id}:{request.url.path}", 
            limit, 
            window
        )
        
        if is_limited:
            logger.warning("Rate limit exceeded", 
                         client_id=client_id, 
                         path=request.url.path,
                         limit=limit)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window_minutes": window,
                    "retry_after": window * 60
                }
            )
        
        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int((datetime.utcnow() + timedelta(minutes=window)).timestamp()))
        
        return response
    
    def _get_rate_limit_config(self, request: Request) -> tuple[int, int]:
        """Get rate limit configuration for endpoint"""
        # Define rate-limited endpoints
        rate_limited_endpoints = {
            "/API/GetRandomKey": (10, 60),
            "/API/GetAllValidKeys": (10, 60),
        }
        
        for endpoint, (limit, window) in rate_limited_endpoints.items():
            if request.url.path.startswith(endpoint):
                return limit, window
        
        return None, None
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting"""
        # Try to get Discord user ID from headers first
        discord_id = request.headers.get("X-Discord-ID")
        if discord_id:
            return f"discord:{discord_id}"
        
        # Fall back to IP address
        ip = self._get_client_ip(request)
        return f"ip:{ip}"
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        return str(request.client.host) if request.client else "unknown"
    
    async def _cleanup_task(self):
        """Periodic cleanup of old rate limit entries"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self.store.cleanup_old_entries()
                logger.debug("Rate limit store cleanup completed")
            except Exception as e:
                logger.error("Error in rate limit cleanup", error=str(e))


def rate_limit(limit: int = 5, window_minutes: int = 60):
    """Decorator for applying rate limiting to specific endpoints"""
    def decorator(func):
        # Store rate limit config on function
        func._rate_limit_config = (limit, window_minutes)
        
        async def wrapper(*args, **kwargs):
            # Rate limiting is handled by middleware
            return await func(*args, **kwargs)
        
        wrapper._rate_limit_config = (limit, window_minutes)
        return wrapper
    return decorator