"""
Watchtower live feed ingestion service.

Handles:
- Fetching from providers
- Redis caching
- Postgres persistence
- Sync status tracking
"""
import asyncio
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

import redis
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import WatchtowerItem, WatchtowerSyncStatus

from .providers.base import WatchtowerProvider, WatchItem
from .providers.fda_recalls import FDARecallsProvider
from .providers.fda_warning_letters import FDAWarningLettersProvider
from .providers.fda_shortages import FDAShortagesProvider

logger = get_logger(__name__)

# Avoid hammering external sources in a tight loop.
SYNC_DELAY_SECONDS = float(os.getenv("WATCHTOWER_SYNC_DELAY_SECONDS", "0.5"))

# Centralized source configuration
# - enabled: whether to include in sync operations
# - required: if True, affects degraded status when failing
SOURCE_CONFIG: Dict[str, Dict[str, Any]] = {
    "fda_recalls": {
        "enabled": True,
        "required": True,
        "url": "https://api.fda.gov/drug/enforcement.json",
        "description": "FDA Drug Recalls via openFDA API",
    },
    "fda_shortages": {
        "enabled": True,
        "required": True,
        "url": "https://api.fda.gov/drug/shortages.json",
        "description": "FDA Drug Shortages via openFDA API",
    },
    "fda_warning_letters": {
        "enabled": True,
        "required": True,
        "url": "https://www.fda.gov/.../warning-letters",
        "description": "FDA Warning Letters via HTML scraping",
    },
}

# Registry of available providers
PROVIDERS: Dict[str, WatchtowerProvider] = {
    "fda_recalls": FDARecallsProvider(),
    "fda_warning_letters": FDAWarningLettersProvider(),
    "fda_shortages": FDAShortagesProvider(),
}


def get_provider(source_id: str) -> Optional[WatchtowerProvider]:
    """Get a provider by its source ID."""
    return PROVIDERS.get(source_id)


def list_providers() -> List[Dict[str, Any]]:
    """List all available providers with their metadata."""
    return [
        {
            "source_id": p.source_id,
            "source_name": p.source_name,
            "category": p.category,
        }
        for p in PROVIDERS.values()
    ]


async def sync_provider(
    source_id: str,
    db: Session,
    force: bool = False
) -> Dict[str, Any]:
    """
    Sync a single provider - fetch, cache, and persist items.

    This function NEVER raises exceptions - it always returns a result dict.
    All errors are caught and returned in the result.

    Args:
        source_id: Provider source ID
        db: Database session
        force: If True, ignore cache and force fresh fetch

    Returns:
        Sync result with status, items_added, timestamps, and any error
    """
    now = datetime.utcnow()

    result = {
        "source": source_id,
        "success": False,
        "items_fetched": 0,
        "items_added": 0,
        "items_saved": 0,  # alias for items_added
        "items_new": 0,  # alias for backward compat
        "error": None,
        "error_message": None,
        "last_http_status": None,
        "cached": False,
        "updated_at": now.isoformat(),
        "last_success_at": None,
        "last_error_at": None,
    }

    # Check if provider exists
    provider = get_provider(source_id)
    if not provider:
        error_msg = f"Unknown provider: {source_id}"
        logger.error(f"[{source_id}] {error_msg}")
        result["error"] = error_msg
        result["error_message"] = error_msg
        result["last_error_at"] = now.isoformat()
        _update_sync_status(db, source_id, success=False, error=error_msg)
        return result

    logger.info(f"[{source_id}] Starting sync (force={force})")

    try:
        # Check cache first
        cached_items = None
        if not force:
            cached_items = _get_from_cache(provider)

        if cached_items is not None:
            logger.info(f"[{source_id}] Using cached data: {len(cached_items)} items")
            result["cached"] = True
            items = cached_items
        else:
            # Fetch fresh data
            logger.info(f"[{source_id}] Fetching fresh data from provider")
            items = await provider.fetch()
            logger.info(f"[{source_id}] Fetched {len(items)} items successfully")
            # Update cache
            _set_cache(provider, items)

        # Try to get HTTP status from provider if available
        http_status = getattr(provider, 'last_http_status', None)
        result["last_http_status"] = http_status

        result["items_fetched"] = len(items)

        # Persist to database
        new_count = _persist_items(db, items)
        result["items_added"] = new_count
        result["items_saved"] = new_count
        result["items_new"] = new_count  # alias
        logger.info(f"[{source_id}] Persisted {new_count} new items to database")

        # Update sync status with all tracking fields
        _update_sync_status(
            db, source_id, success=True,
            http_status=http_status,
            items_fetched=len(items),
            items_saved=new_count
        )

        result["success"] = True
        result["last_success_at"] = now.isoformat()
        logger.info(f"[{source_id}] Sync completed successfully")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{source_id}] Sync failed: {error_msg}", exc_info=True)
        result["error"] = error_msg
        result["error_message"] = error_msg
        result["last_error_at"] = now.isoformat()

        # Try to get HTTP status from provider even on failure
        http_status = getattr(provider, 'last_http_status', None)
        result["last_http_status"] = http_status

        _update_sync_status(
            db, source_id, success=False, error=error_msg,
            http_status=http_status
        )

    return result


async def sync_all_providers(db: Session, force: bool = False) -> Dict[str, Any]:
    """
    Sync all registered providers.
    
    This function NEVER raises exceptions. It catches all errors per-source
    and returns a comprehensive result object.
    
    Returns:
        Dict with:
        - status: "ok" (at least one success), "degraded" (some failures), or "error" (all failed)
        - degraded: True if any source failed
        - results: List of per-source results
        - total_items_added: Sum of all items_added across sources
        - sources_succeeded: Count of successful sources
        - sources_failed: Count of failed sources
    """
    results = []
    total_items_added = 0
    sources_succeeded = 0
    sources_failed = 0
    
    enabled_providers = [
        source_id for source_id, config in SOURCE_CONFIG.items()
        if config.get("enabled", True)
    ]
    
    # If SOURCE_CONFIG doesn't match PROVIDERS, fall back to PROVIDERS
    if not enabled_providers:
        enabled_providers = list(PROVIDERS.keys())
    
    logger.info(f"Starting sync for {len(enabled_providers)} providers: {enabled_providers}")
    
    for index, source_id in enumerate(enabled_providers):
        try:
            if index > 0 and SYNC_DELAY_SECONDS > 0:
                await asyncio.sleep(SYNC_DELAY_SECONDS)
            
            # sync_provider already handles its own exceptions
            result = await sync_provider(source_id, db, force=force)
            results.append(result)
            
            if result.get("success"):
                sources_succeeded += 1
                total_items_added += result.get("items_added", 0)
            else:
                sources_failed += 1
                
        except Exception as e:
            # This should never happen since sync_provider catches all,
            # but we double-wrap for safety
            logger.error(f"[{source_id}] Unexpected error in sync_all_providers: {e}", exc_info=True)
            sources_failed += 1
            results.append({
                "source": source_id,
                "success": False,
                "items_fetched": 0,
                "items_added": 0,
                "error": str(e),
                "error_message": str(e),
                "cached": False,
                "updated_at": datetime.utcnow().isoformat(),
                "last_error_at": datetime.utcnow().isoformat(),
            })
    
    # Determine overall status
    if sources_failed == 0:
        status = "ok"
        degraded = False
    elif sources_succeeded == 0:
        status = "error"
        degraded = True
    else:
        status = "ok"  # Partial success is still "ok"
        degraded = True
    
    logger.info(f"Sync complete: status={status}, succeeded={sources_succeeded}, failed={sources_failed}, items_added={total_items_added}")
    
    return {
        "status": status,
        "degraded": degraded,
        "results": results,
        "total_items_added": total_items_added,
        "sources_succeeded": sources_succeeded,
        "sources_failed": sources_failed,
    }


def get_feed_items(
    db: Session,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> List[WatchtowerItem]:
    """Get feed items from database."""
    query = db.query(WatchtowerItem)
    
    if source:
        query = query.filter(WatchtowerItem.source == source)
    
    return query.order_by(desc(WatchtowerItem.published_at)).offset(offset).limit(limit).all()


def get_sync_statuses(db: Session) -> List[WatchtowerSyncStatus]:
    """Get sync status for all sources."""
    return db.query(WatchtowerSyncStatus).all()


def get_sync_status(db: Session, source_id: str) -> Optional[WatchtowerSyncStatus]:
    """Get sync status for a specific source."""
    return db.query(WatchtowerSyncStatus).filter(
        WatchtowerSyncStatus.source == source_id
    ).first()


def get_feed_summary(db: Session) -> Dict[str, Any]:
    """Get summary statistics for watchtower feed."""
    total_items = db.query(WatchtowerItem).count()
    
    # Count by source
    by_source = {}
    for provider in PROVIDERS.values():
        count = db.query(WatchtowerItem).filter(
            WatchtowerItem.source == provider.source_id
        ).count()
        by_source[provider.source_id] = count
    
    # Get last sync info
    sync_statuses = get_sync_statuses(db)
    status_by_source = {status.source: status for status in sync_statuses}
    last_sync = None
    all_healthy = True

    for status in sync_statuses:
        if status.last_run_at:
            if last_sync is None or status.last_run_at > last_sync:
                last_sync = status.last_run_at

    for provider in PROVIDERS.values():
        status = status_by_source.get(provider.source_id)
        if not status or not status.last_run_at:
            all_healthy = False
            continue
        if status.last_error_at and (
            status.last_success_at is None or
            status.last_error_at > status.last_success_at
        ):
            all_healthy = False
    
    return {
        "total_items": total_items,
        "by_source": by_source,
        "last_sync_at": last_sync.isoformat() if last_sync else None,
        "all_sources_healthy": all_healthy,
        "sources_count": len(PROVIDERS),
    }


def get_health_status(db: Session) -> Dict[str, Any]:
    """
    Get detailed health status for Watchtower including per-source status.
    
    Returns:
        Dict with overall_status (healthy/degraded/down), per-source statuses, and counts
    """
    from app.db.models import Vendor, Facility, WatchtowerAlert, WatchtowerAlertStatus
    
    sync_statuses = get_sync_statuses(db)
    status_by_source = {status.source: status for status in sync_statuses}
    
    sources = []
    required_sources_count = 0
    required_sources_healthy = 0
    required_sources_failing = 0
    
    for source_id, config in SOURCE_CONFIG.items():
        if not config.get("enabled", True):
            continue
        
        is_required = config.get("required", False)
        if is_required:
            required_sources_count += 1
        
        status = status_by_source.get(source_id)
        
        # Determine source status
        if not status or not status.last_run_at:
            source_status = "pending"
            is_healthy = False
        elif status.last_error_at and (
            status.last_success_at is None or
            status.last_error_at > status.last_success_at
        ):
            source_status = "error"
            is_healthy = False
        else:
            source_status = "ok"
            is_healthy = True
        
        if is_required:
            if is_healthy:
                required_sources_healthy += 1
            else:
                required_sources_failing += 1
        
        sources.append({
            "source_id": source_id,
            "source_name": PROVIDERS.get(source_id).source_name if source_id in PROVIDERS else source_id,
            "status": source_status,
            "required": is_required,
            "last_success_at": status.last_success_at.isoformat() if status and status.last_success_at else None,
            "last_attempt_at": status.last_run_at.isoformat() if status and status.last_run_at else None,
            "last_error": status.last_error_message if status else None,
            "last_error_message": status.last_error_message if status else None,  # alias
            "last_http_status": status.last_http_status if status else None,
            "items_fetched": status.items_fetched if status else 0,
            "items_saved": status.items_saved if status else 0,
        })
    
    # Determine overall status
    if required_sources_count == 0:
        overall_status = "healthy"
    elif required_sources_failing == required_sources_count:
        overall_status = "down"
    elif required_sources_failing > 0:
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    # Get counts
    feed_items = db.query(WatchtowerItem).count()
    active_alerts = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.status == WatchtowerAlertStatus.ACTIVE
    ).count()
    vendors = db.query(Vendor).count()
    facilities = db.query(Facility).count()
    
    return {
        "overall_status": overall_status,
        "sources": sources,
        "counts": {
            "feed_items": feed_items,
            "active_alerts": active_alerts,
            "vendors": vendors,
            "facilities": facilities,
        },
        "all_sources_healthy": required_sources_failing == 0,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============= Private Helpers =============

def _get_redis_client():
    """Get Redis client."""
    try:
        return redis.from_url(settings.REDIS_URL)
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
        return None


def _get_from_cache(provider: WatchtowerProvider) -> Optional[List[WatchItem]]:
    """Get cached items for a provider."""
    r = _get_redis_client()
    if not r:
        return None
    
    try:
        cached = r.get(provider.get_cache_key())
        if cached:
            data = json.loads(cached)
            items = []
            for item_data in data:
                pub_at = item_data.get("published_at")
                if pub_at:
                    pub_at = datetime.fromisoformat(pub_at)
                items.append(WatchItem(
                    source=item_data["source"],
                    external_id=item_data["external_id"],
                    title=item_data["title"],
                    url=item_data.get("url"),
                    published_at=pub_at,
                    summary=item_data.get("summary"),
                    category=item_data.get("category"),
                    raw_json=item_data.get("raw_json", {})
                ))
            return items
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    
    return None


def _set_cache(provider: WatchtowerProvider, items: List[WatchItem]) -> None:
    """Cache items for a provider."""
    r = _get_redis_client()
    if not r:
        return
    
    try:
        data = []
        for item in items:
            data.append({
                "source": item.source,
                "external_id": item.external_id,
                "title": item.title,
                "url": item.url,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "summary": item.summary,
                "category": item.category,
                "raw_json": item.raw_json,
            })
        r.setex(
            provider.get_cache_key(),
            provider.get_cache_ttl(),
            json.dumps(data)
        )
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


def _persist_items(db: Session, items: List[WatchItem]) -> int:
    """
    Persist items to database, skipping duplicates. Returns count of new items.

    Uses individual inserts with rollback on unique constraint violation to ensure
    robustness. Each item is handled in its own mini-transaction to avoid a single
    duplicate corrupting the entire batch.
    """
    new_count = 0

    for item in items:
        try:
            # Check for existing first (faster than catching exception)
            existing = db.query(WatchtowerItem).filter(
                WatchtowerItem.source == item.source,
                WatchtowerItem.external_id == item.external_id
            ).first()

            if existing:
                continue

            db_item = WatchtowerItem(
                source=item.source,
                external_id=item.external_id,
                title=item.title,
                url=item.url,
                published_at=item.published_at,
                summary=item.summary,
                category=item.category,
                raw_json=item.raw_json,
            )
            db.add(db_item)
            db.flush()  # Flush to detect constraint violations immediately
            new_count += 1

        except Exception as e:
            # Handle unique constraint violation or any other DB error
            db.rollback()
            error_str = str(e).lower()
            if "unique" in error_str or "duplicate" in error_str:
                logger.debug(f"Skipping duplicate item: {item.source}/{item.external_id}")
            else:
                logger.warning(f"Failed to persist item {item.source}/{item.external_id}: {e}")
            continue

    # Final commit for all successfully added items
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Final commit failed in _persist_items: {e}")
        # Return whatever count we had - items may not have persisted
        return 0

    return new_count


def _update_sync_status(
    db: Session,
    source_id: str,
    success: bool,
    error: Optional[str] = None,
    http_status: Optional[int] = None,
    items_fetched: int = 0,
    items_saved: int = 0,
) -> None:
    """
    Update sync status for a source. Handles DB errors gracefully.

    Args:
        db: Database session
        source_id: Provider source ID
        success: Whether the sync succeeded
        error: Error message if failed
        http_status: HTTP status code from last request
        items_fetched: Number of items fetched from provider
        items_saved: Number of new items persisted to DB
    """
    try:
        # Ensure session is in a clean state
        if db.is_active and (db.new or db.dirty or db.deleted):
            try:
                db.rollback()
            except Exception:
                pass

        status = db.query(WatchtowerSyncStatus).filter(
            WatchtowerSyncStatus.source == source_id
        ).first()

        now = datetime.utcnow()

        if not status:
            status = WatchtowerSyncStatus(source=source_id)
            db.add(status)

        status.last_run_at = now
        status.last_http_status = http_status
        status.items_fetched = items_fetched
        status.items_saved = items_saved

        if success:
            status.last_success_at = now
            status.last_error_at = None
            status.last_error_message = None
        else:
            status.last_error_at = now
            status.last_error_message = error[:500] if error else None

        db.commit()

    except Exception as e:
        logger.error(f"Failed to update sync status for {source_id}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
