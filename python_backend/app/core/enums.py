from enum import Enum
from typing import Optional


class SearchProviderEnum(Enum):
    """Search provider enumeration matching C# CommonEnums.cs"""
    UNKNOWN = -99
    GITHUB = 1
    GITLAB = 2
    BITBUCKET = 3
    SOURCEGRAPH = 4


class ApiStatusEnum(Enum):
    """API status enumeration matching C# CommonEnums.cs"""
    # The key was found but not yet checked for validity
    UNVERIFIED = -99
    
    # The key was checked and is valid/working
    VALID = 1
    
    # The key was checked and is not working (invalid, expired, revoked, etc.)
    INVALID = 0
    
    # The key was removed at the request of the repo owner or by admin action
    REMOVED = 3
    
    # The key was flagged for removal at the request of the repo owner
    FLAGGED_FOR_REMOVAL = 4
    
    # The key is no longer valid (Fixed / Removed)
    NO_LONGER_WORKING = 5
    
    # The key was checked and is erroring out for some reason
    ERROR = 6
    
    # The key is valid but has no credits/quota
    VALID_NO_CREDITS = 7


class ApiTypeEnum(Enum):
    """API type enumeration matching C# CommonEnums.cs"""
    # Default
    UNKNOWN = -99
    
    # AI Services (100+)
    OPENAI = 100
    AZURE_OPENAI = 110
    ANTHROPIC_CLAUDE = 120
    GOOGLE_AI = 130
    COHERE = 140
    HUGGINGFACE = 150
    STABILITY_AI = 160
    MISTRAL_AI = 170
    REPLICATE = 180
    TOGETHER_AI = 190
    OPEN_ROUTER = 195
    
    # New AI Services
    PERPLEXITY_AI = 196
    GROQ = 197
    DEEPSEEK = 198
    ELEVENLABS = 199
    RUNWAY_ML = 201
    ASSEMBLY_AI = 202
    PINECONE = 203
    WEAVIATE = 204
    CHROMA_DB = 205
    LANGCHAIN = 206
    
    # Cloud Providers (200+)
    AWS = 200
    AZURE = 210
    GCP = 220
    
    # Source Control (300+)
    GITHUB = 300
    GITLAB = 310
    BITBUCKET = 320
    
    # Common Services (400+)
    STRIPE = 400
    SENDGRID = 410
    TWILIO = 420
    MONGODB = 430
    FIREBASE = 440


class IssueVerificationStatus(Enum):
    """Issue verification status matching C# CommonEnums.cs"""
    NOT_FOUND = 0
    OPEN = 1
    CLOSED = 2
    VERIFICATION_ERROR = 3