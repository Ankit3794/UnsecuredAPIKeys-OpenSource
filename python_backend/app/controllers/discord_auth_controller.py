from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import httpx
import structlog

from app.core.database import get_db
from app.core.config import settings
from app.models.database import DiscordUser
from app.schemas.api_schemas import (
    DiscordCallbackRequest, DiscordAuthResponse, DiscordUserResponse
)

logger = structlog.get_logger()
router = APIRouter()


@router.get("/login")
async def get_login_url():
    """Get Discord OAuth login URL, matching C# DiscordAuthController.GetLoginUrl"""
    try:
        if not settings.discord_client_id:
            raise HTTPException(status_code=500, detail="Discord OAuth not configured")
        
        # Build Discord OAuth URL
        params = {
            "client_id": settings.discord_client_id,
            "redirect_uri": settings.discord_redirect_uri,
            "response_type": "code",
            "scope": "identify guilds"
        }
        
        base_url = "https://discord.com/api/oauth2/authorize"
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        auth_url = f"{base_url}?{query_string}"
        
        return {"loginUrl": auth_url}
        
    except Exception as e:
        logger.error("Error generating Discord login URL", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/callback", response_model=DiscordAuthResponse)
async def handle_callback(
    request_data: DiscordCallbackRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Handle Discord OAuth callback, matching C# DiscordAuthController.HandleCallback"""
    try:
        if not settings.discord_client_id or not settings.discord_client_secret:
            raise HTTPException(status_code=500, detail="Discord OAuth not configured")
        
        # Exchange code for access token
        token_data = await exchange_code_for_token(request_data.code)
        if not token_data:
            return DiscordAuthResponse(success=False, error="Failed to exchange code for token")
        
        # Get user info from Discord
        user_info = await get_discord_user_info(token_data["access_token"])
        if not user_info:
            return DiscordAuthResponse(success=False, error="Failed to get user info")
        
        # Get client IP
        ip_address = get_client_ip(request)
        
        # Create or update Discord user
        discord_user = await get_or_create_discord_user(
            db, user_info, token_data, ip_address
        )
        
        return DiscordAuthResponse(
            success=True,
            user={
                "discordId": discord_user.DiscordId,
                "username": discord_user.Username,
                "avatar": discord_user.Avatar,
                "isServerMember": discord_user.IsServerMember
            }
        )
        
    except Exception as e:
        logger.error("Error handling Discord callback", error=str(e))
        return DiscordAuthResponse(success=False, error="Internal server error")


@router.get("/user/{discord_id}", response_model=DiscordUserResponse)
async def get_user_info(discord_id: str, db: AsyncSession = Depends(get_db)):
    """Get Discord user info, matching C# DiscordAuthController.GetUserInfo"""
    try:
        from sqlalchemy import select
        
        query = select(DiscordUser).where(DiscordUser.DiscordId == discord_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Determine rate limit based on server membership
        rate_limit = None
        if user.IsServerMember:
            rate_limit = settings.rate_limit_server_member
        
        return DiscordUserResponse(
            DiscordId=user.DiscordId,
            Username=user.Username,
            Avatar=user.Avatar,
            IsServerMember=user.IsServerMember,
            RateLimit=rate_limit
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting user info", error=str(e), discord_id=discord_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/refresh-membership/{discord_id}")
async def refresh_membership(discord_id: str, db: AsyncSession = Depends(get_db)):
    """Refresh user's server membership status"""
    try:
        from sqlalchemy import select
        
        query = select(DiscordUser).where(DiscordUser.DiscordId == discord_id)
        result = await db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Refresh token if needed
        if user.TokenExpiresAt <= datetime.utcnow():
            await refresh_user_token(user)
            await db.commit()
        
        # Check server membership
        is_member = await verify_server_membership(user.DiscordId, user.AccessToken)
        user.IsServerMember = is_member
        await db.commit()
        
        return {"success": True, "isServerMember": is_member}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error refreshing membership", error=str(e), discord_id=discord_id)
        raise HTTPException(status_code=500, detail="Internal server error")


async def exchange_code_for_token(code: str) -> dict:
    """Exchange OAuth code for access token"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": settings.discord_client_id,
                    "client_secret": settings.discord_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.discord_redirect_uri
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error("Failed to exchange code for token", 
                           status_code=response.status_code,
                           response=response.text)
                return None
                
    except Exception as e:
        logger.error("Error exchanging code for token", error=str(e))
        return None


async def get_discord_user_info(access_token: str) -> dict:
    """Get Discord user information"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error("Failed to get Discord user info",
                           status_code=response.status_code)
                return None
                
    except Exception as e:
        logger.error("Error getting Discord user info", error=str(e))
        return None


async def verify_server_membership(discord_id: str, access_token: str) -> bool:
    """Verify if user is member of the Discord server"""
    try:
        if not settings.discord_server_id:
            return False
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://discord.com/api/users/@me/guilds/{settings.discord_server_id}/member",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            return response.status_code == 200
            
    except Exception as e:
        logger.error("Error verifying server membership", error=str(e))
        return False


async def get_or_create_discord_user(
    db: AsyncSession, 
    user_info: dict, 
    token_data: dict, 
    ip_address: str
) -> DiscordUser:
    """Get or create Discord user in database"""
    from sqlalchemy import select
    
    discord_id = user_info["id"]
    
    # Check if user exists
    query = select(DiscordUser).where(DiscordUser.DiscordId == discord_id)
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    token_expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
    
    if user:
        # Update existing user
        user.Username = user_info["username"]
        user.Avatar = user_info.get("avatar")
        user.AccessToken = token_data["access_token"]
        user.RefreshToken = token_data["refresh_token"]
        user.TokenExpiresAt = token_expires_at
        user.LastLoginUTC = datetime.utcnow()
        user.IpAddress = ip_address
    else:
        # Create new user
        user = DiscordUser(
            DiscordId=discord_id,
            Username=user_info["username"],
            Avatar=user_info.get("avatar"),
            AccessToken=token_data["access_token"],
            RefreshToken=token_data["refresh_token"],
            TokenExpiresAt=token_expires_at,
            IsServerMember=False,
            LastLoginUTC=datetime.utcnow(),
            IpAddress=ip_address
        )
        db.add(user)
    
    # Check server membership
    user.IsServerMember = await verify_server_membership(discord_id, token_data["access_token"])
    
    await db.commit()
    return user


async def refresh_user_token(user: DiscordUser):
    """Refresh user's Discord access token"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id": settings.discord_client_id,
                    "client_secret": settings.discord_client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": user.RefreshToken
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code == 200:
                token_data = response.json()
                user.AccessToken = token_data["access_token"]
                user.RefreshToken = token_data["refresh_token"]
                user.TokenExpiresAt = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
                logger.info("Discord token refreshed", discord_id=user.DiscordId)
            else:
                logger.error("Failed to refresh Discord token",
                           discord_id=user.DiscordId,
                           status_code=response.status_code)
                
    except Exception as e:
        logger.error("Error refreshing Discord token", error=str(e))


def get_client_ip(request: Request) -> str:
    """Get client IP address from request"""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    return str(request.client.host) if request.client else "Unknown"