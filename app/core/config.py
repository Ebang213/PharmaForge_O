"""
Application configuration with environment variables.
"""
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, field_validator
from typing import Optional, List
import os


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )
    
    # Application
    APP_NAME: str = "PharmaForge OS"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "your-secret-key-change-in-production"
    
    # Database
    POSTGRES_USER: str = "pharmaforge"
    POSTGRES_PASSWORD: str = "pharmaforge"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str = "pharmaforge"
    DATABASE_URL: Optional[str] = None
    
    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    
    # JWT Settings
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 hour (tightened from 24h)
    
    # Vector DB (Qdrant)
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "pharmaforge_docs"
    
    # LLM Provider
    LLM_PROVIDER: str = "mock"  # mock, openai, anthropic
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # Embedding
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"  # sentence-transformers model
    
    # Storage
    UPLOAD_DIR: str = "/code/uploads"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:8001", "http://localhost:3000"]
    
    # =========================================
    # Auth Hardening Settings
    # =========================================
    
    # Demo seeding - MUST be false in production
    SEED_DEMO: bool = False
    
    # Admin bootstrap - used to create initial admin on first startup
    # Only used if no users exist in database
    ADMIN_BOOTSTRAP_EMAIL: Optional[str] = None
    ADMIN_BOOTSTRAP_PASSWORD: Optional[str] = None
    
    # Registration control
    ALLOW_PUBLIC_REGISTRATION: bool = False  # Disable public registration in prod
    
    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def assemble_db_url(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v
        
        # Access individual fields from the values dict
        data = info.data
        user = data.get("POSTGRES_USER", "pharmaforge")
        password = data.get("POSTGRES_PASSWORD", "pharmaforge")
        host = data.get("POSTGRES_HOST", "postgres")
        port = data.get("POSTGRES_PORT", "5432")
        db = data.get("POSTGRES_DB", "pharmaforge")
        
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    @field_validator('SECRET_KEY')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Warn if SECRET_KEY is weak (don't crash, but log warning)."""
        weak_keys = [
            "your-secret-key-change-in-production",
            "change-me-in-production-use-random-64-chars",
            "secret",
            "changeme",
        ]
        if v in weak_keys or len(v) < 32:
            import warnings
            warnings.warn(
                "SECRET_KEY is weak or default! Set a strong random key in production.",
                UserWarning
            )
        return v


settings = Settings()
