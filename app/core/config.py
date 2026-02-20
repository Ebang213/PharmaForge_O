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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # 30 minutes (short-lived access tokens)
    
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
    def validate_secret_key(cls, v: str, info) -> str:
        """Reject weak SECRET_KEY in production, warn in development."""
        weak_keys = {
            "your-secret-key-change-in-production",
            "change-me-in-production-use-random-64-chars",
            "change-me-in-production",
            "secret",
            "changeme",
        }
        is_weak = v in weak_keys or len(v) < 32
        if is_weak:
            debug = info.data.get("DEBUG", False)
            if not debug:
                raise ValueError(
                    "SECRET_KEY is weak or default. "
                    "Generate a strong key with: openssl rand -hex 32"
                )
            import warnings
            warnings.warn(
                "SECRET_KEY is weak or default! Set a strong key before deploying.",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator('SEED_DEMO')
    @classmethod
    def validate_seed_demo(cls, v: bool, info) -> bool:
        """Prevent demo seeding in production."""
        if v and not info.data.get("DEBUG", False):
            raise ValueError(
                "SEED_DEMO=true is not allowed when DEBUG=false. "
                "Demo seeding creates predictable credentials."
            )
        return v

    @field_validator('POSTGRES_PASSWORD')
    @classmethod
    def validate_postgres_password(cls, v: str, info) -> str:
        """Reject default database password in production."""
        weak = {"pharmaforge", "postgres", "password", "changeme", ""}
        if v in weak and not info.data.get("DEBUG", False):
            raise ValueError(
                "POSTGRES_PASSWORD is set to a default value. "
                "Set a strong database password for production."
            )
        return v


settings = Settings()
