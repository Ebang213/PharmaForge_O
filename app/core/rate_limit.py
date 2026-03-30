"""
Rate limiting configuration using slowapi.

Applied to sensitive endpoints:
- Evidence upload (10/min)
- Workflow execution (10/min)
- Watchtower sync (10/min)
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
