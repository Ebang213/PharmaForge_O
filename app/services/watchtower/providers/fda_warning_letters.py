"""
FDA Warning Letters Provider via HTML page scraping.

Uses the official FDA Warning Letters page:
https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters

There is no openFDA API for warning letters, so we scrape the HTML table.
"""
import re
from datetime import datetime
from typing import List, Optional
from html.parser import HTMLParser

import httpx

from .base import WatchtowerProvider, WatchItem
from app.core.logging import get_logger
from app.services.watchtower.constants import (
    FDA_WARNING_LETTERS_PRIMARY,
    HTTP_TIMEOUT,
    MAX_RETRIES,
    BACKOFF_BASE,
    DEFAULT_HEADERS,
)

logger = get_logger(__name__)

# Use imported constant
FDA_WARNING_LETTERS_URL = FDA_WARNING_LETTERS_PRIMARY


class WarningLetterTableParser(HTMLParser):
    """Parse FDA Warning Letters HTML table."""
    
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
        self.cell_index = 0
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "table":
            # Look for the warning letters table
            table_class = attrs_dict.get("class", "")
            if "datatable" in table_class or "views-table" in table_class:
                self.in_table = True
                
        if self.in_table:
            if tag == "tbody":
                self.in_tbody = True
            elif tag == "tr" and self.in_tbody:
                self.in_row = True
                self.current_row = []
                self.cell_index = 0
            elif tag in ("td", "th") and self.in_row:
                self.in_cell = True
                self.current_cell = ""
                self.current_link = None
            elif tag == "a" and self.in_cell:
                href = attrs_dict.get("href", "")
                if href and not href.startswith("#"):
                    # Make absolute URL
                    if href.startswith("/"):
                        self.current_link = f"https://www.fda.gov{href}"
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
            cell_data = {
                "text": self.current_cell.strip(),
                "link": self.current_link
            }
            self.current_row.append(cell_data)
            self.cell_index += 1
    
    def handle_data(self, data):
        if self.in_cell:
            self.current_cell += data


class FDAWarningLettersProvider(WatchtowerProvider):
    """Provider for FDA Warning Letters via HTML page scraping."""
    
    def __init__(self):
        self._last_http_status: Optional[int] = None
    
    @property
    def last_http_status(self) -> Optional[int]:
        """Last HTTP status code received."""
        return self._last_http_status
    
    @property
    def source_id(self) -> str:
        return "fda_warning_letters"
    
    @property
    def source_name(self) -> str:
        return "FDA Warning Letters"
    
    @property
    def category(self) -> str:
        return "warning_letter"
    
    async def fetch(self) -> List[WatchItem]:
        """Fetch warning letters from FDA page with retry logic."""
        import asyncio
        
        last_error = None
        
        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Fetching FDA warning letters from: {FDA_WARNING_LETTERS_URL} (attempt {attempt + 1})")
                
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(HTTP_TIMEOUT, connect=5.0),
                    headers=DEFAULT_HEADERS
                ) as client:
                    response = await client.get(
                        FDA_WARNING_LETTERS_URL,
                        follow_redirects=True
                    )
                    
                    # Track HTTP status for diagnostics
                    self._last_http_status = response.status_code
                    
                    # Fail fast on 4xx (except 429)
                    if 400 <= response.status_code < 500 and response.status_code != 429:
                        error_msg = f"HTTP {response.status_code}: {response.reason_phrase}"
                        logger.error(f"FDA warning letters fetch failed (non-retryable): {error_msg}")
                        raise Exception(error_msg)
                    
                    # Retry on 429 or 5xx
                    if response.status_code == 429 or response.status_code >= 500:
                        last_error = f"HTTP {response.status_code}: {response.reason_phrase}"
                        logger.warning(f"FDA warning letters fetch failed (retrying): {last_error}")
                        if attempt < MAX_RETRIES - 1:
                            wait_time = BACKOFF_BASE * (2 ** attempt)
                            await asyncio.sleep(wait_time)
                            continue
                        raise Exception(last_error)
                    
                    response.raise_for_status()
                
                items = self._parse_html(response.text)
                logger.info(f"Successfully fetched {len(items)} items from FDA warning letters")
                return items
                
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
                if e.response.status_code >= 400 and e.response.status_code < 500 and e.response.status_code != 429:
                    raise Exception(last_error)
                logger.warning(f"FDA warning letters fetch failed (attempt {attempt + 1}): {last_error}")
                
            except httpx.RequestError as e:
                last_error = f"Request error: {str(e)}"
                logger.warning(f"FDA warning letters fetch failed (attempt {attempt + 1}): {last_error}")
                
            except Exception as e:
                last_error = str(e)
                logger.error(f"FDA warning letters unexpected error (attempt {attempt + 1}): {last_error}")
            
            # Exponential backoff between retries
            if attempt < MAX_RETRIES - 1:
                wait_time = BACKOFF_BASE * (2 ** attempt)
                await asyncio.sleep(wait_time)
        
        # All retries failed
        raise Exception(f"All FDA warning letters fetch attempts failed. Last error: {last_error}")
    
    def _parse_html(self, html_content: str) -> List[WatchItem]:
        """Parse FDA Warning Letters HTML page into WatchItem list."""
        items = []
        
        # Try HTML table parser first
        parser = WarningLetterTableParser()
        try:
            parser.feed(html_content)
        except Exception as e:
            logger.warning(f"HTML table parsing failed: {e}")
        
        if parser.items:
            for row in parser.items[:50]:  # Limit to 50 items
                try:
                    item = self._parse_table_row(row)
                    if item:
                        items.append(item)
                except Exception as e:
                    logger.warning(f"Failed to parse warning letter row: {e}")
                    continue
            return items
        
        # Fallback: Try to extract links from the page
        items = self._extract_links(html_content)
        return items
    
    def _parse_table_row(self, row: List[dict]) -> Optional[WatchItem]:
        """Parse a single table row into a WatchItem."""
        if len(row) < 2:
            return None
        
        # Try to extract company/subject and date
        # FDA table typically has: Company, Subject, Posted Date, etc.
        company_cell = row[0] if row else {"text": "", "link": None}
        
        company_name = company_cell.get("text", "").strip()
        letter_link = company_cell.get("link")
        
        if not company_name:
            return None
        
        # Find date cell (usually contains date-like text)
        posted_date = None
        subject = ""
        
        for i, cell in enumerate(row[1:], start=1):
            cell_text = cell.get("text", "").strip()
            
            # Try to parse as date
            date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", cell_text)
            if date_match:
                try:
                    posted_date = datetime.strptime(date_match.group(1), "%m/%d/%Y")
                except ValueError:
                    pass
            elif not subject and len(cell_text) > 10:
                subject = cell_text
        
        # Generate unique external ID
        date_str = posted_date.strftime("%Y%m%d") if posted_date else datetime.now().strftime("%Y%m%d")
        external_id = f"wl-{company_name[:30].replace(' ', '-').lower()}-{date_str}"
        
        # Build title
        title = f"Warning Letter: {company_name}"
        
        # Use link from cell or main page
        url = letter_link or FDA_WARNING_LETTERS_URL
        
        return WatchItem(
            source=self.source_id,
            external_id=external_id,
            title=title[:200],
            url=url,
            published_at=posted_date,
            summary=subject[:1000] if subject else None,
            category=self.category,
            raw_json={"company": company_name, "subject": subject}
        )
    
    def _extract_links(self, html_content: str) -> List[WatchItem]:
        """Fallback: Extract warning letter links from HTML."""
        items = []
        
        # Find links to warning letters
        link_pattern = r'href="(/inspections[^"]*warning-letters[^"]*)"[^>]*>([^<]+)</a>'
        matches = re.findall(link_pattern, html_content, re.IGNORECASE)
        
        for href, text in matches[:50]:
            text = text.strip()
            if not text or len(text) < 3:
                continue
            
            url = f"https://www.fda.gov{href}" if href.startswith("/") else href
            external_id = f"wl-{text[:30].replace(' ', '-').lower()}-{datetime.now().strftime('%Y%m%d')}"
            
            items.append(WatchItem(
                source=self.source_id,
                external_id=external_id,
                title=f"Warning Letter: {text[:150]}",
                url=url,
                published_at=datetime.now(),
                summary=None,
                category=self.category,
                raw_json={"text": text, "href": href}
            ))
        
        return items
