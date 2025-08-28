import asyncio
from typing import Dict, Set
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()


class DisplayCountService:
    """Service for tracking display counts, matching C# DisplayCountService"""
    
    def __init__(self):
        self._total_display_count = 0
        self._lock = asyncio.Lock()
    
    @property
    def total_display_count(self) -> int:
        """Get total display count"""
        return self._total_display_count
    
    async def increment_display_count(self):
        """Increment the global display count"""
        async with self._lock:
            self._total_display_count += 1
            logger.debug("Display count incremented", count=self._total_display_count)
    
    async def set_display_count(self, count: int):
        """Set the display count (for initialization from database)"""
        async with self._lock:
            self._total_display_count = count
            logger.info("Display count initialized", count=count)


class ActiveUserService:
    """Service for tracking active users, matching C# ActiveUserService"""
    
    def __init__(self):
        self._connections: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        
        # Start cleanup task
        asyncio.create_task(self._cleanup_task())
    
    @property
    def active_user_count(self) -> int:
        """Get current active user count"""
        return len(self._connections)
    
    async def user_connected(self, connection_id: str):
        """Track user connection"""
        async with self._lock:
            self._connections[connection_id] = datetime.utcnow()
            logger.debug("User connected", connection_id=connection_id, active_count=len(self._connections))
    
    async def user_disconnected(self, connection_id: str):
        """Track user disconnection"""
        async with self._lock:
            if connection_id in self._connections:
                del self._connections[connection_id]
                logger.debug("User disconnected", connection_id=connection_id, active_count=len(self._connections))
    
    async def update_last_seen(self, connection_id: str):
        """Update last seen time for connection"""
        async with self._lock:
            if connection_id in self._connections:
                self._connections[connection_id] = datetime.utcnow()
    
    async def validate_connections(self):
        """Validate active connections (remove stale ones)"""
        async with self._lock:
            cutoff = datetime.utcnow() - timedelta(minutes=5)  # 5 minute timeout
            stale_connections = [
                conn_id for conn_id, last_seen in self._connections.items()
                if last_seen < cutoff
            ]
            
            for conn_id in stale_connections:
                del self._connections[conn_id]
                logger.debug("Removed stale connection", connection_id=conn_id)
    
    async def _cleanup_task(self):
        """Periodic cleanup of stale connections"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                await self.validate_connections()
            except Exception as e:
                logger.error("Error in active user cleanup", error=str(e))