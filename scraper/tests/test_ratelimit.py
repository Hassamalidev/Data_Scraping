import threading
import time

from mbd.fetch.ratelimit import DomainRateLimiter


def make_limiter(clock, delay=3.0):
    return DomainRateLimiter(delay, clock=clock, sleep=clock.sleep)


def test_first_request_to_a_domain_does_not_wait(clock):
    limiter = make_limiter(clock)
    with limiter.slot("a.test"):
        pass
    assert clock.sleeps == []


def test_back_to_back_requests_are_spaced_by_the_delay(clock):
    limiter = make_limiter(clock)
    for _ in range(3):
        with limiter.slot("a.test"):
            pass
    assert clock.sleeps == [3.0, 3.0]


def test_only_the_remaining_part_of_the_delay_is_waited(clock):
    limiter = make_limiter(clock)
    with limiter.slot("a.test"):
        pass
    clock.now += 1.25
    with limiter.slot("a.test"):
        pass
    assert clock.sleeps == [1.75]


def test_no_wait_once_the_delay_has_already_elapsed(clock):
    limiter = make_limiter(clock)
    with limiter.slot("a.test"):
        pass
    clock.now += 10
    with limiter.slot("a.test"):
        pass
    assert clock.sleeps == []


def test_delay_is_measured_from_the_end_of_the_previous_request(clock):
    limiter = make_limiter(clock)
    with limiter.slot("a.test"):
        clock.now += 5  # a slow request
    with limiter.slot("a.test"):
        pass
    assert clock.sleeps == [3.0]


def test_domains_are_limited_independently(clock):
    limiter = make_limiter(clock)
    with limiter.slot("a.test"):
        pass
    with limiter.slot("b.test"):
        pass
    assert clock.sleeps == []


def test_per_domain_delay_overrides_the_default(clock):
    limiter = make_limiter(clock)
    limiter.set_delay("Slow.test", 10.0)
    for domain in ("slow.test", "slow.test", "a.test", "a.test"):
        with limiter.slot(domain):
            pass
    assert clock.sleeps == [10.0, 3.0]


def test_requests_to_one_domain_never_overlap():
    limiter = DomainRateLimiter(0.0)
    active = 0
    max_active = 0
    counter_lock = threading.Lock()

    def worker():
        nonlocal active, max_active
        with limiter.slot("a.test"):
            with counter_lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.01)
            with counter_lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1
