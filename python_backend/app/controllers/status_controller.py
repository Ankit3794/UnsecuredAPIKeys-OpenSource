from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import structlog

from app.core.database import get_db
from app.schemas.api_schemas import SystemStatus

logger = structlog.get_logger()
router = APIRouter()


@router.get("/health", response_model=SystemStatus)
async def get_health_status(db: AsyncSession = Depends(get_db)):
    """Health check endpoint matching C# StatusController"""
    try:
        # Test database connection
        await db.execute("SELECT 1")
        database_connected = True
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        database_connected = False
    
    # Check service status
    services = {
        "database": "healthy" if database_connected else "unhealthy",
        "api": "healthy",
        "websocket": "healthy"
    }
    
    overall_status = "healthy" if all(status == "healthy" for status in services.values()) else "unhealthy"
    
    return SystemStatus(
        status=overall_status,
        timestamp=datetime.utcnow(),
        services=services,
        database_connected=database_connected
    )


@router.get("/")
async def status_root():
    """Basic status endpoint"""
    return {
        "service": "UnsecuredAPIKeys Python Backend",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }