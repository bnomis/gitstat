# wambatic

Statistics from github.com for a user, an organisation or a single repository, as a report in your terminal or as JSON.

wambatic reads the default-branch history from GitHub's GraphQL and REST APIs, keeps it in a local SQLite cache, and reports commits, contributors, active days and lines added, deleted and net, by year, month, week or day. Only the changes since the last run are fetched, so a repeat run is fast and a report from a warm cache works offline.

## Install

You need Python 3.14 and [uv](https://docs.astral.sh/uv/).

```shell
git clone https://github.com/bnomis/wambatic
cd wambatic
uv sync
source bin/activate.sh
wambatic --help
```

`wambatic --help` lists the `report` and `cache` commands. `python -m wambatic` runs the same program.

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
- Trends: a sparkline for each metric, cropped to the width of your terminal;
- By repository (for a user or organisation) and By author (with `--by-author`);
- Top contributors, with only the first rows shown (the JSON output has every row);
- Unavailable: metrics that are not built yet, with the reason;
- where the data came from: when it was computed, when each resource was last fetched, and the wambatic and cache schema versions.

Nothing in the output depends on colour: net lines carry an explicit sign, and partial periods carry a mark.

## Common workflows

```shell
# Report from the cache only: no network, no token
wambatic report repo:octocat/Hello-World --no-fetch

# Sync only if the cache is more than a day old
wambatic report org:github --max-age 1d

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
| `--format terminal\|json` | `report.format` | The output format; `html` is not built yet |
| `--by year\|month\|week\|day\|total` | `month` | The period to bucket by; weeks are ISO weeks starting on Monday |
| `--since YYYY-MM-DD` | the first commit | First day, inclusive, in the report time zone |
| `--until YYYY-MM-DD` | today | Last day, inclusive, in the report time zone |
| `--groups NAMES` | `activity,flow` | Comma-separated metric groups: `activity`, `delivery`, `flow`. Only `activity` is built, so the others are listed as unavailable |
| `--by-author` | off | Break activity down by author; not for a user target |
| `--tz ZONE` | `stats.timezone` | An [IANA time zone](https://www.iana.org/time-zones) such as `Europe/Berlin` |
| `--full-refresh` | off | Read all history again and ignore `--max-age`; cannot be used with `--no-fetch` |
| `--no-fetch` | off | Use the cache only, with no network and no token |
| `--max-age DURATION` | `fetch.max_age` | Skip the network when every resource was synced more recently, for example `30m` or `1d` |
| `--ignore-cache-version` | off | Read a cache written by a different wambatic or schema version, and say so in the report |

Without `--no-fetch` and `--max-age`, every run syncs first, because `fetch.max_age` defaults to zero. A sync of a repository that has not changed costs one request.

Dates must be written `YYYY-MM-DD`; other ISO forms are rejected. Merge commits count as commits but add no lines.

## The cache

The cache is derived data kept at `fetch.cache_path`, by default `~/.cache/wambatic/cache.sqlite3`. It records the schema version, the wambatic version and a hash of each query, and wambatic refuses a cache written by a different version rather than mix results.

```shell
wambatic cache info
wambatic cache clear
```

`cache info` prints the path, the size, the recorded identity, every key that differs from this wambatic (with both values), the number of repositories and commits and when the cache was last synced. It reads the file without changing it, so it works on a cache that `report` refuses. `cache clear` deletes the cache and its `-wal` and `-shm` files without asking; the next report fetches again.

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
| `report.allow_remote` | `false` | For the web app, which is not built yet |
| `report.format` | `terminal` | The default output format: `terminal` or `json` (`html` is not built yet) |
| `report.html_theme` | `auto` | For the HTML report, which is not built yet |
| `report.out_dir` | `./wambatic-reports` | For the HTML report, which is not built yet |
| `report.web_host` | `127.0.0.1` | For the web app, which is not built yet |
| `report.web_port` | `8000` | For the web app, which is not built yet |
| `stats.bot_logins` | `["dependabot[bot]", "renovate[bot]"]` | Authors left out of contributor counts and the top-contributors table |
| `stats.deploy_workflow` | none | For the delivery group, which is not built yet |
| `stats.exclude_merge_commits` | `true` | Leave merge commits out of line counts |
| `stats.failure_window` | `7d` | For the delivery group, which is not built yet |
| `stats.hotfix_labels` | `["hotfix"]` | For the flow group, which is not built yet |
| `stats.timezone` | `UTC` | The zone used when `--tz` is absent; an unknown zone is an error |

## Exit statuses

| Status | Meaning |
|--------|---------|
| 0 | Success, and `--help` |
| 1 | A GitHub or cache error (no token, a missing user or repository, the rate limit, a cache from another version), a report error (nothing to report, an unknown group, a range that ends before it starts), or an unexpected error, which is logged with its traceback |
| 2 | A command line that cannot be run: an unknown option, a malformed target or date, a clash such as `--full-refresh` with `--no-fetch`, or a bad config file or setting |
| 130 | Interrupted with Ctrl-C |

Each failure prints one line to stderr that says what to do, such as setting `GITHUB_TOKEN` or running `wambatic cache clear`. Reports go to stdout and logs to stderr, so `--format json` can be piped; if the reader of a pipe goes away (`| head`), wambatic ends quietly with status 1.

## Limits

- Only the default branch's history is read.
- Line counts are not filtered for generated files.
- A report uses one time zone.
- GitHub Enterprise Server is not supported.
- The flow and delivery groups, the HTML report (`--format html`) and the local web app (`serve`) are not built yet.

## More

The design is in [the system spec](agents/specs/system/spec.md), [fetch and cache](agents/specs/fetch-and-cache/spec.md), [stats](agents/specs/stats/spec.md) and [reports](agents/specs/reports/spec.md); the order of work is in [the implementation order](agents/specs/implementation-order.md). Contributor and agent rules are in [AGENTS.md](AGENTS.md).
