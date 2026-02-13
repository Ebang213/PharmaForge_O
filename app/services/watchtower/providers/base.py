"""
Base interface for Watchtower data providers.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional
from dataclasses import dataclass, field
import hashlib


@dataclass
class WatchItem:
    """
    Normalized data item from a Watchtower provider.

    All feed items are normalized to this schema for consistent storage and display.
    Fields:
        source: Provider source ID (e.g., "fda_recalls", "fda_shortages")
        external_id: Unique ID from source (stable across fetches)
        title: Display title for the item
        url: Link to the source document/page
        published_at: When the item was published (ISO datetime, timezone-aware)
        summary: Brief description or snippet
        category: Item category (recall, shortage, warning_letter)
        tags: List of tags/labels for filtering
        vendor_name: Manufacturer/vendor name if available (nullable, not "Unknown")
        manufacturer: Alias for vendor_name for shortages
        status: Item status (e.g., "current", "resolved", "terminated") - nullable
        raw_json: Original source data for reference
        ingested_at: When this item was fetched (set automatically)
    """
    source: str  # e.g., "fda_recalls", "fda_shortages", "fda_warning_letters"
    external_id: str
    title: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    summary: Optional[str] = None
    category: Optional[str] = None  # "recall", "shortage", "warning_letter"
    tags: List[str] = field(default_factory=list)
    vendor_name: Optional[str] = None  # Nullable - don't use "Unknown"
    manufacturer: Optional[str] = None  # Alias for vendor_name (shortages)
    status: Optional[str] = None  # e.g., "current", "resolved", "terminated" - nullable
    raw_json: dict = field(default_factory=dict)
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        """Ensure manufacturer and vendor_name are in sync."""
        # Sync manufacturer and vendor_name
        if self.manufacturer and not self.vendor_name:
            self.vendor_name = self.manufacturer
        elif self.vendor_name and not self.manufacturer:
            self.manufacturer = self.vendor_name

    @staticmethod
    def generate_stable_id(source: str, url: Optional[str], published_at: Optional[datetime], title: str) -> str:
        """
        Generate a stable ID from source + url + published_at + title.

        This ensures the same item always gets the same external_id,
        preventing duplicate insertions.
        """
        parts = [
            source or "",
            url or "",
            published_at.isoformat() if published_at else "",
            title or "",
        ]
        combined = "|".join(parts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:32]


class WatchtowerProvider(ABC):
    """
    Abstract base class for Watchtower data providers.
    
    Each provider is responsible for fetching data from a specific source
    and normalizing it into WatchItem objects.
    """
    
    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique identifier for this source (e.g., 'fda_recalls')."""
        pass
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name for this source."""
        pass
    
    @property
    def category(self) -> str:
        """Category of items from this source."""
        return "general"
    
    @abstractmethod
    async def fetch(self) -> List[WatchItem]:
        """
        Fetch items from the external source.
        
        Returns:
            List of WatchItem objects
            
        Raises:
            Exception if fetch fails
        """
        pass
    
    def get_cache_key(self) -> str:
        """Get Redis cache key for this provider."""
        return f"watchtower:cache:{self.source_id}"
    
    def get_cache_ttl(self) -> int:
        """Get cache TTL in seconds (default: 15 minutes)."""
        return 900
