from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.orm import selectinload
from typing import Optional, List
import random
from datetime import datetime, timedelta
import structlog

from app.core.database import get_db
from app.models.database import APIKey, RepoReference, IssueSubmissionTracking, DonationTracking
from app.schemas.api_schemas import (
    APIKeyResponse, PaginatedResponse, ApiTypeCountDto, StatsResponse,
    IssueSubmissionTrackingDto, DonationClickTrackingDto, KeyFixedNotification
)
from app.core.enums import ApiStatusEnum, ApiTypeEnum
from app.middleware.rate_limit import rate_limit
from app.middleware.referrer_check import check_referrer
from app.services.display_count_service import DisplayCountService
from app.services.websocket_service import WebSocketManager

logger = structlog.get_logger()
router = APIRouter()

# Service instances
display_count_service = DisplayCountService()
websocket_manager = WebSocketManager()


@router.get("/GetRandomKey", response_model=Optional[APIKeyResponse])
@check_referrer
@rate_limit(limit=10)
async def get_random_key(
    type: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    request: Request = None
):
    """Get a random valid API key, matching C# GetRandomKey endpoint"""
    try:
        # Build query for valid keys
        query = select(APIKey).options(selectinload(APIKey.References)).where(
            APIKey.Status == ApiStatusEnum.VALID
        )
        
        # Add type filter if specified
        if type is not None:
            try:
                api_type = ApiTypeEnum(type)
                query = query.where(APIKey.ApiType == api_type)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid API type")
        
        # Execute query to get all valid keys
        result = await db.execute(query)
        keys = result.scalars().all()
        
        if not keys:
            return None
        
        # Select random key
        selected_key = random.choice(keys)
        
        # Update display count
        selected_key.TimesDisplayed += 1
        await db.commit()
        
        # Update global display count
        display_count_service.increment_display_count()
        
        # Send real-time update
        await websocket_manager.broadcast({
            "type": "key_displayed",
            "data": {
                "keyId": selected_key.Id,
                "totalDisplayCount": display_count_service.total_display_count
            }
        })
        
        logger.info("Random key retrieved", key_id=selected_key.Id, api_type=selected_key.ApiType.value)
        return selected_key
        
    except Exception as e:
        logger.error("Error getting random key", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetDisplayCount", response_model=int)
async def get_display_count():
    """Get total display count, matching C# GetDisplayCount endpoint"""
    return display_count_service.total_display_count


@router.get("/GetAllValidKeys", response_model=PaginatedResponse)
@check_referrer
@rate_limit(limit=10)
async def get_all_valid_keys(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=100),
    type: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Get paginated list of valid API keys, matching C# GetAllValidKeys endpoint"""
    try:
        # Build query
        query = select(APIKey).options(selectinload(APIKey.References)).where(
            APIKey.Status == ApiStatusEnum.VALID
        )
        
        # Add type filter if specified
        if type is not None:
            try:
                api_type = ApiTypeEnum(type)
                query = query.where(APIKey.ApiType == api_type)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid API type")
        
        # Get total count
        count_query = select(func.count(APIKey.Id)).where(
            APIKey.Status == ApiStatusEnum.VALID
        )
        if type is not None:
            count_query = count_query.where(APIKey.ApiType == api_type)
        
        total_count_result = await db.execute(count_query)
        total_count = total_count_result.scalar()
        
        # Apply pagination and ordering
        query = query.order_by(asc(APIKey.Id)).offset((page - 1) * pageSize).limit(pageSize)
        
        # Execute query
        result = await db.execute(query)
        items = result.scalars().all()
        
        # Calculate total pages
        total_pages = (total_count + pageSize - 1) // pageSize
        
        return PaginatedResponse(
            Items=items,
            Page=page,
            PageSize=pageSize,
            TotalCount=total_count,
            TotalPages=total_pages
        )
        
    except Exception as e:
        logger.error("Error getting valid keys", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetStats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get API key statistics, matching C# GetStats endpoint"""
    try:
        # Get counts by status
        total_keys_result = await db.execute(select(func.count(APIKey.Id)))
        total_keys = total_keys_result.scalar()
        
        valid_keys_result = await db.execute(
            select(func.count(APIKey.Id)).where(APIKey.Status == ApiStatusEnum.VALID)
        )
        valid_keys = valid_keys_result.scalar()
        
        invalid_keys_result = await db.execute(
            select(func.count(APIKey.Id)).where(APIKey.Status == ApiStatusEnum.INVALID)
        )
        invalid_keys = invalid_keys_result.scalar()
        
        unverified_keys_result = await db.execute(
            select(func.count(APIKey.Id)).where(APIKey.Status == ApiStatusEnum.UNVERIFIED)
        )
        unverified_keys = unverified_keys_result.scalar()
        
        # Get total references
        total_references_result = await db.execute(select(func.count(RepoReference.Id)))
        total_references = total_references_result.scalar()
        
        return StatsResponse(
            TotalKeys=total_keys,
            ValidKeys=valid_keys,
            InvalidKeys=invalid_keys,
            UnverifiedKeys=unverified_keys,
            TotalReferences=total_references
        )
        
    except Exception as e:
        logger.error("Error getting stats", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetKeyTypes", response_model=List[ApiTypeCountDto])
async def get_key_types(db: AsyncSession = Depends(get_db)):
    """Get API key counts by type, matching C# GetKeyTypes endpoint"""
    try:
        query = select(
            APIKey.ApiType,
            func.count(APIKey.Id).label('count')
        ).where(
            APIKey.Status == ApiStatusEnum.VALID
        ).group_by(APIKey.ApiType).order_by(desc('count'))
        
        result = await db.execute(query)
        rows = result.all()
        
        return [
            ApiTypeCountDto(ApiType=row.ApiType, Count=row.count)
            for row in rows
        ]
        
    except Exception as e:
        logger.error("Error getting key types", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/TrackIssueSubmission")
async def track_issue_submission(
    request_data: IssueSubmissionTrackingDto,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Track issue submission, matching C# TrackIssueSubmission endpoint"""
    try:
        # Get client IP
        ip_address = get_client_ip(request)
        
        # Create tracking record
        tracking = IssueSubmissionTracking(
            ApiKeyId=request_data.ApiKeyId,
            IpAddress=ip_address,
            SubmittedUTC=datetime.utcnow(),
            IssueURL=request_data.IssueURL
        )
        
        db.add(tracking)
        await db.commit()
        
        logger.info("Issue submission tracked", api_key_id=request_data.ApiKeyId, ip=ip_address)
        return {"success": True}
        
    except Exception as e:
        logger.error("Error tracking issue submission", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/TrackDonationClick")
async def track_donation_click(
    request_data: DonationClickTrackingDto,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Track donation click, matching C# TrackDonationClick endpoint"""
    try:
        # Get client IP
        ip_address = get_client_ip(request)
        
        # Create or update tracking record
        existing_query = select(DonationTracking).where(
            DonationTracking.TrackingId == request_data.TrackingId
        )
        result = await db.execute(existing_query)
        existing = result.scalar_one_or_none()
        
        if not existing:
            tracking = DonationTracking(
                TrackingId=request_data.TrackingId,
                IpAddress=ip_address,
                ClickUTC=datetime.utcnow()
            )
            db.add(tracking)
            await db.commit()
        
        logger.info("Donation click tracked", tracking_id=request_data.TrackingId, ip=ip_address)
        return {"success": True}
        
    except Exception as e:
        logger.error("Error tracking donation click", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/GetDonationStats")
async def get_donation_stats(db: AsyncSession = Depends(get_db)):
    """Get donation statistics, matching C# GetDonationStats endpoint"""
    try:
        # Get total clicks
        total_clicks_result = await db.execute(select(func.count(DonationTracking.Id)))
        total_clicks = total_clicks_result.scalar()
        
        # Get confirmed donations
        confirmed_donations_result = await db.execute(
            select(func.count(DonationTracking.Id)).where(
                DonationTracking.ConfirmedDonation == True
            )
        )
        confirmed_donations = confirmed_donations_result.scalar()
        
        return {
            "totalClicks": total_clicks,
            "confirmedDonations": confirmed_donations,
            "conversionRate": (confirmed_donations / total_clicks * 100) if total_clicks > 0 else 0
        }
        
    except Exception as e:
        logger.error("Error getting donation stats", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/webhook/key-fixed")
async def key_fixed_webhook(notification: KeyFixedNotification, db: AsyncSession = Depends(get_db)):
    """Handle key fixed webhook, matching C# KeyFixedWebhook endpoint"""
    try:
        # Update key status to invalid/fixed
        query = select(APIKey).where(APIKey.Id == notification.ApiKeyId)
        result = await db.execute(query)
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            raise HTTPException(status_code=404, detail="API key not found")
        
        api_key.Status = ApiStatusEnum.NO_LONGER_WORKING
        api_key.LastCheckedUTC = notification.FixedUTC
        
        await db.commit()
        
        # Send real-time update
        await websocket_manager.broadcast({
            "type": "key_fixed",
            "data": {
                "keyId": notification.ApiKeyId,
                "reason": notification.Reason
            }
        })
        
        logger.info("Key marked as fixed", key_id=notification.ApiKeyId, reason=notification.Reason)
        return {"success": True}
        
    except Exception as e:
        logger.error("Error processing key fixed webhook", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


def get_client_ip(request: Request) -> str:
    """Get client IP address from request"""
    # Check for forwarded IP headers first (for load balancers/proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # Fall back to direct connection IP
    return str(request.client.host) if request.client else "Unknown"