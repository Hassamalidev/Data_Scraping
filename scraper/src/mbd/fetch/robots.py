import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)

ROBOTS_TTL_SECONDS = 24 * 60 * 60
# A robots.txt we could not read is retried much sooner than a good one.
ROBOTS_ERROR_TTL_SECONDS = 10 * 60


@dataclass
class _Entry:
    parser: RobotFileParser
    expires_at: float


class RobotsCache:
    """Answers "may we fetch this URL?" from each site's robots.txt, cached for 24h.

    `fetch` performs the actual GET of a robots.txt URL so the caller controls
    the HTTP client, User-Agent and rate limiting.

    Status handling follows RFC 9309, erring on the side of not fetching:
    2xx is parsed; 401/403 and 5xx/network failures disallow everything;
    any other 4xx (e.g. 404, no robots.txt) allows everything.
    """

    def __init__(
        self,
        fetch: Callable[[str], httpx.Response],
        user_agent: str,
        *,
        ttl: float = ROBOTS_TTL_SECONDS,
        error_ttl: float = ROBOTS_ERROR_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._fetch = fetch
        self._user_agent = user_agent
        self._ttl = ttl
        self._error_ttl = error_ttl
        self._clock = clock
        self._entries: dict[str, _Entry] = {}

    def allowed(self, url: str) -> bool:
        return self._entry_for(url).parser.can_fetch(self._user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        """The site's Crawl-delay for our User-Agent, if it declares one."""
        delay = self._entry_for(url).parser.crawl_delay(self._user_agent)
        return float(delay) if delay is not None else None

    def _entry_for(self, url: str) -> _Entry:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError(f"Not an http(s) URL: {url!r}")
        origin = f"{parts.scheme}://{parts.netloc.lower()}"
        entry = self._entries.get(origin)
        if entry is None or self._clock() >= entry.expires_at:
            entry = self._load(origin)
            self._entries[origin] = entry
        return entry

    def _load(self, origin: str) -> _Entry:
        robots_url = f"{origin}/robots.txt"
        parser = RobotFileParser(robots_url)
        ttl = self._ttl
        try:
            response = self._fetch(robots_url)
        except httpx.HTTPError as exc:
            logger.warning("robots.txt unreachable for %s (%s); disallowing", origin, exc)
            parser.disallow_all = True
            ttl = self._error_ttl
        else:
            status = response.status_code
            if 200 <= status < 300:
                parser.parse(response.text.splitlines())
            elif status in (401, 403) or status >= 500:
                logger.warning("robots.txt for %s returned %s; disallowing", origin, status)
                parser.disallow_all = True
                ttl = self._error_ttl
            else:
                parser.allow_all = True
        return _Entry(parser=parser, expires_at=self._clock() + ttl)
