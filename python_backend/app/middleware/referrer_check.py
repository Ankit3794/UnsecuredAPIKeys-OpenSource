from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List
import structlog

logger = structlog.get_logger()


class ReferrerCheckMiddleware(BaseHTTPMiddleware):
    """Middleware to check allowed referrers for specific endpoints"""
    
    def __init__(self, app, allowed_domains: List[str] = None):
        super().__init__(app)
        self.allowed_domains = allowed_domains or ["localhost:3000", "localhost:3001"]
    
    async def dispatch(self, request: Request, call_next):
        # Check if this endpoint requires referrer validation
        if self._requires_referrer_check(request.url.path):
            if not self._is_allowed_referrer(request):
                logger.warning("Blocked request from unauthorized referrer", 
                             path=request.url.path, 
                             referrer=request.headers.get("referer"))
                raise HTTPException(status_code=403, detail="Forbidden")
        
        response = await call_next(request)
        return response
    
    def _requires_referrer_check(self, path: str) -> bool:
        """Check if path requires referrer validation"""
        protected_paths = [
            "/API/GetRandomKey",
            "/API/GetAllValidKeys"
        ]
        return any(path.startswith(protected_path) for protected_path in protected_paths)
    
    def _is_allowed_referrer(self, request: Request) -> bool:
        """Check if referrer is allowed"""
        referrer = request.headers.get("referer", "")
        
        # Allow requests without referrer for development
        if not referrer:
            return True
        
        # Check against allowed domains
        for domain in self.allowed_domains:
            if domain in referrer:
                return True
        
        return False


def check_referrer(func):
    """Decorator for referrer checking (used in route handlers)"""
    async def wrapper(*args, **kwargs):
        request = kwargs.get('request')
        if request and hasattr(request, 'headers'):
            middleware = ReferrerCheckMiddleware(None)
            if middleware._requires_referrer_check(request.url.path):
                if not middleware._is_allowed_referrer(request):
                    raise HTTPException(status_code=403, detail="Forbidden")
        return await func(*args, **kwargs)
    return wrapper