from sqlalchemy import Column, BigInteger, String, DateTime, Integer, Boolean, Text, ForeignKey, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import List

from app.core.enums import SearchProviderEnum, ApiStatusEnum, ApiTypeEnum, IssueVerificationStatus

Base = declarative_base()


class APIKey(Base):
    """APIKey model matching C# APIKey.cs"""
    __tablename__ = "APIKeys"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    ApiKey = Column(String, nullable=False, index=True)
    Status = Column(Enum(ApiStatusEnum), nullable=False, index=True)
    ApiType = Column(Enum(ApiTypeEnum), nullable=False, default=ApiTypeEnum.UNKNOWN, index=True)
    SearchProvider = Column(Enum(SearchProviderEnum), nullable=False)
    LastCheckedUTC = Column(DateTime, nullable=True, index=True)
    FirstFoundUTC = Column(DateTime, nullable=False, default=func.now())
    LastFoundUTC = Column(DateTime, nullable=False, default=func.now())
    TimesDisplayed = Column(Integer, nullable=False, default=0)
    ErrorCount = Column(Integer, nullable=False, default=0)
    
    # Relationships
    References = relationship("RepoReference", back_populates="APIKey")
    ApiKeyModels = relationship("ApiKeyModel", back_populates="APIKey")


class RepoReference(Base):
    """RepoReference model matching C# RepoReference.cs"""
    __tablename__ = "RepoReferences"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    APIKeyId = Column(BigInteger, ForeignKey("APIKeys.Id"), nullable=False, index=True)
    
    # Repository information
    RepoURL = Column(String, nullable=False)
    RepoOwner = Column(String, nullable=True)
    RepoName = Column(String, nullable=True)
    RepoDescription = Column(String, nullable=True)
    RepoId = Column(BigInteger, nullable=False)
    
    # File information
    FileURL = Column(String, nullable=False)
    FileName = Column(String, nullable=True)
    FilePath = Column(String, nullable=True)
    FileSHA = Column(String, nullable=True)
    ApiContentUrl = Column(String, nullable=True)
    
    # Context information
    CodeContext = Column(String, nullable=True)
    LineNumber = Column(Integer, nullable=False)
    
    # Discovery metadata
    SearchQueryId = Column(BigInteger, nullable=False)
    FoundUTC = Column(DateTime, nullable=False, default=func.now())
    Provider = Column(String, nullable=True)
    Branch = Column(String, nullable=True)
    
    # Relationships
    APIKey = relationship("APIKey", back_populates="References")


class ApplicationSetting(Base):
    """ApplicationSetting model matching C# ApplicationSetting.cs"""
    __tablename__ = "ApplicationSettings"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    Key = Column(String, nullable=False, unique=True)
    Value = Column(Text, nullable=True)
    LastUpdatedUTC = Column(DateTime, nullable=False, default=func.now())


class SearchProviderToken(Base):
    """SearchProviderToken model matching C# SearchProviderToken.cs"""
    __tablename__ = "SearchProviderTokens"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    Provider = Column(Enum(SearchProviderEnum), nullable=False)
    Token = Column(String, nullable=False)
    IsActive = Column(Boolean, nullable=False, default=True)
    RateLimitRemaining = Column(Integer, nullable=True)
    RateLimitResetUTC = Column(DateTime, nullable=True)
    LastUsedUTC = Column(DateTime, nullable=True)


class SearchQuery(Base):
    """SearchQuery model matching C# SearchQuery.cs"""
    __tablename__ = "SearchQueries"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    Query = Column(String, nullable=False)
    Provider = Column(Enum(SearchProviderEnum), nullable=False)
    IsEnabled = Column(Boolean, nullable=False, default=True, index=True)
    LastSearchUTC = Column(DateTime, nullable=True, index=True)
    ResultCount = Column(Integer, nullable=False, default=0)


class RateLimitLog(Base):
    """RateLimitLog model matching C# RateLimitLog.cs"""
    __tablename__ = "RateLimitLogs"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    IpAddress = Column(String, nullable=False, index=True)
    Endpoint = Column(String, nullable=False)
    RequestUTC = Column(DateTime, nullable=False, default=func.now(), index=True)
    UserAgent = Column(String, nullable=True)
    Referer = Column(String, nullable=True)


class IssueSubmissionTracking(Base):
    """IssueSubmissionTracking model matching C# IssueSubmissionTracking.cs"""
    __tablename__ = "IssueSubmissionTrackings"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    ApiKeyId = Column(BigInteger, ForeignKey("APIKeys.Id"), nullable=False, index=True)
    DiscordUserId = Column(String, nullable=True)
    IpAddress = Column(String, nullable=False)
    SubmittedUTC = Column(DateTime, nullable=False, default=func.now())
    IssueURL = Column(String, nullable=True)
    
    # Relationships
    APIKey = relationship("APIKey")


class IssueVerification(Base):
    """IssueVerification model matching C# IssueVerification.cs"""
    __tablename__ = "IssueVerifications"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    ApiKeyId = Column(BigInteger, ForeignKey("APIKeys.Id"), nullable=False, index=True)
    IssueURL = Column(String, nullable=False)
    Status = Column(Enum(IssueVerificationStatus), nullable=False)
    LastCheckedUTC = Column(DateTime, nullable=False, default=func.now())
    
    # Relationships
    APIKey = relationship("APIKey")


class SnitchLeaderboard(Base):
    """SnitchLeaderboard model matching C# SnitchLeaderboard.cs"""
    __tablename__ = "SnitchLeaderboards"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    DiscordUserId = Column(String, nullable=False, unique=True, index=True)
    DiscordUsername = Column(String, nullable=True)
    IssuesSubmitted = Column(Integer, nullable=False, default=0)
    LastSubmissionUTC = Column(DateTime, nullable=True)


class Proxy(Base):
    """Proxy model matching C# Proxy.cs"""
    __tablename__ = "Proxies"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    ProxyUrl = Column(String, nullable=False)
    IsActive = Column(Boolean, nullable=False, default=True)
    LastUsedUTC = Column(DateTime, nullable=True)
    SuccessRate = Column(Integer, nullable=False, default=100)


class VerificationBatchResult(Base):
    """VerificationBatchResult model matching C# VerificationBatchResult.cs"""
    __tablename__ = "VerificationBatchResults"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    BatchId = Column(BigInteger, nullable=False)
    ProcessedUTC = Column(DateTime, nullable=False, default=func.now())
    TotalKeys = Column(Integer, nullable=False)
    ValidKeys = Column(Integer, nullable=False)
    InvalidKeys = Column(Integer, nullable=False)
    ErrorKeys = Column(Integer, nullable=False)


class ApiKeyModel(Base):
    """ApiKeyModel model matching C# ApiKeyModel.cs"""
    __tablename__ = "ApiKeyModels"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    ApiKeyId = Column(BigInteger, ForeignKey("APIKeys.Id"), nullable=False)
    ModelName = Column(String, nullable=False)
    HasAccess = Column(Boolean, nullable=False, default=False)
    LastCheckedUTC = Column(DateTime, nullable=True)
    
    # Relationships
    APIKey = relationship("APIKey", back_populates="ApiKeyModels")


class DiscordUser(Base):
    """DiscordUser model matching C# DiscordUser.cs"""
    __tablename__ = "DiscordUsers"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    DiscordId = Column(String, nullable=False, unique=True, index=True)
    Username = Column(String, nullable=False)
    Avatar = Column(String, nullable=True)
    AccessToken = Column(String, nullable=False)
    RefreshToken = Column(String, nullable=False)
    TokenExpiresAt = Column(DateTime, nullable=False)
    IsServerMember = Column(Boolean, nullable=False, default=False)
    ServerJoinedAt = Column(DateTime, nullable=True)
    LastLoginUTC = Column(DateTime, nullable=False, default=func.now())
    IpAddress = Column(String, nullable=True)


class DonationSupporter(Base):
    """DonationSupporter model matching C# DonationSupporter.cs"""
    __tablename__ = "DonationSupporters"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    PayerEmail = Column(String, nullable=False)
    PayerId = Column(String, nullable=True)
    FirstName = Column(String, nullable=True)
    LastName = Column(String, nullable=True)
    DonationAmountUSD = Column(Integer, nullable=False)  # Amount in cents
    DonationUTC = Column(DateTime, nullable=False)
    TransactionId = Column(String, nullable=False, unique=True)
    IsPublic = Column(Boolean, nullable=False, default=False)


class DonationTracking(Base):
    """DonationTracking model matching C# DonationTracking.cs"""
    __tablename__ = "DonationTrackings"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    TrackingId = Column(String, nullable=False, unique=True)
    IpAddress = Column(String, nullable=False)
    ClickUTC = Column(DateTime, nullable=False, default=func.now())
    ConfirmedDonation = Column(Boolean, nullable=False, default=False, index=True)


class KeyInvalidation(Base):
    """KeyInvalidation model matching C# KeyInvalidation.cs"""
    __tablename__ = "KeyInvalidations"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    ApiKeyId = Column(BigInteger, ForeignKey("APIKeys.Id"), nullable=False, index=True)
    InvalidatedUTC = Column(DateTime, nullable=False, default=func.now())
    Reason = Column(String, nullable=True)
    
    # Relationships
    ApiKey = relationship("APIKey")


class KeyRotation(Base):
    """KeyRotation model matching C# KeyRotation.cs"""
    __tablename__ = "KeyRotations"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    OldKeyId = Column(BigInteger, ForeignKey("APIKeys.Id"), nullable=False)
    NewKeyId = Column(BigInteger, ForeignKey("APIKeys.Id"), nullable=False)
    RotatedUTC = Column(DateTime, nullable=False, default=func.now())
    
    # Relationships  
    OldKey = relationship("APIKey", foreign_keys=[OldKeyId])
    NewKey = relationship("APIKey", foreign_keys=[NewKeyId])


class PatternEffectiveness(Base):
    """PatternEffectiveness model matching C# PatternEffectiveness.cs"""
    __tablename__ = "PatternEffectiveness"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    Pattern = Column(String, nullable=False)
    TotalMatches = Column(Integer, nullable=False, default=0)
    ValidMatches = Column(Integer, nullable=False, default=0)
    InvalidMatches = Column(Integer, nullable=False, default=0)
    LastUpdatedUTC = Column(DateTime, nullable=False, default=func.now())


class ProviderModel(Base):
    """ProviderModel model matching C# ProviderModel.cs"""
    __tablename__ = "ProviderModels"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    Provider = Column(Enum(ApiTypeEnum), nullable=False)
    ModelName = Column(String, nullable=False)
    IsActive = Column(Boolean, nullable=False, default=True)


class UserBan(Base):
    """UserBan model matching C# UserBan.cs"""
    __tablename__ = "UserBans"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    IpAddress = Column(String, nullable=True, index=True)
    DiscordUserId = Column(String, nullable=True, index=True)
    BannedUTC = Column(DateTime, nullable=False, default=func.now())
    Reason = Column(String, nullable=True)
    IsActive = Column(Boolean, nullable=False, default=True)


class UserSession(Base):
    """UserSession model matching C# UserSession.cs"""
    __tablename__ = "UserSessions"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    SessionId = Column(String, nullable=False, unique=True, index=True)
    IpAddress = Column(String, nullable=False)
    UserAgent = Column(String, nullable=True)
    CreatedUTC = Column(DateTime, nullable=False, default=func.now())
    LastSeenUTC = Column(DateTime, nullable=False, default=func.now())
    IsActive = Column(Boolean, nullable=False, default=True)


class VerificationBatch(Base):
    """VerificationBatch model matching C# VerificationBatch.cs"""
    __tablename__ = "VerificationBatches"
    
    Id = Column(BigInteger, primary_key=True, index=True)
    StartKeyId = Column(BigInteger, nullable=False, index=True)
    EndKeyId = Column(BigInteger, nullable=False, index=True)
    Status = Column(String, nullable=False, index=True)
    InstanceId = Column(String, nullable=False, index=True)
    CreatedUTC = Column(DateTime, nullable=False, default=func.now())
    StartedUTC = Column(DateTime, nullable=True)
    CompletedUTC = Column(DateTime, nullable=True)
    LockExpiresAtUTC = Column(DateTime, nullable=True, index=True)