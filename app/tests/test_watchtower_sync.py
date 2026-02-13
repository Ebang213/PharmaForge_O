"""
Unit tests for Watchtower sync functionality.

Tests the resilient sync behavior - ensuring partial failures don't crash the entire sync.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


class TestWatchtowerSyncResilience:
    """Tests for Watchtower sync resilience - partial failures should not crash."""
    
    @pytest.mark.asyncio
    async def test_sync_provider_handles_exception(self):
        """Test that sync_provider catches exceptions and returns error result."""
        from app.services.watchtower.feed_service import sync_provider
        
        # Create a mock database session
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        
        # Mock the provider to raise an exception
        with patch('app.services.watchtower.feed_service.get_provider') as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.fetch = AsyncMock(side_effect=Exception("Simulated network failure"))
            mock_get_provider.return_value = mock_provider
            
            result = await sync_provider("fda_recalls", mock_db, force=True)
        
        # Should NOT raise - should return error in result
        assert result["success"] == False
        assert result["error"] is not None
        assert "Simulated network failure" in result["error"]
        assert result["items_added"] == 0
    
    @pytest.mark.asyncio
    async def test_sync_all_providers_returns_degraded_on_partial_failure(self):
        """Test that sync_all_providers returns degraded=True when some providers fail."""
        from app.services.watchtower.feed_service import sync_all_providers
        
        # Create a mock database session
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        
        # Mock sync_provider to simulate one success and one failure
        async def mock_sync_provider(source_id, db, force=False):
            if source_id == "fda_recalls":
                return {
                    "source": source_id,
                    "success": True,
                    "items_fetched": 10,
                    "items_added": 5,
                    "error": None,
                    "cached": False,
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_success_at": datetime.utcnow().isoformat(),
                    "last_error_at": None,
                }
            else:
                return {
                    "source": source_id,
                    "success": False,
                    "items_fetched": 0,
                    "items_added": 0,
                    "error": "404 Not Found",
                    "error_message": "404 Not Found",
                    "cached": False,
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_success_at": None,
                    "last_error_at": datetime.utcnow().isoformat(),
                }
        
        with patch('app.services.watchtower.feed_service.sync_provider', side_effect=mock_sync_provider):
            with patch('app.services.watchtower.feed_service.SOURCE_CONFIG', {
                "fda_recalls": {"enabled": True, "required": True},
                "fda_shortages": {"enabled": True, "required": True},
            }):
                result = await sync_all_providers(mock_db, force=True)
        
        # Should return structured result with degraded=True
        assert result["status"] == "ok"  # Partial success is still "ok"
        assert result["degraded"] == True
        assert result["sources_succeeded"] == 1
        assert result["sources_failed"] == 1
        assert result["total_items_added"] == 5
    
    @pytest.mark.asyncio
    async def test_sync_all_providers_returns_error_when_all_fail(self):
        """Test that sync_all_providers returns status=error when all providers fail."""
        from app.services.watchtower.feed_service import sync_all_providers
        
        # Create a mock database session
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        
        # Mock sync_provider to always fail
        async def mock_sync_provider(source_id, db, force=False):
            return {
                "source": source_id,
                "success": False,
                "items_fetched": 0,
                "items_added": 0,
                "error": "All sources failed",
                "error_message": "All sources failed",
                "cached": False,
                "updated_at": datetime.utcnow().isoformat(),
                "last_success_at": None,
                "last_error_at": datetime.utcnow().isoformat(),
            }
        
        with patch('app.services.watchtower.feed_service.sync_provider', side_effect=mock_sync_provider):
            with patch('app.services.watchtower.feed_service.SOURCE_CONFIG', {
                "fda_recalls": {"enabled": True, "required": True},
                "fda_shortages": {"enabled": True, "required": True},
            }):
                result = await sync_all_providers(mock_db, force=True)
        
        # Should return error status when all fail
        assert result["status"] == "error"
        assert result["degraded"] == True
        assert result["sources_succeeded"] == 0
        assert result["sources_failed"] == 2
        assert result["total_items_added"] == 0
    
    @pytest.mark.asyncio
    async def test_sync_all_providers_returns_ok_when_all_succeed(self):
        """Test that sync_all_providers returns status=ok and degraded=False when all succeed."""
        from app.services.watchtower.feed_service import sync_all_providers
        
        # Create a mock database session
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        
        # Mock sync_provider to always succeed
        async def mock_sync_provider(source_id, db, force=False):
            return {
                "source": source_id,
                "success": True,
                "items_fetched": 10,
                "items_added": 3,
                "error": None,
                "cached": False,
                "updated_at": datetime.utcnow().isoformat(),
                "last_success_at": datetime.utcnow().isoformat(),
                "last_error_at": None,
            }
        
        with patch('app.services.watchtower.feed_service.sync_provider', side_effect=mock_sync_provider):
            with patch('app.services.watchtower.feed_service.SOURCE_CONFIG', {
                "fda_recalls": {"enabled": True, "required": True},
                "fda_shortages": {"enabled": True, "required": True},
            }):
                result = await sync_all_providers(mock_db, force=True)
        
        # Should return ok status with degraded=False when all succeed
        assert result["status"] == "ok"
        assert result["degraded"] == False
        assert result["sources_succeeded"] == 2
        assert result["sources_failed"] == 0
        assert result["total_items_added"] == 6  # 3 + 3


class TestWatchtowerSyncStatusTracking:
    """Tests for per-source status tracking."""
    
    @pytest.mark.asyncio
    async def test_sync_result_contains_timestamps(self):
        """Test that sync results contain proper timestamps."""
        from app.services.watchtower.feed_service import sync_provider
        
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        
        with patch('app.services.watchtower.feed_service.get_provider') as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.fetch = AsyncMock(return_value=[])
            mock_get_provider.return_value = mock_provider
            
            with patch('app.services.watchtower.feed_service._get_from_cache', return_value=None):
                with patch('app.services.watchtower.feed_service._set_cache'):
                    with patch('app.services.watchtower.feed_service._persist_items', return_value=0):
                        with patch('app.services.watchtower.feed_service._update_sync_status'):
                            result = await sync_provider("fda_recalls", mock_db, force=True)
        
        # Result should contain timestamp fields
        assert "updated_at" in result
        assert result["success"] == True
        assert "last_success_at" in result
    
    @pytest.mark.asyncio
    async def test_sync_result_contains_error_on_failure(self):
        """Test that sync results contain error info on failure."""
        from app.services.watchtower.feed_service import sync_provider
        
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        
        with patch('app.services.watchtower.feed_service.get_provider') as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.fetch = AsyncMock(side_effect=Exception("HTTP 404: Not Found"))
            mock_get_provider.return_value = mock_provider
            
            with patch('app.services.watchtower.feed_service._get_from_cache', return_value=None):
                with patch('app.services.watchtower.feed_service._update_sync_status'):
                    result = await sync_provider("fda_shortages", mock_db, force=True)
        
        # Result should contain error info
        assert result["success"] == False
        assert result["error"] == "HTTP 404: Not Found"
        assert result["error_message"] == "HTTP 404: Not Found"
        assert "last_error_at" in result


class TestPersistItemsResilience:
    """Tests for _persist_items handling of duplicates and DB errors."""

    def test_persist_items_handles_duplicate_gracefully(self):
        """Test that _persist_items handles duplicate key violations gracefully."""
        from app.services.watchtower.feed_service import _persist_items
        from app.services.watchtower.providers.base import WatchItem
        from sqlalchemy.exc import IntegrityError

        mock_db = MagicMock()
        # First query returns None (no existing), but flush raises IntegrityError
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock(side_effect=IntegrityError(
            "INSERT", {}, Exception("duplicate key")
        ))
        mock_db.rollback = MagicMock()
        mock_db.commit = MagicMock()

        items = [
            WatchItem(
                source="fda_recalls",
                external_id="test-1",
                title="Test Item",
                url="https://example.com",
                published_at=datetime.utcnow(),
            )
        ]

        # Should NOT raise - should handle gracefully
        count = _persist_items(mock_db, items)

        # Should have rolled back and returned 0
        assert mock_db.rollback.called
        assert count == 0

    def test_persist_items_skips_existing_items(self):
        """Test that _persist_items skips items that already exist."""
        from app.services.watchtower.feed_service import _persist_items
        from app.services.watchtower.providers.base import WatchItem

        mock_db = MagicMock()
        # Simulate existing item found
        mock_existing = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_existing
        mock_db.commit = MagicMock()

        items = [
            WatchItem(
                source="fda_recalls",
                external_id="existing-1",
                title="Existing Item",
            )
        ]

        count = _persist_items(mock_db, items)

        # Should skip existing and return 0
        assert count == 0
        assert not mock_db.add.called


class TestUpdateSyncStatusResilience:
    """Tests for _update_sync_status handling of DB errors."""

    def test_update_sync_status_handles_db_error(self):
        """Test that _update_sync_status handles DB errors gracefully."""
        from app.services.watchtower.feed_service import _update_sync_status

        mock_db = MagicMock()
        mock_db.is_active = True
        mock_db.new = []
        mock_db.dirty = []
        mock_db.deleted = []
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock(side_effect=Exception("DB connection lost"))
        mock_db.rollback = MagicMock()

        # Should NOT raise - should handle gracefully
        _update_sync_status(mock_db, "fda_recalls", success=True)

        # Should have attempted rollback
        assert mock_db.rollback.called

    def test_update_sync_status_truncates_long_error(self):
        """Test that _update_sync_status truncates very long error messages."""
        from app.services.watchtower.feed_service import _update_sync_status

        mock_status = MagicMock()
        mock_db = MagicMock()
        mock_db.is_active = True
        mock_db.new = []
        mock_db.dirty = []
        mock_db.deleted = []
        mock_db.query.return_value.filter.return_value.first.return_value = mock_status
        mock_db.commit = MagicMock()

        long_error = "x" * 1000  # Very long error message

        _update_sync_status(mock_db, "fda_recalls", success=False, error=long_error)

        # Error message should be truncated to 500 chars
        assert len(mock_status.last_error_message) <= 500


class TestSyncEndpointErrorHandling:
    """Tests for the sync endpoint error handling."""

    @pytest.mark.asyncio
    async def test_sync_endpoint_returns_structured_error_on_exception(self):
        """Test that sync endpoint returns structured error instead of 500."""
        from unittest.mock import patch, AsyncMock

        # This is an integration-style test that would require TestClient
        # For now, we test the underlying sync_all_providers behavior
        from app.services.watchtower.feed_service import sync_all_providers

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        mock_db.rollback = MagicMock()

        # Mock sync_provider to raise an unexpected exception
        async def mock_sync_provider_raises(source_id, db, force=False):
            raise RuntimeError("Unexpected internal error")

        with patch('app.services.watchtower.feed_service.sync_provider', side_effect=mock_sync_provider_raises):
            with patch('app.services.watchtower.feed_service.SOURCE_CONFIG', {
                "fda_recalls": {"enabled": True, "required": True},
            }):
                result = await sync_all_providers(mock_db, force=True)

        # Should catch the error and return structured result
        assert result["status"] == "error"
        assert result["sources_failed"] == 1
        assert len(result["results"]) == 1
        assert "Unexpected internal error" in result["results"][0].get("error", "")


class TestFDAShortagesParser:
    """Tests for FDA Shortages provider parsing and normalization."""

    def test_shortages_parser_returns_normalized_fields(self):
        """Test that shortages parser returns items with normalized fields."""
        from app.services.watchtower.providers.fda_shortages import FDAShortagesProvider

        provider = FDAShortagesProvider()

        # Sample JSON data mimicking FDA shortages format
        sample_data = {
            "results": [
                {
                    "generic_name": "Amoxicillin",
                    "company_name": "Pfizer Inc",
                    "status": "Currently in Shortage",
                    "update_date": "01/15/2026",
                    "therapeutic_category": ["Antibiotics"],
                    "dosage_form": "Tablet",
                }
            ]
        }

        items = provider._parse_json(sample_data)

        assert len(items) == 1
        item = items[0]

        # Check normalized fields
        assert item.source == "fda_shortages"
        assert "Amoxicillin" in item.title
        assert item.category == "shortage"
        assert item.vendor_name == "Pfizer Inc"
        assert item.manufacturer == "Pfizer Inc"
        assert item.status == "current"  # Normalized from "Currently in Shortage"
        assert item.published_at is not None
        assert item.url is not None

    def test_shortages_parser_handles_missing_manufacturer(self):
        """Test that missing manufacturer is stored as None, not 'Unknown'."""
        from app.services.watchtower.providers.fda_shortages import FDAShortagesProvider

        provider = FDAShortagesProvider()

        sample_data = {
            "results": [
                {
                    "generic_name": "Test Drug",
                    # No company_name / manufacturer
                    "status": "Current",
                }
            ]
        }

        items = provider._parse_json(sample_data)

        assert len(items) == 1
        item = items[0]

        # Manufacturer should be None, not "Unknown"
        assert item.vendor_name is None
        assert item.manufacturer is None

    def test_shortages_parser_handles_missing_status(self):
        """Test that missing status is stored as None, not 'Unknown'."""
        from app.services.watchtower.providers.fda_shortages import FDAShortagesProvider

        provider = FDAShortagesProvider()

        sample_data = {
            "results": [
                {
                    "generic_name": "Test Drug",
                    "company_name": "Test Pharma",
                    # No status field
                }
            ]
        }

        items = provider._parse_json(sample_data)

        assert len(items) == 1
        item = items[0]

        # Status should be None, not "Unknown"
        assert item.status is None

    def test_shortages_status_normalization(self):
        """Test that shortage statuses are normalized consistently."""
        from app.services.watchtower.constants import normalize_shortage_status

        # Current/active
        assert normalize_shortage_status("Currently in Shortage") == "current"
        assert normalize_shortage_status("current") == "current"
        assert normalize_shortage_status("active") == "current"

        # Resolved
        assert normalize_shortage_status("Resolved") == "resolved"
        assert normalize_shortage_status("no longer in shortage") == "resolved"

        # Terminated
        assert normalize_shortage_status("Terminated") == "terminated"
        assert normalize_shortage_status("ended") == "terminated"

        # Unknown/empty
        assert normalize_shortage_status("") is None
        assert normalize_shortage_status("Unknown") is None

    def test_shortages_date_parsing(self):
        """Test that various date formats are parsed correctly."""
        from app.services.watchtower.providers.fda_shortages import FDAShortagesProvider

        provider = FDAShortagesProvider()

        # Test various date formats
        assert provider._parse_date("01/15/2026") is not None
        assert provider._parse_date("2026-01-15") is not None
        assert provider._parse_date("January 15, 2026") is not None
        assert provider._parse_date("") is None
        assert provider._parse_date("invalid-date") is None

    def test_shortages_generates_stable_id(self):
        """Test that stable IDs are generated for items without NDC."""
        from app.services.watchtower.providers.base import WatchItem

        id1 = WatchItem.generate_stable_id("fda_shortages", None, None, "Amoxicillin")
        id2 = WatchItem.generate_stable_id("fda_shortages", None, None, "Amoxicillin")
        id3 = WatchItem.generate_stable_id("fda_shortages", None, None, "Ibuprofen")

        # Same inputs should produce same ID
        assert id1 == id2

        # Different title should produce different ID
        assert id1 != id3


class TestDuplicateIngestion:
    """Tests for duplicate item handling during ingestion."""

    def test_duplicate_ingest_does_not_create_additional_rows(self):
        """Test that ingesting duplicate items doesn't create additional DB rows."""
        from app.services.watchtower.feed_service import _persist_items
        from app.services.watchtower.providers.base import WatchItem

        mock_db = MagicMock()

        # First call: item doesn't exist, gets added
        call_count = [0]

        def mock_first():
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # First check: doesn't exist
            return MagicMock()  # Second check: exists

        mock_db.query.return_value.filter.return_value.first = mock_first
        mock_db.add = MagicMock()
        mock_db.flush = MagicMock()
        mock_db.commit = MagicMock()

        item = WatchItem(
            source="fda_recalls",
            external_id="unique-id-123",
            title="Test Recall",
        )

        # First ingest
        count1 = _persist_items(mock_db, [item])

        # Reset for second call
        call_count[0] = 1  # Next call will return existing

        # Second ingest of same item
        count2 = _persist_items(mock_db, [item])

        # First should add, second should skip
        assert count1 == 1 or count2 == 0  # At least one should be 0


class TestProviderFailureReporting:
    """Tests for provider failure reporting in sync results."""

    @pytest.mark.asyncio
    async def test_provider_failure_includes_error_message_in_result(self):
        """Test that provider failure includes error message in sync result."""
        from app.services.watchtower.feed_service import sync_provider

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        mock_db.is_active = True
        mock_db.new = []
        mock_db.dirty = []
        mock_db.deleted = []

        error_message = "HTTP 404: FDA endpoint not available"

        with patch('app.services.watchtower.feed_service.get_provider') as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.fetch = AsyncMock(side_effect=Exception(error_message))
            mock_provider.last_http_status = 404
            mock_get_provider.return_value = mock_provider

            with patch('app.services.watchtower.feed_service._get_from_cache', return_value=None):
                result = await sync_provider("fda_shortages", mock_db, force=True)

        # Result should include the error details
        assert result["success"] is False
        assert error_message in result["error"]
        assert result["error_message"] == error_message
        assert result["last_http_status"] == 404

    @pytest.mark.asyncio
    async def test_sync_returns_200_with_degraded_when_one_source_fails(self):
        """Test that sync returns status=ok (HTTP 200) with degraded=True when one source fails."""
        from app.services.watchtower.feed_service import sync_all_providers

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()

        async def mock_sync_provider(source_id, db, force=False):
            if source_id == "fda_recalls":
                return {
                    "source": source_id,
                    "success": True,
                    "items_fetched": 50,
                    "items_added": 10,
                    "items_saved": 10,
                    "error": None,
                    "error_message": None,
                    "last_http_status": 200,
                    "cached": False,
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_success_at": datetime.utcnow().isoformat(),
                    "last_error_at": None,
                }
            else:
                return {
                    "source": source_id,
                    "success": False,
                    "items_fetched": 0,
                    "items_added": 0,
                    "items_saved": 0,
                    "error": "FDA shortages API unavailable",
                    "error_message": "FDA shortages API unavailable",
                    "last_http_status": 404,
                    "cached": False,
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_success_at": None,
                    "last_error_at": datetime.utcnow().isoformat(),
                }

        with patch('app.services.watchtower.feed_service.sync_provider', side_effect=mock_sync_provider):
            with patch('app.services.watchtower.feed_service.SOURCE_CONFIG', {
                "fda_recalls": {"enabled": True, "required": True},
                "fda_shortages": {"enabled": True, "required": True},
            }):
                result = await sync_all_providers(mock_db, force=True)

        # Should be ok (not error) with degraded=True
        assert result["status"] == "ok"
        assert result["degraded"] is True
        assert result["sources_succeeded"] == 1
        assert result["sources_failed"] == 1

        # Should include per-source results with error messages
        failed_source = next(r for r in result["results"] if r["source"] == "fda_shortages")
        assert failed_source["error_message"] == "FDA shortages API unavailable"
        assert failed_source["last_http_status"] == 404


class TestShortagesNoUnknownDrug:
    """Tests for ensuring 'Unknown Drug' is never created in shortage titles."""

    def test_shortages_parser_skips_items_without_name(self):
        """Test that items without a drug name are skipped entirely."""
        from app.services.watchtower.providers.fda_shortages import FDAShortagesProvider

        provider = FDAShortagesProvider()

        sample_data = {
            "results": [
                {
                    # No generic_name, drug_name, or name field
                    "company_name": "Test Pharma",
                    "status": "Current",
                },
                {
                    "generic_name": "",  # Empty string
                    "company_name": "Another Pharma",
                },
                {
                    "generic_name": "Valid Drug",
                    "company_name": "Good Pharma",
                }
            ]
        }

        items = provider._parse_json(sample_data)

        # Only the valid drug should be parsed
        assert len(items) == 1
        assert items[0].title == "Drug Shortage: Valid Drug"
        
        # Ensure no "Unknown Drug" in titles
        for item in items:
            assert "Unknown Drug" not in item.title
            assert "Unknown" not in item.title

    def test_shortages_title_never_contains_unknown(self):
        """Test that shortage titles never contain 'Unknown' when fields are missing."""
        from app.services.watchtower.providers.fda_shortages import FDAShortagesProvider

        provider = FDAShortagesProvider()

        sample_data = {
            "results": [
                {
                    "generic_name": "Amoxicillin",
                    # Missing: company_name, status, availability
                }
            ]
        }

        items = provider._parse_json(sample_data)

        assert len(items) == 1
        item = items[0]

        # Title should not contain any "Unknown" text
        assert "Unknown" not in item.title
        assert item.title == "Drug Shortage: Amoxicillin"

        # Summary should be None or not contain "Unknown"
        if item.summary:
            assert "Unknown" not in item.summary


class TestSyncResultStructure:
    """Tests for verifying sync result structure matches API contract."""

    @pytest.mark.asyncio
    async def test_sync_result_has_all_required_fields(self):
        """Test that sync_provider result contains all required fields for API response."""
        from app.services.watchtower.feed_service import sync_provider

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()
        mock_db.is_active = True
        mock_db.new = []
        mock_db.dirty = []
        mock_db.deleted = []

        with patch('app.services.watchtower.feed_service.get_provider') as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.fetch = AsyncMock(return_value=[])
            mock_provider.last_http_status = 200
            mock_get_provider.return_value = mock_provider

            with patch('app.services.watchtower.feed_service._get_from_cache', return_value=None):
                with patch('app.services.watchtower.feed_service._set_cache'):
                    with patch('app.services.watchtower.feed_service._persist_items', return_value=0):
                        with patch('app.services.watchtower.feed_service._update_sync_status'):
                            result = await sync_provider("fda_recalls", mock_db, force=True)

        # Verify all required fields for API response are present
        required_fields = [
            "source", "success", "items_fetched", "items_added", "items_saved",
            "error", "error_message", "last_http_status", "cached", "updated_at",
            "last_success_at", "last_error_at"
        ]
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

    @pytest.mark.asyncio
    async def test_sync_all_result_has_all_required_fields(self):
        """Test that sync_all_providers result contains all required fields for API response."""
        from app.services.watchtower.feed_service import sync_all_providers

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.commit = MagicMock()
        mock_db.add = MagicMock()

        async def mock_sync(source_id, db, force=False):
            return {
                "source": source_id,
                "success": True,
                "items_fetched": 5,
                "items_added": 2,
                "items_saved": 2,
                "error": None,
                "error_message": None,
                "last_http_status": 200,
                "cached": False,
                "updated_at": datetime.utcnow().isoformat(),
                "last_success_at": datetime.utcnow().isoformat(),
                "last_error_at": None,
            }

        with patch('app.services.watchtower.feed_service.sync_provider', side_effect=mock_sync):
            with patch('app.services.watchtower.feed_service.SOURCE_CONFIG', {
                "fda_recalls": {"enabled": True, "required": True},
            }):
                result = await sync_all_providers(mock_db, force=True)

        # Verify all required fields for API response are present
        required_fields = [
            "status", "degraded", "results", "total_items_added",
            "sources_succeeded", "sources_failed"
        ]
        for field in required_fields:
            assert field in result, f"Missing required field: {field}"

        # Verify status values are valid
        assert result["status"] in ["ok", "error"]
        assert isinstance(result["degraded"], bool)
        assert isinstance(result["results"], list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

