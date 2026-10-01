import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class DomainRateLimiter:
    """Per-domain token bucket of capacity one.

    A domain's single token is taken for the whole duration of a request and
    becomes available again `delay` seconds after that request finishes, so
    requests to one domain never overlap and are spaced at least `delay` apart.
    Different domains do not block each other.
    """

    def __init__(
        self,
        default_delay: float = 3.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._default_delay = default_delay
        self._clock = clock
        self._sleep = sleep
        self._delays: dict[str, float] = {}
        self._next_allowed: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def set_delay(self, domain: str, delay: float) -> None:
        self._delays[domain.lower()] = delay

    def delay_for(self, domain: str) -> float:
        return self._delays.get(domain.lower(), self._default_delay)

    def _lock_for(self, domain: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(domain, threading.Lock())

    @contextmanager
    def slot(self, domain: str) -> Iterator[None]:
        """Hold the domain's token for the duration of one request."""
        domain = domain.lower()
        with self._lock_for(domain):
            next_allowed = self._next_allowed.get(domain)
            if next_allowed is not None:
                wait = next_allowed - self._clock()
                if wait > 0:
                    self._sleep(wait)
            try:
                yield
            finally:
                self._next_allowed[domain] = self._clock() + self.delay_for(domain)
