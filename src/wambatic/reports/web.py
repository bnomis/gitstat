"""The local web app: the report page and the JSON of a result for any target, with the syncs
a large target needs run as jobs, so no request waits for a sync."""

import asyncio
import collections.abc
import contextlib
import dataclasses
import datetime
import ipaddress
import secrets
import socket
import string
import time
import typing
import urllib.parse

import fastapi
import fastapi.exceptions
import fastapi.responses
import loguru
import uvicorn

import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.fetch.errors
import wambatic.fetch.ratelimit
import wambatic.reports.base
import wambatic.reports.errors
import wambatic.reports.html
import wambatic.reports.service
import wambatic.settings
import wambatic.stats
import wambatic.stats.base
import wambatic.version

JobKey = tuple[str, frozenset[str]]
INTERNAL_ERROR = 'internal error; see the server log'
BAD_REQUEST = (
    wambatic.settings.SettingsError,
    wambatic.stats.UnknownGroupError,
    wambatic.stats.InvalidRangeError,
    wambatic.stats.InvalidRequestError,
)
NOT_FOUND = (wambatic.fetch.errors.NotFoundError, wambatic.stats.EmptySubjectError)
LOOPBACK_HOSTS = ('localhost', '127.0.0.1', '[::1]')
PAGE_PATHS = frozenset({'/', '/report'})
TRUE_VALUES = frozenset({'1', 'on', 'true'})


class JobError(Exception):
    """A failed job's error, raised again for the request that reports it."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def error_status(error: BaseException) -> int:
    """The HTTP status an error maps to (reports spec, Error handling)."""
    if isinstance(error, JobError):
        return error.status
    if isinstance(error, (wambatic.reports.errors.UsageError, *BAD_REQUEST)):
        return 400
    if isinstance(error, NOT_FOUND):
        return 404
    if isinstance(error, wambatic.fetch.errors.FetchError):
        return 502
    return 500


def error_response(error: BaseException) -> tuple[int, str]:
    """The status and the message a response may show: redacted, and for an unexpected error
    only a pointer to the log, where its traceback is."""
    status = error_status(error)
    if status == 500:
        loguru.logger.exception(f'Unexpected error: {wambatic.reports.service.redact_error(error)}')
        return status, INTERNAL_ERROR
    return status, wambatic.reports.service.redact_environment_token(str(error))


@dataclasses.dataclass(slots=True)
class SyncJob:
    id: str
    key: JobKey
    phase: typing.Literal['queued', 'running', 'done', 'failed'] = 'queued'
    progress: wambatic.fetch.base.SyncProgress = dataclasses.field(
        default_factory=wambatic.fetch.base.SyncProgress
    )
    subject: wambatic.fetch.base.Subject | None = None
    error: str | None = None
    status: int | None = None

    @property
    def state(self) -> typing.Literal['queued', 'listing', 'syncing', 'done', 'failed']:
        """`listing` until the fetcher has read the repository listing, then `syncing`."""
        if self.phase == 'running':
            return 'listing' if self.progress.repos_listed is None else 'syncing'
        return self.phase


class Jobs:
    """Each key's latest job; one job syncs at a time, the others wait as `queued`."""

    def __init__(self) -> None:
        self.latest: dict[JobKey, SyncJob] = {}
        self.by_id: dict[str, SyncJob] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self.lock = asyncio.Lock()

    def start(
        self, key: JobKey, run: collections.abc.Callable[[SyncJob], collections.abc.Awaitable[None]]
    ) -> SyncJob:
        """The key's running or queued job, else a new one running `run`."""
        current = self.latest.get(key)
        if current is not None and current.phase in ('queued', 'running'):
            return current
        if current is not None:
            del self.by_id[current.id]
        job = SyncJob(secrets.token_hex(8), key)
        self.latest[key] = job
        self.by_id[job.id] = job
        task = asyncio.get_running_loop().create_task(self.execute(job, run))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    def get(self, job_id: str) -> SyncJob | None:
        return self.by_id.get(job_id)

    def forget(self, job: SyncJob) -> None:
        """Drop `job` unless a newer job has replaced it."""
        if self.latest.get(job.key) is job:
            del self.latest[job.key]
            del self.by_id[job.id]

    async def execute(
        self,
        job: SyncJob,
        run: collections.abc.Callable[[SyncJob], collections.abc.Awaitable[None]],
    ) -> None:
        try:
            async with self.lock:
                job.phase = 'running'
                await run(job)
            job.phase = 'done'
        except Exception as e:  # noqa: BLE001 - logged by error_response()
            job.status, job.error = error_response(e)
            job.phase = 'failed'

    async def close(self) -> None:
        """Cancel the running and queued jobs and wait for them to end."""
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


Target = typing.Annotated[
    str | None,
    fastapi.Query(description='user:NAME, org:NAME, repo:OWNER/NAME, OWNER/NAME or a bare NAME'),
]
By = typing.Annotated[
    str | None,
    fastapi.Query(description='year, month, week, day or total (default month)'),
]
Since = typing.Annotated[
    str | None, fastapi.Query(description='First day, YYYY-MM-DD (default: first commit)')
]
Until = typing.Annotated[
    str | None, fastapi.Query(description='Last day, YYYY-MM-DD (default: today)')
]
Groups = typing.Annotated[
    str | None,
    fastapi.Query(
        description=(
            'Comma-separated metric groups: activity, flow, delivery, popularity '
            '(default: activity,flow)'
        )
    ),
]
ByAuthor = typing.Annotated[
    str | None,
    fastapi.Query(description='1, true or on to break activity down by author'),
]
Tz = typing.Annotated[str | None, fastapi.Query(description='Time zone (default: stats.timezone)')]
JobId = typing.Annotated[
    str | None,
    fastapi.Query(description='The job a 202 answer named, to read the result once it is done'),
]


@dataclasses.dataclass(frozen=True, slots=True)
class RawQuery:
    """The query parameters of a data request, as the client sent them."""

    target: str | None
    by: str | None
    since: str | None
    until: str | None
    groups: str | None
    by_author: str | None
    tz: str | None
    job: str | None


def raw_query(
    target: Target = None,
    by: By = None,
    since: Since = None,
    until: Until = None,
    groups: Groups = None,
    by_author: ByAuthor = None,
    tz: Tz = None,
    job: JobId = None,
) -> RawQuery:
    return RawQuery(target, by, since, until, groups, by_author, tz, job)


@dataclasses.dataclass(frozen=True, slots=True)
class Query:
    """A data request after parsing: the target, the request and the key its sync job has."""

    target: wambatic.fetch.base.Subject | str
    request: wambatic.stats.base.StatsRequest
    by_author: bool
    key: JobKey
    job: str | None


def blank_to_none(value: str | None) -> str | None:
    """A form submits an empty field as an empty value, which means the field was left out."""
    return value.strip() or None if value is not None else None


def parse_query(settings: wambatic.settings.Settings, raw: RawQuery, *, page: bool) -> Query:
    """The CLI's parsers applied to the parameters, so a value the CLI rejects is rejected with
    the same message."""
    text = (blank_to_none(raw.target) or '').strip()
    if not text:
        raise wambatic.reports.errors.UsageError(
            f'target is required: {wambatic.reports.service.TARGET_FORMS}'
        )
    target = wambatic.reports.service.parse_target(text)
    by = blank_to_none(raw.by) or 'month'
    if page and by == 'total':
        raise wambatic.reports.errors.UsageError(
            'by=total is not for the report page: the page shows the totals as tiles and '
            'switches between year, month, week and day'
        )
    by_author = (raw.by_author or '').lower() in TRUE_VALUES
    if by_author and not isinstance(target, str):
        wambatic.reports.service.check_by_author(target)
    tz = blank_to_none(raw.tz)
    effective = (
        settings
        if tz is None
        else dataclasses.replace(settings, stats=dataclasses.replace(settings.stats, timezone=tz))
    )
    request = wambatic.reports.service.make_request(
        by,
        blank_to_none(raw.since),
        blank_to_none(raw.until),
        blank_to_none(raw.groups),
        by_author,
        wambatic.reports.service.resolve_tz(effective),
        effective,
    )
    resources = wambatic.stats.resources_for(request.groups) & wambatic.fetch.base.BUILT_RESOURCES
    return Query(target, request, by_author, (text, resources), blank_to_none(raw.job))


CallNext = collections.abc.Callable[[fastapi.Request], collections.abc.Awaitable[fastapi.Response]]


def progress_json(job: SyncJob) -> dict[str, object]:
    progress = job.progress
    rows = None if progress.repos_listed is None else sum(progress.rows_written.values())
    return {
        'job': job.id,
        'state': job.state,
        'repos_listed': progress.repos_listed,
        'repos_pending': progress.repos_pending,
        'repos_done': None if progress.repos_pending is None else progress.repos_done,
        'rows_written': rows,
        'error': job.error,
        'status': job.status,
    }


def reload_path(url: urllib.parse.SplitResult, job_id: str | None) -> str:
    """The path and query of `url` with its `job` parameter set to `job_id`, or removed."""
    pairs = [(k, v) for k, v in urllib.parse.parse_qsl(url.query) if k != 'job']
    if job_id is not None:
        pairs.append(('job', job_id))
    return urllib.parse.urlunsplit(('', '', url.path, urllib.parse.urlencode(pairs), ''))


def make_app(
    settings: wambatic.settings.Settings,
    cache: wambatic.fetch.cache.Cache,
    *,
    default_target: str | None = None,
    check_host: bool = True,
    clock: collections.abc.Callable[[], datetime.datetime] = wambatic.fetch.ratelimit.utc_now,
) -> fastapi.FastAPI:
    jobs = Jobs()
    theme = settings.report.html_theme

    def page(name: str, **values: str) -> str:
        return string.Template(wambatic.reports.html.read_template(name)).substitute(
            theme_attribute=wambatic.reports.html.theme_attribute(theme),
            style=wambatic.reports.html.stylesheet(),
            **values,
        )

    def error_reply(request: fastapi.Request, status: int, message: str) -> fastapi.Response:
        if request.url.path in PAGE_PATHS:
            body = page(
                'message.html',
                status=str(status),
                message=wambatic.reports.html.escape(message),
            )
            return fastapi.responses.HTMLResponse(body, status_code=status)
        return fastapi.responses.JSONResponse({'error': message}, status_code=status)

    async def stale(subject: wambatic.fetch.base.Subject, resources: frozenset[str]) -> bool:
        reader = wambatic.reports.service.make_fetcher('', cache, settings.fetch)
        provenance = await reader.provenance(subject, resources)
        return wambatic.reports.service.needs_sync(
            provenance, resources, settings.fetch, False, False, clock()
        )

    async def compute(
        subject: wambatic.fetch.base.Subject,
        query: Query,
        requests: list[wambatic.stats.base.StatsRequest],
    ) -> list[wambatic.stats.base.StatsResult]:
        _, results = await wambatic.reports.service.build_results(
            settings,
            cache,
            subject,
            requests,
            by_author=query.by_author,
            full_refresh=False,
            no_fetch=False,
            sync=False,
            clock=clock,
        )
        return results

    def start_job(query: Query) -> SyncJob:
        async def run(job: SyncJob) -> None:
            job.subject = await wambatic.reports.service.sync_target(
                settings,
                cache,
                query.target,
                query.request.groups,
                by_author=query.by_author,
                full_refresh=False,
                no_fetch=False,
                sync=True,
                progress=job.progress,
                clock=clock,
            )

        return jobs.start(query.key, run)

    async def results_or_job(
        query: Query, requests: list[wambatic.stats.base.StatsRequest]
    ) -> list[wambatic.stats.base.StatsResult] | SyncJob:
        """The results at once when the cache is fresh or the request names its finished job;
        else the job that brings the cache up to date."""
        job = jobs.get(query.job) if query.job is not None else None
        if job is not None and job.key == query.key:
            if job.phase == 'failed':
                jobs.forget(job)
                raise JobError(job.error or INTERNAL_ERROR, job.status or 500)
            if job.phase == 'done' and job.subject is not None:
                return await compute(job.subject, query, requests)
            if job.phase != 'done':
                return job
        if not isinstance(query.target, str) and not await stale(query.target, query.key[1]):
            return await compute(query.target, query, requests)
        return start_job(query)

    @contextlib.asynccontextmanager
    async def lifespan(app: fastapi.FastAPI) -> collections.abc.AsyncIterator[None]:
        yield
        await jobs.close()

    app = fastapi.FastAPI(
        title='wambatic', version=wambatic.version.VERSION, lifespan=lifespan, redoc_url=None
    )

    @app.middleware('http')
    async def convert_errors(
        request: fastapi.Request,
        call_next: CallNext,
    ) -> fastapi.Response:
        try:
            return await call_next(request)
        except Exception as e:  # noqa: BLE001 - logged by error_response()
            return error_reply(request, *error_response(e))

    @app.middleware('http')
    async def check_host_header(
        request: fastapi.Request,
        call_next: CallNext,
    ) -> fastapi.Response:
        if check_host:
            server = request.scope.get('server')
            port = server[1] if server else None
            suffix = '' if port is None else f':{port}'
            if request.headers.get('host') not in {f'{name}{suffix}' for name in LOOPBACK_HOSTS}:
                return fastapi.responses.JSONResponse(
                    {'error': 'unexpected Host header'}, status_code=403
                )
        return await call_next(request)

    @app.middleware('http')
    async def log_requests(
        request: fastapi.Request,
        call_next: CallNext,
    ) -> fastapi.Response:
        started = time.monotonic()
        response = await call_next(request)
        milliseconds = (time.monotonic() - started) * 1000
        loguru.logger.debug(
            f'{request.method} {request.url.path} {response.status_code} {milliseconds:.0f} ms'
        )
        return response

    @app.exception_handler(fastapi.exceptions.RequestValidationError)
    async def invalid_request(
        request: fastapi.Request, error: fastapi.exceptions.RequestValidationError
    ) -> fastapi.Response:
        message = '; '.join(
            f'{".".join(str(part) for part in item["loc"])}: {item["msg"]}'
            for item in error.errors()
        )
        return error_reply(request, 400, message)

    @app.get('/', include_in_schema=False)
    async def form() -> fastapi.responses.HTMLResponse:
        target = wambatic.reports.html.escape(default_target or '')
        return fastapi.responses.HTMLResponse(page('form.html', target=target))

    @app.get('/report', include_in_schema=False)
    async def report(
        request: fastapi.Request, raw: typing.Annotated[RawQuery, fastapi.Depends(raw_query)]
    ) -> fastapi.responses.HTMLResponse:
        query = parse_query(settings, raw, page=True)
        outcome = await results_or_job(query, wambatic.reports.html.period_requests(query.request))
        if isinstance(outcome, SyncJob):
            reload = reload_path(request.url.components, outcome.id)
            data = {
                'job': outcome.id,
                'progress': f'/api/progress?job={outcome.id}',
                'reload': reload,
            }
            body = page(
                'progress.html',
                target=wambatic.reports.html.escape(query.key[0]),
                retry=wambatic.reports.html.escape(reload_path(request.url.components, None)),
                data=wambatic.reports.html.json_for_script(data),
                script=wambatic.reports.html.read_template('progress.js'),
            )
            return fastapi.responses.HTMLResponse(body, status_code=202)
        document = await asyncio.to_thread(
            wambatic.reports.html.html_document,
            wambatic.reports.html.html_report(outcome, query.request.granularity),
            theme,
        )
        return fastapi.responses.HTMLResponse(document)

    @app.get('/api/stats')
    async def stats(
        raw: typing.Annotated[RawQuery, fastapi.Depends(raw_query)],
    ) -> fastapi.responses.JSONResponse:
        """The result as `report --format json` prints it, or 202 and a job to follow."""
        query = parse_query(settings, raw, page=False)
        outcome = await results_or_job(query, [query.request])
        if isinstance(outcome, SyncJob):
            return fastapi.responses.JSONResponse(
                {'job': outcome.id, 'progress': f'/api/progress?job={outcome.id}'},
                status_code=202,
            )
        return fastapi.responses.JSONResponse(wambatic.reports.base.result_to_dict(outcome[0]))

    @app.get('/api/progress')
    async def progress(job: JobId = None) -> fastapi.responses.JSONResponse:
        """How a sync job is going."""
        found = jobs.get(job) if job else None
        if found is None:
            return fastapi.responses.JSONResponse({'error': 'no such job'}, status_code=404)
        return fastapi.responses.JSONResponse(progress_json(found))

    return app


def is_loopback(host: str) -> bool:
    """Exactly `localhost`, or an IP address (IPv6 in brackets or not) that is loopback; no name
    is resolved."""
    if host == 'localhost':
        return True
    try:
        return ipaddress.ip_address(host.strip('[]')).is_loopback
    except ValueError:
        return False


def check_bind(host: str, allow_remote: bool) -> None:
    """Refuse a host that other machines can reach unless remote access was asked for."""
    if is_loopback(host):
        return
    if not allow_remote:
        raise wambatic.reports.errors.UsageError(
            f'{host} is not a loopback address, so anyone who can reach it would act with your '
            'GitHub token; pass --allow-remote (or set report.allow_remote) to allow that'
        )
    loguru.logger.warning(
        f'Listening on {host}: anyone who can reach this port acts with your GitHub token'
    )


def listen(host: str, port: int) -> socket.socket:
    """The listening socket, bound here rather than by uvicorn, which logs a bind failure and
    exits the process itself."""
    bare = host.strip('[]')
    family = socket.AF_INET6 if ':' in bare else socket.AF_INET
    try:
        return socket.create_server((bare, port), family=family)
    except OSError as e:
        raise wambatic.reports.errors.ServeError(
            f'cannot listen on {host}:{port}: {e.strerror or e}'
        ) from e


def serve(
    settings: wambatic.settings.Settings, *, default_target: str | None, ignore_cache_version: bool
) -> None:
    """Open the cache, bind `report.web_host:report.web_port`, then run the app on uvicorn until
    Ctrl-C, which ends in the KeyboardInterrupt uvicorn raises again after a graceful stop."""
    report = settings.report
    check_bind(report.web_host, report.allow_remote)
    if not 1 <= report.web_port <= 65535:
        raise wambatic.reports.errors.UsageError('the port must be from 1 to 65535')
    if default_target is not None:
        wambatic.reports.service.parse_target(default_target)
    cache = wambatic.fetch.cache.Cache.open(
        settings.fetch.cache_path, ignore_version=ignore_cache_version
    )
    sock: socket.socket | None = None
    try:
        sock = listen(report.web_host, report.web_port)
        app = make_app(
            settings, cache, default_target=default_target, check_host=not report.allow_remote
        )
        shown = f'[{report.web_host}]' if ':' in report.web_host else report.web_host
        base = f'http://{shown}:{sock.getsockname()[1]}'
        loguru.logger.info(f'Serving on {base}/ (Ctrl-C to stop)')
        if default_target is not None:
            quoted = urllib.parse.quote(default_target, safe='')
            loguru.logger.info(f'Report of {default_target}: {base}/report?target={quoted}')
        config = uvicorn.Config(
            app,
            loop='asyncio',
            lifespan='on',
            log_config=None,
            access_log=False,
            log_level='warning',
        )
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        if sock is not None:
            sock.close()
        cache.close()
