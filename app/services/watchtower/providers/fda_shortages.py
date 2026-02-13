"""
FDA Drug Shortages Provider.

Uses the official openFDA drug/shortages.json API endpoint which provides
structured JSON data on drug shortages including:
- package_ndc, generic_name, status, company_name
- therapeutic_category, dosage_form, presentation
- initial_posting_date, update_date, availability

Fallback to HTML scraping if the API is temporarily unavailable.
"""
import asyncio
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from html.parser import HTMLParser

import httpx

from .base import WatchtowerProvider, WatchItem
from app.core.logging import get_logger
from app.services.watchtower.constants import (
    FDA_SHORTAGES_PRIMARY,
    FDA_SHORTAGES_FALLBACK_URLS,
    FDA_SHORTAGES_PARAMS,
    HTTP_TIMEOUT,
    MAX_RETRIES,
    BACKOFF_BASE,
    DEFAULT_HEADERS,
    normalize_shortage_status,
)

logger = get_logger(__name__)


class ShortagesTableParser(HTMLParser):
    """Parse FDA Drug Shortages HTML table."""

    def __init__(self):
        super().__init__()
        self.items = []
        self.in_table = False
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.current_cell = ""
        self.current_link = None

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "table":
            table_class = attrs_dict.get("class", "")
            table_id = attrs_dict.get("id", "")
            # Look for shortages table
            if "shortage" in table_class.lower() or "shortage" in table_id.lower() or "datatable" in table_class:
                self.in_table = True

        if self.in_table:
            if tag == "tbody":
                self.in_tbody = True
            elif tag == "tr" and self.in_tbody:
                self.in_row = True
                self.current_row = []
            elif tag in ("td", "th") and self.in_row:
                self.in_cell = True
                self.current_cell = ""
                self.current_link = None
            elif tag == "a" and self.in_cell:
                href = attrs_dict.get("href", "")
                if href and not href.startswith("#"):
                    if href.startswith("/"):
                        self.current_link = f"https://www.accessdata.fda.gov{href}"
                    elif href.startswith("http"):
                        self.current_link = href

    def handle_endtag(self, tag):
        if tag == "table" and self.in_table:
            self.in_table = False
            self.in_tbody = False
        elif tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row and len(self.current_row) >= 2:
                self.items.append(self.current_row)
        elif tag in ("td", "th") and self.in_cell:
            self.in_cell = False
            self.current_row.append({
                "text": self.current_cell.strip(),
                "link": self.current_link
            })

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


class FDAShortagesProvider(WatchtowerProvider):
    """
    Provider for FDA Drug Shortages.

    This provider implements graceful degradation:
    - Tries multiple URLs with fallbacks
    - Uses retry with exponential backoff
    - Returns empty list (not crash) if all sources fail
    - Tracks HTTP status codes for diagnostics
    """

    def __init__(self):
        self._last_http_status: Optional[int] = None
        self._last_url_used: Optional[str] = None

    @property
    def source_id(self) -> str:
        return "fda_shortages"

    @property
    def source_name(self) -> str:
        return "FDA Drug Shortages"

    @property
    def category(self) -> str:
        return "shortage"

    @property
    def last_http_status(self) -> Optional[int]:
        """Last HTTP status code received."""
        return self._last_http_status

    async def fetch(self) -> List[WatchItem]:
        """
        Fetch drug shortage items from FDA sources.

        Tries multiple URLs with retries and fallbacks.
        Returns empty list on failure (graceful degradation).
        """
        last_error = None
        all_urls = [FDA_SHORTAGES_PRIMARY] + FDA_SHORTAGES_FALLBACK_URLS

        for attempt in range(MAX_RETRIES):
            for url in all_urls:
                try:
                    items, http_status = await self._try_fetch_url(url)
                    self._last_http_status = http_status
                    self._last_url_used = url

                    if items:
                        logger.info(f"[fda_shortages] Fetched {len(items)} items from {url}")
                        return items

                    # Got response but no items - try next URL
                    logger.warning(f"[fda_shortages] No items found at {url}, trying next...")

                except httpx.HTTPStatusError as e:
                    self._last_http_status = e.response.status_code
                    last_error = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
                    logger.warning(f"[fda_shortages] {last_error} for {url}")

                    # Don't retry on 4xx (except 429)
                    if 400 <= e.response.status_code < 500 and e.response.status_code != 429:
                        continue  # Try next URL

                except httpx.RequestError as e:
                    last_error = f"Request error: {str(e)}"
                    logger.warning(f"[fda_shortages] {last_error} for {url}")

                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"[fda_shortages] Unexpected error for {url}: {last_error}")

            # Exponential backoff between retry rounds
            if attempt < MAX_RETRIES - 1:
                wait_time = BACKOFF_BASE * (2 ** attempt)
                logger.info(f"[fda_shortages] Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)

        # All attempts exhausted - raise exception to mark source as failed
        error_msg = (
            f"FDA drug shortages data unavailable. "
            f"Last error: {last_error or 'No endpoints available'}"
        )
        logger.error(f"[fda_shortages] {error_msg}")
        raise Exception(error_msg)

    async def _try_fetch_url(self, url: str) -> Tuple[List[WatchItem], int]:
        """
        Try to fetch and parse data from a single URL.

        Returns:
            Tuple of (items, http_status_code)
        """
        logger.info(f"[fda_shortages] Fetching from: {url}")

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(HTTP_TIMEOUT, connect=5.0),
            headers=DEFAULT_HEADERS,
            follow_redirects=True
        ) as client:
            response = await client.get(url, params=FDA_SHORTAGES_PARAMS)
            logger.info(f"[fda_shortages] Response status: {response.status_code}")

            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            # Try JSON parsing first
            if "json" in content_type or url.endswith(".json"):
                try:
                    data = response.json()
                    items = self._parse_json(data)
                    return items, response.status_code
                except Exception as e:
                    logger.warning(f"[fda_shortages] JSON parse failed: {e}")

            # Try HTML parsing
            if "html" in content_type or "text" in content_type:
                try:
                    items = self._parse_html(response.text)
                    return items, response.status_code
                except Exception as e:
                    logger.warning(f"[fda_shortages] HTML parse failed: {e}")

            # Unknown content type - try both
            try:
                data = response.json()
                items = self._parse_json(data)
                if items:
                    return items, response.status_code
            except Exception:
                pass

            try:
                items = self._parse_html(response.text)
                return items, response.status_code
            except Exception:
                pass

            return [], response.status_code

    def _parse_json(self, data: dict) -> List[WatchItem]:
        """Parse JSON response into WatchItem list."""
        items = []

        # Handle different JSON structures
        results = data.get("results", data.get("data", data.get("shortages", [])))

        if isinstance(results, dict):
            results = [results]

        for item in results:
            try:
                parsed = self._parse_shortage_item(item)
                if parsed:
                    items.append(parsed)
            except Exception as e:
                logger.debug(f"[fda_shortages] Failed to parse item: {e}")
                continue

        return items

    def _parse_shortage_item(self, item: dict) -> Optional[WatchItem]:
        """Parse a single shortage item from JSON."""
        # Try various field names used by FDA
        generic_name = (
            item.get("generic_name") or
            item.get("drug_name") or
            item.get("product_name") or
            item.get("name", "")
        )

        if not generic_name:
            return None

        # Manufacturer - use null if not present, never "Unknown"
        company_name = (
            item.get("company_name") or
            item.get("manufacturer") or
            item.get("labeler") or
            item.get("firm_name")
        )
        # Don't use "Unknown" - leave as None if not present

        # Status - normalize it
        raw_status = (
            item.get("status") or
            item.get("availability") or
            item.get("shortage_status") or
            ""
        )
        normalized_status = normalize_shortage_status(raw_status)

        # Dates - try multiple field names and formats
        update_date = (
            item.get("update_date") or
            item.get("updated_date") or
            item.get("last_update") or
            item.get("date") or
            ""
        )
        initial_date = item.get("initial_posting_date") or item.get("initial_date") or ""

        published_at = self._parse_date(update_date) or self._parse_date(initial_date)

        # Generate stable external ID
        package_ndc = item.get("package_ndc") or item.get("ndc") or ""
        if package_ndc:
            external_id = f"shortage-{package_ndc}"
        else:
            # Use stable hash-based ID
            external_id = WatchItem.generate_stable_id(
                self.source_id,
                None,  # No URL for individual items
                published_at,
                generic_name
            )

        # Build title - include availability if present
        availability = item.get("availability") or item.get("available", "")
        title = f"Drug Shortage: {generic_name}"
        if availability and availability.lower() not in ("unknown", ""):
            title += f" ({availability})"

        # Build summary with available fields
        summary_parts = []
        if company_name:
            summary_parts.append(f"Manufacturer: {company_name}")
        if normalized_status:
            summary_parts.append(f"Status: {normalized_status}")

        therapeutic_category = item.get("therapeutic_category", [])
        if therapeutic_category:
            if isinstance(therapeutic_category, list):
                categories = ", ".join(therapeutic_category)
            else:
                categories = str(therapeutic_category)
            summary_parts.append(f"Category: {categories}")

        dosage_form = item.get("dosage_form") or item.get("form", "")
        if dosage_form:
            summary_parts.append(f"Form: {dosage_form}")

        presentation = item.get("presentation") or item.get("strength", "")
        if presentation:
            summary_parts.append(f"Presentation: {presentation}")

        summary = ". ".join(summary_parts) if summary_parts else None

        # FDA Drug Shortages page URL
        url = "https://www.accessdata.fda.gov/scripts/drugshortages/default.cfm"

        # Build tags
        tags = ["shortage"]
        if therapeutic_category:
            if isinstance(therapeutic_category, list):
                tags.extend(therapeutic_category)
            else:
                tags.append(str(therapeutic_category))

        return WatchItem(
            source=self.source_id,
            external_id=external_id,
            title=title,
            url=url,
            published_at=published_at,
            summary=summary[:1000] if summary else None,
            category=self.category,
            tags=tags,
            vendor_name=company_name,  # None if not present
            manufacturer=company_name,  # None if not present
            status=normalized_status,  # None if unknown
            raw_json=item
        )

    def _parse_html(self, html_content: str) -> List[WatchItem]:
        """Parse HTML response (shortages table) into WatchItem list."""
        items = []

        # Try table parser
        parser = ShortagesTableParser()
        try:
            parser.feed(html_content)
        except Exception as e:
            logger.warning(f"[fda_shortages] HTML table parse error: {e}")

        if parser.items:
            for row in parser.items[:50]:  # Limit to 50 items
                try:
                    item = self._parse_table_row(row)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.debug(f"[fda_shortages] Failed to parse table row: {e}")
                    continue

        return items

    def _parse_table_row(self, row: List[dict]) -> Optional[WatchItem]:
        """Parse a single table row into a WatchItem."""
        if len(row) < 2:
            return None

        # First cell is usually drug name
        drug_cell = row[0]
        drug_name = drug_cell.get("text", "").strip()
        drug_link = drug_cell.get("link")

        if not drug_name:
            return None

        # Look for manufacturer, status, and date in other cells
        manufacturer = None
        status = None
        posted_date = None

        for cell in row[1:]:
            cell_text = cell.get("text", "").strip()

            # Try to parse as date
            parsed_date = self._parse_date(cell_text)
            if parsed_date:
                posted_date = parsed_date
                continue

            # Check if it looks like a status
            status_check = normalize_shortage_status(cell_text)
            if status_check:
                status = status_check
                continue

            # Otherwise, might be manufacturer
            if not manufacturer and len(cell_text) > 3:
                manufacturer = cell_text

        # Generate stable ID
        external_id = WatchItem.generate_stable_id(
            self.source_id,
            drug_link,
            posted_date,
            drug_name
        )

        title = f"Drug Shortage: {drug_name}"

        # Build summary
        summary_parts = []
        if manufacturer:
            summary_parts.append(f"Manufacturer: {manufacturer}")
        if status:
            summary_parts.append(f"Status: {status}")

        summary = ". ".join(summary_parts) if summary_parts else None

        return WatchItem(
            source=self.source_id,
            external_id=external_id,
            title=title[:200],
            url=drug_link or "https://www.accessdata.fda.gov/scripts/drugshortages/default.cfm",
            published_at=posted_date,
            summary=summary,
            category=self.category,
            vendor_name=manufacturer,
            manufacturer=manufacturer,
            status=status,
            raw_json={"drug_name": drug_name, "manufacturer": manufacturer, "status": status}
        )

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string in various formats.

        Returns timezone-aware datetime or None.
        """
        if not date_str:
            return None

        date_str = date_str.strip()

        # Common FDA date formats
        formats = [
            "%m/%d/%Y",       # 01/15/2026
            "%Y-%m-%d",       # 2026-01-15
            "%Y%m%d",         # 20260115
            "%B %d, %Y",      # January 15, 2026
            "%b %d, %Y",      # Jan 15, 2026
            "%d-%b-%Y",       # 15-Jan-2026
            "%Y-%m-%dT%H:%M:%S",  # ISO format
            "%Y-%m-%dT%H:%M:%SZ",  # ISO with Z
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str[:len(date_str)], fmt)
                # Make timezone-aware (assume UTC if not specified)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        # Try extracting date with regex
        date_match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if date_match:
            try:
                month, day, year = date_match.groups()
                dt = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass

        return None
