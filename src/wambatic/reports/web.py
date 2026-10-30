"""The local web app: the report page and the JSON of a result for any target, with the syncs
a large target needs run as jobs, so no request waits for a sync."""

import asyncio
import collections.abc
import dataclasses
import secrets
import typing

import loguru

import wambatic.fetch.base
import wambatic.fetch.errors
import wambatic.reports.errors
import wambatic.reports.service
import wambatic.settings
import wambatic.stats

JobKey = tuple[str, frozenset[str]]
INTERNAL_ERROR = 'internal error; see the server log'
BAD_REQUEST = (
    wambatic.reports.errors.UsageError,
    wambatic.settings.SettingsError,
    wambatic.stats.UnknownGroupError,
    wambatic.stats.InvalidRangeError,
    wambatic.stats.InvalidRequestError,
)
NOT_FOUND = (wambatic.fetch.errors.NotFoundError, wambatic.stats.EmptySubjectError)


class JobError(Exception):
    """A failed job's error, raised again for the request that reports it."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


def error_status(error: BaseException) -> int:
    """The HTTP status an error maps to (reports spec, Error handling)."""
    if isinstance(error, JobError):
        return error.status
    if isinstance(error, BAD_REQUEST):
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
        loguru.logger.exception(f'Unexpected error: {error}')
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
        except Exception as e:
            job.status, job.error = error_response(e)
            job.phase = 'failed'

    async def close(self) -> None:
        """Cancel the running and queued jobs and wait for them to end."""
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
