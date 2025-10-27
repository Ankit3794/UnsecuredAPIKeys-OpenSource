from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.core.enums import ApiStatusEnum, ApiTypeEnum, SearchProviderEnum


class APIKeyBase(BaseModel):
    """Base schema for APIKey"""
    ApiKey: str
    Status: ApiStatusEnum
    ApiType: ApiTypeEnum = ApiTypeEnum.UNKNOWN
    SearchProvider: SearchProviderEnum
    TimesDisplayed: int = 0
    ErrorCount: int = 0


class APIKeyCreate(APIKeyBase):
    """Schema for creating APIKey"""
    pass


class APIKeyUpdate(BaseModel):
    """Schema for updating APIKey"""
    Status: Optional[ApiStatusEnum] = None
    ApiType: Optional[ApiTypeEnum] = None
    LastCheckedUTC: Optional[datetime] = None
    TimesDisplayed: Optional[int] = None
    ErrorCount: Optional[int] = None


class APIKeyResponse(APIKeyBase):
    """Schema for APIKey response"""
    Id: int
    LastCheckedUTC: Optional[datetime] = None
    FirstFoundUTC: datetime
    LastFoundUTC: datetime
    
    class Config:
        from_attributes = True


class RepoReferenceBase(BaseModel):
    """Base schema for RepoReference"""
    RepoURL: str
    RepoOwner: Optional[str] = None
    RepoName: Optional[str] = None
    RepoDescription: Optional[str] = None
    RepoId: int
    FileURL: str
    FileName: Optional[str] = None
    FilePath: Optional[str] = None
    FileSHA: Optional[str] = None
    ApiContentUrl: Optional[str] = None
    CodeContext: Optional[str] = None
    LineNumber: int
    SearchQueryId: int
    Provider: Optional[str] = None
    Branch: Optional[str] = None


class RepoReferenceCreate(RepoReferenceBase):
    """Schema for creating RepoReference"""
    APIKeyId: int


class RepoReferenceResponse(RepoReferenceBase):
    """Schema for RepoReference response"""
    Id: int
    APIKeyId: int
    FoundUTC: datetime
    
    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    """Generic paginated response schema"""
    Items: List[APIKeyResponse]
    Page: int
    PageSize: int
    TotalCount: int
    TotalPages: int


class ApiTypeCountDto(BaseModel):
    """Schema for API type counts"""
    ApiType: ApiTypeEnum
    Count: int


class StatsResponse(BaseModel):
    """Schema for statistics response"""
    TotalKeys: int
    ValidKeys: int
    InvalidKeys: int
    UnverifiedKeys: int
    TotalReferences: int


class IssueSubmissionTrackingDto(BaseModel):
    """Schema for issue submission tracking"""
    ApiKeyId: int
    IssueURL: Optional[str] = None


class DonationClickTrackingDto(BaseModel):
    """Schema for donation click tracking"""
    TrackingId: str


class KeyFixedNotification(BaseModel):
    """Schema for key fixed webhook notification"""
    ApiKeyId: int
    FixedUTC: datetime
    Reason: Optional[str] = None


class DiscordCallbackRequest(BaseModel):
    """Schema for Discord OAuth callback"""
    code: str
    state: Optional[str] = None


class DiscordAuthResponse(BaseModel):
    """Schema for Discord auth response"""
    success: bool
    user: Optional[dict] = None
    error: Optional[str] = None


class DiscordUserResponse(BaseModel):
    """Schema for Discord user response"""
    DiscordId: str
    Username: str
    Avatar: Optional[str] = None
    IsServerMember: bool
    RateLimit: Optional[int] = None


class RateLimitResponse(BaseModel):
    """Schema for rate limit response"""
    allowed: bool
    limit: int
    remaining: int
    reset_time: datetime
    message: Optional[str] = None


class WebSocketMessage(BaseModel):
    """Schema for WebSocket messages"""
    type: str
    data: dict


class SystemStatus(BaseModel):
    """Schema for system status"""
    status: str
    timestamp: datetime
    services: dict
    database_connected: bool