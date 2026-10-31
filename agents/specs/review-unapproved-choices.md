# Review: unapproved choices from implementation steps 1 to 9

**Date:** 2026-10-31
**Checked against:** `main` at `79b7840`
**Review page:** https://claude.ai/artifact/WUq1DQtuKGZoNnfgwAraXH (approve or flag each item there; answers are copied into Answers below)

## What is being reviewed and how

Each planning step wrote a review report listing the choices it made on the specs' own logic. Steps 9 and 10 had theirs approved on review pages (reports review 3, stats review 4), and step 3's two decisions were answered on decision cards. The rest were built without an explicit answer: the choices in fetch-and-cache review 1 (recorded only as "none flagged; PR #10 was merged"), stats reviews 1 to 3 and reports reviews 1 and 2, plus the decision cards of stats review 2 and reports review 2, which were never answered. Steps 1 and 2 had no review reports. This document collects those items, checks each against `main`, and says what changed since. Approve each choice or flag it with what to change; pick an option for each decision. A flag becomes a fix (spec paragraph, code and tests) in a follow-up PR.

## Automatic checks

- Every numbered choice and decision in the six source reviews is on the page: 92 choices and 2 decisions, counted from the source files (pass).
- Each item was checked against `main` by reading the code it names (`fetch/base.py`, `fetch/cache.py`, `stats/*.py`, `reports/*.py`, `cli.py`, `pyproject.toml`, the CI workflow and the fixtures). 20 items have changed or been superseded since; they say so under "On main now". The rest are built as written.
- The review page script passed `node --check` and a headless render against a stub database that refuses invalid document ids: all 92 items and 2 decisions render, and accept-all saved an answer for every unanswered item while keeping a flag and a non-recommended option already given (pass).

## The items

### Step 3: cache and incremental sync

Source: `agents/specs/fetch-and-cache/review-1.md`. Both decisions were answered on decision cards on 2026-10-29. The nine choices were recorded only as "none flagged; PR #10 was merged", so they are here for an explicit answer.

- **3.1 Merge commits are flagged.** `Commit` has `is_merge` (more than one parent), so line counts can leave merges out by default (`stats.exclude_merge_commits`).
- **3.2 Only `sync` reaches the network.** `repos()` and `commits()` read the cache, so a warm-cache report makes no requests.
- **3.3 New types: `Repo`, `SyncReport`, `RESOURCES`, `Cache` and `SyncState`.** Defined because 1.1 used them without defining them. A resource whose step was not built raised `NotImplementedError`. *On main now:* Every resource is built now: `BUILT_RESOURCES` equals `RESOURCES`, so nothing raises `NotImplementedError` any more.
- **3.4 The skip rule compares GitHub's values with GitHub's values.** A repo is skipped when its listed `pushedAt` and `updatedAt` equal the values stored in `sync_state` with its rows, instead of comparing server time with the local clock. An interrupted repo is never skipped.
- **3.5 `Fetcher` takes an optional `client`.** Tests inject a `GitHubClient` pointed at the replay server; production passes none.
- **3.6 Missing repos are left out of `repos()`.** A deleted or transferred repo keeps its cached rows but no longer counts in a report. Flag this if you want history from deleted repos kept in reports.
- **3.7 `--max-age` and `--no-fetch` belong to step 5.** Step 3 delivered `sync(..., full_refresh=True)`; the flags came with the CLI. *On main now:* Done: both flags shipped in step 5.
- **3.8 Fixtures may be hand-written when GraphQL is unreachable.** The cloud sandbox refused GraphQL, so fixtures were written from GitHub's documented shapes, to be re-recorded later. *On main now:* Superseded: on 2026-10-31 the successful responses were recorded from the live API into `src/tests/fixtures/fetch/recorded.py` by `bin/record-fixtures.sh` (PR #29, re-recorded after #33). Hand-written builders remain only for error responses and variations no recording holds.
- **3.9 Each step creates only the tables it uses.** Later steps add theirs with a `SCHEMA_VERSION` increase, which the identity check turns into a `CacheVersionError`. *On main now:* Followed since: `SCHEMA_VERSION` is 4 on main (steps 6, 8 and 10 each raised it).

### Step 4: activity stats

Source: `agents/specs/stats/review-1.md`. No decisions; eleven choices with an empty Answers section. Its open item (forks, watchers and languages) was settled by step 10, whose review you approved.

- **4.1 `compute` never syncs.** The front end calls `Fetcher.sync(subject, resources_for(groups))` and then `compute`, which reads the cache alone. This is what lets `--no-fetch` and `--max-age` work.
- **4.2 Unbuilt groups and metrics are listed as unavailable, not errors.** Each unbuilt group got a row in `tables['unavailable']` naming the step that builds it; a request whose groups are all unbuilt raises `EmptySubjectError`. *On main now:* Every group is built now, so the unavailable table only carries unconfigured DORA proxies and repositories whose stargazers the token cannot see.
- **4.3 `until` is inclusive; a missing bound comes from the data or the clock.** `--until 2026-10-31` includes the 31st. No `since` starts at the bucket of the earliest record; no `until` is today in the report timezone, so the current period is marked partial.
- **4.4 A range shorter than one bucket is valid.** `InvalidRangeError` only when `since` is after `until`; `--since 2026-10-01 --by year` gives one partial bucket.
- **4.5 `InvalidRequestError` and a `StatsError` base.** Stats raises `InvalidRequestError` for `by_author` on a user subject; every stats error subclasses `StatsError`, as fetch errors subclass `FetchError`.
- **4.6 Settings travel in the request.** `StatsRequest.settings` carries `stats.bot_logins` and `stats.exclude_merge_commits`, so the result records what it was computed with.
- **4.7 What each activity metric counts.** Merge commits are left out of line counts only, so `commits` includes them. Bots are left out of `contributors` and top contributors only, so their commits and lines count. Logins compare case-insensitively. Flag this if you want merges or bots out of commit counts too.
- **4.8 Breakdown series say what they break down by.** `Series.by_kind` is `author` or `repo`. Breakdowns carry `commits` as well as lines; per-repo for user and org subjects, per-author with `by_author`; a top-contributors table for every subject.
- **4.9 Provenance comes through `Fetcher`.** `Fetcher.provenance` gives the cache identity, any version override, `fetched_at:<resource>` (oldest sync over the subject's repos), `computed_at`, the timezone and the partial bucket labels.
- **4.10 `TOTAL` buckets and labels.** `bucket_for` raises `ValueError` for `TOTAL`; `bucket_range` returns one bucket labelled `total`. `bucket_range` and `partial_buckets` are public.
- **4.11 Module layout.** `compute` in its own `compute.py`, errors in `errors.py`, as in fetch. *On main now:* As built. One side effect: `wambatic.stats` re-exports the `compute` function, which shadows the `wambatic.stats.compute` submodule as a package attribute.

### Step 5: terminal report and CLI

Source: `agents/specs/reports/review-1.md`. No decisions; nineteen choices with an empty Answers section.

- **5.1 Unbuilt resources are never synced.** The CLI syncs `resources_for(groups) & BUILT_RESOURCES`; each step added its own resources to `BUILT_RESOURCES`. *On main now:* Every resource is built now (`BUILT_RESOURCES = RESOURCES`), so the intersection no longer removes anything.
- **5.2 A bare `NAME` is resolved with REST `GET /users/{login}`.** User and org logins share one namespace, so a name is never both; the REST `type` field says which. GraphQL would have changed the cache identity. With `--no-fetch` a bare name is a usage error asking for `user:` or `org:`.
- **5.3 `--max-age` is decided from `Fetcher.provenance`.** The sync is skipped when `fetch.max_age` is above zero and every `fetched_at` is younger than it; a subject never synced always syncs; `--full-refresh` overrides it.
- **5.4 No token is needed for a report that makes no requests.** With `--no-fetch` or a fresh `--max-age`, the `Fetcher` is never entered, so no `GITHUB_TOKEN` is needed.
- **5.5 The step 5 "Done when" names `--no-fetch` or `--max-age`.** `fetch.max_age` defaults to zero, so a plain report always syncs; the warm-cache check uses one of the flags.
- **5.6 `--format html`, `--out` and `serve` wait for their steps.** Step 5 built `report` and `cache` only. *On main now:* Superseded: `--format html` and `--out` shipped in step 7 and `serve` in step 9.
- **5.7 Flags that set a setting go through `load_settings`.** `--format`, `--max-age` and `--tz` override `report.format`, `fetch.max_age` and `stats.timezone`, so a bad value is a `SettingsError` (exit 2). An unknown zone names `stats.timezone`.
- **5.8 Strict target and date syntax.** Logins 1 to 39 of letters, digits and `-`; repo names 1 to 100 of letters, digits, `.`, `_` and `-`; dates exactly `YYYY-MM-DD` (not the extra forms `date.fromisoformat` accepts). Anything else is a usage error before any cache or network access.
- **5.9 `--ignore-cache-version` on `report`.** Opens the cache with `ignore_version=True`; provenance records it and the footer shows a warning.
- **5.10 `-v`, `-q` and a short log format.** Default `INFO`, `-q` `WARNING`, `-v` `DEBUG`. Lines read `ERROR: <message>` except at `DEBUG`. Logs go to stderr so `--format json` can be piped.
- **5.11 The exit status table.** `FetchError` and `StatsError` bases exit 1, cappa parse failures 2, and any other exception is logged with its traceback and exits 1.
- **5.12 `cache info` reads without opening.** `inspect_cache(path)` uses plain SELECTs with no schema, identity or pragma writes, so it can diagnose a `CacheVersionError`. A missing cache is reported, not created.
- **5.13 `cache clear` deletes without prompting.** Removes the file and its `-wal` and `-shm` files and logs each path. The cache is derived data, so a prompt would only get in the way of scripts.
- **5.14 The terminal layout is fixed.** Title, activity by period, trends, by repository and by author, top contributors, unavailable, provenance. Partial periods marked ` *`; a Total row; signed net lines so nothing relies on colour; the first 20 top contributors (JSON keeps all). *On main now:* Extended since by the flow, delivery and popularity tables in the same style.
- **5.15 A versioned JSON shape.** `points` as `{label, start, value}`, durations as `"<seconds>s"`, and `format_version: 1`. Step 9's `/api/stats` reuses it. *On main now:* Still `format_version` 1 on main: later steps only added groups and series, which an older reader can ignore.
- **5.16 `wambatic.cli` is the composition root.** `cli` may import every layer; `wambatic.reports` stays clear of `wambatic.fetch`. The layering test enforces both. *On main now:* Amended by step 9 (reports review 3, choice 2, approved): `reports.service` and `reports.web` may also import `wambatic.fetch`.
- **5.17 How the command is installed.** A `[project.scripts]` entry `wambatic = 'wambatic.cli:run'` and `__main__.py`, so `uv sync` puts `wambatic` on the path.
- **5.18 A README user guide.** `README.md` covers install, token, report, cache, config file and exit statuses; `pyproject.toml`'s `readme` stays `AGENTS.md`. *On main now:* The README has grown sections for HTML, the web app, flow, delivery and popularity. `readme` is still `AGENTS.md`, which matters if the package is ever published to PyPI.
- **5.19 The `Renderer` protocol waits for step 7.** With one renderer it had no caller. *On main now:* Superseded: step 7 dropped it (reports review 2, choice 14, below).

### Step 6: pull request and issue flow

Source: `agents/specs/stats/review-2.md`. The decision card was never answered, so the plan and the code follow the recommended option. Seventeen choices with an empty Answers section.

- **6.2 Records.** `PullRequest` gains `updated_at`; `Issue` has repo, number, author, created, updated and closed. `merged_at` is kept only for `MERGED`, `closed_at` only when not `OPEN`, so a reopened issue counts as open.
- **6.3 First review.** The earliest submitted review among the first 20, by anyone but the author and accounts of GraphQL type `Bot`, so automatic reviewers such as Copilot's and an author's own replies do not count. A deleted account's review counts. *On main now:* Confirmed by the live recordings (2026-10-30): the Copilot reviewer's author type is `Bot`.
- **6.4 Bot logins in REST form.** GraphQL gives a bot's login without `[bot]`; the fetch layer stores a `Bot` author as `<login>[bot]`, so one login means one account and matches `stats.bot_logins`. *On main now:* Confirmed by the live recordings: GraphQL bot logins lack `[bot]`.
- **6.5 The watermark is the `Date` header.** The first page's `Date` header is the server-side timestamp; a response without it raises `GraphQLError` rather than falling back to the local clock.
- **6.6 A full re-read replaces the repo's rows.** When `fetch.full_refresh_after` has passed or `--full-refresh` is given, the repo's rows are replaced in one transaction, so a deleted or transferred issue leaves the cache.
- **6.7 Reading filters on `updated_at`.** `pull_requests(repo, since)` and `issues(repo, since)` return rows with `updated_at >= since`, a superset of the items with an event in range; stats filters each metric by its own date.
- **6.8 Cache schema 2, no migration.** An older cache is refused once with the `CacheVersionError` message (`wambatic cache clear` or `--ignore-cache-version`). *On main now:* Same rule used at steps 8 and 10; schema is 4 now.
- **6.9 `cache info` and the sync log name the new resources.** `CacheInfo` gains pull request and issue counts; the log gives rows per resource. `SyncReport.full_refetches` stays commits-only, since a full read of pull requests is routine.
- **6.10 What each flow count counts.** `prs_opened` and `issues_opened` by creation, `prs_merged` by merge, `issues_closed` by close for issues closed now. A pull request closed unmerged counts in opened only. `time_to_close` is the issue's open-to-close time.
- **6.11 Series names and percentiles.** Each duration is `<name>_p50` and `_p90` in hours; p90 uses `statistics.quantiles(..., method='inclusive')`, which stays inside the values. PR size is `median_low` of merged pull requests, so it is one real integer size. Empty buckets have no value.
- **6.12 Bots are counted in flow.** As in activity, `stats.bot_logins` affects contributor counts only, so Dependabot's pull requests count in opened, merged and time to merge. Flag this if you want them out of flow; it is one filter.
- **6.13 A user subject counts the user's own pull requests and issues.** Only items the user authored, in the user's repositories, as with commits.
- **6.14 No flow breakdowns.** Total series only; per-repo and per-author breakdowns stay with activity and can be added later.
- **6.15 Range and empty results across groups.** No `since` starts at the earliest record of any requested group. `EmptySubjectError` only when no requested group has a record in range; a repo with pull requests but no commits in range shows activity as zeros.
- **6.16 Terminal layout for flow.** Flow by period (four counts, Total row) and Flow times by period (six percentiles in hours to one decimal, PR size, `-` for no data, no Total). Trends gain the four counts. `--groups flow` alone works.
- **6.17 No labels yet.** Pull request labels and first-commit times were left to step 8, which needed them. *On main now:* Done: step 8 added both.
- **6.18 One task list, in `agents/tasks/stats/`.** The list lives with the spec whose group it builds and carries the fetch and reports work it needs.

### Step 7: static HTML report

Source: `agents/specs/reports/review-2.md`. The decision card was never answered, so the plan and the code follow the recommended option. Fifteen choices with an empty Answers section.

- **7.2 The page is built from five results.** The CLI syncs once and runs `compute` five times (`TOTAL` plus year, month, week, day), because medians cannot be combined across buckets; five cache reads. *On main now:* The five-result build moved to `html.py` in step 9 (approved there).
- **7.3 `--by` picks the granularity shown on load.** `--by total` with HTML is a usage error, since the tiles already are the totals.
- **7.4 Where the file goes.** `--out` is a file or an existing directory; otherwise `report.out_dir / repo-OWNER-NAME.html` (or `user-`, `org-`). Parents created, atomic write through `os.replace`, the path printed to stdout. `--out` with another format is a usage error.
- **7.5 `Figure` is wambatic's own dataclass, with three builders.** `build_figures` for per-period charts, `build_range_figures` for whole-range bars, `build_calendar` for the day heat-map.
- **7.6 Only total series are embedded per granularity.** Per-repo series for a large org over years of days would make the file hundreds of MB; breakdowns come from the `TOTAL` result.
- **7.7 The switch swaps figures, it does not toggle traces.** `Plotly.react` with the chosen granularity's figure; tables are pre-rendered and toggled with `hidden`, so they work without script.
- **7.8 The charts.** One y-axis per chart; deleted lines below zero beside added above, net as a line; p50 and p90 lines with gaps for empty buckets; a calendar of ISO weeks by weekday.
- **7.9 Partial buckets.** Hatched bars, open markers on lines, and a caption, matching the terminal's ` *` without relying on colour.
- **7.10 The palette is written into the spec.** Copied from the dataviz skill's validated palette (read 2026-10-30): three categorical slots, a blue ramp for the heat-map, surfaces and inks. No chart has more than three series.
- **7.11 Themes are applied in the browser.** Figures carry slot numbers; the page script fills colours from the active theme. `auto` follows `prefers-color-scheme` and re-themes on change.
- **7.12 Data tables on the page, from code shared with the terminal.** The terminal's tables are the page's accessible data view; their rows live in `rows.py`, used by both renderers.
- **7.13 No templating library.** One template plus CSS and script files, filled with `string.Template`; every data string HTML-escaped, and `<`, `>`, `&` escaped in embedded JSON.
- **7.14 No `Renderer` protocol.** The HTML renderer takes five results and a path, so a `render(result)` protocol fits neither it nor the CLI; dropped from the spec.
- **7.15 The browser test uses Playwright for Python.** A `browser` pytest marker; Playwright's own Chromium, else `/opt/pw-browsers/chromium`, else skip. `check` leaves these out and a separate `browser` CI job runs them.
- **7.16 The README gains an HTML section.** Per the shared user-guides rule.

### Step 8: delivery stats

Source: `agents/specs/stats/review-3.md`. No decisions; twenty-one choices with an empty Answers section.

- **8.1 Stars, forks, watchers and languages move to a new step 10.** Their fetch resources were never specified, and step 8 with them was too big for one list. *On main now:* Done: step 10 was specified, approved (stats review 4) and built.
- **8.2 The delivery group reads pull requests, releases and workflow runs.** `resources_for('delivery')` is `{pull_requests, releases, workflow_runs}`. The default groups stay `activity,flow`; delivery is asked for with `--groups`.
- **8.3 Records.** `Release` keeps published releases only (drafts are visible only with push access, which would make the cache depend on whose token filled it). `WorkflowRun` keeps each run's latest attempt.
- **8.4 Pull request labels and first commit.** The first 20 labels and the first commit's `authoredDate`, so a rebase does not reset lead time; no commit falls back to `created_at`.
- **8.5 Releases are read in full when a listing probe changes.** Releases page only by creation time, so every read is full; the listing's release count and newest release `updatedAt` are the probe. An edit to an older release waits for the next full re-read (30 days by default).
- **8.6 Workflow runs: an unfiltered REST list with a free 304.** The `created` filter caps results at 1,000, so runs are listed unfiltered, newest first, through the ETag store. Unfinished cached runs are re-read by id; a 404 on the list reads as no runs.
- **8.7 All run history is fetched.** A repo with N runs costs about N/100 REST requests once; `fetch.on_rate_limit` `wait` rides out the limit. `--since` limits the report, not the fetch. Flag this if you want a setting that bounds the backfill.
- **8.8 Cache schema 3, no migration.** An older cache is refused once with the existing message. *On main now:* Schema is 4 now (step 10).
- **8.9 `cache info` names the new resources.** `CacheInfo` gains release and run counts.
- **8.10 Actions metrics.** Runs counted by `created_at`. Success rate is `success` over runs concluding `success`, `failure`, `timed_out` or `startup_failure`; cancelled, skipped and similar are left out. Duration p50/p90 is `updated_at - run_started_at` in minutes, a proxy.
- **8.11 Release metrics.** `release_count` by `published_at`, prereleases included. `release_interval_p50` is the `median_low` of whole days between consecutive releases of a repo, bucketed by the later one.
- **8.12 What a deployment is.** With `stats.deploy_workflow`, a successful run of that workflow (file name or name) when it finished; otherwise a non-prerelease release.
- **8.13 "Configured" means the inputs exist in the cache.** Deployments and lead time appear when the subject has a deployment; change failure rate and time to restore when it also has a hotfix pull request. Otherwise each is an unavailable row saying what is missing, so a repo that never labels hotfixes does not show a misleading 0%.
- **8.14 Lead time.** From a merged pull request's first commit to the repo's first deployment at or after the merge. Whether that deployment contains the merge is not checked, which is why it is a proxy.
- **8.15 Change failure rate and time to restore.** A deployment failed when a hotfix pull request was opened after it within `stats.failure_window`; time to restore is a hotfix pull request's open-to-merge time.
- **8.16 A user subject's delivery counts the whole repository.** Every release, run and pull request of the user's repos, because a release ships the whole repo's work.
- **8.17 No delivery breakdowns.** Total series only, like flow.
- **8.18 Reading the cache for delivery.** Releases whole, runs from a day before the range (all with `deploy_workflow`), pull requests whole and only when a proxy needs them. With only delivery, no `since` starts at the earliest release or run.
- **8.19 Terminal layout.** Delivery by period (runs, success %, duration p50/p90 in minutes, releases, interval p50 in days) and DORA proxies by period (only emitted proxies). Trends gain runs, releases and deployments.
- **8.20 HTML layout.** A Delivery section after Flow: tiles, per-period charts (ratios on a fixed 0 to 100% axis), the two tables, and a line saying the DORA figures are proxies explained in the README.
- **8.21 One task list, in `agents/tasks/stats/`.** As at step 6.

## Decisions

### Decision: how a sync tells that a repo's pull requests and issues are unchanged (agents/specs/stats/review-2.md)

**What is being decided:** Whether the repo listing probes each repo's newest pull request and issue update time, or every sync queries every repo.

**Background:** Since step 3 a repo whose listed `pushedAt` and `updatedAt` are unchanged is skipped. Nothing in GitHub's documentation says those move when an issue is opened or a pull request is reviewed, so that rule could skip repos whose pull requests and issues changed. Asked as a card on 2026-10-29; not answered.

**What it affects:** The rate-limit cost of every sync that includes `flow`, which the default report does.

**Options:**

- **A. Probe in the repo listing (built) (recommended).** The listing also reads each repo's newest pull request and issue `updatedAt`; a repo is skipped when that is before the stored watermark less `fetch.overlap`. About 2 points per 100 repos instead of 1. Nothing changes.
- **B. Always query every repo.** One pull request and one issue query per repo every sync, about 2 points per repo: an org of 500 repos spends about 1,000 of the 5,000 hourly points. Removing the probe fields means a code change and a cache schema increase.

**Recommendation:** A. Built that way and working: unchanged repos cost nothing beyond the listing, and the probe never skips a changed repo.

### Decision: how the HTML report uses Plotly, which ships no type information (agents/specs/reports/review-2.md)

**What is being decided:** Where the charts are built, given that `mypy --strict` rejects importing a package with no `py.typed` and no stubs.

**Background:** The reports spec has named Plotly since 1.0. Plotly 7.1.0 has no `py.typed` and no stub package (checked 2026-10-30), and the step 5 list said to ask before adding an `ignore_missing_imports` override. Asked as a card on 2026-10-30; not answered.

**What it affects:** `pyproject.toml` (an override or a stub package), how much of `figures.py` mypy checks, and the HTML tests.

**Options:**

- **A. Own JSON figures, plotly.js only (built) (recommended).** `figures.py` builds plain Plotly JSON in typed code; `html.py` imports `plotly` once for the bundled plotly.js, under an override for `plotly` only. Nothing changes.
- **B. `plotly.graph_objects` throughout.** Same override, but every figure call returns `Any`, so mypy checks nothing in the figure code. Means rewriting `figures.py` and its tests.
- **C. `plotly-stubs` as a dev dependency.** A young, partial third-party stub package (0.1.4, one maintainer) instead of the override; missing stubs surface as type errors to work around.
- **D. Vendor plotly.min.js, no `plotly` dependency.** A 4.8 MB file committed and updated by hand; no override, but tests lose Plotly's validators.

**Recommendation:** A. Built that way: the figure code is fully type-checked, the untyped import is one call in `html.py`, and tests still validate every figure with Plotly's own validators.

## Answers

(empty: your verdict on each choice and your option for each decision, with the date)
