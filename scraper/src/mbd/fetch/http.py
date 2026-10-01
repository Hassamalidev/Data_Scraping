import hashlib
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Self
from urllib.parse import urlencode

import httpx
from tenacity import RetryCallState, Retrying, retry_if_exception_type, stop_after_attempt

from mbd.config import Settings
from mbd.fetch.ratelimit import DomainRateLimiter
from mbd.fetch.robots import RobotsCache
from mbd.fetch.validators import FileValidatorStore, Validators, ValidatorStore

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0
BACKOFF_MAX_SECONDS = 60.0
# A server asking us to stay away longer than this ends the fetch instead of blocking the run.
MAX_RETRY_AFTER_SECONDS = 300.0


class FetchError(Exception):
    """The URL could not be fetched (after retries, where retrying made sense)."""

    def __init__(self, url: str, message: str, *, status_code: int | None = None) -> None:
        super().__init__(f"{message}: {url}")
        self.url = url
        self.status_code = status_code


class RobotsDisallowedError(FetchError):
    """robots.txt forbids this URL for our User-Agent; it was not requested."""

    def __init__(self, url: str) -> None:
        super().__init__(url, "Disallowed by robots.txt")


class _RetryableStatus(Exception):
    def __init__(self, response: httpx.Response, retry_after: float | None) -> None:
        super().__init__(f"HTTP {response.status_code}")
        self.response = response
        self.retry_after = retry_after


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    body: str
    # True when the server answered 304 and `body` was read back from `raw_path`.
    not_modified: bool
    raw_path: Path
    headers: Mapping[str, str]
    fetched_at: datetime


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Seconds to wait from a Retry-After header (delta-seconds or HTTP-date)."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - (now or datetime.now(UTC))).total_seconds())


def _extension_for(content_type: str) -> str:
    content_type = content_type.lower()
    if "json" in content_type:
        return "json"
    if "xml" in content_type and "html" not in content_type:
        return "xml"
    return "html"


class PoliteClient:
    """The only way the scraper talks to the network.

    Every request is checked against robots.txt, rate limited per domain,
    retried with backoff on 429/5xx/timeouts, made conditional when we hold
    validators for it, and archived under `raw_dir` for reproducibility.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        raw_dir: Path,
        default_delay: float = 3.0,
        timeout: float = 30.0,
        validators: ValidatorStore | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._raw_dir = raw_dir
        self._sleep = sleep
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self.limiter = DomainRateLimiter(default_delay, clock=clock, sleep=sleep)
        self.robots = RobotsCache(self._fetch_robots, user_agent, clock=clock)
        self._validators = validators or FileValidatorStore(raw_dir / "validators.json")

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            user_agent=settings.scraper_user_agent,
            raw_dir=settings.raw_data_dir,
            default_delay=settings.scraper_default_delay_seconds,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(
        self,
        url: str,
        *,
        source_id: str,
        params: Mapping[str, Any] | None = None,
        conditional: bool = True,
        timeout: float | None = None,
    ) -> FetchResult:
        full_url = str(httpx.URL(url, params=params)) if params else url
        return self._request(
            "GET", full_url, source_id=source_id, conditional=conditional, timeout=timeout
        )

    def post(
        self,
        url: str,
        *,
        source_id: str,
        data: Mapping[str, str],
        timeout: float | None = None,
    ) -> FetchResult:
        return self._request("POST", url, source_id=source_id, data=data, timeout=timeout)

    def _fetch_robots(self, robots_url: str) -> httpx.Response:
        with self.limiter.slot(httpx.URL(robots_url).host):
            return self._client.get(robots_url)

    def _request(
        self,
        method: str,
        url: str,
        *,
        source_id: str,
        data: Mapping[str, str] | None = None,
        conditional: bool = False,
        timeout: float | None = None,
    ) -> FetchResult:
        host = httpx.URL(url).host

        if not self.robots.allowed(url):
            logger.warning("Skipping %s: disallowed by robots.txt", url)
            raise RobotsDisallowedError(url)
        crawl_delay = self.robots.crawl_delay(url)
        if crawl_delay is not None and crawl_delay > self.limiter.delay_for(host):
            self.limiter.set_delay(host, crawl_delay)

        # Identifies the request: the URL, plus the form body for a POST.
        request_key = url if not data else f"{url}?{urlencode(sorted(data.items()))}"
        cache_key = f"{source_id} {request_key}"

        headers: dict[str, str] = {}
        cached = self._validators.get(cache_key) if conditional else None
        if cached is not None and Path(cached.raw_path).is_file():
            if cached.etag:
                headers["If-None-Match"] = cached.etag
            if cached.last_modified:
                headers["If-Modified-Since"] = cached.last_modified
        else:
            cached = None

        response = self._send_with_retries(
            method, url, host, headers=headers, data=data, timeout=timeout
        )
        fetched_at = datetime.now(UTC)

        if response.status_code == 304 and cached is not None:
            raw_path = Path(cached.raw_path)
            return FetchResult(
                url=str(response.url),
                status_code=304,
                body=raw_path.read_bytes().decode(cached.encoding, errors="replace"),
                not_modified=True,
                raw_path=raw_path,
                headers=dict(response.headers),
                fetched_at=fetched_at,
            )
        if not response.is_success:
            raise FetchError(url, f"HTTP {response.status_code}", status_code=response.status_code)

        raw_path = self._save_raw(source_id, request_key, response, fetched_at)
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if method == "GET" and (etag or last_modified):
            self._validators.put(
                cache_key,
                Validators(
                    etag=etag,
                    last_modified=last_modified,
                    raw_path=str(raw_path),
                    encoding=response.encoding or "utf-8",
                ),
            )
        return FetchResult(
            url=str(response.url),
            status_code=response.status_code,
            body=response.text,
            not_modified=False,
            raw_path=raw_path,
            headers=dict(response.headers),
            fetched_at=fetched_at,
        )

    def _send_with_retries(
        self,
        method: str,
        url: str,
        host: str,
        *,
        headers: Mapping[str, str],
        data: Mapping[str, str] | None,
        timeout: float | None,
    ) -> httpx.Response:
        # Slow endpoints (e.g. Overpass queries) may need more than the client default.
        request_timeout = timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT
        retrying = Retrying(
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=_backoff,
            retry=retry_if_exception_type(
                (_RetryableStatus, httpx.TimeoutException, httpx.TransportError)
            ),
            sleep=self._sleep,
            reraise=True,
        )
        try:
            for attempt in retrying:
                with attempt, self.limiter.slot(host):
                    response = self._client.request(
                        method, url, headers=headers, data=data, timeout=request_timeout
                    )
                    if response.status_code == 429 or response.status_code >= 500:
                        retry_after = parse_retry_after(response.headers.get("Retry-After"))
                        if retry_after is not None and retry_after > MAX_RETRY_AFTER_SECONDS:
                            raise FetchError(
                                url,
                                f"HTTP {response.status_code} with Retry-After {retry_after:.0f}s",
                                status_code=response.status_code,
                            )
                        logger.info("HTTP %s from %s; will retry", response.status_code, url)
                        raise _RetryableStatus(response, retry_after)
        except _RetryableStatus as exc:
            status = exc.response.status_code
            raise FetchError(
                url, f"HTTP {status} after {MAX_ATTEMPTS} attempts", status_code=status
            ) from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise FetchError(url, f"{type(exc).__name__} after {MAX_ATTEMPTS} attempts") from exc
        return response

    def _save_raw(
        self, source_id: str, request_key: str, response: httpx.Response, fetched_at: datetime
    ) -> Path:
        digest = hashlib.sha1(request_key.encode("utf-8")).hexdigest()
        extension = _extension_for(response.headers.get("Content-Type", ""))
        directory = self._raw_dir / source_id / fetched_at.strftime("%Y-%m-%d")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.{extension}"
        path.write_bytes(response.content)
        return path


def _backoff(retry_state: RetryCallState) -> float:
    """Exponential backoff, stretched to the server's Retry-After when it sends one."""
    backoff = min(BACKOFF_BASE_SECONDS * 2 ** (retry_state.attempt_number - 1), BACKOFF_MAX_SECONDS)
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    retry_after = getattr(exc, "retry_after", None)
    return max(backoff, retry_after) if retry_after is not None else backoff
