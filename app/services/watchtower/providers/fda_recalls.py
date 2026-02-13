"""
FDA Drug Recalls Provider using openFDA Drug Enforcement API.

Uses the official openFDA Drug Enforcement API:
https://api.fda.gov/drug/enforcement.json

This provides reliable access to FDA recall data.
"""
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional
from email.utils import parsedate_to_datetime

import httpx

from .base import WatchtowerProvider, WatchItem
from app.core.logging import get_logger
from app.services.watchtower.constants import (
    FDA_ENFORCEMENT_PRIMARY,
    FDA_RECALLS_RSS_URLS,
    FDA_ENFORCEMENT_PARAMS,
    HTTP_TIMEOUT,
    MAX_RETRIES,
    BACKOFF_BASE,
    DEFAULT_HEADERS,
)

logger = get_logger(__name__)

# Use imported constants
FDA_ENFORCEMENT_API = FDA_ENFORCEMENT_PRIMARY


class FDARecallsProvider(WatchtowerProvider):
    """Provider for FDA Drug Recalls via openFDA API."""
    
    def __init__(self):
        self._last_http_status: Optional[int] = None
    
    @property
    def last_http_status(self) -> Optional[int]:
        """Last HTTP status code received."""
        return self._last_http_status
    
    @property
    def source_id(self) -> str:
        return "fda_recalls"
    
    @property
    def source_name(self) -> str:
        return "FDA Drug Recalls"
    
    @property
    def category(self) -> str:
        return "recall"
    
    async def fetch(self) -> List[WatchItem]:
        """Fetch drug recall items from openFDA API with retry logic."""
        last_error = None
        
        # Try openFDA API first (most reliable)
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Fetching FDA recalls from openFDA API (attempt {attempt + 1})")
                
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(HTTP_TIMEOUT, connect=5.0),
                    headers=DEFAULT_HEADERS
                ) as client:
                    response = await client.get(
                        FDA_ENFORCEMENT_API,
                        params=FDA_ENFORCEMENT_PARAMS,
                        follow_redirects=True
                    )
                    
                    # Track HTTP status for diagnostics
                    self._last_http_status = response.status_code
                    
                    # Fail fast on 4xx (except 429)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        logger.warning(f"openFDA API returned {response.status_code}: {response.reason_phrase}, trying RSS fallback")
                        break  # Try RSS fallback
                    
                    # Retry on 429 or 5xx
                    if response.status_code == 429 or response.status_code >= 500:
                        last_error = f"HTTP {response.status_code}: {response.reason_phrase}"
                        logger.warning(f"FDA recalls fetch failed (retrying): {last_error}")
                        if attempt < MAX_RETRIES - 1:
                            wait_time = BACKOFF_BASE * (2 ** attempt)
                            await asyncio.sleep(wait_time)
                            continue
                        break  # Try RSS fallback
                    
                    response.raise_for_status()
                
                items = self._parse_json(response.json())
                logger.info(f"Successfully fetched {len(items)} items from openFDA API")
                return items
                
            except httpx.RequestError as e:
                last_error = f"Request error: {str(e)}"
                logger.warning(f"FDA recalls fetch failed (attempt {attempt + 1}): {last_error}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = BACKOFF_BASE * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    
            except Exception as e:
                last_error = str(e)
                logger.warning(f"FDA recalls unexpected error (attempt {attempt + 1}): {last_error}")
                if attempt < MAX_RETRIES - 1:
                    wait_time = BACKOFF_BASE * (2 ** attempt)
                    await asyncio.sleep(wait_time)
        
        # Fallback: Try RSS feeds
        logger.info("Trying RSS fallback for FDA recalls")
        items = await self._try_rss_fallback()
        if items:
            return items
        
        # All sources failed
        raise Exception(f"All FDA recall sources failed. Last error: {last_error}")
    
    async def _try_rss_fallback(self) -> List[WatchItem]:
        """Try RSS feeds as fallback."""
        urls_to_try = FDA_RECALLS_RSS_URLS
        
        for url in urls_to_try:
            try:
                logger.info(f"Trying RSS fallback: {url}")
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(HTTP_TIMEOUT, connect=5.0),
                    headers=DEFAULT_HEADERS
                ) as client:
                    response = await client.get(url, follow_redirects=True)
                    
                    if response.status_code == 404:
                        logger.warning(f"RSS feed not found: {url}")
                        continue
                    
                    response.raise_for_status()
                    
                items = self._parse_rss(response.text)
                logger.info(f"Successfully fetched {len(items)} items from RSS fallback")
                return items
                
            except Exception as e:
                logger.warning(f"RSS fallback failed for {url}: {e}")
                continue
        
        return []
    
    def _parse_json(self, data: dict) -> List[WatchItem]:
        """Parse openFDA JSON response into WatchItem list."""
        items = []
        
        results = data.get("results", [])
        
        for item in results:
            try:
                recall_number = item.get("recall_number", "")
                recalling_firm = item.get("recalling_firm", "Unknown Manufacturer")
                product_description = item.get("product_description", "Unknown Product")
                reason_for_recall = item.get("reason_for_recall", "")
                classification = item.get("classification", "")
                report_date = item.get("report_date", "")
                status = item.get("status", "")
                
                # Generate external ID
                external_id = recall_number or f"recall-{recalling_firm[:20]}-{report_date}"
                
                # Parse report date (YYYYMMDD format)
                published_at = None
                if report_date:
                    try:
                        published_at = datetime.strptime(report_date[:8], "%Y%m%d")
                    except ValueError:
                        pass
                
                # Build title
                product_short = product_description[:100] if len(product_description) > 100 else product_description
                title = f"Recall: {product_short}"
                if classification:
                    title = f"[{classification}] {title}"
                
                # Build summary
                summary_parts = []
                if recalling_firm:
                    summary_parts.append(f"Firm: {recalling_firm}")
                if reason_for_recall:
                    summary_parts.append(f"Reason: {reason_for_recall[:200]}")
                if status:
                    summary_parts.append(f"Status: {status}")
                
                summary = ". ".join(summary_parts) if summary_parts else None
                
                # Build URL
                url = f"https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRES/res.cfm?id={recall_number}" if recall_number else None
                
                items.append(WatchItem(
                    source=self.source_id,
                    external_id=external_id,
                    title=title[:200],
                    url=url,
                    published_at=published_at,
                    summary=summary[:1000] if summary else None,
                    category=self.category,
                    raw_json=item
                ))
                
            except Exception as e:
                logger.warning(f"Failed to parse recall item: {e}")
                continue
        
        return items
    
    def _parse_rss(self, xml_content: str) -> List[WatchItem]:
        """Parse RSS XML content into WatchItem list."""
        items = []
        
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            # Try removing any BOM or problematic characters
            xml_content = xml_content.lstrip('\ufeff').strip()
            root = ET.fromstring(xml_content)
        
        # RSS 2.0 structure: rss > channel > item
        channel = root.find("channel")
        if channel is None:
            channel = root
        
        for item in channel.findall("item"):
            try:
                parsed_item = self._parse_rss_item(item)
                if parsed_item:
                    items.append(parsed_item)
            except Exception as e:
                logger.warning(f"Failed to parse RSS item: {e}")
                continue
        
        # Try Atom entries if no RSS items found
        if not items:
            for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
                try:
                    parsed_item = self._parse_atom_entry(entry)
                    if parsed_item:
                        items.append(parsed_item)
                except Exception as e:
                    logger.warning(f"Failed to parse Atom entry: {e}")
                    continue
        
        return items
    
    def _parse_rss_item(self, item: ET.Element) -> Optional[WatchItem]:
        """Parse a single RSS item element."""
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        description = item.findtext("description", "").strip()
        pub_date = item.findtext("pubDate", "")
        guid = item.findtext("guid", link).strip()
        
        if not title or not guid:
            return None
        
        # Parse publication date
        published_at = None
        if pub_date:
            try:
                published_at = parsedate_to_datetime(pub_date)
            except (ValueError, TypeError):
                try:
                    published_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                except ValueError:
                    pass
        
        return WatchItem(
            source=self.source_id,
            external_id=guid,
            title=title,
            url=link or None,
            published_at=published_at,
            summary=description[:1000] if description else None,
            category=self.category,
            raw_json={
                "title": title,
                "link": link,
                "description": description,
                "pubDate": pub_date,
                "guid": guid
            }
        )
    
    def _parse_atom_entry(self, entry: ET.Element) -> Optional[WatchItem]:
        """Parse a single Atom entry element."""
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        title = entry.findtext("atom:title", "", ns).strip()
        link_elem = entry.find("atom:link[@rel='alternate']", ns) or entry.find("atom:link", ns)
        link = link_elem.get("href", "") if link_elem is not None else ""
        summary = entry.findtext("atom:summary", "", ns).strip() or entry.findtext("atom:content", "", ns).strip()
        updated = entry.findtext("atom:updated", "", ns) or entry.findtext("atom:published", "", ns)
        entry_id = entry.findtext("atom:id", link, ns).strip()
        
        if not title or not entry_id:
            return None
        
        published_at = None
        if updated:
            try:
                published_at = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                pass
        
        return WatchItem(
            source=self.source_id,
            external_id=entry_id,
            title=title,
            url=link or None,
            published_at=published_at,
            summary=summary[:1000] if summary else None,
            category=self.category,
            raw_json={"title": title, "link": link, "summary": summary, "id": entry_id}
        )
