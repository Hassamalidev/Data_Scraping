"""Fetch core tests. No live network: every request is answered by respx."""

import hashlib
from datetime import UTC, datetime

import httpx
import pytest

from mbd.fetch import FetchError, PoliteClient, RobotsDisallowedError
from mbd.fetch.http import MAX_ATTEMPTS, parse_retry_after
from mbd.fetch.validators import FileValidatorStore, MemoryValidatorStore, Validators

UA = "TestBot/1.0 (+https://example.org/about; contact@example.org)"
SITE = "https://directory.test"
DAY = 24 * 60 * 60


@pytest.fixture
def raw_dir(tmp_path):
    return tmp_path / "raw"


@pytest.fixture
def client(raw_dir, clock, respx_mock):
    with PoliteClient(
        user_agent=UA,
        raw_dir=raw_dir,
        default_delay=3.0,
        validators=MemoryValidatorStore(),
        clock=clock,
        sleep=clock.sleep,
        # Wired straight into the respx router: no sockets, no TLS setup.
        transport=httpx.MockTransport(respx_mock.handler),
    ) as polite:
        yield polite


def robots(respx_mock, text="User-agent: *\nDisallow:\n", site=SITE):
    return respx_mock.get(f"{site}/robots.txt").respond(200, text=text)


# --- robots.txt -------------------------------------------------------------


@pytest.mark.respx(assert_all_called=False)
def test_disallowed_url_is_never_requested(respx_mock, client):
    robots(respx_mock, "User-agent: *\nDisallow: /private/\n")
    page = respx_mock.get(f"{SITE}/private/members").respond(200, text="secret")

    with pytest.raises(RobotsDisallowedError):
        client.get(f"{SITE}/private/members", source_id="test")

    assert not page.called


def test_allowed_path_on_a_site_with_disallow_rules_is_fetched(respx_mock, client):
    robots(respx_mock, "User-agent: *\nDisallow: /private/\n")
    respx_mock.get(f"{SITE}/directory").respond(200, text="public")

    assert client.get(f"{SITE}/directory", source_id="test").body == "public"


@pytest.mark.respx(assert_all_called=False)
def test_rules_addressed_to_our_user_agent_are_respected(respx_mock, client):
    robots(respx_mock, "User-agent: TestBot\nDisallow: /\n\nUser-agent: *\nDisallow:\n")
    page = respx_mock.get(f"{SITE}/directory").respond(200, text="public")

    with pytest.raises(RobotsDisallowedError):
        client.get(f"{SITE}/directory", source_id="test")

    assert not page.called


def test_robots_txt_is_cached_for_24_hours(respx_mock, client, clock):
    robots_route = robots(respx_mock)
    respx_mock.get(f"{SITE}/a").respond(200, text="a")

    client.get(f"{SITE}/a", source_id="test")
    clock.now += DAY - 60
    client.get(f"{SITE}/a", source_id="test")
    assert robots_route.call_count == 1

    clock.now += 120
    client.get(f"{SITE}/a", source_id="test")
    assert robots_route.call_count == 2


def test_missing_robots_txt_allows_fetching(respx_mock, client):
    respx_mock.get(f"{SITE}/robots.txt").respond(404)
    respx_mock.get(f"{SITE}/a").respond(200, text="a")

    assert client.get(f"{SITE}/a", source_id="test").body == "a"


@pytest.mark.respx(assert_all_called=False)
@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_unreadable_robots_txt_blocks_fetching(respx_mock, client, status):
    respx_mock.get(f"{SITE}/robots.txt").respond(status)
    page = respx_mock.get(f"{SITE}/a").respond(200, text="a")

    with pytest.raises(RobotsDisallowedError):
        client.get(f"{SITE}/a", source_id="test")

    assert not page.called


@pytest.mark.respx(assert_all_called=False)
def test_unreachable_robots_txt_blocks_fetching(respx_mock, client):
    respx_mock.get(f"{SITE}/robots.txt").mock(side_effect=httpx.ConnectError("down"))
    page = respx_mock.get(f"{SITE}/a").respond(200, text="a")

    with pytest.raises(RobotsDisallowedError):
        client.get(f"{SITE}/a", source_id="test")

    assert not page.called


def test_crawl_delay_longer_than_our_default_is_adopted(respx_mock, client, clock):
    robots(respx_mock, "User-agent: *\nCrawl-delay: 10\nDisallow:\n")
    respx_mock.get(f"{SITE}/a").respond(200, text="a")

    client.get(f"{SITE}/a", source_id="test")
    client.get(f"{SITE}/a", source_id="test")

    assert clock.sleeps[-1] == 10.0


# --- rate limiting ----------------------------------------------------------


def test_requests_to_one_host_are_spaced_by_the_default_delay(respx_mock, client, clock):
    robots(respx_mock)
    respx_mock.get(f"{SITE}/a").respond(200, text="a")
    respx_mock.get(f"{SITE}/b").respond(200, text="b")

    client.get(f"{SITE}/a", source_id="test")
    client.get(f"{SITE}/b", source_id="test")

    # robots.txt -> /a -> /b, each 3s after the previous one finished.
    assert clock.sleeps == [3.0, 3.0]


def test_a_second_host_is_not_delayed_by_the_first(respx_mock, client, clock):
    other = "https://other.test"
    robots(respx_mock)
    robots(respx_mock, site=other)
    respx_mock.get(f"{SITE}/a").respond(200, text="a")
    respx_mock.get(f"{other}/a").respond(200, text="a")

    client.get(f"{SITE}/a", source_id="test")
    sleeps_before = list(clock.sleeps)
    client.get(f"{other}/a", source_id="test")

    # Only the gap between other.test's own robots.txt and page is waited.
    assert clock.sleeps[len(sleeps_before) :] == [3.0]


# --- retries ----------------------------------------------------------------


def test_429_is_retried_and_retry_after_is_honoured(respx_mock, client, clock):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/a").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, text="finally"),
        ]
    )

    result = client.get(f"{SITE}/a", source_id="test")

    assert result.body == "finally"
    assert page.call_count == 2
    assert clock.sleeps == [3.0, 7.0]


def test_5xx_is_retried_with_exponential_backoff(respx_mock, client, clock):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/a").mock(
        side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, text="ok")]
    )

    result = client.get(f"{SITE}/a", source_id="test")

    assert result.body == "ok"
    assert page.call_count == 3
    # 3s rate limit, 2s backoff (+1s to complete the rate limit), then 4s backoff.
    assert clock.sleeps == [3.0, 2.0, 1.0, 4.0]


def test_timeouts_are_retried(respx_mock, client):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/a").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, text="ok")]
    )

    assert client.get(f"{SITE}/a", source_id="test").body == "ok"
    assert page.call_count == 2


def test_gives_up_after_four_attempts(respx_mock, client):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/a").respond(500)

    with pytest.raises(FetchError) as excinfo:
        client.get(f"{SITE}/a", source_id="test")

    assert excinfo.value.status_code == 500
    assert page.call_count == MAX_ATTEMPTS == 4


def test_persistent_timeouts_raise_fetch_error(respx_mock, client):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/a").mock(side_effect=httpx.ConnectTimeout("no route"))

    with pytest.raises(FetchError):
        client.get(f"{SITE}/a", source_id="test")

    assert page.call_count == 4


def test_404_is_not_retried(respx_mock, client):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/gone").respond(404)

    with pytest.raises(FetchError) as excinfo:
        client.get(f"{SITE}/gone", source_id="test")

    assert excinfo.value.status_code == 404
    assert page.call_count == 1


def test_excessive_retry_after_ends_the_fetch_without_retrying(respx_mock, client, clock):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/a").respond(429, headers={"Retry-After": "86400"})

    with pytest.raises(FetchError) as excinfo:
        client.get(f"{SITE}/a", source_id="test")

    assert excinfo.value.status_code == 429
    assert page.call_count == 1
    assert max(clock.sleeps) == 3.0


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("120", 120.0),
        ("0", 0.0),
        ("Thu, 01 Oct 2026 12:00:30 GMT", 30.0),
        ("Thu, 01 Oct 2026 11:00:00 GMT", 0.0),
        ("soon", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_retry_after(header, expected):
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after(header, now=now) == expected


# --- conditional GET --------------------------------------------------------


def test_conditional_get_sends_validators_and_304_reuses_the_saved_body(respx_mock, client):
    robots(respx_mock)
    last_modified = "Wed, 30 Sep 2026 10:00:00 GMT"
    page = respx_mock.get(f"{SITE}/list").mock(
        side_effect=[
            httpx.Response(
                200,
                text="<html>v1</html>",
                headers={"ETag": '"abc"', "Last-Modified": last_modified},
            ),
            httpx.Response(304),
        ]
    )

    first = client.get(f"{SITE}/list", source_id="test")
    second = client.get(f"{SITE}/list", source_id="test")

    first_request, second_request = (call.request for call in page.calls)
    assert "If-None-Match" not in first_request.headers
    assert "If-Modified-Since" not in first_request.headers
    assert second_request.headers["If-None-Match"] == '"abc"'
    assert second_request.headers["If-Modified-Since"] == last_modified

    assert first.not_modified is False
    assert second.not_modified is True
    assert second.status_code == 304
    assert second.body == "<html>v1</html>"
    assert second.raw_path == first.raw_path


def test_304_body_keeps_its_original_encoding(respx_mock, client):
    robots(respx_mock)
    respx_mock.get(f"{SITE}/list").mock(
        side_effect=[
            httpx.Response(
                200,
                content="Boucherie Montréal".encode("iso-8859-1"),
                headers={"ETag": '"fr"', "Content-Type": "text/html; charset=iso-8859-1"},
            ),
            httpx.Response(304),
        ]
    )

    client.get(f"{SITE}/list", source_id="test")

    assert client.get(f"{SITE}/list", source_id="test").body == "Boucherie Montréal"


def test_no_conditional_headers_without_validators(respx_mock, client):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/list").respond(200, text="no validators here")

    client.get(f"{SITE}/list", source_id="test")
    client.get(f"{SITE}/list", source_id="test")

    for call in page.calls:
        assert "If-None-Match" not in call.request.headers
        assert "If-Modified-Since" not in call.request.headers


def test_conditional_can_be_switched_off(respx_mock, client):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/list").respond(200, text="v1", headers={"ETag": '"abc"'})

    client.get(f"{SITE}/list", source_id="test")
    client.get(f"{SITE}/list", source_id="test", conditional=False)

    assert "If-None-Match" not in page.calls[1].request.headers


def test_validators_are_not_used_when_the_saved_body_is_gone(respx_mock, client):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/list").respond(200, text="v1", headers={"ETag": '"abc"'})

    first = client.get(f"{SITE}/list", source_id="test")
    first.raw_path.unlink()
    second = client.get(f"{SITE}/list", source_id="test")

    assert "If-None-Match" not in page.calls[1].request.headers
    assert second.body == "v1"


def test_file_validator_store_persists_between_instances(tmp_path):
    path = tmp_path / "raw" / "validators.json"
    validators = Validators(etag='"abc"', last_modified=None, raw_path="x.html", encoding="utf-8")

    FileValidatorStore(path).put("test https://directory.test/list", validators)

    assert FileValidatorStore(path).get("test https://directory.test/list") == validators
    assert FileValidatorStore(path).get("unknown") is None


# --- raw archive, headers, POST ---------------------------------------------


def test_raw_response_is_archived_by_source_date_and_url_hash(respx_mock, client, raw_dir):
    robots(respx_mock)
    url = f"{SITE}/list?page=2"
    respx_mock.get(url).respond(200, content=b"<html>caf\xc3\xa9</html>")

    result = client.get(url, source_id="jaffari_dir")

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    expected = raw_dir / "jaffari_dir" / today / f"{hashlib.sha1(url.encode()).hexdigest()}.html"
    assert result.raw_path == expected
    assert expected.read_bytes() == b"<html>caf\xc3\xa9</html>"
    assert result.body == "<html>café</html>"


def test_json_responses_are_archived_with_a_json_extension(respx_mock, client):
    robots(respx_mock)
    respx_mock.get(f"{SITE}/api").respond(200, json={"elements": []})

    assert client.get(f"{SITE}/api", source_id="test").raw_path.suffix == ".json"


def test_query_params_are_part_of_the_requested_url(respx_mock, client):
    robots(respx_mock)
    page = respx_mock.get(f"{SITE}/directory", params={"view": "list"}).respond(200, text="ok")

    client.get(f"{SITE}/directory", source_id="test", params={"view": "list"})

    assert page.called


def test_every_request_identifies_itself(respx_mock, client):
    robots_route = robots(respx_mock)
    page = respx_mock.get(f"{SITE}/a").respond(200, text="a")

    client.get(f"{SITE}/a", source_id="test")

    assert robots_route.calls[0].request.headers["User-Agent"] == UA
    assert page.calls[0].request.headers["User-Agent"] == UA


def test_post_sends_form_data_and_archives_per_request_body(respx_mock, client):
    robots(respx_mock)
    endpoint = respx_mock.post(f"{SITE}/api/interpreter").respond(200, json={"elements": []})

    first = client.post(f"{SITE}/api/interpreter", source_id="test", data={"data": "query one"})
    second = client.post(f"{SITE}/api/interpreter", source_id="test", data={"data": "query two"})

    assert endpoint.calls[0].request.content == b"data=query+one"
    assert first.raw_path != second.raw_path
    assert first.raw_path.suffix == ".json"
