"""
Base classes for data ingestion fetchers.

Provides shared functionality like rate limiting and HTTP session management.
"""

import logging
import time
from typing import Optional

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_REQUEST_DELAY = 1.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class BaseFetcher:
    """
    Base class for data fetchers with rate limiting and HTTP session.
    
    Provides:
    - Rate limiting between requests
    - Shared HTTP session with appropriate headers
    - Logging utilities
    """
    
    def __init__(
        self,
        request_delay: float = DEFAULT_REQUEST_DELAY,
        user_agent: Optional[str] = None,
    ):
        """
        Initialize base fetcher.
        
        Args:
            request_delay: Minimum seconds between requests.
            user_agent: Custom user agent string.
        """
        self.request_delay = request_delay
        self._last_request_time = 0.0
        
        self.session = None
        if REQUESTS_AVAILABLE:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": user_agent or DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            })
    
    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()
    
    def _log_progress(self, current: int, total: int, message: str) -> None:
        """Log progress for long operations."""
        if total > 0:
            pct = (current / total) * 100
            logger.info(f"[{current}/{total}] {pct:.0f}% - {message}")
        else:
            logger.info(f"[{current}] {message}")
