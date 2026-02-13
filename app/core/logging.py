"""
Structured logging configuration.
"""
import logging
import sys
from datetime import datetime
import json
from typing import Any, Optional

from app.core.config import settings


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id
        if hasattr(record, "org_id"):
            log_entry["org_id"] = record.org_id
        if hasattr(record, "action"):
            log_entry["action"] = record.action
        if hasattr(record, "entity_type"):
            log_entry["entity_type"] = record.entity_type
        if hasattr(record, "entity_id"):
            log_entry["entity_id"] = record.entity_id
        
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_entry)


def setup_logging():
    """Configure application logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    
    # Console handler with structured output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(console_handler)
    
    # Suppress noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


class AuditLogger:
    """Helper for logging audit events."""
    
    def __init__(self):
        self.logger = get_logger("audit")
    
    def log(
        self,
        action: str,
        user_id: Optional[int] = None,
        org_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        """Log an audit event."""
        extra = {
            "user_id": user_id,
            "org_id": org_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
        }
        
        message = f"AUDIT: {action}"
        if entity_type and entity_id:
            message += f" on {entity_type}:{entity_id}"
        if details:
            message += f" - {json.dumps(details)}"
        
        self.logger.info(message, extra=extra)


audit_logger = AuditLogger()
