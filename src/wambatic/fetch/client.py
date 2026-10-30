import asyncio
import collections.abc
import dataclasses
import datetime
import email.utils
import random
import re

import aiohttp
import loguru

import wambatic.fetch.auth
import wambatic.fetch.errors
import wambatic.fetch.ratelimit
import wambatic.settings
import wambatic.version

REQUEST_TIMEOUT = 60.0
TRANSIENT_STATUSES = frozenset({500, 502, 503, 504})
NEXT_LINK = re.compile(r'<([^>]*)>\s*;\s*rel="next"')


@dataclasses.dataclass(frozen=True, slots=True)
class RestResponse:
    status: int
    data: object | None
    etag: str | None
    next_url: str | None
    date: datetime.datetime | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: collections.abc.Mapping[str, str]
    data: object | None
    request_info: aiohttp.RequestInfo


def next_link(header: str | None) -> str | None:
    """The `rel="next"` URL of a `Link` header, or None."""
    if header is None:
        return None
    for part in header.split(','):
        match = NEXT_LINK.search(part)
        if match:
            return match.group(1)
    return None


def error_types(data: object) -> list[tuple[str, str]]:
    """`(type, message)` pairs of a GraphQL response's `errors`."""
    if not isinstance(data, dict):
        return []
    errors = data.get('errors')
    if not isinstance(errors, list):
        return []
    return [
        (str(error.get('type', 'UNKNOWN')), str(error.get('message', '')))
        for error in errors
        if isinstance(error, dict)
    ]


def header_date(response: Response) -> datetime.datetime | None:
    """The `Date` header as an aware UTC datetime; None when it is missing or unparseable."""
    value = response.headers.get('Date')
    try:
        parsed = None if value is None else email.utils.parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    if parsed is None or parsed.tzinfo is None:
        return None
    return parsed.astimezone(datetime.UTC)


def require_date(date: datetime.datetime | None) -> datetime.datetime:
    """`date`, or `GraphQLError` (`MALFORMED`) when the response had no parseable `Date`."""
    if date is None:
        raise wambatic.fetch.errors.GraphQLError(
            [('MALFORMED', 'response has no parseable Date header')]
        )
    return date


def response_date(response: Response) -> datetime.datetime:
    """The `Date` header as an aware UTC datetime; `GraphQLError` (`MALFORMED`) when it is
    missing or unparseable."""
    return require_date(header_date(response))


class GitHubClient:
    def __init__(
        self,
        token: str,
        settings: wambatic.settings.FetchSettings,
        *,
        api_url: str = 'https://api.github.com',
        sleep: collections.abc.Callable[[float], collections.abc.Awaitable[None]] = asyncio.sleep,
        clock: collections.abc.Callable[[], datetime.datetime] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.token = token
        self.settings = settings
        self.api_url = api_url
        self.sleep = sleep
        self.clock = clock or wambatic.fetch.ratelimit.utc_now
        self.rng = rng or random.Random()
        self.session: aiohttp.ClientSession | None = None
        self.limits = {
            'graphql': wambatic.fetch.ratelimit.RateLimitState(),
            'rest': wambatic.fetch.ratelimit.RateLimitState(),
        }
        self.logger = loguru.logger.patch(self.redact_record)

    def redact_record(self, record: loguru.Record) -> None:
        record['message'] = wambatic.fetch.auth.redact(record['message'], self.token)

    async def __aenter__(self) -> GitHubClient:
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            headers={
                'Authorization': f'Bearer {self.token}',
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
                'User-Agent': f'wambatic/{wambatic.version.VERSION}',
            },
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self.session is not None:
            await self.session.close()

    @property
    def graphql_limit(self) -> wambatic.fetch.ratelimit.RateLimitState:
        return self.limits['graphql']

    @property
    def rest_limit(self) -> wambatic.fetch.ratelimit.RateLimitState:
        return self.limits['rest']

    async def graphql(
        self, query: str, variables: collections.abc.Mapping[str, object]
    ) -> dict[str, object]:
        """POST `{api_url}/graphql`; returns `data`; raises the typed errors."""
        return (await self.graphql_dated(query, variables))[0]

    async def graphql_dated(
        self, query: str, variables: collections.abc.Mapping[str, object]
    ) -> tuple[dict[str, object], datetime.datetime]:
        """As `graphql`, with the response's `Date` header as an aware UTC datetime: GitHub's
        clock, for a watermark that does not depend on this machine's."""
        response = await self.request(
            'graphql', 'POST', '/graphql', json={'query': query, 'variables': dict(variables)}
        )
        pairs = error_types(response.data)
        if any(kind == 'NOT_FOUND' for kind, _ in pairs):
            raise wambatic.fetch.errors.NotFoundError('; '.join(message for _, message in pairs))
        if pairs:
            raise wambatic.fetch.errors.GraphQLError(pairs)
        data = response.data.get('data') if isinstance(response.data, dict) else None
        if not isinstance(data, dict) or not isinstance(data.get('rateLimit'), dict):
            raise wambatic.fetch.errors.GraphQLError(
                [('MALFORMED', 'response has no data or lacks rateLimit')]
            )
        return data, response_date(response)

    async def rest_get(
        self,
        path: str,
        params: collections.abc.Mapping[str, str] | None = None,
        etag: str | None = None,
    ) -> RestResponse:
        """GET `{api_url}{path}` with `If-None-Match: etag` when given."""
        headers = {'If-None-Match': etag} if etag else None
        pending = 0
        while True:
            response = await self.request('rest', 'GET', path, params=params, headers=headers)
            if response.status != 202:
                break
            if pending >= self.settings.stats_retries:
                raise wambatic.fetch.errors.StatsPendingError(
                    f'GitHub is still computing {path}; try again later'
                )
            await self.sleep(wambatic.fetch.ratelimit.backoff_delay(pending, self.rng))
            pending += 1
        if response.status == 304:
            return RestResponse(304, None, etag, None, header_date(response))
        return RestResponse(
            response.status,
            response.data,
            response.headers.get('ETag'),
            next_link(response.headers.get('Link')),
            header_date(response),
        )

    async def send(
        self,
        method: str,
        path: str,
        *,
        json: object = None,
        params: collections.abc.Mapping[str, str] | None = None,
        headers: collections.abc.Mapping[str, str] | None = None,
    ) -> Response:
        """One request; no classification."""
        if self.session is None:
            raise RuntimeError('GitHubClient must be used inside `async with`')
        url = f'{self.api_url}{path}'
        async with self.session.request(
            method, url, json=json, params=params, headers=headers
        ) as raw:
            body = await raw.read()
            self.logger.debug(f'{method} {url} {raw.status}')
            data: object | None = None
            if body:
                try:
                    data = await raw.json(content_type=None)
                except ValueError:
                    if raw.ok:
                        raise
            return Response(raw.status, raw.headers, data, raw.request_info)

    def update_limits(self, endpoint: str, response: Response) -> None:
        state = wambatic.fetch.ratelimit.RateLimitState.from_headers(response.headers)
        if endpoint == 'graphql' and isinstance(response.data, dict):
            data = response.data.get('data')
            rate_limit = data.get('rateLimit') if isinstance(data, dict) else None
            if isinstance(rate_limit, dict):
                state = wambatic.fetch.ratelimit.RateLimitState.from_graphql(rate_limit)
        if state != wambatic.fetch.ratelimit.RateLimitState():
            self.limits[endpoint] = state

    def limit_kind(self, endpoint: str, response: Response) -> str | None:
        """'retry-after', 'primary', 'secondary' or None for a limit signal in `response`."""
        if endpoint == 'graphql' and any(
            kind == 'RATE_LIMITED' for kind, _ in error_types(response.data)
        ):
            return 'primary'
        if response.status not in (403, 429):
            return None
        if 'retry-after' in response.headers:
            return 'retry-after'
        if response.headers.get('x-ratelimit-remaining') == '0':
            return 'primary'
        message = response.data.get('message') if isinstance(response.data, dict) else None
        if isinstance(message, str) and 'secondary rate limit' in message.lower():
            return 'secondary'
        return None

    async def wait_for_reset(self, endpoint: str, reset_at: datetime.datetime) -> None:
        """Fail or wait out an exhausted primary limit, per `on_rate_limit`."""
        if self.settings.on_rate_limit == 'fail':
            raise wambatic.fetch.errors.RateLimitError(reset_at)
        wait = (reset_at - self.clock()).total_seconds() + 1
        self.logger.info(
            f'ETA: GitHub rate limit resets in {datetime.timedelta(seconds=round(wait))}'
        )
        await self.sleep(wait)
        self.limits[endpoint] = wambatic.fetch.ratelimit.RateLimitState()

    def retry_after(self, response: Response) -> float:
        try:
            return float(response.headers['retry-after'])
        except KeyError, ValueError:
            return wambatic.fetch.ratelimit.SECONDARY_WAIT

    async def request(
        self,
        endpoint: str,
        method: str,
        path: str,
        *,
        json: object = None,
        params: collections.abc.Mapping[str, str] | None = None,
        headers: collections.abc.Mapping[str, str] | None = None,
    ) -> Response:
        """`send` with classification, rate-limit accounting and retries."""
        retries = 0
        max_retries = self.settings.max_retries
        while True:
            state = self.limits[endpoint]
            if state.reset_at is not None and state.exhausted(self.clock()):
                await self.wait_for_reset(endpoint, state.reset_at)
            try:
                response = await self.send(method, path, json=json, params=params, headers=headers)
            except aiohttp.ClientConnectionError, TimeoutError:
                if retries >= max_retries:
                    raise
                await self.sleep(wambatic.fetch.ratelimit.backoff_delay(retries, self.rng))
                retries += 1
                continue
            self.update_limits(endpoint, response)
            status = response.status
            if status == 401:
                raise wambatic.fetch.errors.AuthError('GitHub rejected the token (401)')
            kind = self.limit_kind(endpoint, response)
            minimum = wambatic.fetch.ratelimit.SECONDARY_WAIT
            if kind == 'primary':
                state = self.limits[endpoint]
                if state.reset_at is not None and state.exhausted(self.clock()):
                    await self.wait_for_reset(endpoint, state.reset_at)
                    continue
                kind = 'secondary'
            elif kind == 'retry-after':
                minimum = self.retry_after(response)
            if kind is not None:
                wait = max(minimum, wambatic.fetch.ratelimit.backoff_delay(retries, self.rng))
                if retries >= max_retries:
                    raise wambatic.fetch.errors.RateLimitError(
                        self.clock() + datetime.timedelta(seconds=wait)
                    )
                await self.sleep(wait)
                retries += 1
                continue
            if status == 403:
                scopes = response.headers.get('x-accepted-oauth-scopes')
                raise wambatic.fetch.errors.AuthError(
                    'GitHub denied access (403)'
                    + (f'; the endpoint accepts scopes: {scopes}' if scopes else '')
                )
            if status == 404:
                raise wambatic.fetch.errors.NotFoundError(f'{path} not found or not visible')
            if status in TRANSIENT_STATUSES:
                if retries >= max_retries:
                    raise self.status_error(response)
                await self.sleep(wambatic.fetch.ratelimit.backoff_delay(retries, self.rng))
                retries += 1
                continue
            if 200 <= status < 300 or status == 304:
                return response
            raise self.status_error(response)

    def status_error(self, response: Response) -> aiohttp.ClientResponseError:
        return aiohttp.ClientResponseError(
            response.request_info, (), status=response.status, headers=None
        )
