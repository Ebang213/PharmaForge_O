"""
Centralized FDA endpoint constants for Watchtower providers.

This file centralizes all FDA API and web endpoints to:
1. Make URL changes easy to manage in one place
2. Support fallback URLs when primary endpoints return 404
3. Enable environment variable overrides for testing
"""
import os
from typing import List, Dict, Any

# =============================================================================
# FDA DRUG ENFORCEMENT (RECALLS) ENDPOINTS
# =============================================================================

# Primary: openFDA Drug Enforcement API (official, most reliable)
FDA_ENFORCEMENT_PRIMARY = os.getenv(
    "FDA_ENFORCEMENT_API_URL",
    "https://api.fda.gov/drug/enforcement.json"
)

# Fallback RSS feeds for recalls
FDA_RECALLS_RSS_URLS: List[str] = [
    "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drug-recalls/rss.xml",
    "https://www.fda.gov/drugs/drug-safety-and-availability/drug-recalls/rss",
]

# Default parameters for openFDA enforcement API
FDA_ENFORCEMENT_PARAMS: Dict[str, Any] = {
    "limit": 50,
    "sort": "report_date:desc",
}

# =============================================================================
# FDA DRUG SHORTAGES ENDPOINTS
# =============================================================================

# Primary: openFDA Drug Shortages API (official, reliable JSON endpoint)
# This endpoint provides structured data on drug shortages with fields like:
# - package_ndc, generic_name, status, company_name, therapeutic_category, etc.
FDA_SHORTAGES_PRIMARY = os.getenv(
    "FDA_SHORTAGES_API_URL",
    "https://api.fda.gov/drug/shortages.json"
)

# Fallback URLs to try for shortages data
FDA_SHORTAGES_FALLBACK_URLS: List[str] = [
    # AccessData shortages page (HTML scraping fallback)
    "https://www.accessdata.fda.gov/scripts/drugshortages/default.cfm",
]

# Default parameters for shortages queries
FDA_SHORTAGES_PARAMS: Dict[str, Any] = {
    "limit": 50,
    "sort": "update_date:desc",
}

# =============================================================================
# FDA WARNING LETTERS ENDPOINTS
# =============================================================================

# Primary: FDA Warning Letters page (HTML scraping required)
FDA_WARNING_LETTERS_PRIMARY = os.getenv(
    "FDA_WARNING_LETTERS_URL",
    "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters"
)

# Fallback URLs for warning letters
FDA_WARNING_LETTERS_FALLBACK_URLS: List[str] = [
    "https://www.fda.gov/drugs/enforcement-activities-fda/warning-letters-and-notice-violation-letters-pharmaceutical-companies",
]

# =============================================================================
# HTTP CONFIGURATION
# =============================================================================

# HTTP timeout in seconds
HTTP_TIMEOUT = int(os.getenv("WATCHTOWER_HTTP_TIMEOUT", "15"))

# Maximum retry attempts for transient failures
MAX_RETRIES = int(os.getenv("WATCHTOWER_MAX_RETRIES", "3"))

# Base for exponential backoff (seconds)
BACKOFF_BASE = float(os.getenv("WATCHTOWER_BACKOFF_BASE", "1.0"))

# User-Agent string for HTTP requests
USER_AGENT = os.getenv(
    "WATCHTOWER_USER_AGENT",
    "PharmaForgeWatchtower/1.0 (+https://pharmaforge)"
)

# Default headers for all HTTP requests
DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/html, application/xml;q=0.9, */*;q=0.8",
}

# =============================================================================
# SHORTAGE STATUS MAPPINGS
# =============================================================================

# Standardize shortage status values
SHORTAGE_STATUS_MAP: Dict[str, str] = {
    # Current/active statuses
    "currently in shortage": "current",
    "current": "current",
    "active": "current",
    "ongoing": "current",

    # Resolved statuses
    "resolved": "resolved",
    "no longer in shortage": "resolved",
    "discontinued": "resolved",

    # Terminated/ended statuses
    "terminated": "terminated",
    "ended": "terminated",

    # Unknown/other
    "unknown": None,
    "": None,
}

def normalize_shortage_status(status: str) -> str:
    """
    Normalize shortage status to one of: current, resolved, terminated, or None.

    Args:
        status: Raw status string from FDA data

    Returns:
        Normalized status string or None if unknown
    """
    if not status:
        return None

    status_lower = status.strip().lower()

    # Direct mapping lookup
    if status_lower in SHORTAGE_STATUS_MAP:
        return SHORTAGE_STATUS_MAP[status_lower]

    # Fuzzy matching for partial matches
    if "current" in status_lower or "shortage" in status_lower:
        return "current"
    if "resolved" in status_lower or "available" in status_lower:
        return "resolved"
    if "terminated" in status_lower or "ended" in status_lower:
        return "terminated"

    # Return None for truly unknown statuses (don't label as "Unknown")
    return None
