from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings matching C# appsettings.json structure"""
    
    # Database
    database_url: str = "postgresql+asyncpg://postgres:your_password@localhost:5432/UnsecuredAPIKeys"
    
    # Discord OAuth
    discord_client_id: Optional[str] = None
    discord_client_secret: Optional[str] = None
    discord_server_id: Optional[str] = None
    discord_redirect_uri: str = "http://localhost:8000/discordauth/callback"
    
    # PayPal
    paypal_mode: str = "sandbox"
    paypal_client_id: Optional[str] = None
    paypal_client_secret: Optional[str] = None
    
    # Rate Limiting
    rate_limit_default: int = 5
    rate_limit_window_minutes: int = 60
    rate_limit_server_member: int = 20
    rate_limit_site_creator: int = 999999
    
    # Service Names
    scraper_service_name: str = "api-scraper"
    verifier_service_name: str = "api-verifier"
    
    # CORS
    allowed_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    
    # Redis for caching and rate limiting
    redis_url: str = "redis://localhost:6379"
    
    # JWT Secret
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    
    # Logging
    log_level: str = "INFO"
    
    # Production settings
    production_domain: Optional[str] = None
    environment: str = "development"
    
    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False


settings = Settings()