# wambatic

Statistics from github.com for a user, an organisation or a single repository, as a report in your terminal, as one self-contained HTML page, as JSON or in a web app on your own machine.

wambatic reads the default-branch history, pull requests, issues, releases and GitHub Actions runs from GitHub's GraphQL and REST APIs, keeps them in a local SQLite cache, and reports commits, contributors, active days and lines added, deleted and net, together with how pull requests and issues flow (opened, merged, closed, and how long that takes) and how the project delivers (runs, releases and proxies for the DORA metrics), by year, month, week or day. Only the changes since the last run are fetched, so a repeat run is fast and a report from a warm cache works offline.

## Install

You need Python 3.14 and [uv](https://docs.astral.sh/uv/).

```shell
git clone https://github.com/bnomis/wambatic
cd wambatic
uv sync
source bin/activate.sh
wambatic --help
```

`wambatic --help` lists the `report`, `serve` and `cache` commands. `python -m wambatic` runs the same program.

## The token

wambatic reads a GitHub token from the `GITHUB_TOKEN` environment variable, and falls back to `gh auth token` when the [GitHub CLI](https://cli.github.com/) is signed in. A token with `public_repo` is enough for public repositories; use `repo` for private repositories and `read:org` for private organisation membership. The token is never written to the cache, the logs or a report, and a `GITHUB_TOKEN` that appears in an error message is replaced by `***`.

A report that makes no request (see `--no-fetch` and `--max-age` below) needs no token.

```shell
export GITHUB_TOKEN=<token from https://github.com/settings/tokens>
```

## A first report

```shell
wambatic report repo:octocat/Hello-World --by month
```

The first run reads the whole history of the repository and may take a while for a large one; later runs fetch only what is new. The report prints, in order:

- a title line with the subject, the date range, the period and the time zone;
- Activity by period: commits, contributors, active days, lines added, deleted and net for each period, with a `Total` row when there is more than one period. A period that the range cuts short ends in `*`, which the caption explains;
- Trends: a sparkline for each metric that has a value in every period (the activity metrics, the flow counts and the delivery counts), cropped to the width of your terminal;
- By repository (for a user or organisation) and By author (with `--by-author`);
- Top contributors, with only the first rows shown (the JSON output has every row);
- Flow by period: pull requests opened and merged and issues opened and closed for each period, with a `Total` row when there is more than one period;
- Flow times by period: the median and 90th percentile of review, merge and close times in hours, and the median size of merged pull requests, with `-` where a period has no data (see [Flow](#flow));
- with `--groups delivery`, Delivery by period (runs, success rate, run durations in minutes, releases and the release interval in days) and DORA proxies by period (see [Delivery](#delivery));
- Unavailable: metrics that are not built yet, or whose inputs are not in the cache, with the reason;
- where the data came from: when it was computed, when each resource was last fetched, and the wambatic and cache schema versions.

Nothing in the output depends on colour: net lines carry an explicit sign, and partial periods carry a mark.

## The HTML report

```shell
wambatic report org:github --format html
```

This writes one HTML file and prints its path on stdout, so a script can capture it (`open "$(wambatic report org:github --format html)"`). The page has summary tiles, a chart for each measure, the whole-range charts (top contributors, and by repository and by author), a calendar of commits by day, and the same tables as the terminal report. The tables are plain HTML, so they can be read, copied and searched even with script turned off.

- **Where the file goes.** `--out PATH` is a file, or an existing directory to write into. Without it the file goes in `report.out_dir`. The file is named `repo-OWNER-NAME.html`, `user-NAME.html` or `org-NAME.html`. Missing directories are created and an existing file is replaced. The write is atomic: a failed write leaves the earlier file as it was and no partial file. `--out` is an error with another format.
- **Switching period.** The page has a Year, Month, Week and Day switch and does not need the network or wambatic to change it. `--by` picks the period shown when the page opens (default month); `--by total` is an error, because the tiles already show the totals. A repeat report from the same cache makes one sync and writes one file.
- **Themes.** `report.html_theme` is `auto` (follow the viewer's light or dark setting, and change with it), `light` or `dark`. The charts use one colour set per theme and never rely on colour alone: a period the range cuts short is hatched in bar charts, drawn with open markers in line charts, and named in the chart's caption.
- **Offline and shareable.** The file holds its own copy of [plotly.js](https://plotly.com/javascript/) and makes no request, so it opens from disk and can be hosted or attached to an issue. It is megabytes in size for that reason.
- **Per-period charts** show the total series only. The breakdown by repository and by author is for the whole range.

## The web app

```shell
wambatic serve octocat
```

This starts a web app on your machine and logs the address, `http://127.0.0.1:8000/`, and the URL of the report for the target you gave. Open the printed address to get a form for any target; the target on the command line only fills the form in, and is optional. Submitting the form shows the same page as `report --format html`, on the same cache.

- **The progress page.** A report that needs a sync does not make the browser wait for it. The server answers at once with a progress page that shows the state (waiting, listing, syncing), how many repositories are done and how many rows were written, polls once a second, and loads the report when the sync is done. A large organisation can take minutes; the rest of the app stays responsive meanwhile. One sync runs at a time, so a second target waits its turn, and asking again for a target that is already syncing joins its sync. If a sync fails, the page shows the message and a link to try again.
- **How fresh is fresh.** The web app syncs on the same rule as `report`: `--max-age` (or `fetch.max_age`) says how recent a sync may be to skip the network. The default is zero, so every page you open syncs first, as a `report` does; for a server you leave running, `wambatic serve --max-age 1h` is usually what you want. A page you reach from the progress page does not sync a second time.
- **The JSON routes.** `/api/stats` takes the same parameters as the report (`target`, `by`, `since`, `until`, `groups`, `by_author`, `tz`) and returns what `report --format json` prints; `by=total` is allowed there, and `by_author` is `1`, `true` or `on`. When a sync is needed it answers 202 with a job to follow, and you ask again with `job=ID` once `/api/progress` says it is done:

  ```shell
  curl -s 'http://127.0.0.1:8000/api/stats?target=repo:octocat/Hello-World&by=week'
  # {"job": "9c1b...", "progress": "/api/progress?job=9c1b..."}
  curl -s 'http://127.0.0.1:8000/api/progress?job=9c1b...'
  # {"job": "9c1b...", "state": "syncing", "repos_listed": 1, "repos_pending": 1, "repos_done": 0, ...}
  curl -s 'http://127.0.0.1:8000/api/stats?target=repo:octocat/Hello-World&by=week&job=9c1b...'
  ```

  Errors are `{"error": "..."}` with status 400 for a bad parameter, 404 for a target that does not exist or has nothing in range, 502 for a GitHub error (for example no token) and 500 for anything unexpected, whose details are in the server's log. The report pages show the same errors as a short page.
- **The API page.** `/docs` is a generated page describing the JSON routes. It loads its script and style from jsDelivr, so unlike the other pages it needs a network connection.
- **Security.** The server uses the `GITHUB_TOKEN` of the environment it runs in, and never sends it to the browser. It listens on loopback only, and refuses any other address unless you pass `--allow-remote` (or set `report.allow_remote`), because anyone who can reach the port can then read whatever your token can read, private repositories included, and make wambatic spend your rate limit. On loopback it also answers 403 to a request whose `Host` header is not `localhost`, `127.0.0.1` or `[::1]` with the port the server listens on, which stops a web page on another site from reaching it through DNS rebinding. That check is off with `--allow-remote`, since the names the server is reached by are not known. The app sends no CORS headers, so other sites cannot read its answers.
- **Stopping.** Press Ctrl-C. A running sync is cancelled and resumes where it stopped on the next sync, and the exit status is 130.

## `wambatic serve` options

Global options come before the command, as for `report`.

| Option | Default | Meaning |
|--------|---------|---------|
| `TARGET` | none | Optional. Fills in the form and names the first report URL; a malformed target is an error before the server starts |
| `--host ADDRESS` | `report.web_host` | The address to listen on. Only `localhost` and loopback addresses are accepted without `--allow-remote`; no name is looked up, so use `127.0.0.1` or `::1` |
| `--port PORT` | `report.web_port` | The port, from 1 to 65535 |
| `--allow-remote` | `report.allow_remote` | Listen on an address other than loopback, and turn off the `Host` check; logs a warning |
| `--max-age DURATION` | `fetch.max_age` | As for `report` |
| `--ignore-cache-version` | off | As for `report` |

## Flow

The `flow` group counts pull requests and issues. Each event is placed in the period of its own date in the report time zone, so a pull request opened in one month and merged in the next is in `prs_opened` for the first and `prs_merged` for the second.

| Metric | What it is |
|--------|------------|
| `prs_opened` | Pull requests created in the period |
| `prs_merged` | Pull requests merged in the period; one closed without merging counts only in `prs_opened` |
| `issues_opened` | Issues created in the period |
| `issues_closed` | Issues closed in the period and still closed; a reopened issue is open |
| `time_to_first_review_p50`, `time_to_first_review_p90` | Hours from a pull request being opened to its first review, by the date of the review |
| `time_to_merge_p50`, `time_to_merge_p90` | Hours from a pull request being opened to being merged, by the date of the merge |
| `time_to_close_p50`, `time_to_close_p90` | Hours from an issue being opened to being closed, by the date of the close |
| `pr_size_p50` | The median of added plus deleted lines over the pull requests merged in the period |

`p50` is the median and `p90` the 90th percentile of the values in the period. A period with no value has no point for these (the terminal shows `-`), because a median of nothing is not zero. The review time leaves out reviews by the pull request's author and by bots, so an automatic reviewer does not make every review time a few minutes; a pull request with no other reviewer has no review time. Bots' own pull requests and issues are counted, because `stats.bot_logins` only affects contributor counts. For a user target, only the pull requests and issues the user opened count.

## Delivery

The `delivery` group counts GitHub Actions runs and releases, and derives proxies for the DORA metrics from them. Ask for it with `--groups delivery` (or `--groups activity,flow,delivery` for everything); it is not in the default groups because it reads every workflow run of every repository.

```shell
wambatic report repo:octocat/Hello-World --groups delivery
```

Each event is placed in the period of its own date in the report time zone, as in [Flow](#flow).

| Metric | What it is |
|--------|------------|
| `workflow_runs` | Workflow runs created in the period, whatever their state |
| `workflow_success_rate` | Of the completed runs created in the period whose conclusion is success, failure, timed out or startup failure, the share that succeeded; cancelled and skipped runs are not outcomes of the code and are left out. Shown as a percentage |
| `workflow_duration_p50`, `workflow_duration_p90` | Minutes from a completed run starting to its last update; an approximation, since GitHub does not report a run's end time |
| `release_count` | Releases published in the period, prereleases included, drafts left out |
| `release_interval_p50` | The median whole days since the repository's previous release, for the releases published in the period; a repository's first release has none |

`p50` and `p90` are as in Flow, and a period with no value shows `-`. Runs triggered by pull requests are counted like any other. The success rate and the durations have no point in a period without a completed run. For a user target, the runs and releases of the user's own repositories count, whoever made them.

### DORA proxies

[DORA's four keys](https://dora.dev/guides/dora-metrics-four-keys/) are deployment frequency, lead time for changes, change failure rate and time to restore service. GitHub records none of them, so wambatic estimates each from what it does record. They are proxies: use them to see a trend, not to compare teams.

| Metric | How it is measured |
|--------|--------------------|
| `deployments` | A deployment is a release that is not a prerelease, at the time it was published. With `stats.deploy_workflow` set it is instead a successful, completed run of that workflow, at the time the run finished. Deployments are counted for each repository |
| `lead_time_p50`, `lead_time_p90` | Hours from a merged pull request's first commit (its creation, when that is not known) to the first deployment of the same repository at or after the merge, in the period of the deployment. A pull request that no deployment has followed yet is not counted |
| `change_failure_rate` | Of the deployments in the period, the share followed, within `stats.failure_window`, by a pull request of the same repository that carries a label in `stats.hotfix_labels`. A deployment whose window is still open at the end of the range counts as not failed. Shown as a percentage |
| `time_to_restore_p50`, `time_to_restore_p90` | Hours from a hotfix pull request being opened to being merged, in the period of the merge |

Each proxy is shown only when what it needs is in the cache, and otherwise appears under Unavailable with the reason. `deployments` and the lead time need at least one deployment: a release, or a successful run of `stats.deploy_workflow`. The change failure rate also needs a pull request with a hotfix label, and the time to restore needs one. That is deliberate: a repository that never labels its hotfixes would otherwise show a change failure rate of 0%, which reads as good news and means nothing.

## Common workflows

```shell
# Report from the cache only: no network, no token
wambatic report repo:octocat/Hello-World --no-fetch

# Sync only if the cache is more than a day old
wambatic report org:github --max-age 1d

# A self-contained HTML page, opening on the week view, written to a file of your choice
wambatic report org:github --format html --by week --out reports/github.html

# How a repository ships: runs, releases and the DORA proxies
wambatic report repo:OWNER/NAME --groups delivery

# Machine-readable output, with logs kept on stderr
wambatic report org:github --format json | jq '.series[0].points'

# Who did the work in an organisation
wambatic report org:github --by-author --since 2026-01-01

# One bucket for the whole range, in another time zone
wambatic report user:octocat --by total --tz Europe/Berlin

# Read all the history again, for example after a force-push you suspect
wambatic report repo:octocat/Hello-World --full-refresh
```

## Targets

| Target | Meaning |
|--------|---------|
| `user:NAME` | The repositories owned by a user, counting only that user's own commits |
| `org:NAME` | The repositories owned by an organisation |
| `repo:OWNER/NAME` or `OWNER/NAME` | One repository |
| `NAME` | Asks GitHub whether `NAME` is a user or an organisation (one request, so not with `--no-fetch`) |

A `NAME` or `OWNER` is 1 to 39 letters, digits and `-`; a repository `NAME` is 1 to 100 letters, digits, `.`, `_` and `-`. Prefixes are lower case.

Forked and archived repositories are left out of a user or organisation unless `fetch.include_forks` or `fetch.include_archived` is set.

## `wambatic report` options

Global options come before the command: `wambatic -v report ...`.

| Option | Default | Meaning |
|--------|---------|---------|
| `-v`, `--verbose` | off | Log debugging detail, with time and source location |
| `-q`, `--quiet` | off | Log warnings and errors only; cannot be used with `-v` |
| `--format terminal\|html\|json` | `report.format` | The output format |
| `--out PATH` | `report.out_dir` | With `--format html`, the file to write, or an existing directory to write the report into; an error with another format |
| `--by year\|month\|week\|day\|total` | `month` | The period to bucket by; weeks are ISO weeks starting on Monday. With `--format html`, the period shown when the page opens, and `total` is an error |
| `--since YYYY-MM-DD` | the first commit | First day, inclusive, in the report time zone |
| `--until YYYY-MM-DD` | today | Last day, inclusive, in the report time zone |
| `--groups NAMES` | `activity,flow` | Comma-separated metric groups: `activity`, `delivery`, `flow`. `delivery` is off by default because it reads every workflow run, which costs requests (see [The cache](#the-cache)) |
| `--by-author` | off | Break activity down by author; not for a user target |
| `--tz ZONE` | `stats.timezone` | An [IANA time zone](https://www.iana.org/time-zones) such as `Europe/Berlin` |
| `--full-refresh` | off | Read all history again and ignore `--max-age`; cannot be used with `--no-fetch` |
| `--no-fetch` | off | Use the cache only, with no network and no token |
| `--max-age DURATION` | `fetch.max_age` | Skip the network when every resource was synced more recently, for example `30m` or `1d` |
| `--ignore-cache-version` | off | Read a cache written by a different wambatic or schema version, and say so in the report |

Without `--no-fetch` and `--max-age`, every run syncs first, because `fetch.max_age` defaults to zero. A sync costs the repository listing, and a repository with nothing new in the listing costs no request of its own.

Dates must be written `YYYY-MM-DD`; other ISO forms are rejected. Merge commits count as commits but add no lines.

## The cache

The cache is derived data kept at `fetch.cache_path`, by default `~/.cache/wambatic/cache.sqlite3`. It records the schema version, the wambatic version and a hash of each query, and wambatic refuses a cache written by a different version rather than mix results.

```shell
wambatic cache info
wambatic cache clear
```

`cache info` prints the path, the size, the recorded identity, every key that differs from this wambatic (with both values), the number of repositories, commits, pull requests, issues, releases and workflow runs and when the cache was last synced. It reads the file without changing it, so it works on a cache that `report` refuses. `cache clear` deletes the cache and its `-wal` and `-shm` files without asking; the next report fetches again.

A cache written by an earlier wambatic, before releases and workflow runs were kept, is refused once after you upgrade: the cache is derived data, so run `wambatic cache clear` and the next report fetches it again.

The first sync with `--groups delivery` reads every workflow run of each repository, newest first, about one request for each hundred runs, so a repository with a long Actions history costs many. Later syncs ask for the newest page with a conditional request, which GitHub answers for free when nothing has run since, and read further only when something has. Releases are read again only when a repository's release count or newest release has changed.

When `report` stops with "The cache was written by a different version", either run `wambatic cache clear` and let it fetch again, or pass `--ignore-cache-version` for one run. The override is recorded in the cache and shown as a warning in the report.

## The config file

Settings are layered, and a later layer wins: built-in defaults, then the JSON file `~/.config/wambatic/config.json`, then command line flags. Set `WAMBATIC_CONFIG` to use another file; a missing file named that way is an error, while a missing default file is not. The token is not a setting.

```json
{
  "fetch": {"workers": 8, "max_age": "1h"},
  "stats": {"timezone": "Europe/Berlin", "bot_logins": ["dependabot[bot]"]},
  "report": {"format": "json"}
}
```

A duration is a whole number and one unit, `s`, `m`, `h`, `d` or `w`, such as `"30d"`. A leading `~` in a path is expanded. An unknown key or a value of the wrong type is an error that names the key.

| Setting | Default | Meaning and trade-off |
|---------|---------|-----------------------|
| `fetch.cache_path` | `~/.cache/wambatic/cache.sqlite3` | Where the cache lives |
| `fetch.full_refresh_after` | `30d` | Age of the last full read after which a resource is read in full again to catch deletions; shorter is more accurate and costs more requests |
| `fetch.include_archived` | `false` | Include archived repositories of a user or organisation |
| `fetch.include_forks` | `false` | Include forks of a user or organisation |
| `fetch.max_age` | `0s` | Skip the network when the subject was synced more recently than this; zero always syncs |
| `fetch.max_retries` | `5` | Retries for transient and secondary-limit errors |
| `fetch.on_rate_limit` | `wait` | `wait` sleeps until the limit resets, `fail` stops with an error that gives the reset time |
| `fetch.overlap` | `1h` | Safety margin subtracted from the watermark so a late arrival is not missed |
| `fetch.stats_retries` | `6` | Retries while a REST statistics endpoint is still computing |
| `fetch.workers` | `4` | Repositories fetched at once; more is faster and closer to GitHub's secondary limits |
| `report.allow_remote` | `false` | Let `serve` listen on an address other than loopback; anyone who can reach the port then acts with your token |
| `report.format` | `terminal` | The default output format: `terminal`, `html` or `json` |
| `report.html_theme` | `auto` | The HTML report's colours: `auto` follows the viewer's system setting, `light` and `dark` are fixed |
| `report.out_dir` | `./wambatic-reports` | The directory the HTML report is written to when `--out` is absent |
| `report.web_host` | `127.0.0.1` | The address `serve` listens on |
| `report.web_port` | `8000` | The port `serve` listens on |
| `stats.bot_logins` | `["dependabot[bot]", "renovate[bot]"]` | Authors left out of contributor counts and the top-contributors table |
| `stats.deploy_workflow` | none | The workflow whose successful runs are the deployments, matched against a run's workflow file name (`deploy.yml`) or its name; unset, releases that are not prereleases are the deployments |
| `stats.exclude_merge_commits` | `true` | Leave merge commits out of line counts |
| `stats.failure_window` | `7d` | How long after a deployment a hotfix pull request marks it as failed |
| `stats.hotfix_labels` | `["hotfix"]` | Pull request labels that mark a failure fix, compared without regard to case |
| `stats.timezone` | `UTC` | The zone used when `--tz` is absent; an unknown zone is an error |

## Exit statuses

| Status | Meaning |
|--------|---------|
| 0 | Success, and `--help` |
| 1 | A GitHub or cache error (no token, a missing user or repository, the rate limit, a cache from another version), a report error (nothing to report, an unknown group, a range that ends before it starts), an HTML report that cannot be written to its path, a port that `serve` cannot listen on, or an unexpected error, which is logged with its traceback |
| 2 | A command line that cannot be run: an unknown option, a malformed target or date, a clash such as `--full-refresh` with `--no-fetch`, a bad config file or setting, or `serve` asked to listen on an address other than loopback without `--allow-remote` or on a port outside 1 to 65535 |
| 130 | Interrupted with Ctrl-C, including a stopped `serve` |

Each failure prints one line to stderr that says what to do, such as setting `GITHUB_TOKEN` or running `wambatic cache clear`. Reports go to stdout and logs to stderr, so `--format json` can be piped; if the reader of a pipe goes away (`| head`), wambatic ends quietly with status 1.

## Limits

- Only the default branch's history is read.
- A pull request's first review is found among its first reviews on GitHub; more than a few by the author or bots before the first other reviewer leaves it without a review time.
- Line counts are not filtered for generated files.
- A report uses one time zone.
- GitHub Enterprise Server is not supported.
- The DORA figures are proxies built on conventions that GitHub does not enforce (see [DORA proxies](#dora-proxies)).
- Stars, forks, watchers and languages are not built yet.

## More

The design is in [the system spec](agents/specs/system/spec.md), [fetch and cache](agents/specs/fetch-and-cache/spec.md), [stats](agents/specs/stats/spec.md) and [reports](agents/specs/reports/spec.md); the order of work is in [the implementation order](agents/specs/implementation-order.md). Contributor and agent rules are in [AGENTS.md](AGENTS.md).
