# Audit Review 1

**Date:** 2026-10-31
**Scope:** full (`agents/specs/`, `src/wambatic/`, `src/tests/`, `bin/`, `AGENTS.md`, `README.md`; there is no `docs/`)
**Script output:** `/tmp/audit-wambatic.jsonl` (570 hits, 0 accepted, 570 unaccepted)
**Script version:** `4d7de71faa4067b7b05e53afe41973ffdfdc298f80d249b86f5085cfd7bac365`
**Convergence note:** first audit of this project, so there is no earlier run to compare with. The checker was not changed during this audit.
**Review page:** https://claude.ai/artifact/Eb7chtX2Vkvnmj7YEdFbTG

## What is being reviewed and how

This is the first `/auditme` audit of wambatic, run against `main` at `e0a5e0f` on 2026-10-31. A script swept every Python file under `src/` and `bin/` for mechanical rule hits. Nine reviewers then applied every Phase B checklist question (architecture A1-A25, standards S1-S4, performance P1-P3, security Sec1-Sec5, testing T1-T3, dependencies D1-D3, documentation Doc1-Doc5), each question across every file, and checked the four specs against the code and against the specdev template. There were no earlier findings or audit task lists to re-verify. For each **item** (a finding group below), approve it for the task list or flag it with a comment. For each **decision**, pick an option. The approved findings then become a task list (`/taskdev`).

This checkout's `.agents` submodule is not initialised (`git submodule status` shows `-ec0d8ca`; the directory is empty). So `.claude/rules`, every `.claude/skills/*` link and the `@.agents/claude/CLAUDE.md` include in `AGENTS.md` point at nothing. The audit ran from the shared copy in `~/.claude/skills`, which is unaffected. Run `git submodule update --init` to repair the checkout (Doc1 below).

## Summary

The mechanical sweep found 570 unaccepted hits, about three quarters of them in `src/tests/`: `literal-duplication` 272 (254 in tests), `reexport-in-non-init` 72 (69 in tests), `non-alphabetical-literal` 50, `aliased-imports` 25 (all tests), `typing-deprecated-alias` 24, `missing-raises-section` 23, `non-alphabetical-dict-keys` 22, `layer-has-domain-error-raises-stdlib` 21, `mutable-module-level-exported` 17, and fewer than 15 for each of the other 14 rules. Phase B found hits on 31 of the 48 checklist questions. The most serious are an unredacted exception message in the web server's error log (Sec5), aiohttp and sqlite3 errors that reach the user as tracebacks instead of domain errors (A1/A2), an `OverflowError` that escapes settings validation (Sec2), and 17 places where a spec and the code disagree (Doc4).

## Automatic checks

| Check | Result |
|---|---|
| `requests.md` `## Open` empty at audit start | pass |
| `checks/audit.py` run, JSONL saved | pass: 570 hits |
| Every unaccepted hit listed below | pass: 570 of 570 (generated from the JSONL, not typed) |
| Every Phase B question run with per-question fan-out | pass: 48 questions, nine reviewers, no `--category` |
| Every reviewer returned a hit list or "no hits" | pass |
| Earlier `summary.md` findings re-verified | n/a: first audit |
| Incomplete audit task files re-verified | n/a: none exist |
| No check added to the checker during the audit | pass |
| No Phase B predicate widened during the audit | pass |
| `uv lock --check` | pass (10:36 UTC) |
| `ruff --select ANN` over `src` and `bin` | pass: no missing annotations |

## Mechanical findings (from checks/audit.py)

Every `accepted: false` hit is listed, grouped by rule, in the order the script emitted them.

### Rule: aliased-imports

- **Severity:** low
- **Instance count:** 25 (src/tests: 25)
- **Variants:** import X as Y (25)
- **Locations:**
  - `src/tests/fetch/test_base.py:6` - `import tests.fixtures.fetch.responses as responses`
  - `src/tests/fetch/test_client.py:11` - `import tests.fixtures.fetch.responses as responses`
  - `src/tests/fetch/test_client.py:12` - `import tests.fixtures.fetch.server as server_module`
  - `src/tests/reports/test_base.py:8` - `import hypothesis.strategies as st`
  - `src/tests/reports/test_base.py:11` - `import tests.fixtures.stats as fixture`
  - `src/tests/reports/test_figures.py:10` - `import tests.fixtures.stats as fixture`
  - `src/tests/reports/test_html.py:15` - `import tests.fixtures.stats as fixture`
  - `src/tests/reports/test_rows.py:6` - `import tests.fixtures.stats as fixture`
  - `src/tests/reports/test_service.py:7` - `import hypothesis.strategies as st`
  - `src/tests/reports/test_terminal.py:7` - `import hypothesis.strategies as st`
  - `src/tests/reports/test_terminal.py:13` - `import tests.fixtures.stats as fixture`
  - `src/tests/reports/test_web.py:16` - `import hypothesis.strategies as st`
  - `src/tests/stats/test_activity.py:6` - `import hypothesis.strategies as st`
  - `src/tests/stats/test_activity.py:9` - `import tests.fixtures.stats as fixture`
  - `src/tests/stats/test_buckets.py:5` - `import hypothesis.strategies as st`
  - `src/tests/stats/test_compute.py:9` - `import hypothesis.strategies as st`
  - `src/tests/stats/test_compute.py:12` - `import tests.fixtures.stats as fixture`
  - `src/tests/stats/test_delivery.py:6` - `import hypothesis.strategies as st`
  - `src/tests/stats/test_delivery.py:9` - `import tests.fixtures.stats as fixture`
  - `src/tests/stats/test_fixtures.py:5` - `import tests.fixtures.stats as fixture`
  - `src/tests/stats/test_flow.py:5` - `import hypothesis.strategies as st`
  - `src/tests/stats/test_flow.py:8` - `import tests.fixtures.stats as fixture`
  - `src/tests/stats/test_percentile.py:5` - `import hypothesis.strategies as st`
  - `src/tests/stats/test_popularity.py:5` - `import hypothesis.strategies as st`
  - `src/tests/stats/test_popularity.py:8` - `import tests.fixtures.stats as fixture`
- **Recommendation:** Replace `import X as Y` with the full import path (imports.md "No as imports"); mechanical.

### Rule: in-function-import

- **Severity:** low
- **Instance count:** 1 (src/tests: 1)
- **Variants:** third-party (1)
- **Locations:**
  - `src/tests/reports/test_html.py:197` - `import plotly.offline`
- **Recommendation:** Move `import plotly.offline` to the top of `test_html.py`, or accept with a scoped marker if the deferred import keeps plotly out of collection on purpose.

### Rule: except-interpolation

- **Severity:** low
- **Instance count:** 8 (src/tests: 2, src/wambatic: 6)
- **Variants:** f-string interpolates caught exception (8)
- **Locations:**
  - `src/tests/reports/conftest.py:21` - `pytest.skip(f'no Chromium can be launched: {str(first).splitlines()[0]}')`
  - `src/tests/reports/conftest.py:25` - `pytest.skip(f'no Chromium can be launched: {str(second).splitlines()[0]}')`
  - `src/wambatic/cli.py:234` - `raise wambatic.reports.errors.OutputError(f'cannot write {path}: {e.strerror or e}') from e`
  - `src/wambatic/cli.py:405` - `f'Unexpected error: {wambatic.reports.service.redact_environment_token(str(e))}'`
  - `src/wambatic/reports/service.py:246` - `f'{e}; the cache may only need a sync, so try again without --no-fetch'`
  - `src/wambatic/reports/web.py:535` - `f'cannot listen on {host}:{port}: {e.strerror or e}'`
  - `src/wambatic/settings.py:155` - `raise SettingsError(f'config file {path} is not valid JSON ({e.msg})') from None`
  - `src/wambatic/settings.py:107` - `raise SettingsError(f'{key}: {e}') from None`
- **Recommendation:** Keep the message categorical (exception type and context); where the exception text is the payload, accept with a scoped marker giving the reason.

### Rule: literal-duplication

- **Severity:** low
- **Instance count:** 272 (bin: 2, src/tests: 254, src/wambatic: 16)
- **Locations:**
  - `src/tests/conftest.py:332` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/stats/test_base.py:30` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/stats/test_compute.py:86` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/stats/test_compute.py:255` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/stats/test_compute.py:292` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/stats/test_compute.py:309` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/stats/test_compute.py:329` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/stats/test_compute.py:338` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/test_cli.py:109` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/test_cli.py:515` - `('activity', 'flow')` (identical unordered literal across 10 locations)
  - `src/tests/conftest.py:256` - `('delivery',)` (identical unordered literal across 4 locations)
  - `src/tests/reports/test_figures.py:456` - `('delivery',)` (identical unordered literal across 4 locations)
  - `src/tests/stats/test_compute.py:84` - `('delivery',)` (identical unordered literal across 4 locations)
  - `src/tests/stats/test_compute.py:357` - `('delivery',)` (identical unordered literal across 4 locations)
  - `src/tests/conftest.py:269` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/conftest.py:311` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/reports/test_figures.py:529` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/reports/test_rows.py:339` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/reports/test_rows.py:366` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/reports/test_terminal.py:343` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/reports/test_terminal.py:543` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/reports/test_terminal.py:604` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/reports/test_terminal.py:618` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/stats/test_compute.py:85` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/stats/test_compute.py:631` - `('popularity',)` (identical unordered literal across 11 locations)
  - `src/tests/conftest.py:368` - `('activity', 'delivery', 'flow')` (identical unordered literal across 4 locations)
  - `src/tests/stats/test_compute.py:236` - `('activity', 'flow', 'delivery')` (identical unordered literal across 4 locations)
  - `src/tests/stats/test_compute.py:238` - `('delivery', 'flow', 'activity')` (identical unordered literal across 4 locations)
  - `src/tests/stats/test_compute.py:455` - `('activity', 'flow', 'delivery')` (identical unordered literal across 4 locations)
  - `src/tests/conftest.py:380` - `('activity', 'popularity')` (identical unordered literal across 3 locations)
  - `src/tests/stats/test_compute.py:697` - `('activity', 'popularity')` (identical unordered literal across 3 locations)
  - `src/tests/stats/test_compute.py:741` - `('activity', 'popularity')` (identical unordered literal across 3 locations)
  - `src/tests/fetch/test_auth.py:15` - `('gh',)` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_auth.py:52` - `('gh',)` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_cache.py:1008` - `('star_events', 'forks')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_live.py:69` - `('star_events', 'forks')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_cache.py:380` - `('s1',)` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_cache.py:446` - `('s1',)` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_cache.py:747` - `('s1',)` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_cache.py:469` - `('c1',)` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_cache.py:484` - `('c1',)` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_cache.py:710` - `('Hotfix', 'bug')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_cache.py:718` - `('Hotfix', 'bug')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_cache.py:712` - `('ünïcode ✓',)` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_cache.py:719` - `('ünïcode ✓',)` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_client.py:20` - `('POST', '/graphql')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:393` - `('POST', '/graphql')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:614` - `('POST', '/graphql')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_client.py:402` - `('rest', 'graphql')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_client.py:416` - `('rest', 'graphql')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_errors.py:41` - `('1', '2')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_errors.py:52` - `('1', '2')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:35` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/fetch/test_live.py:45` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:29` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:187` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:188` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:191` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:192` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:193` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:194` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:195` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_service.py:196` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_web.py:36` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/reports/test_web.py:37` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/stats/test_compute.py:82` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/test_cli.py:45` - `('commits',)` (identical unordered literal across 15 locations)
  - `src/tests/fetch/test_fetcher.py:1470` - `('commits', 'issues', 'pull_requests')` (identical unordered literal across 3 locations)
  - `src/tests/stats/test_compute.py:86` - `('commits', 'issues', 'pull_requests')` (identical unordered literal across 3 locations)
  - `src/tests/test_cli.py:46` - `('commits', 'issues', 'pull_requests')` (identical unordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1663` - `('releases', 'workflow_runs')` (identical unordered literal across 2 locations)
  - `src/tests/test_package.py:138` - `('releases', 'workflow_runs')` (identical unordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:1361` - `('2',)` (identical unordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1806` - `('2',)` (identical unordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:2234` - `('2',)` (identical unordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:2181` - `('empty', 'forbidden')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:2183` - `('empty', 'forbidden')` (identical ordered literal across 3 locations)
  - `src/tests/fixtures/fetch/upstream.py:115` - `('empty', 'forbidden')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:2462` - `('star_events', 'forks')` (identical unordered literal across 3 locations)
  - `src/tests/stats/test_compute.py:85` - `('forks', 'star_events')` (identical unordered literal across 3 locations)
  - `src/tests/test_cli.py:1619` - `('forks', 'star_events')` (identical unordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:304` - `('s1', 's2')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:1024` - `('s1', 's2')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:322` - `('h1', 'h2', 'h3')` (identical ordered literal across 7 locations)
  - `src/tests/fetch/test_fetcher.py:419` - `('h1', 'h2', 'h3')` (identical ordered literal across 7 locations)
  - `src/tests/fetch/test_fetcher.py:691` - `('h1', 'h2', 'h3')` (identical ordered literal across 7 locations)
  - `src/tests/fetch/test_fetcher.py:778` - `('h1', 'h2', 'h3')` (identical ordered literal across 7 locations)
  - `src/tests/fetch/test_fetcher.py:804` - `('h1', 'h2', 'h3')` (identical ordered literal across 7 locations)
  - `src/tests/fetch/test_fetcher.py:872` - `('h1', 'h2', 'h3')` (identical ordered literal across 7 locations)
  - `src/tests/fetch/test_fetcher.py:1018` - `('h1', 'h2', 'h3')` (identical ordered literal across 7 locations)
  - `src/tests/fetch/test_fetcher.py:641` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:653` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:676` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:688` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:996` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:1537` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:1750` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:2104` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:2149` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:2333` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:2466` - `('listing',)` (identical ordered literal across 11 locations)
  - `src/tests/fetch/test_fetcher.py:663` - `('listing', 'history')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:930` - `('listing', 'history')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1022` - `('listing', 'history')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:664` - `('h1', 'h2')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:859` - `('h1', 'h2')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:707` - `('listing', 'compare', 'nodes')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:751` - `('listing', 'compare', 'nodes')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:1736` - `('v1', 'v2', 'v3')` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:1752` - `('v1', 'v2', 'v3')` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:1809` - `('v1', 'v2', 'v3')` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:1824` - `('v1', 'v2', 'v3')` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:1748` - `('listing', 'releases')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1781` - `('listing', 'releases')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1792` - `('listing', 'releases')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1832` - `('runs', 'runs', 'runs')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1965` - `('runs', 'runs', 'runs')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1977` - `('runs', 'runs', 'runs')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:1850` - `('runs',)` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:1867` - `('runs',)` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:1931` - `('runs',)` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:1960` - `('runs',)` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:1906` - `('runs', 'run')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:1921` - `('runs', 'run')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:2089` - `('listing', 'stargazers', 'stargazers', 'stargazers')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:2164` - `('listing', 'stargazers', 'stargazers', 'stargazers')` (identical ordered literal across 2 locations)
  - `src/tests/fetch/test_fetcher.py:2091` - `('U_1', 'U_2', 'U_3', 'U_4', 'U_5')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:2208` - `('U_1', 'U_2', 'U_3', 'U_4', 'U_5')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:2237` - `('U_1', 'U_2', 'U_3', 'U_4', 'U_5')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_fetcher.py:2119` - `('listing', 'stargazers')` (identical ordered literal across 5 locations)
  - `src/tests/fetch/test_fetcher.py:2152` - `('listing', 'stargazers')` (identical ordered literal across 5 locations)
  - `src/tests/fetch/test_fetcher.py:2178` - `('listing', 'stargazers')` (identical ordered literal across 5 locations)
  - `src/tests/fetch/test_fetcher.py:2188` - `('listing', 'stargazers')` (identical ordered literal across 5 locations)
  - `src/tests/fetch/test_fetcher.py:2205` - `('listing', 'stargazers')` (identical ordered literal across 5 locations)
  - `src/tests/fetch/test_fetcher.py:2344` - `('listing', 'forks')` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:2356` - `('listing', 'forks')` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:2367` - `('listing', 'forks')` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:2380` - `('listing', 'forks')` (identical ordered literal across 4 locations)
  - `src/tests/fetch/test_fetcher.py:533` - `('releases',)` (identical unordered literal across 8 locations)
  - `src/tests/fetch/test_fetcher.py:1747` - `('releases',)` (identical unordered literal across 8 locations)
  - `src/tests/fetch/test_fetcher.py:1749` - `('releases',)` (identical unordered literal across 8 locations)
  - `src/tests/fetch/test_fetcher.py:1764` - `('releases',)` (identical unordered literal across 8 locations)
  - `src/tests/fetch/test_fetcher.py:1775` - `('releases',)` (identical unordered literal across 8 locations)
  - `src/tests/fetch/test_fetcher.py:1780` - `('releases',)` (identical unordered literal across 8 locations)
  - `src/tests/fetch/test_fetcher.py:1789` - `('releases',)` (identical unordered literal across 8 locations)
  - `src/tests/fetch/test_fetcher.py:1791` - `('releases',)` (identical unordered literal across 8 locations)
  - `src/tests/fetch/test_server.py:34` - `('GET', '/x')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_server.py:42` - `('GET', '/x')` (identical ordered literal across 3 locations)
  - `src/tests/fetch/test_server.py:49` - `('GET', '/x')` (identical ordered literal across 3 locations)
  - `src/tests/fixtures/fetch/responses.py:414` - `('repository',)` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:1658` - `('repository',)` (identical ordered literal across 2 locations)
  - `src/tests/fixtures/fetch/responses.py:424` - `('repository', 'stargazers')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:1640` - `('repository', 'stargazers')` (identical ordered literal across 2 locations)
  - `src/tests/fixtures/reports.py:182` - `('2026-10', '2026-11', '2026-12', '2027-01')` (identical ordered literal across 4 locations)
  - `src/tests/fixtures/reports.py:212` - `('2026-10', '2026-11', '2026-12', '2027-01')` (identical ordered literal across 4 locations)
  - `src/tests/fixtures/reports.py:222` - `('2026-10', '2026-11', '2026-12', '2027-01')` (identical ordered literal across 4 locations)
  - `src/tests/fixtures/stats.py:32` - `('2026-10', '2026-11', '2026-12', '2027-01')` (identical ordered literal across 4 locations)
  - `src/tests/fixtures/reports.py:214` - `('circle', 'circle', 'circle', 'circle')` (identical ordered literal across 2 locations)
  - `src/tests/fixtures/reports.py:224` - `('circle', 'circle', 'circle', 'circle')` (identical ordered literal across 2 locations)
  - `src/tests/fixtures/reports.py:184` - `('', '', '', '')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_figures.py:148` - `('', '', '', '')` (identical ordered literal across 2 locations)
  - `src/tests/fixtures/stats.py:426` - `('hotfix',)` (identical ordered literal across 2 locations)
  - `src/tests/test_settings.py:37` - `('hotfix',)` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_base.py:209` - `('stars_added', 'stars_total', 'forks_added', 'forks_total')` (identical ordered literal across 6 locations)
  - `src/tests/reports/test_rows.py:399` - `('stars_added', 'stars_total', 'forks_added', 'forks_total')` (identical ordered literal across 6 locations)
  - `src/tests/reports/test_terminal.py:636` - `('stars_added', 'stars_total', 'forks_added', 'forks_total')` (identical ordered literal across 6 locations)
  - `src/tests/stats/test_compute.py:632` - `('stars_added', 'stars_total', 'forks_added', 'forks_total')` (identical ordered literal across 6 locations)
  - `src/tests/stats/test_popularity.py:22` - `('stars_added', 'stars_total', 'forks_added', 'forks_total')` (identical ordered literal across 6 locations)
  - `src/tests/test_cli.py:1694` - `('stars_added', 'stars_total', 'forks_added', 'forks_total')` (identical ordered literal across 6 locations)
  - `src/tests/reports/test_base.py:131` - `('count', 'ratio', 'minutes', 'days', 'hours')` (identical unordered literal across 2 locations)
  - `src/tests/stats/test_delivery.py:101` - `('count', 'ratio', 'minutes', 'days', 'hours')` (identical unordered literal across 2 locations)
  - `src/tests/reports/test_base.py:158` - `('dependabot[bot]', 'renovate[bot]')` (identical ordered literal across 2 locations)
  - `src/tests/test_settings.py:33` - `('dependabot[bot]', 'renovate[bot]')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_base.py:214` - `('Python', 'Go', 'Shell', 'Other')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_rows.py:381` - `('Python', 'Go', 'Shell', 'Other')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_figures.py:281` - `('activity-top-contributors', 'activity-by-repository', 'activity-by-author')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_html.py:110` - `('activity-top-contributors', 'activity-by-repository', 'activity-by-author')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_figures.py:338` - `('prs', 'issues')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_figures.py:427` - `('prs', 'issues')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_html.py:106` - `('day', 'month', 'week', 'year')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_html.py:129` - `('day', 'month', 'week', 'year')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_html.py:132` - `('month',)` (identical unordered literal across 2 locations)
  - `src/tests/reports/test_html_browser.py:136` - `('month',)` (identical unordered literal across 2 locations)
  - `src/tests/reports/test_html.py:460` - `('report.html',)` (identical ordered literal across 3 locations)
  - `src/tests/reports/test_html.py:508` - `('report.html',)` (identical ordered literal across 3 locations)
  - `src/tests/test_cli.py:1247` - `('report.html',)` (identical ordered literal across 3 locations)
  - `src/tests/reports/test_html.py:373` - `('auto', 'dark', 'light')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_html_browser.py:37` - `('auto', 'dark', 'light')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_html.py:344` - `('activity',)` (identical unordered literal across 4 locations)
  - `src/tests/reports/test_terminal.py:392` - `('activity',)` (identical unordered literal across 4 locations)
  - `src/tests/stats/test_compute.py:27` - `('activity',)` (identical unordered literal across 4 locations)
  - `src/tests/stats/test_compute.py:82` - `('activity',)` (identical unordered literal across 4 locations)
  - `src/tests/reports/test_rows.py:103` - `('Octocat', 'hubot', 'dependabot[bot]', 'monalisa', 'unattributed')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_terminal.py:250` - `('Octocat', 'hubot', 'dependabot[bot]', 'monalisa', 'unattributed')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_rows.py:311` - `('workflow_runs', 'release_count', 'deployments')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_fixtures.py:286` - `('workflow_runs', 'release_count', 'deployments')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_service.py:46` - `('text', 'expected')` (identical ordered literal across 2 locations)
  - `src/tests/test_settings.py:158` - `('text', 'expected')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_service.py:199` - `('commits', 'issues')` (identical unordered literal across 2 locations)
  - `src/tests/reports/test_service.py:207` - `('commits', 'issues')` (identical unordered literal across 2 locations)
  - `src/tests/reports/test_terminal.py:19` - `('commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net')` (identical ordered literal across 3 locations)
  - `src/tests/stats/test_activity.py:21` - `('commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net')` (identical ordered literal across 3 locations)
  - `src/tests/stats/test_compute.py:29` - `('commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net')` (identical ordered literal across 3 locations)
  - `src/tests/reports/test_terminal.py:142` - `('total',)` (identical ordered literal across 3 locations)
  - `src/tests/stats/test_compute.py:206` - `('total',)` (identical ordered literal across 3 locations)
  - `src/tests/stats/test_popularity.py:87` - `('total',)` (identical ordered literal across 3 locations)
  - `src/tests/reports/test_terminal.py:381` - `('prs_opened', 'prs_merged', 'issues_opened', 'issues_closed')` (identical unordered literal across 2 locations)
  - `src/tests/stats/test_flow.py:22` - `('prs_opened', 'prs_merged', 'issues_opened', 'issues_closed')` (identical unordered literal across 2 locations)
  - `src/tests/reports/test_terminal.py:355` - `('flow',)` (identical unordered literal across 3 locations)
  - `src/tests/stats/test_compute.py:28` - `('flow',)` (identical unordered literal across 3 locations)
  - `src/tests/stats/test_compute.py:83` - `('flow',)` (identical unordered literal across 3 locations)
  - `src/tests/reports/test_terminal.py:417` - `('Total',)` (identical ordered literal across 4 locations)
  - `src/tests/reports/test_terminal.py:419` - `('Total',)` (identical ordered literal across 4 locations)
  - `src/tests/reports/test_terminal.py:427` - `('Total',)` (identical ordered literal across 4 locations)
  - `src/tests/reports/test_terminal.py:570` - `('Total',)` (identical ordered literal across 4 locations)
  - `src/tests/reports/test_terminal.py:437` - `('2026-10', '*')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_terminal.py:649` - `('2026-10', '*')` (identical ordered literal across 2 locations)
  - `src/tests/reports/test_web.py:41` - `('error', 'status')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:864` - `('error', 'status')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_activity.py:22` - `('commits', 'lines_added', 'lines_deleted', 'lines_net')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_compute.py:30` - `('commits', 'lines_added', 'lines_deleted', 'lines_net')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_activity.py:55` - `('tz', 'expected')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_activity.py:67` - `('tz', 'expected')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_base.py:14` - `('activity', 'delivery', 'flow', 'popularity')` (identical unordered literal across 2 locations)
  - `src/tests/stats/test_compute.py:667` - `('activity', 'flow', 'delivery', 'popularity')` (identical unordered literal across 2 locations)
  - `src/tests/stats/test_compute.py:358` - `('deployments', 'lead_time_p50', 'lead_time_p90', 'change_failure_rate', 'time_to_restore_p50', '...` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_delivery.py:35` - `('deployments', 'lead_time_p50', 'lead_time_p90', 'change_failure_rate', 'time_to_restore_p50', '...` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_compute.py:330` - `('commits', 'issues', 'pull_requests')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_fixtures.py:203` - `('commits', 'issues', 'pull_requests')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_compute.py:83` - `('issues', 'pull_requests')` (identical unordered literal across 2 locations)
  - `src/tests/test_package.py:128` - `('issues', 'pull_requests')` (identical unordered literal across 2 locations)
  - `src/tests/stats/test_compute.py:84` - `('pull_requests', 'releases', 'workflow_runs')` (identical unordered literal across 2 locations)
  - `src/tests/test_cli.py:47` - `('pull_requests', 'releases', 'workflow_runs')` (identical unordered literal across 2 locations)
  - `src/tests/stats/test_compute.py:230` - `('stars', 'forks')` (identical ordered literal across 2 locations)
  - `src/tests/stats/test_fixtures.py:353` - `('stars', 'forks')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:433` - `('/graphql',)` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:1659` - `('/graphql',)` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:543` - `('GET', '/users/octocat')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:587` - `('GET', '/users/octocat')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:774` - `('0',)` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:777` - `('0',)` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:873` - `('report', 'repo:octo-org/alpha')` (identical ordered literal across 5 locations)
  - `src/tests/test_cli.py:885` - `('report', 'repo:octo-org/alpha')` (identical ordered literal across 5 locations)
  - `src/tests/test_cli.py:895` - `('report', 'repo:octo-org/alpha')` (identical ordered literal across 5 locations)
  - `src/tests/test_cli.py:986` - `('report', 'repo:octo-org/alpha')` (identical ordered literal across 5 locations)
  - `src/tests/test_cli.py:1005` - `('report', 'repo:octo-org/alpha')` (identical ordered literal across 5 locations)
  - `src/tests/test_cli.py:902` - `('--help',)` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:1601` - `('--help',)` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:912` - `('cache', 'info')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:969` - `('cache', 'info')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:931` - `('report', 'repo:a/b', '--format', 'html', '--by', 'total')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:1210` - `('report', 'repo:a/b', '--format', 'html', '--by', 'total')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:252` - `('-q', 'cache', 'clear')` (identical ordered literal across 2 locations)
  - `src/tests/test_cli.py:971` - `('-q', 'cache', 'clear')` (identical ordered literal across 2 locations)
  - `src/wambatic/cli.py:33` - `('html', 'json', 'terminal')` (identical ordered literal across 2 locations)
  - `src/wambatic/settings.py:36` - `('html', 'json', 'terminal')` (identical ordered literal across 2 locations)
  - `src/wambatic/fetch/cache.py:623` - `('repo', 'number')` (identical ordered literal across 2 locations)
  - `src/wambatic/fetch/cache.py:656` - `('repo', 'number')` (identical ordered literal across 2 locations)
  - `src/wambatic/fetch/cache.py:708` - `('repo', 'id')` (identical ordered literal across 2 locations)
  - `src/wambatic/fetch/cache.py:762` - `('repo', 'id')` (identical ordered literal across 2 locations)
  - `src/wambatic/reports/figures.py:65` - `('activity', 'delivery', 'flow', 'popularity')` (identical ordered literal across 2 locations)
  - `src/wambatic/reports/figures.py:86` - `('activity', 'delivery', 'flow', 'popularity')` (identical ordered literal across 2 locations)
  - `src/wambatic/reports/html.py:24` - `('auto', 'dark', 'light')` (identical ordered literal across 2 locations)
  - `src/wambatic/settings.py:37` - `('auto', 'dark', 'light')` (identical ordered literal across 2 locations)
  - `src/wambatic/reports/rows.py:22` - `('workflow_runs', 'release_count', 'deployments')` (identical ordered literal across 2 locations)
  - `src/wambatic/stats/delivery.py:132` - `('workflow_runs', 'release_count', 'deployments')` (identical ordered literal across 2 locations)
  - `src/wambatic/reports/service.py:25` - `('org', 'repo', 'user')` (identical ordered literal across 2 locations)
  - `src/wambatic/reports/service.py:40` - `('org', 'repo', 'user')` (identical ordered literal across 2 locations)
  - `src/wambatic/stats/activity.py:63` - `('author', 'repo')` (identical ordered literal across 2 locations)
  - `src/wambatic/stats/base.py:32` - `('author', 'repo')` (identical ordered literal across 2 locations)
  - `bin/record-fixtures.py:181` - `('login', 'type')` (identical ordered literal across 2 locations)
  - `bin/record-fixtures.py:182` - `('login', 'type')` (identical ordered literal across 2 locations)
- **Recommendation:** In `src/` and `bin/`, name the repeated literal once as a constant. In `src/tests/` see Decision 1.

### Rule: non-alphabetical-literal

- **Severity:** low
- **Instance count:** 50 (bin: 4, src/tests: 24, src/wambatic: 22)
- **Variants:** string members not alphabetically sorted (50)
- **Locations:**
  - `src/tests/fetch/test_client.py:20` - `['POST', '/graphql']`
  - `src/tests/fetch/test_client.py:21` - `['GET', '/repos/octocat/Hello-World']`
  - `src/tests/fetch/test_client.py:22` - `['GET', '/repos/octocat/Hello-World/stats/code_frequency']`
  - `src/tests/fixtures/stats.py:463` - `['prs_opened', 'prs_merged', 'issues_opened', 'issues_closed', 'time_to_first_review_p50', 'time_...`
  - `src/tests/reports/test_base.py:17` - `['format_version', 'subject', 'request', 'since', 'until', 'series', 'tables', 'provenance']`
  - `src/tests/reports/test_base.py:27` - `['granularity', 'groups', 'since', 'until', 'by_author', 'tz', 'settings']`
  - `src/tests/reports/test_base.py:28` - `['metric', 'unit', 'by', 'by_kind', 'points']`
  - `src/tests/reports/test_figures.py:16` - `['activity-commits', 'activity-contributors', 'activity-active-days', 'activity-lines', 'flow-pul...`
  - `src/tests/reports/test_figures.py:28` - `['delivery-runs', 'delivery-success-rate', 'delivery-duration', 'delivery-releases', 'delivery-re...`
  - `src/tests/reports/test_figures.py:39` - `['deployments', 'lead_time', 'change_failure_rate', 'time_to_restore']`
  - `src/tests/reports/test_figures.py:516` - `['popularity-stars-added', 'popularity-stars-total', 'popularity-forks-added', 'popularity-forks-...`
  - `src/tests/reports/test_terminal.py:19` - `['commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net']`
  - `src/tests/reports/test_web_browser.py:23` - `['Waiting for another sync to finish', 'Listing repositories', 'Syncing repositories', 'Done, loa...`
  - `src/tests/stats/test_activity.py:21` - `['commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net']`
  - `src/tests/stats/test_compute.py:29` - `['commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net']`
  - `src/tests/stats/test_compute.py:358` - `['deployments', 'lead_time_p50', 'lead_time_p90', 'change_failure_rate', 'time_to_restore_p50', '...`
  - `src/tests/stats/test_compute.py:632` - `['stars_added', 'stars_total', 'forks_added', 'forks_total']`
  - `src/tests/stats/test_delivery.py:27` - `['workflow_runs', 'workflow_success_rate', 'workflow_duration_p50', 'workflow_duration_p90', 'rel...`
  - `src/tests/stats/test_delivery.py:35` - `['deployments', 'lead_time_p50', 'lead_time_p90', 'change_failure_rate', 'time_to_restore_p50', '...`
  - `src/tests/stats/test_popularity.py:22` - `['stars_added', 'stars_total', 'forks_added', 'forks_total']`
  - `src/tests/test_cli.py:273` - `['--since', '2026-10-01', '--until', '2027-01-31']`
  - `src/tests/test_cli.py:1270` - `['--groups', 'delivery', '--since', '2026-10-01', '--until', '2026-10-31']`
  - `src/tests/test_cli.py:1618` - `['--groups', 'popularity', '--since', '2026-10-01', '--until', '2027-01-31']`
  - `src/tests/test_layering.py:5` - `['wambatic.cli', 'wambatic.__main__']`
  - `src/wambatic/fetch/__init__.py:30` - `['BUILT_RESOURCES', 'RESOURCES', 'AuthError', 'Cache', 'CacheInfo', 'CacheVersionError', 'Commit'...`
  - `src/wambatic/fetch/cache.py:132` - `['repo', 'oid', 'authored_at', 'author_login', 'additions', 'deletions', 'is_merge']`
  - `src/wambatic/fetch/cache.py:141` - `['repo', 'number', 'author_login', 'created_at', 'updated_at', 'merged_at', 'closed_at', 'first_r...`
  - `src/wambatic/fetch/cache.py:155` - `['repo', 'number', 'author_login', 'created_at', 'updated_at', 'closed_at']`
  - `src/wambatic/fetch/cache.py:156` - `['repo', 'tag_name', 'created_at', 'published_at', 'is_prerelease']`
  - `src/wambatic/fetch/cache.py:157` - `['repo', 'id', 'workflow_path', 'name', 'event', 'head_branch', 'status', 'conclusion', 'created_...`
  - `src/wambatic/fetch/cache.py:171` - `['repo', 'user_id', 'starred_at']`
  - `src/wambatic/fetch/cache.py:172` - `['repo', 'id', 'created_at']`
  - `src/wambatic/reports/figures.py:437` - `['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']`
  - `src/wambatic/reports/rows.py:22` - `['workflow_runs', 'release_count', 'deployments']`
  - `src/wambatic/reports/rows.py:29` - `['stars_added', 'forks_added']`
  - `src/wambatic/reports/rows.py:33` - `['Commits', 'Contributors', 'Active days', 'Added', 'Deleted', 'Net']`
  - `src/wambatic/reports/rows.py:34` - `['PRs opened', 'PRs merged', 'Issues opened', 'Issues closed']`
  - `src/wambatic/reports/rows.py:36` - `['Review p50', 'Review p90', 'Merge p50', 'Merge p90', 'Close p50', 'Close p90', 'PR size p50']`
  - `src/wambatic/reports/rows.py:45` - `['Name', 'Commits', 'Added', 'Deleted', 'Net']`
  - `src/wambatic/reports/rows.py:46` - `['Login', 'Commits', 'Added', 'Deleted', 'Net', 'Active days']`
  - `src/wambatic/reports/rows.py:61` - `['workflow_runs', 'release_count', 'deployments']`
  - `src/wambatic/reports/rows.py:62` - `['Stars added', 'Stars total', 'Forks added', 'Forks total']`
  - `src/wambatic/reports/rows.py:63` - `['Repository', 'Stars', 'Forks', 'Watchers']`
  - `src/wambatic/reports/rows.py:64` - `['Language', 'Bytes', 'Share']`
  - `src/wambatic/reports/web.py:45` - `['localhost', '127.0.0.1', '[::1]']`
  - `src/wambatic/stats/__init__.py:12` - `['GROUPS', 'Bucket', 'EmptySubjectError', 'Granularity', 'InvalidRangeError', 'InvalidRequestErro...`
  - `bin/record-fixtures.py:37` - `['octocat', 'Hello-World']`
  - `bin/record-fixtures.py:40` - `['miguelangellv', 'ha-gas-station-spain']`
  - `bin/record-fixtures.py:42` - `['bnomis', 'ab2cb']`
  - `bin/record-fixtures.py:70` - `['id', 'name', 'path', 'event', 'head_branch', 'status', 'conclusion', 'created_at', 'updated_at'...`
- **Recommendation:** Sort the members where order carries no meaning; where it does (column order, display order, argv), add `# auditme: accept[non-alphabetical-literal] <why the order matters>`.

### Rule: paired-sibling-helpers

- **Severity:** low
- **Instance count:** 6 (src/tests: 6)
- **Variants:** 3 functions share a body across files (6)
- **Locations:**
  - `src/tests/fetch/test_base.py:71` - `def test_every_resource_is_built(...) - matches: (peer)`
  - `src/tests/fetch/test_fetcher.py:2471` - `def test_every_resource_is_built(...) - matches: (peer)`
  - `src/tests/test_package.py:146` - `def test_every_resource_is_built(...) - matches: (peer)`
  - `src/tests/stats/test_delivery.py:68` - `def pick(...) - matches: (peer)`
  - `src/tests/stats/test_flow.py:54` - `def pick(...) - matches: (peer)`
  - `src/tests/stats/test_popularity.py:46` - `def pick(...) - matches: (peer)`
- **Recommendation:** Factor the shared body into one test helper or a parametrised test.

### Rule: passthrough-shim

- **Severity:** low
- **Instance count:** 13 (src/tests: 9, src/wambatic: 4)
- **Locations:**
  - `src/tests/fetch/test_fetcher.py:95` - `def settings_with(...): return dataclasses.replace(...)` (settings_with is a pass-through wrapper for dataclasses.replace)
  - `src/tests/reports/test_base.py:32` - `def as_dict(...): return wambatic.reports.base.result_to_dict(...)` (as_dict is a pass-through wrapper for wambatic.reports.base.result_to_dict)
  - `src/tests/reports/test_figures.py:64` - `def with_partial(...): return dataclasses.replace(...)` (with_partial is a pass-through wrapper for dataclasses.replace)
  - `src/tests/reports/test_figures.py:445` - `def delivery_figures(...): return wambatic.reports.figures.build_figures(...)` (delivery_figures is a pass-through wrapper for wambatic.reports.figures.build_figures)
  - `src/tests/reports/test_terminal.py:352` - `def flow_only_result(...): return recompute(...)` (flow_only_result is a pass-through wrapper for recompute)
  - `src/tests/stats/test_buckets.py:19` - `def date(...): return datetime.date.fromisoformat(...)` (date is a pass-through wrapper for datetime.date.fromisoformat)
  - `src/tests/stats/test_buckets.py:23` - `def utc(...): return datetime.datetime(...)` (utc is a pass-through wrapper for datetime.datetime)
  - `src/tests/stats/test_compute.py:244` - `def flow_only(...): return compute(...)` (flow_only is a pass-through wrapper for compute)
  - `src/tests/stats/test_compute.py:370` - `def delivery_only(...): return compute(...)` (delivery_only is a pass-through wrapper for compute)
  - `src/wambatic/fetch/cache.py:214` - `def from_text(...): return datetime.datetime.fromisoformat(...)` (from_text is a pass-through wrapper for datetime.datetime.fromisoformat)
  - `src/wambatic/reports/service.py:120` - `def make_fetcher(...): return wambatic.fetch.base.Fetcher(...)` (make_fetcher is a pass-through wrapper for wambatic.fetch.base.Fetcher)
  - `src/wambatic/reports/terminal.py:62` - `def text_cell(...): return rich.text.Text(...)` (text_cell is a pass-through wrapper for rich.text.Text)
  - `src/wambatic/reports/web.py:206` - `def raw_query(...): return RawQuery(...)` (raw_query is a pass-through wrapper for RawQuery)
- **Recommendation:** Call the wrapped function directly, or accept with a scoped marker where the shim names a domain concept.

### Rule: duplicate-call-sequence

- **Severity:** low
- **Instance count:** 2 (src/tests: 2)
- **Variants:** open_report shares 8 calls in order with src/tests/reports/test_web_browser.py:test_the_progress_page_becomes_the_report_with_every_chart_drawn (1); open_page shares 8 calls in order with src/tests/reports/test_web_browser.py:test_the_progress_page_becomes_the_report_with_every_chart_drawn (1)
- **Locations:**
  - `src/tests/reports/test_html_browser.py:29` - `shared sequence: new_context -> new_page -> route -> on -> goto -> wait_for_selector -> continue_...`
  - `src/tests/reports/test_html_browser.py:36` - `shared sequence: new_context -> new_page -> route -> on -> goto -> wait_for_selector -> continue_...`
- **Recommendation:** Extract the shared Playwright page-opening sequence into one helper in `src/tests/reports/conftest.py`.

### Rule: build-name-has-side-effect

- **Severity:** low
- **Instance count:** 2 (src/tests: 2)
- **Variants:** compute_stats calls side-effect `run` despite `build_`/`compute_` name (1); build_with calls side-effect `run` despite `build_`/`compute_` name (1)
- **Locations:**
  - `src/tests/conftest.py:236` - `return asyncio.run(`
  - `src/tests/reports/test_service.py:339` - `return asyncio.run(scenario())`
- **Recommendation:** Rename the test helpers (`run_stats`, `run_build`) or accept with a scoped marker.

### Rule: mutable-module-level-exported

- **Severity:** medium
- **Instance count:** 17 (src/tests: 16, src/wambatic: 1)
- **Locations:**
  - `src/tests/fixtures/fetch/recorded.py:17` - `QUERY_SHA256 = {` (QUERY_SHA256 is a mutable dict literal read by 1 other file(s); wrap in types.MappingProxyType(...))
  - `src/tests/fixtures/fetch/responses.py:22` - `RATE_HEADERS = {'x-ratelimit-remaining': '4990', 'x-ratelimit-reset': RESET_EPOCH}` (RATE_HEADERS is a mutable dict literal read by 4 other file(s); wrap in types.MappingProxyType(...))
  - `src/tests/fixtures/fetch/responses.py:396` - `GRAPHQL_NOT_FOUND = {` (GRAPHQL_NOT_FOUND is a mutable dict literal read by 1 other file(s); wrap in types.MappingProxyType(...))
  - `src/tests/fixtures/fetch/responses.py:409` - `GRAPHQL_REPOSITORY_NOT_FOUND = {` (GRAPHQL_REPOSITORY_NOT_FOUND is a mutable dict literal read by 1 other file(s); wrap in types.MappingProxyType(...))
  - `src/tests/fixtures/fetch/responses.py:419` - `GRAPHQL_FORBIDDEN = {` (GRAPHQL_FORBIDDEN is a mutable dict literal read by 1 other file(s); wrap in types.MappingProxyType(...))
  - `src/tests/fixtures/fetch/responses.py:441` - `NOT_FOUND = {'message': 'Not Found', 'documentation_url': 'https://docs.github.com/rest'}` (NOT_FOUND is a mutable dict literal read by 7 other file(s); wrap in types.MappingProxyType(...))
  - `src/tests/fixtures/fetch/responses.py:442` - `SERVER_ERROR = {'message': 'Server Error'}` (SERVER_ERROR is a mutable dict literal read by 6 other file(s); wrap in types.MappingProxyType(...))
  - `src/tests/fixtures/reports.py:172` - `ORG_MONTH_FIGURES = {` (ORG_MONTH_FIGURES is a mutable dict literal read by 1 other file(s); wrap in types.MappingProxyType(...))
  - `src/tests/fixtures/stats.py:65` - `REPOS = [` (REPOS is a mutable list literal read by 2 other file(s); wrap in tuple(...))
  - `src/tests/fixtures/stats.py:109` - `COMMITS = [` (COMMITS is a mutable list literal read by 3 other file(s); wrap in tuple(...))
  - `src/tests/fixtures/stats.py:343` - `PULL_REQUESTS = [` (PULL_REQUESTS is a mutable list literal read by 2 other file(s); wrap in tuple(...))
  - `src/tests/fixtures/stats.py:449` - `ISSUES = [` (ISSUES is a mutable list literal read by 2 other file(s); wrap in tuple(...))
  - `src/tests/fixtures/stats.py:551` - `RELEASES = [` (RELEASES is a mutable list literal read by 2 other file(s); wrap in tuple(...))
  - `src/tests/fixtures/stats.py:602` - `WORKFLOW_RUNS = [` (WORKFLOW_RUNS is a mutable list literal read by 2 other file(s); wrap in tuple(...))
  - `src/tests/fixtures/stats.py:766` - `STAR_EVENTS = [` (STAR_EVENTS is a mutable list literal read by 3 other file(s); wrap in tuple(...))
  - `src/tests/fixtures/stats.py:783` - `FORKS = [` (FORKS is a mutable list literal read by 3 other file(s); wrap in tuple(...))
  - `src/wambatic/reports/figures.py:40` - `PALETTE: dict[typing.Literal['dark', 'light'], Theme] = {` (PALETTE is a mutable dict literal read by 6 other file(s); wrap in types.MappingProxyType(...))
- **Recommendation:** Wrap in `types.MappingProxyType(...)` (dict) or `tuple(...)` (list); `PALETTE` in `src/wambatic` is also A20. For the recorded and canned responses in `src/tests/fixtures/` see Decision 1.

### Rule: non-alphabetical-dict-keys

- **Severity:** low
- **Instance count:** 22 (src/tests: 17, src/wambatic: 5)
- **Variants:** dict with string keys not alphabetically sorted (22)
- **Locations:**
  - `src/tests/fetch/test_client.py:23` - `keys: ['login', 'cursor']`
  - `src/tests/fixtures/fetch/recorded.py:278` - `keys: ['status', 'ahead_by', 'behind_by', 'total_commits', 'commits']`
  - `src/tests/fixtures/fetch/recorded.py:320` - `keys: ['id', 'full_name', 'default_branch']`
  - `src/tests/fixtures/fetch/recorded.py:1201` - `keys: ['id', 'name', 'path', 'event', 'head_branch', 'status', 'conclusion', 'created_at', 'updat...`
  - `src/tests/fixtures/fetch/responses.py:436` - `keys: ['message', 'documentation_url']`
  - `src/tests/fixtures/fetch/responses.py:441` - `keys: ['message', 'documentation_url']`
  - `src/tests/fixtures/stats.py:189` - `keys: ['commits', 'contributors', 'active_days', 'lines_added', 'lines_deleted', 'lines_net']`
  - `src/tests/fixtures/stats.py:481` - `keys: ['prs_opened', 'prs_merged', 'issues_opened', 'issues_closed', 'time_to_first_review_p50', ...`
  - `src/tests/fixtures/stats.py:513` - `keys: ['prs_merged', 'time_to_merge_p50', 'time_to_merge_p90', 'pr_size_p50']`
  - `src/tests/fixtures/stats.py:522` - `keys: ['prs_opened', 'prs_merged', 'issues_opened', 'issues_closed', 'time_to_first_review_p50', ...`
  - `src/tests/fixtures/stats.py:628` - `keys: ['workflow_runs', 'workflow_success_rate', 'workflow_duration_p50', 'workflow_duration_p90'...`
  - `src/tests/fixtures/stats.py:653` - `keys: ['workflow_runs', 'workflow_success_rate', 'workflow_duration_p50', 'workflow_duration_p90'...`
  - `src/tests/fixtures/stats.py:667` - `keys: ['deployments', 'lead_time_p50', 'lead_time_p90', 'change_failure_rate', 'time_to_restore_p...`
  - `src/tests/fixtures/stats.py:693` - `keys: ['deployments', 'lead_time_p50', 'lead_time_p90', 'change_failure_rate', 'time_to_restore_p...`
  - `src/tests/fixtures/stats.py:705` - `keys: ['deployments', 'lead_time_p50', 'lead_time_p90', 'change_failure_rate', 'time_to_restore_p...`
  - `src/tests/fixtures/stats.py:730` - `keys: ['workflow_runs', 'workflow_success_rate', 'workflow_duration_p50', 'workflow_duration_p90'...`
  - `src/tests/fixtures/stats.py:840` - `keys: ['stars_added', 'stars_total', 'forks_added', 'forks_total']`
  - `src/wambatic/reports/figures.py:40` - `keys: ['light', 'dark']`
  - `src/wambatic/reports/html.py:31` - `keys: ['<', '>', '&']`
  - `src/wambatic/reports/rows.py:47` - `keys: ['workflow_runs', 'workflow_success_rate', 'workflow_duration_p50', 'workflow_duration_p90'...`
  - `src/wambatic/settings.py:55` - `keys: ['s', 'm', 'h', 'd', 'w']`
  - `src/wambatic/stats/compute.py:14` - `keys: ['activity', 'flow', 'delivery', 'popularity']`
- **Recommendation:** As for `non-alphabetical-literal`: sort, or accept where the key order is the order GitHub returns or the order a table shows.

### Rule: reexport-in-non-init

- **Severity:** low
- **Instance count:** 72 (src/tests: 69, src/wambatic: 3)
- **Locations:**
  - `src/tests/fetch/test_base.py:139` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_cache.py:17` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_client.py:19` - `Canned = server_module.Canned` (`Canned = server_module.Canned` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:23` - `Canned = tests.fixtures.fetch.server.Canned` (`Canned = tests.fixtures.fetch.server.Canned` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:24` - `FakeCommit = tests.fixtures.fetch.upstream.FakeCommit` (`FakeCommit = tests.fixtures.fetch.upstream.FakeCommit` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:25` - `FakeIssue = tests.fixtures.fetch.upstream.FakeIssue` (`FakeIssue = tests.fixtures.fetch.upstream.FakeIssue` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:26` - `FakePull = tests.fixtures.fetch.upstream.FakePull` (`FakePull = tests.fixtures.fetch.upstream.FakePull` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:27` - `FakeFork = tests.fixtures.fetch.upstream.FakeFork` (`FakeFork = tests.fixtures.fetch.upstream.FakeFork` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:28` - `FakeRepo = tests.fixtures.fetch.upstream.FakeRepo` (`FakeRepo = tests.fixtures.fetch.upstream.FakeRepo` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:29` - `FakeStar = tests.fixtures.fetch.upstream.FakeStar` (`FakeStar = tests.fixtures.fetch.upstream.FakeStar` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:30` - `Upstream = tests.fixtures.fetch.upstream.Upstream` (`Upstream = tests.fixtures.fetch.upstream.Upstream` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:1661` - `FakeRelease = tests.fixtures.fetch.upstream.FakeRelease` (`FakeRelease = tests.fixtures.fetch.upstream.FakeRelease` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_fetcher.py:1662` - `FakeRun = tests.fixtures.fetch.upstream.FakeRun` (`FakeRun = tests.fixtures.fetch.upstream.FakeRun` at module scope in non-__init__.py file)
  - `src/tests/fetch/test_server.py:7` - `Canned = tests.fixtures.fetch.server.Canned` (`Canned = tests.fixtures.fetch.server.Canned` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:20` - `Canned = tests.fixtures.fetch.server.Canned` (`Canned = tests.fixtures.fetch.server.Canned` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:383` - `OWNER_REPOSITORIES_OK = Recorded.OWNER_REPOSITORIES_OK` (`OWNER_REPOSITORIES_OK = Recorded.OWNER_REPOSITORIES_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:384` - `REPOSITORY_OK = Recorded.REPOSITORY_OK` (`REPOSITORY_OK = Recorded.REPOSITORY_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:385` - `COMMIT_HISTORY_OK = Recorded.COMMIT_HISTORY_OK` (`COMMIT_HISTORY_OK = Recorded.COMMIT_HISTORY_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:386` - `COMPARE_AHEAD = Recorded.COMPARE_AHEAD` (`COMPARE_AHEAD = Recorded.COMPARE_AHEAD` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:387` - `COMMIT_COUNTS_OK = Recorded.COMMIT_COUNTS_OK` (`COMMIT_COUNTS_OK = Recorded.COMMIT_COUNTS_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:388` - `PULL_REQUESTS_OK = Recorded.PULL_REQUESTS_OK` (`PULL_REQUESTS_OK = Recorded.PULL_REQUESTS_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:389` - `ISSUES_OK = Recorded.ISSUES_OK` (`ISSUES_OK = Recorded.ISSUES_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:390` - `RELEASES_OK = Recorded.RELEASES_OK` (`RELEASES_OK = Recorded.RELEASES_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:391` - `WORKFLOW_RUNS_OK = Recorded.WORKFLOW_RUNS_OK` (`WORKFLOW_RUNS_OK = Recorded.WORKFLOW_RUNS_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:392` - `WORKFLOW_RUN_OK = Recorded.WORKFLOW_RUN_OK` (`WORKFLOW_RUN_OK = Recorded.WORKFLOW_RUN_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:393` - `STARGAZERS_OK = Recorded.STARGAZERS_OK` (`STARGAZERS_OK = Recorded.STARGAZERS_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:394` - `FORKS_OK = Recorded.FORKS_OK` (`FORKS_OK = Recorded.FORKS_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:395` - `BOT_REVIEWS_OK = Recorded.BOT_REVIEWS_OK` (`BOT_REVIEWS_OK = Recorded.BOT_REVIEWS_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:454` - `REPO = Recorded.REPO` (`REPO = Recorded.REPO` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:455` - `REPO_ETAG = Recorded.REPO_ETAG` (`REPO_ETAG = Recorded.REPO_ETAG` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:460` - `USER_OK = Recorded.USER_OK` (`USER_OK = Recorded.USER_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/fetch/responses.py:461` - `ORGANIZATION_OK = Recorded.ORGANIZATION_OK` (`ORGANIZATION_OK = Recorded.ORGANIZATION_OK` at module scope in non-__init__.py file)
  - `src/tests/fixtures/reports.py:26` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/fixtures/stats.py:17` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/reports/test_figures.py:15` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/reports/test_html.py:21` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/reports/test_html_browser.py:15` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/reports/test_service.py:23` - `Subject = wambatic.fetch.base.Subject` (`Subject = wambatic.fetch.base.Subject` at module scope in non-__init__.py file)
  - `src/tests/reports/test_service.py:24` - `UsageError = wambatic.reports.errors.UsageError` (`UsageError = wambatic.reports.errors.UsageError` at module scope in non-__init__.py file)
  - `src/tests/reports/test_service.py:25` - `SettingsError = wambatic.settings.SettingsError` (`SettingsError = wambatic.settings.SettingsError` at module scope in non-__init__.py file)
  - `src/tests/reports/test_service.py:26` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/reports/test_service.py:27` - `StatsRequest = wambatic.stats.base.StatsRequest` (`StatsRequest = wambatic.stats.base.StatsRequest` at module scope in non-__init__.py file)
  - `src/tests/reports/test_service.py:28` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/reports/test_terminal.py:20` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/reports/test_web.py:196` - `NOW = tests.fixtures.stats.NOW` (`NOW = tests.fixtures.stats.NOW` at module scope in non-__init__.py file)
  - `src/tests/stats/test_activity.py:16` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/stats/test_activity.py:17` - `Series = wambatic.stats.base.Series` (`Series = wambatic.stats.base.Series` at module scope in non-__init__.py file)
  - `src/tests/stats/test_activity.py:18` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/stats/test_base.py:9` - `Bucket = wambatic.stats.base.Bucket` (`Bucket = wambatic.stats.base.Bucket` at module scope in non-__init__.py file)
  - `src/tests/stats/test_base.py:10` - `Series = wambatic.stats.base.Series` (`Series = wambatic.stats.base.Series` at module scope in non-__init__.py file)
  - `src/tests/stats/test_buckets.py:11` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/stats/test_buckets.py:12` - `Bucket = wambatic.stats.base.Bucket` (`Bucket = wambatic.stats.base.Bucket` at module scope in non-__init__.py file)
  - `src/tests/stats/test_buckets.py:14` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/stats/test_compute.py:22` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/stats/test_compute.py:24` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/stats/test_delivery.py:16` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/stats/test_delivery.py:17` - `Series = wambatic.stats.base.Series` (`Series = wambatic.stats.base.Series` at module scope in non-__init__.py file)
  - `src/tests/stats/test_delivery.py:18` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/stats/test_flow.py:15` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/stats/test_flow.py:16` - `Series = wambatic.stats.base.Series` (`Series = wambatic.stats.base.Series` at module scope in non-__init__.py file)
  - `src/tests/stats/test_flow.py:17` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/stats/test_percentile.py:10` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/stats/test_popularity.py:14` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/tests/stats/test_popularity.py:15` - `Series = wambatic.stats.base.Series` (`Series = wambatic.stats.base.Series` at module scope in non-__init__.py file)
  - `src/tests/stats/test_popularity.py:16` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/tests/test_cli.py:42` - `Subject = wambatic.fetch.base.Subject` (`Subject = wambatic.fetch.base.Subject` at module scope in non-__init__.py file)
  - `src/tests/test_cli.py:43` - `UsageError = wambatic.reports.errors.UsageError` (`UsageError = wambatic.reports.errors.UsageError` at module scope in non-__init__.py file)
  - `src/tests/test_cli.py:44` - `SettingsError = wambatic.settings.SettingsError` (`SettingsError = wambatic.settings.SettingsError` at module scope in non-__init__.py file)
  - `src/tests/test_cli.py:271` - `UTC = datetime.UTC` (`UTC = datetime.UTC` at module scope in non-__init__.py file)
  - `src/wambatic/reports/html.py:23` - `Granularity = wambatic.stats.base.Granularity` (`Granularity = wambatic.stats.base.Granularity` at module scope in non-__init__.py file)
  - `src/wambatic/reports/rows.py:14` - `UNATTRIBUTED = wambatic.stats.activity.UNATTRIBUTED` (`UNATTRIBUTED = wambatic.stats.activity.UNATTRIBUTED` at module scope in non-__init__.py file)
  - `src/wambatic/reports/rows.py:21` - `SIZE_METRIC = wambatic.stats.flow.SIZE_METRIC` (`SIZE_METRIC = wambatic.stats.flow.SIZE_METRIC` at module scope in non-__init__.py file)
- **Recommendation:** Use the full path (`datetime.UTC`, `wambatic.stats.base.Granularity`) at each use instead of a module-level alias. In `src/tests/` see Decision 1.

### Rule: typing-deprecated-alias

- **Severity:** low
- **Instance count:** 24 (src/tests: 18, src/wambatic: 6)
- **Variants:** typing.Callable -> collections.abc.Callable (15); typing.Iterator -> collections.abc.Iterator (4); typing.Awaitable -> collections.abc.Awaitable (1); typing.Sequence -> collections.abc.Sequence (3); typing.Iterable -> collections.abc.Iterable (1)
- **Locations:**
  - `src/tests/conftest.py:22` - `MakeClient = typing.Callable[..., wambatic.fetch.client.GitHubClient]`
  - `src/tests/conftest.py:23` - `MakeFetcher = typing.Callable[..., wambatic.fetch.base.Fetcher]`
  - `src/tests/conftest.py:80` - `) -> typing.Iterator[MakeFetcher]:`
  - `src/tests/conftest.py:196` - `def stats_cache(tmp_path: pathlib.Path) -> typing.Iterator[wambatic.fetch.cache.Cache]:`
  - `src/tests/fetch/test_cache.py:31` - `def cache(cache_path: pathlib.Path) -> typing.Iterator[wambatic.fetch.cache.Cache]:`
  - `src/tests/reports/test_html.py:533` - `report: wambatic.reports.html.HtmlReport, keep: typing.Callable[[str], bool]`
  - `src/tests/reports/test_html_browser.py:33` - `) -> collections.abc.Iterator[typing.Callable[..., Opened]]:`
  - `src/tests/reports/test_html_browser.py:80` - `open_report: typing.Callable[..., Opened], org_report: wambatic.reports.html.HtmlReport`
  - `src/tests/reports/test_html_browser.py:93` - `open_report: typing.Callable[..., Opened],`
  - `src/tests/reports/test_html_browser.py:109` - `open_report: typing.Callable[..., Opened],`
  - `src/tests/reports/test_html_browser.py:132` - `open_report: typing.Callable[..., Opened], org_report: wambatic.reports.html.HtmlReport`
  - `src/tests/reports/test_html_browser.py:157` - `open_report: typing.Callable[..., Opened],`
  - `src/tests/reports/test_html_browser.py:171` - `open_report: typing.Callable[..., Opened],`
  - `src/tests/reports/test_html_browser.py:183` - `open_report: typing.Callable[..., Opened],`
  - `src/tests/test_cli.py:821` - `def restore_logger() -> typing.Iterator[None]:`
  - `src/tests/test_cli.py:834` - `def raising(error: BaseException) -> typing.Callable[..., typing.Awaitable[None]]:`
  - `src/tests/test_cli.py:834` - `def raising(error: BaseException) -> typing.Callable[..., typing.Awaitable[None]]:`
  - `src/tests/test_cli.py:1453` - `run: typing.Callable[[uvicorn.Server], None] \| None = None,`
  - `src/wambatic/reports/html.py:170` - `headers: typing.Sequence[str],`
  - `src/wambatic/reports/html.py:171` - `rows: typing.Sequence[typing.Sequence[str]],`
  - `src/wambatic/reports/html.py:173` - `footer: typing.Sequence[str] \| None = None,`
  - `src/wambatic/reports/html.py:229` - `build: typing.Callable[`
  - `src/wambatic/reports/html.py:232` - `note: typing.Callable[[wambatic.reports.rows.PeriodTable], str],`
  - `src/wambatic/reports/rows.py:206` - `label: str, partial: frozenset[str], values: typing.Iterable[float \| None]`
- **Recommendation:** Replace `typing.Callable/Iterator/Sequence/...` with `collections.abc.*`; mechanical.

### Rule: silent-broad-except

- **Severity:** low
- **Instance count:** 2 (src/wambatic: 2)
- **Variants:** no logger and no raise in body (2)
- **Locations:**
  - `src/wambatic/reports/web.py:146` - `except Exception as e:`
  - `src/wambatic/reports/web.py:402` - `except Exception as e:`
- **Recommendation:** Both handlers log through `error_response()` (`web.py:71-78`), which calls `logger.exception` for a 500 and returns a domain message otherwise. Accept with `# auditme: accept[silent-broad-except] logged by error_response()`; the redaction gap at `web.py:76` is a separate finding (Sec5/S4).

### Rule: mixed-raise-types

- **Severity:** low
- **Instance count:** 1 (src/wambatic: 1)
- **Variants:** convert mixes stdlib (['TypeError']) with project errors (['SettingsError']) (1)
- **Locations:**
  - `src/wambatic/settings.py:77` - `convert: raises ['SettingsError', 'TypeError']`
- **Recommendation:** `settings.convert` raises `TypeError` for an annotation it has no conversion for: a programmer error. Raise `SettingsError`, or accept with a scoped marker (see Decision 2).

### Rule: sibling-errors-no-common-base

- **Severity:** low
- **Instance count:** 1 (src/wambatic: 1)
- **Variants:** 3 Error classes co-defined with no shared parent: ['OutputError', 'ServeError', 'UsageError'] (1)
- **Locations:**
  - `src/wambatic/reports/errors.py:1` - `classes: OutputError, ServeError, UsageError`
- **Recommendation:** Give `OutputError`, `ServeError` and `UsageError` a shared `ReportsError` base, as `fetch` has `FetchError`.

### Rule: layer-has-domain-error-raises-stdlib

- **Severity:** medium
- **Instance count:** 21 (src/wambatic: 21)
- **Variants:** fetch package defines *Error classes but this module raises ValueError (7); fetch package defines *Error classes but this module raises RuntimeError (1); reports package defines *Error classes but this module raises ValueError (7); stats package defines *Error classes but this module raises ValueError (6)
- **Locations:**
  - `src/wambatic/fetch/base.py:36` - `raise ValueError('a repo subject needs a name')`
  - `src/wambatic/fetch/base.py:38` - `raise ValueError(f'a {self.kind} subject has no name')`
  - `src/wambatic/fetch/base.py:43` - `raise ValueError(f'a {self.kind} subject has no repo name')`
  - `src/wambatic/fetch/base.py:689` - `raise ValueError(f'unknown resources: {", ".join(unknown)}')`
  - `src/wambatic/fetch/base.py:1248` - `raise ValueError(f'unknown resources: {", ".join(unknown)}')`
  - `src/wambatic/fetch/cache.py:206` - `raise ValueError('cache times must be timezone-aware')`
  - `src/wambatic/fetch/cache.py:541` - `raise ValueError(f'every record and the state must belong to {repo}')`
  - `src/wambatic/fetch/client.py:209` - `raise RuntimeError('GitHubClient must be used inside 'async with'')`
  - `src/wambatic/reports/figures.py:549` - `raise ValueError(`
  - `src/wambatic/reports/figures.py:564` - `raise ValueError(f'build_calendar needs a DAY result, not {day.request.granularity}')`
  - `src/wambatic/reports/html.py:108` - `raise ValueError(f'total must be a TOTAL result, not {report.total.request.granularity}')`
  - `src/wambatic/reports/html.py:110` - `raise ValueError(`
  - `src/wambatic/reports/html.py:115` - `raise ValueError(f'initial must be one of {", ".join(PERIODS)}, not {report.initial}')`
  - `src/wambatic/reports/html.py:118` - `raise ValueError(f'the {granularity} result is by {result.request.granularity}')`
  - `src/wambatic/reports/html.py:120` - `raise ValueError(f'the {granularity} result differs from the total in {difference}')`
  - `src/wambatic/stats/base.py:36` - `raise ValueError('by and by_kind are both set or both None')`
  - `src/wambatic/stats/buckets.py:64` - `raise ValueError('when must be timezone-aware')`
  - `src/wambatic/stats/buckets.py:75` - `raise ValueError('since is after until')`
  - `src/wambatic/stats/buckets.py:128` - `raise ValueError(f'{day} is outside the buckets')`
  - `src/wambatic/stats/buckets.py:23` - `raise ValueError(f'{granularity} has no bucket start; its bucket depends on the range')`
  - `src/wambatic/stats/buckets.py:40` - `raise ValueError(f'{granularity} has no next bucket')`
- **Recommendation:** Same sites as A3; see Decision 2.

### Rule: mutable-store-without-copy

- **Severity:** low
- **Instance count:** 2 (src/wambatic: 2)
- **Variants:** GraphQLError.__init__ stores dict/list parameter `errors` by reference (1); CacheVersionError.__init__ stores dict/list parameter `differences` by reference (1)
- **Locations:**
  - `src/wambatic/fetch/errors.py:16` - `self.errors = errors`
  - `src/wambatic/fetch/errors.py:43` - `self.differences = differences`
- **Recommendation:** Store `tuple(errors)` / `dict(differences)` (or a `MappingProxyType`) so the exception does not alias the caller's container.

### Rule: filesystem-op-without-envelope

- **Severity:** medium
- **Instance count:** 1 (src/wambatic: 1)
- **Variants:** render_html calls `mkdir` with no surrounding try/except in the function body (1)
- **Locations:**
  - `src/wambatic/reports/html.py:607` - `out.parent.mkdir(parents=True, exist_ok=True)`
- **Recommendation:** Move `out.parent.mkdir` inside the `try` that translates `OSError` to `OutputError` (the CLI catches `OSError` at `cli.py:231`, but `render_html` is also public API).

### Rule: assert-never-missing

- **Severity:** medium
- **Instance count:** 3 (src/wambatic: 3)
- **Variants:** if/elif chain on `resource` with 5 string-equality arms has fall-through else; should end with `else: typing.assert_never(resource)` (1); if/elif chain on `resource` with 4 string-equality arms has fall-through else; should end with `else: typing.assert_never(resource)` (1); if/elif chain on `resource` with 3 string-equality arms has fall-through else; should end with `else: typing.assert_never(resource)` (1)
- **Locations:**
  - `src/wambatic/fetch/base.py:1272` - `if resource == 'commits':`
  - `src/wambatic/fetch/base.py:1276` - `elif resource == 'releases':`
  - `src/wambatic/fetch/base.py:1278` - `elif resource == 'workflow_runs':`
- **Recommendation:** End each chain on `resource` with `else: typing.assert_never(resource)` so mypy checks every resource is handled.

### Rule: duplicated-word

- **Severity:** low
- **Instance count:** 1 (src/wambatic: 1)
- **Variants:** duplicated word 'bucket' (1)
- **Locations:**
  - `src/wambatic/stats/buckets.py:73` - `For TOTAL, the one bucket Bucket(since, 'total')."""`
- **Recommendation:** Docstring typo: "the one bucket Bucket(...)" - reword.

### Rule: missing-raises-section

- **Severity:** low
- **Instance count:** 23 (src/wambatic: 23)
- **Locations:**
  - `src/wambatic/cli.py:180` - `def check_report(report: Report, settings: wambatic.settings.Settings) -> None:` (check_report raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/cli.py:220` - `def render_html_report(` (render_html_report raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/auth.py:7` - `def resolve_token() -> str:` (resolve_token raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/base.py:571` - `async def owner_kind(self, login: str) -> typing.Literal['user', 'org']:` (owner_kind raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/base.py:605` - `async def list_repos(self, subject: Subject) -> list[Repo]:` (list_repos raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/base.py:771` - `async def line_counts(self, repo: Repo, new: list[NewCommit]) -> list[Commit]:` (line_counts raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/client.py:77` - `def require_date(date: datetime.datetime \| None) -> datetime.datetime:` (require_date raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/client.py:149` - `async def graphql_dated(` (graphql_dated raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/client.py:169` - `async def rest_get(` (rest_get raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/client.py:252` - `async def wait_for_reset(self, endpoint: str, reset_at: datetime.datetime) -> None:` (wait_for_reset raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/fetch/client.py:269` - `async def request(` (request raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/reports/service.py:64` - `def parse_date(text: str, flag: str = 'a date') -> datetime.date:` (parse_date raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/reports/service.py:88` - `def make_request(` (make_request raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/reports/service.py:210` - `async def build_results(` (build_results raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/reports/web.py:235` - `def parse_query(settings: wambatic.settings.Settings, raw: RawQuery, *, page: bool) -> Query:` (parse_query raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/reports/web.py:512` - `def check_bind(host: str, allow_remote: bool) -> None:` (check_bind raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/reports/web.py:526` - `def listen(host: str, port: int) -> socket.socket:` (listen raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/reports/web.py:539` - `def serve(` (serve raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/reports/web.py:368` - `async def results_or_job(` (results_or_job raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/settings.py:69` - `def parse_duration(text: str) -> datetime.timedelta:` (parse_duration raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/settings.py:77` - `def convert(key: str, annotation: object, value: object) -> object:` (convert raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/stats/compute.py:22` - `def resources_for(groups: frozenset[str]) -> frozenset[str]:` (resources_for raises a project *Error but docstring lacks a Raises: section)
  - `src/wambatic/stats/compute.py:145` - `async def compute(` (compute raises a project *Error but docstring lacks a Raises: section)
- **Recommendation:** Add a `Raises:` section naming the domain errors each function raises (A4 then checks it).

### Rule: subprocess-without-memoisation

- **Severity:** low
- **Instance count:** 1 (src/wambatic: 1)
- **Variants:** resolve_token shells out via subprocess without @functools.cache (1)
- **Locations:**
  - `src/wambatic/fetch/auth.py:13` - `result = subprocess.run(`
- **Recommendation:** A24 found `resolve_token` runs at most once per sync. Accept with `# auditme: accept[subprocess-without-memoisation] runs once per sync; a cached token would outlive gh auth changes in the long-running server`.

## Phase B per-question results

### A1: External call envelope
- Hits:
  - `src/wambatic/version.py:3` - `importlib.metadata.version('wambatic')` reads package metadata at import time with no envelope; `PackageNotFoundError` escapes
  - `src/wambatic/settings.py:147` - `path.read_text()` translates only `FileNotFoundError`; other `OSError`s and `UnicodeDecodeError` escape untranslated
  - `src/wambatic/fetch/auth.py:13` - `subprocess.run(['gh', ...])` translates only `FileNotFoundError` and `TimeoutExpired`; other `OSError`s (e.g. `PermissionError`) escape
  - `src/wambatic/fetch/client.py:133` - `self.session.close()` (aiohttp) has no envelope
  - `src/wambatic/fetch/client.py:211` - `session.request` / `raw.read()` / `raw.json()` in `send` have no translating envelope; aiohttp errors such as `ClientPayloadError`, `InvalidURL` escape
  - `src/wambatic/fetch/client.py:290` - after retries run out, the aiohttp `ClientConnectionError` / `TimeoutError` is re-raised as is, not translated to `FetchError`
  - `src/wambatic/fetch/client.py:327` - an unclassified transient status out of retries raises third-party `aiohttp.ClientResponseError` (built by `status_error`)
  - `src/wambatic/fetch/client.py:333` - any other unclassified status raises third-party `aiohttp.ClientResponseError`
  - `src/wambatic/fetch/cache.py:372` - `path.parent.mkdir` in `Cache.open` has no envelope
  - `src/wambatic/fetch/cache.py:373` - `sqlite3.connect` has no envelope; the PRAGMA and schema calls (375-377) sit inside `except BaseException`, which re-raises `sqlite3.Error` untranslated
  - `src/wambatic/fetch/cache.py:387` - `connection.close()` has no envelope
  - `src/wambatic/fetch/cache.py:394` - `executemany` / `execute` (also 403) in `check_identity` let `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:409` - `execute` in `recorded_identity` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:419` - `execute` in `version_override_at` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:430` - `execute` / `executemany` (also 433) in `upsert_repos` let `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:467` - `execute` (also 472) in `read_repos` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:481` - `execute` in `sync_state` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:503` - `execute` in `put_state` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:550` - `execute` / `executemany` (550-555) in `write_rows` let `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:580` - `execute` in `read_rows` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:865` - `execute` in `unfinished_runs` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:874` - `execute` in `etag` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:881` - `execute` in `store_etag` lets `sqlite3.Error` escape
  - `src/wambatic/fetch/cache.py:909` - `path.exists`, `sqlite3.connect` (911), the queries at 913-934 (inside `try`/`finally` only) and `stat` (941) in `inspect_cache` have no translating envelope
  - `src/wambatic/fetch/cache.py:962` - `candidate.unlink()` catches only `FileNotFoundError`; `PermissionError` and other `OSError`s escape
  - `src/wambatic/reports/html.py:125` - `resource.read_text(encoding='utf-8')` in `read_template` has no envelope
  - `src/wambatic/reports/html.py:597` - `plotly.offline.get_plotlyjs()` reads the bundled plotly.js file with no envelope
  - `src/wambatic/reports/service.py:83` - `zoneinfo.ZoneInfo` translates `ZoneInfoNotFoundError` and `ValueError` only; an `OSError` reading the tz file escapes
  - `src/wambatic/reports/web.py:573` - `uvicorn.Server(config).run(...)` has no translating envelope (only `try`/`finally`)
  - `src/wambatic/cli.py:400` - `os.open(os.devnull)` / `os.dup2` in the `BrokenPipeError` handler have no envelope
  - `bin/record-fixtures.py:108` - `urllib.request.urlopen` has no envelope
  - `bin/record-fixtures.py:109` - `json.load(response)` has no envelope
  - `bin/record-fixtures.py:235` - `OUT.write_text` has no envelope
  - `bin/record-fixtures.py:236` - `subprocess.run(['ruff', ...], check=True)` has no envelope
- Files inspected: 34; 24 had no external-IO call (terminal/stream writes not counted)

### A2: Except tuple coverage
- Hits:
  - `src/wambatic/settings.py:146` - `try` over `path.read_text()` catches only `FileNotFoundError`; missing `OSError` and `UnicodeDecodeError` (body decodes text)
  - `src/wambatic/fetch/auth.py:12` - `try` over `subprocess.run(..., text=True)` catches `FileNotFoundError`, `TimeoutExpired`; missing `OSError` and `UnicodeDecodeError` (`text=True` decodes output)
  - `src/wambatic/fetch/cache.py:961` - `try` over `candidate.unlink()` catches only `FileNotFoundError`; missing `OSError`
  - `src/wambatic/cli.py:231` - `except OSError` around `render_html`, whose body reaches `html_document` -> `read_template` (`read_text(encoding='utf-8')`); missing `UnicodeDecodeError`
  - `src/wambatic/reports/service.py:82` - `try` over `zoneinfo.ZoneInfo` (reads tzdata from disk) catches `ZoneInfoNotFoundError`, `ValueError`; missing `OSError`
- Files inspected: 34; 27 had no matching `try`/`except`. Passing: `cache.py:374-382` and `html.py:612-619` (`BaseException`); `client.py:218-222` (`ValueError` covers `JSONDecodeError` and `UnicodeDecodeError`)

### A3: Domain-error layering
- Hits:
  - `src/wambatic/settings.py:110` - `TypeError` (no conversion for annotation); package defines `SettingsError`
  - `src/wambatic/fetch/client.py:209` - `RuntimeError` (client used outside `async with`)
  - `src/wambatic/fetch/client.py:222` - bare `raise` re-raises the `ValueError`/`JSONDecodeError` from `raw.json` for an OK response
  - `src/wambatic/fetch/cache.py:206` - `ValueError` (naive datetime in `to_text`)
  - `src/wambatic/fetch/cache.py:541` - `ValueError` (record or state belongs to another repo)
  - `src/wambatic/fetch/base.py:36` - `ValueError` in `Subject.__post_init__` (repo subject with no name)
  - `src/wambatic/fetch/base.py:38` - `ValueError` in `Subject.__post_init__` (non-repo subject with a name)
  - `src/wambatic/fetch/base.py:43` - `ValueError` in `Subject.full_name`
  - `src/wambatic/fetch/base.py:689` - `ValueError` (unknown resources in `provenance`)
  - `src/wambatic/fetch/base.py:1248` - `ValueError` (unknown resources in `sync`)
  - `src/wambatic/stats/base.py:36` - `ValueError` in `Series.__post_init__`
  - `src/wambatic/stats/buckets.py:23` - `ValueError` (TOTAL has no bucket start)
  - `src/wambatic/stats/buckets.py:40` - `ValueError` (TOTAL has no next bucket)
  - `src/wambatic/stats/buckets.py:64` - `ValueError` (naive `when`)
  - `src/wambatic/stats/buckets.py:75` - `ValueError` (`since` after `until`; package has `InvalidRangeError`)
  - `src/wambatic/stats/buckets.py:128` - `ValueError` (day outside the buckets)
  - `src/wambatic/reports/html.py:108`, `:110`, `:115`, `:118`, `:120` - `ValueError` in `check_report`
  - `src/wambatic/reports/figures.py:549` - `ValueError` (`build_range_figures` given a non-TOTAL result)
  - `src/wambatic/reports/figures.py:564` - `ValueError` (`build_calendar` given a non-DAY result)
- Files inspected: 34; 19 had no `raise`; of the 15 with one, 7 had no hit. `bin/record-fixtures.py:114`, `123`, `133` raise `RuntimeError` but the script defines no `*Error` class, so not flagged.

### A4: Docstring `Raises` accuracy
- Hits: no hits
- Files inspected: 34; none has a docstring with a `Raises:` section (raises are mentioned only in prose, e.g. `auth.py:8`, `cache.py:369-371`, `buckets.py:61-62`, `html.py:584-585`, `figures.py:546-547`)

### A16: CLI entry envelope
- Hits: no hits
- Entry points treated as such: `cli.main` (returns `int`), `cli.execute` (takes `Wambatic`), `cli.run_report` (takes `Report`), `cli.run_cache` (takes `CacheCommand`). None contains a `raise`; the validation raises are in helpers `check_verbosity:177` and `check_report:183,185,187,193`, reached through `execute` inside `main`'s `try` at `cli.py:382-383`.
- Files inspected: 34; 33 had no CLI entry function

### A19: Wrong logger level for broad-except
- Hits:
  - `src/wambatic/fetch/cache.py:380` - `except BaseException` closes the connection and re-raises without logging
  - `src/wambatic/reports/html.py:617` - `except BaseException` unlinks the temp file and re-raises without logging
  - `src/wambatic/reports/web.py:146` - `except Exception` in `Jobs.execute` degrades gracefully (marks the job failed); via `error_response` it logs with `logger.exception` only for status 500, not at all otherwise
  - `src/wambatic/reports/web.py:402` - `except Exception` in the `convert_errors` middleware degrades gracefully into an HTTP reply, with the same split logging via `error_response` (`web.py:76`)
- Files inspected: 34; 30 had no `except Exception` / `except BaseException`. `cli.py:402` passes (uses `logger.exception` for a truly unexpected error)

### A22: Fall-through after partial handling
- Hits:
  - `src/wambatic/fetch/base.py:757` - `compare` translates `NotFoundError` to `None`; `update_commits` (829-830) then returns `None`, and `sync_commits` (844-850) falls through to `backfill_commits`, re-reading the whole history; the INFO log names the reason "history rewritten", not the 404
- Files inspected: 34; 19 had no `if`/`else` chain mixing `raise` and `return`

### A5: Two sources of truth
- Hits:
  - `src/wambatic/fetch/base.py:529-540` - `Fetcher.__init__` with an injected `client` ignores `token`, and keeps its own `self.settings` beside `self.client.settings`. The Fetcher reads overlap, full_refresh_after, include_forks and include_archived from one; the client reads max_retries, on_rate_limit and stats_retries from the other. Nothing documents or enforces that they are the same object.
  - `src/wambatic/stats/base.py:46-49` - `StatsRequest.tz` and `StatsRequest.settings.timezone` should agree but nothing checks it; `compute` reads only `tz` (`stats/compute.py:57,196`); `reports/base.py:57-61` emits both, so they can disagree in the JSON. Agreement depends on each caller (`cli.py:249`, `reports/web.py:254-266`).
  - `src/wambatic/reports/service.py:88-117` - `make_request` takes `tz` and `settings` separately and stores both, so `tz` silently wins over `settings.stats.timezone`; no precedence documented
  - `src/wambatic/reports/service.py:210-221` - `build_results(by_author=...)` (and `sync_target(by_author=...)`, line 170) duplicates each request's `StatsRequest.by_author`; the parameter drives `check_by_author`, the field drives `compute`; no precedence or agreement check. `reports/web.py:220-227` (`Query.by_author` beside `Query.request.by_author`) and `cli.py:257-262` pass both.
  - `src/wambatic/reports/web.py:298-303` - `make_app` parameter `check_host` duplicates config `settings.report.allow_remote`; `make_app` ignores the config and trusts the parameter; only `serve` derives one from the other (line 557); undocumented
- Files inspected: 34; 24 had no matching construct

### A6: Stage method dual-path
- Hits: no hits
- Files inspected: 34; 29 had no pipeline-stage class (the 5 with one: `Recorder`, `GitHubClient`, `Fetcher`, `Cache`, `Jobs`)

### A7: Constructor purity
- Hits: no hits
- Files inspected: 34; 28 had no `__init__`

### A8: Late dataclass mutation
- Hits:
  - `src/wambatic/stats/activity.py:83,94-101` - `Tally` instances built at lines 83, 97, 99, 101 are mutated after construction through `.add()`; line 96 mutates a field directly (`totals[index].logins.add(key)`)
  - `src/wambatic/reports/web.py:119` - `SyncJob(...)` built in `Jobs.start`, then fields set later: `job.phase` (143, 145), `job.status`/`job.error` (147), `job.phase` (148), `job.subject` (353); its default-factory `SyncProgress` is mutated by `Fetcher.sync` at `src/wambatic/fetch/base.py:1266-1267,1288,1292`
- Files inspected: 34; 18 had no dataclass instance built inside a function

### A13: Same value to multiple structural slots
- Hits:
  - `src/wambatic/fetch/base.py:718-719` - `SyncState(... synced_at=now, full_synced_at=full_synced_at or now)` puts the same `now` in both slots when `full_synced_at` is None; documented only in the `plan_full_read` docstring (line 946), not at the constructor
  - `src/wambatic/fetch/client.py:189` - `RestResponse(304, None, etag, None, ...)` passes `None` to both the `data` and `next_url` slots
  - `src/wambatic/reports/html.py:438` - `PopularityRow('', 0, 0, 0)` passes `0` to `stars`, `forks`, `watchers`, with no factory or docstring
- Files inspected: 34; 18 had no multi-slot constructor call

### A15: Duplicate constructor / serialisation logic
- Hits:
  - `src/wambatic/fetch/base.py:472`, `src/wambatic/fetch/base.py:806`, `src/wambatic/fetch/cache.py:270` - `Commit` built with the full field set at three sites, no shared helper
  - `src/wambatic/fetch/base.py:299`, `src/wambatic/fetch/cache.py:247` - `Repo` built with the full field set at two sites; many defaulted fields would drift silently
  - `src/wambatic/fetch/base.py:370`, `src/wambatic/fetch/cache.py:285` - `PullRequest` at two sites (`labels`, `first_commit_at` defaulted)
  - `src/wambatic/fetch/base.py:393`, `src/wambatic/fetch/cache.py:303` - `Issue` at two sites
  - `src/wambatic/fetch/base.py:411`, `src/wambatic/fetch/cache.py:315` - `Release` at two sites
  - `src/wambatic/fetch/base.py:429`, `src/wambatic/fetch/cache.py:326` - `WorkflowRun` at two sites
  - `src/wambatic/fetch/base.py:449`, `src/wambatic/fetch/cache.py:344` - `StarEvent` at two sites
  - `src/wambatic/fetch/base.py:459`, `src/wambatic/fetch/cache.py:351` - `Fork` at two sites
  - `src/wambatic/fetch/base.py:711`, `src/wambatic/fetch/cache.py:489` - `SyncState` in `new_state` and `Cache.sync_state` (`probe` defaulted)
  - `src/wambatic/fetch/base.py:910`, `src/wambatic/fetch/base.py:925` - `UpdatedRead(query, connection, parse)` assembled twice in `sync_updated`
  - `src/wambatic/fetch/client.py:189-196` - `RestResponse` built at two adjacent sites with the same positional field set
  - `src/wambatic/fetch/cache.py:433-461` vs `:173-177` - repos column list written again in the INSERT instead of reusing `REPO_COLUMNS`
  - `src/wambatic/fetch/cache.py:481-483` vs `:504-505` - `sync_state` column list written separately in the SELECT and the INSERT
  - `src/wambatic/fetch/cache.py:598,626,659,684,711,745,765` - each write lambda lists a record's fields again, separately from its `*_COLUMNS` tuple (lines 132, 141, 155, 156, 157, 171, 172)
  - `src/wambatic/stats/activity.py:66`, `src/wambatic/stats/flow.py:94`, `:104`, `src/wambatic/stats/delivery.py:219`, `src/wambatic/stats/popularity.py:123` - `Series(metric, unit, points)` built at five sites across four modules
  - `src/wambatic/stats/buckets.py:66`, `:81` - `Bucket(start, label(start, granularity))` repeated
  - `src/wambatic/reports/rows.py:604,620,637,661,699` - `PeriodTable` built with the full positional field set at five sites
  - `src/wambatic/reports/rows.py:331`, `:335`, `src/wambatic/reports/html.py:438` - `PopularityRow` built positionally at three sites
  - `src/wambatic/reports/figures.py:425`, `:474`, `:606` - `Figure` built with the full positional field set at three sites
  - `src/wambatic/reports/figures.py:106-290` - `Chart` and `Trace` built positionally at many sites in `CHARTS`; the `durations` helper (line 94) covers only three
  - `src/wambatic/reports/figures.py:41`, `:50` - `Theme` built twice with the same field set in `PALETTE`
- Files inspected: 34; 21 had no class built from two or more sites

### A23: Discarded multi-return
- Hits:
  - `src/wambatic/fetch/base.py:978` - `self.plan_full_read(...)` returns `(full, full_synced_at)`; both are silently discarded in `sync_releases`. The docstring says `full_synced_at` is what the new state keeps, yet `new_state` at line 994 passes `None`.
- Files inspected: 34; 22 had no call to a function returning a tuple or dataclass

### A9: Pure-named function side effects
- Hits:
  - `src/wambatic/fetch/auth.py:7` - `resolve_token` reads `os.environ` and runs subprocess `gh auth token`
  - `src/wambatic/fetch/cache.py:389` - `check_identity` reads and writes the SQLite meta table and calls `datetime.now(UTC)`
  - `src/wambatic/reports/service.py:81` - `resolve_tz` calls `zoneinfo.ZoneInfo()`, which reads the tz database file from disk
  - `src/wambatic/reports/service.py:210` - `build_results` runs `sync_target` (network sync, gh subprocess) and `stats.compute` (cache reads)
  - `src/wambatic/reports/web.py:235` - `parse_query` does tz-database I/O through `resolve_tz` (line 265)
  - `src/wambatic/reports/web.py:406` - `check_host_header` awaits `call_next`, which runs the whole downstream request handler
  - `src/wambatic/reports/web.py:512` - `check_bind` writes to stderr through `loguru.logger.warning` (line 521)
- Files inspected: 34; 22 had no pure-prefixed function

### A10: Predicate semantics
- Hits: no hits
- Files inspected: 34; 30 had no is_/has_/should_ predicate

### A11: Exhaustion via assert_never
- Hits:
  - `src/wambatic/stats/buckets.py:22` - `match` over `Granularity` in `bucket_start` ends in `case _: raise ValueError`, not `assert_never` (the wildcard catches TOTAL and any new member)
  - `src/wambatic/stats/buckets.py:39` - `match` over `Granularity` in `next_start` ends in `case _: raise ValueError`, not `assert_never`
- Files inspected: 34; 19 had no chain over a Literal or enum

### A12: assert misuse
- Hits: no hits
- Files inspected: 34; none has an `assert`

### A17: Public-surface drift
Only `src/tests/test_package.py` refers to these symbols outside their package, and only to check the re-exports exist; its parametrised `getattr` loop over `__all__` (lines 30-47, 88-90) is not counted as a use.
- Hits:
  - `src/wambatic/__init__.py:6-12` - no `__all__` symbol (Fetcher, Settings, StatsRequest, StatsResult, Subject, compute, load_settings) has a consumer outside the package except `test_package.py:36-37, 77-79`; tests use submodule paths instead (e.g. `src/tests/conftest.py:23` `wambatic.fetch.base.Fetcher`, `src/tests/test_settings.py:64` `wambatic.settings.load_settings`)
  - `src/wambatic/fetch/__init__.py:31,39,40,49,52` - BUILT_RESOURCES, Fetcher, Fork, StarEvent, SyncProgress referenced only by test_package.py
  - `src/wambatic/fetch/__init__.py:32-38,41-48,50,53-57` - RESOURCES, AuthError, Cache, CacheInfo, CacheVersionError, Commit, FetchError, GitHubClient, GraphQLError, Issue, NotFoundError, PullRequest, RateLimitError, Release, Repo, StatsPendingError, SyncReport, WorkflowRun, clear_cache, inspect_cache, resolve_token never used through `wambatic.fetch` outside the package; consumers bypass it through base/cache/errors/client/auth (e.g. `src/wambatic/cli.py:251` `wambatic.fetch.cache.Cache.open`, `src/wambatic/reports/service.py:183` and `bin/record-fixtures.py:233` `wambatic.fetch.auth.resolve_token`); only `Subject` is used through the package path (`src/wambatic/stats/base.py:54`)
  - `src/wambatic/stats/__init__.py:13,14,16,19,24,25,27` - GROUPS, Bucket, Granularity, Series, bucket_for, bucket_range, partial_buckets never used through `wambatic.stats` outside the package; consumers use `wambatic.stats.base` (e.g. `src/wambatic/cli.py:229`)
  - `src/wambatic/stats/__init__.py:21,22` - StatsRequest, StatsResult referenced only by `test_package.py:78-79`
  - `src/wambatic/reports/__init__.py:16-38` - no `__all__` symbol is used through `wambatic.reports` outside the package; every consumer goes to the submodules (e.g. `src/tests/reports/test_html.py:87` `wambatic.reports.html.html_document`)
- Files inspected: 4 `__init__.py` with `__all__`; none empty. Scan at 10:37 UTC.

### A14: Repeated computation per request
- Hits:
  - `src/wambatic/stats/compute.py:251` - `fetcher.provenance()` (cache identity, version override, every repo's sync state) runs once per `compute()`; an HTML report or `/report` page computes five requests, so five times, plus once in `service.py:192` (when `sync is None`, the CLI path) or `web.py:328` (`stale`)
  - `src/wambatic/stats/compute.py:167` - `fetcher.repos(subject)` read from the cache once per `compute()` (five times for HTML), and again inside each `provenance` call (`src/wambatic/fetch/base.py:694`)
  - `src/wambatic/stats/compute.py:137` - `fetcher.stars_hidden()` re-reads the `star_events` sync state per repo once per `compute()`; same row also read by `provenance` (`base.py:698`) and during sync (`base.py:652`, `base.py:1035`)
  - `src/wambatic/stats/compute.py:155` and `:251` - `resources_for(request.groups)` runs twice per `compute()`, on top of `cli.py:250`, `reports/service.py:190`, `reports/web.py:268`: more than ten calls in one HTML report flow
- Files inspected: 34; 29 had no matching construct

### A18: Hot-path setup
- Hits: no hits
- Files inspected: 34; 34 had no matching construct (no `on_step`/`on_log`/`on_evaluate`/`on_batch_*` methods)

### A20: Mutable module-level singleton
- Hits:
  - `src/wambatic/stats/delivery.py:36` - `UNITS = dict(DELIVERY_METRICS)` is a mutable `dict`, read at `src/wambatic/reports/rows.py:25` (`wambatic.stats.delivery.UNITS`) and through that alias by `reports/terminal.py:54`
  - `src/wambatic/reports/figures.py:40` - `PALETTE` is a mutable `dict`, read at `src/wambatic/reports/html.py:158` and `:567`, `src/tests/reports/test_figures.py:260`, `src/tests/reports/test_html_browser.py:17`, `:18`, `:189`
  - `src/wambatic/__init__.py:5` - `__all__` is a `list`, read at `src/tests/test_package.py:27` and `:30`
  - `src/wambatic/fetch/__init__.py:30` - `__all__` is a `list`, read at `src/tests/test_package.py:40`, `:84`, `:123`, `:133`
  - `src/wambatic/stats/__init__.py:12` - `__all__` is a `list`, read at `src/tests/test_package.py:45`
  - `src/wambatic/reports/__init__.py:15` - `__all__` is a `list`, read at `src/tests/test_package.py:64`, `:68`, `:88`, `:113`
- Files inspected: 34; 22 had no matching construct. Not read from another module (all three forms searched): `settings.py` `DURATION_UNITS`/`SECTIONS`, `fetch/base.py` `PROBES`, `reports/service.py` `PREFIXES`, `reports/html.py` `JSON_ESCAPES`, `reports/figures.py` `PERCENT_RANGE`, `reports/rows.py` `DELIVERY_HEADERS`, `stats/compute.py` `RESOURCES_BY_GROUP`

### A21: Lazy init race
- Hits: no hits
- Files inspected: 34; 34 had no matching construct (no module-scope `if X is None: X = ...`, no `global`)

### A24: Identity of subprocess / shell-out calls
- Hits: no hits. `resolve_token` (`gh auth token`, `src/wambatic/fetch/auth.py:13`) runs at most once per `sync_target` call (`service.py:183` and `:198` exclude each other); `bin/record-fixtures.py` calls `resolve_token` once and `ruff` once
- Files inspected: 34; 32 had no matching construct

### A25: Shallow immutable wrapper
- Hits: no hits. Every wrapped member read from another module is a `str`, `int`, enum, class, tuple of `str`, or frozen dataclass (`figures.CHARTS` holds frozen `Chart` objects whose `Trace` tuples are frozen too)
- Files inspected: 34; 20 had no matching construct

### P1: O(n^2) on real-size inputs
- Hits:
  - `src/wambatic/stats/delivery.py:183` - for every deployment, `any(...)` scans every hotfix PR opened in that repo: deployments × hotfixes per repo
  - `src/wambatic/reports/terminal.py:147` - `trend_lines` drops one bucket at a time (`shown -= 1`) and rebuilds `sparkline`/`value_range` each pass: O(buckets²) per metric for long `--by day` ranges
  - `src/wambatic/stats/activity.py:99` and `:101` - a `Tally` (with sets) per author or repo per bucket, and `series_of` (`:106`-`:109`) loops breakdown × metric × bucket: authors-or-repos × buckets, and the HTML report always computes DAY
- Files inspected: 34; 25 had no nested loops over project-data-shaped collections

### P2: Blocking I/O in hot paths
- Hits:
  - `src/wambatic/reports/web.py:310` - `page()` calls `read_template` (synchronous file read) for every response, inside async handlers `form`, `report`, `error_reply`
  - `src/wambatic/reports/web.py:312` - `stylesheet()` re-reads `report.css` synchronously for every page response (via `src/wambatic/reports/html.py:159`)
  - `src/wambatic/reports/web.py:466` - `read_template('progress.js')` synchronous file read inside the async `/report` handler
  - `src/wambatic/reports/service.py:183` and `:198` - `resolve_token()` runs a blocking `subprocess.run` (up to a 10 s timeout, `fetch/auth.py:13`) on the event loop inside async `sync_target`; in the web app, on the server's loop in each sync job
- Files inspected: 34; 29 had no hot-path code

### P3: Repeated expensive computation per request
- Hits:
  - `src/wambatic/reports/service.py:240` - with five period requests, `compute()` re-reads the same cached commits, PRs, issues, runs, releases, stars and forks from SQLite five times, with repos and provenance (`stats/compute.py:167`, `:182`-`:188`, `:251`)
  - `src/wambatic/fetch/base.py:652` - `unchanged()` reads `sync_state` per (repo, resource), then `sync_commits`, `sync_updated`, `sync_releases`, `sync_star_events`, `sync_forks` read the same row again (`base.py:839`, `:905`, `:977`, `:1035`, `:1098`)
  - `src/wambatic/reports/html.py:371` - `period_figures` loops over `(report.initial, *PERIODS)`, building the initial period's figures twice; `page_data` builds every period's figures again (`html.py:571`)
  - `src/wambatic/reports/html.py:492` and `:561` - `build_calendar` runs twice per document
  - `src/wambatic/reports/html.py:491` and `:577` - `build_range_figures` runs twice per document
  - `src/wambatic/reports/html.py:258` and `:433` - `popularity_now(total)` runs twice; `languages_rows(total)` also twice (`html.py:281`, `:440`)
  - `src/wambatic/reports/html.py:494` - whole period tables built only to test for `None`, then discarded (`html.py:510`, `:525`, `:526`, `:538`)
  - `src/wambatic/reports/rows.py:237` - `bucket_list()` recomputes the `total_series()` the same function just built (`rows.py:233`/`:237`, `:250`/`:257`, `:267`/`:275`, `:305`/`:311`)
  - `src/wambatic/reports/figures.py:404` - `bucket_list(result)` (and `total_series`) recomputed inside the per-chart loop though `:395`-`:396` already computed both
  - `src/wambatic/reports/terminal.py:337` - `total_series` and `bucket_list` recomputed across `render_terminal`, `trend_lines` (`terminal.py:137`-`:138`) and every table builder
- Files inspected: 34; 25 had no repeated derivation in a request flow

### S1: Type annotations on every signature
- Hits: no hits. An AST scan and `ruff --select ANN` both found no missing parameter or return annotations in `src/wambatic/` or `bin/record-fixtures.py`.
- src/tests count: 0 missing parameter annotations, 0 missing return annotations, 0 modules affected, 50 of 50 modules fully annotated.
- Files inspected: 84

### S2: PascalCase / UPPER_SNAKE / lower_snake
- `src/wambatic/cli.py:32` - type alias `GRANULARITIES = typing.Literal[...]` is UPPER_SNAKE; every other type alias in the tree is PascalCase (`Theme`, `JobKey`, `Tables`, `Summary`, `Hex`, `MakeClient`)
- `src/wambatic/cli.py:33` - type alias `FORMATS = typing.Literal[...]` is UPPER_SNAKE, against the same convention
- `src/tests/fetch/test_cache.py:497` - module-level hypothesis strategy constant `instants` is lower_snake; the other module-level strategies are UPPER_SNAKE (`TOKENS`, `TIMES`, `LOGINS`, `DATES`, `REPO_NAMES`)
- `src/tests/fetch/test_cache.py:502` - module-level strategy constant `commit_lists` is lower_snake
- `src/tests/reports/test_base.py:174` - module-level strategy constant `durations` is lower_snake
- `src/tests/reports/test_base.py:175` - module-level strategy constant `words` is lower_snake
- Files inspected: 84

### S3: TYPE_CHECKING block placement
- Hits: no hits. The only `typing.TYPE_CHECKING` block is at `src/wambatic/fetch/base.py:16`, at the top of the file just after the imports.
- Files inspected: 84

### S4: Project-specific rule files
- `src/wambatic/reports/web.py:76` - security.md: `loguru.logger.exception(f'Unexpected error: {error}')` logs the unexpected error and traceback without redacting the token; the CLI path redacts first (`cli.py:403-405`)
- `src/wambatic/cli.py:385` - coding-standards.md "Logging exceptions": caught `UsageError`/`SettingsError` logged with `loguru.logger.error`, not `loguru.logger.exception`
- `src/wambatic/cli.py:393` - coding-standards.md "Logging exceptions": caught `FetchError`/`OutputError`/`ServeError`/`StatsError` logged with `loguru.logger.error`, not `loguru.logger.exception`
- `bin/record-fixtures.py:237` - coding-standards.md Logging: `print(OUT)` is outside the CLI entry points the rule allows (it prints a single machine-consumable path)
- `src/tests/reports/test_terminal.py:209` - coding-standards.md String formatting: `ORG_MONTH_TERMINAL.format(...)` uses `.format()` (fills a stored fixture template)
- `src/tests/test_cli.py:821` - testing.md "re-usable fixtures / load in conftest.py": the `restore_logger` fixture is defined in the test module, duplicating `src/tests/test_logs.py:10`
- `src/tests/test_logs.py:10` - testing.md: duplicate `restore_logger` fixture defined in the test module, not `src/tests/conftest.py`
- `src/tests/fetch/test_cache.py:26` - testing.md: fixtures `cache_path` and `cache` (line 31) defined in the test module, not conftest
- `src/tests/reports/conftest.py:12` - testing.md "Load fixtures in src/tests/conftest.py": the `chromium` fixture lives in a second, package-level conftest
- `src/tests/fixtures/fetch/recorded.py:1` - testing.md: fixture file name does not mirror a source module
- `src/tests/fixtures/fetch/responses.py:1` - testing.md: fixture file name does not mirror a source module
- `src/tests/fixtures/fetch/server.py:1` - testing.md: fixture file name does not mirror a source module
- `src/tests/fixtures/fetch/upstream.py:1` - testing.md: fixture file name does not mirror a source module
- `src/wambatic/reports/errors.py:1` - testing.md layout: no mirrored `src/tests/reports/test_errors.py`
- `src/tests/fetch/test_fetcher.py:1` - testing.md layout: test file does not mirror a source module (`Fetcher` lives in `wambatic/fetch/base.py`, which also has `test_base.py`)
- Files inspected: 84

### Sec1: Secrets in source
- Hits: no hits. The `ghp_` literals at `src/tests/test_cli.py:974`, `src/tests/test_settings.py:220` and `src/tests/reports/test_web.py:126` are made-up test tokens: each contains a placeholder word or repeated characters. No recorded fixture contains an `Authorization` header or a token. `.github/workflows/ci.yml:54` uses `${{ github.token }}`, not a literal.
- Files inspected: 131 (every committed file except `uv.lock`, `src/gitstat` and `.agents`, including all 50 `.py` files under `src/tests`)

### Sec2: Input validation at system boundaries
- Hits:
  - `src/wambatic/reports/web.py:259-267` - the `since`/`until` HTTP query parameters reach `make_request` with no lower or upper bound. `parse_date` (`src/wambatic/reports/service.py:111-112`) accepts any date from 0001-01-01 to 9999-12-31. `/report` computes all five period requests, so `bucket_range` (`src/wambatic/stats/buckets.py:80-82`) builds about one bucket per day across the whole range from a single GET. That costs unbounded CPU and memory.
  - `src/wambatic/settings.py:74` - `parse_duration` multiplies an unbounded integer by a timedelta. Something like `--max-age 99999999999d` (or `fetch.max_age` in config) raises `OverflowError`, not `SettingsError`, so it escapes validation (checked by running it). The CLI then logs it as an "Unexpected error" with a traceback and exits 1, not 2.
- Files inspected: 36 (33 `.py` under `src/wambatic`, plus `bin/record-fixtures.py`, `bin/activate.sh` and `bin/record-fixtures.sh`)

### Sec3: Command injection
- Hits: no hits. The only `subprocess` calls are `src/wambatic/fetch/auth.py:13`, a fixed argv `['gh', 'auth', 'token']`, and `bin/record-fixtures.py`, a fixed `ruff format` on a constant path. Neither uses a shell. In `bin/*.sh`, `"$@"` is quoted.
- Files inspected: 36

### Sec4: Path traversal
- Hits: no hits. `--out` (`src/wambatic/cli.py:216-217`), `WAMBATIC_CONFIG` and `cache_path` are paths the local user chooses, not remote input. The file name comes from `report_filename`, which strips unsafe characters with `SAFE_FILENAME` (`src/wambatic/reports/html.py:26,83`). The web app takes no path input. `tz` goes to `zoneinfo.ZoneInfo`, which refuses absolute and `..` keys. REST paths are built from the GitHub-returned `nameWithOwner` or a login that matches the `LOGIN` regex.
- Files inspected: 36

### Sec5: PII in logs
- Hits:
  - `src/wambatic/reports/web.py:564` - the raw CLI `target` argument (`default_target`), a GitHub login or repository name, is logged at INFO.
  - `src/wambatic/reports/web.py:76` - `loguru.logger.exception(f'Unexpected error: {error}')` logs the raw exception text and traceback at ERROR without `redact_environment_token`. The CLI path does redact (`src/wambatic/cli.py:403-405`). The message can carry raw request input.
- Files inspected: 36

### T1: Test coverage of branchy logic
- Hits:
  - `bin/record-fixtures.py:93` - `Recorder.send`: neither the `params` branch nor the `body is None` branch has a test (no test imports or runs the script)
  - `bin/record-fixtures.py:111` - `Recorder.graphql`: no test for the "not a dict or has `errors`" `RuntimeError` branch
  - `bin/record-fixtures.py:121` - `pick`: no test for the "not a dict" `RuntimeError` branch or for skipping absent fields
  - `bin/record-fixtures.py:127` - `compare_commit`: no test for the "unexpected compare commit" branch or for `author is None`
- Files inspected: 84

### T2: Property-based tests
- Hits:
  - `src/wambatic/fetch/cache.py:227` - `repo_from_row` and the row round-trips for pull requests, issues, releases, workflow runs, star events, forks, sync state and ETags (`cache.py:281`, `:301`, `:313`, `:324`, `:342`, `:349`) have example tests only; only commits have a hypothesis round-trip (`test_cache.py:519`)
  - `src/wambatic/fetch/base.py:281` - `parse_repo`, `parse_languages` (`:268`), `parse_pull_request` (`:366`), `parse_issue` (`:390`), `parse_release` (`:405`), `parse_workflow_run` (`:420`), `parse_star_edge` (`:445`), `parse_fork` (`:456`), `parse_history_node` (`:466`), `parse_compare_commit` (`:483`) have no hypothesis test of shape validity or of malformed input raising
  - `src/wambatic/fetch/base.py:221` - `timestamp`, `actor_login` (`:321`) and `count_of_probe` (`:255`) are pure scalar parsers with no hypothesis test
  - `src/wambatic/fetch/ratelimit.py:21` - `RateLimitState.from_headers` and `from_graphql` (`:35`) have no hypothesis test (only `backoff_delay` has one)
  - `src/wambatic/fetch/client.py:40` - `next_link`, `error_types` (`:51`), `header_date` (`:65`): example tests only
  - `src/wambatic/settings.py:77` - `convert` and `apply_layer` (`:128`): no hypothesis test; existing ones cover only the `workers` override and `parse_duration`
  - `src/wambatic/cli.py:180` - `check_report`: flag combinations (`full_refresh`/`no_fetch`, `out`/format, `by total`/html, bare name/`no_fetch`) have example tests only
  - `src/wambatic/reports/service.py:64` - `parse_date`: no hypothesis test (`parse_target` has one)
  - `src/wambatic/stats/delivery.py:111` - `aggregate` DORA proxies via `deployments_by_repo` (`:60`), `hotfixes` (`:85`), `missing_inputs` (`:94`): no property test; hypothesis covers only workflow-run counts and success rate
  - `src/wambatic/stats/compute.py:22` - `resources_for`: example tests only
  - `src/wambatic/reports/rows.py:211` - table builders (`activity_table`, `flow_table` `:229`, `delivery_period_table` `:262`, `popularity_table` `:300`, `breakdown_rows` `:359`, `top_contributors` `:383`): no property test for "rows sum to total" or ordering
  - `src/wambatic/reports/figures.py:384` - `build_figures`, `build_range_figures` (`:543`): no property test for "valid Plotly, at most three series, no colour"
  - `src/wambatic/reports/html.py:80` - `report_filename` and `first_difference` (`:86`): no hypothesis test
  - `src/wambatic/reports/web.py:235` - `parse_query`, `reload_path` (`:290`): no hypothesis test (only `is_loopback` has one)
  - `src/wambatic/reports/terminal.py:34` - `format_number`: example tests only (`sparkline` has a hypothesis test)
- Files inspected: 84

### T3: Integration vs unit balance
- Hits:
  - `bin/record-fixtures.py:232` - `main` (record, then `module_text`, write, `ruff format`) has no end-to-end test; `src/tests/fetch/test_queries.py:136` only checks the query hashes still match the recording
  - Checked, not hits: CLI `report` through `run_report`/`main` against the fake upstream, `cache` commands through `main`, `serve` (uvicorn mocked, app driven over ASGI and in a browser), `Fetcher.sync` against the fake server, `stats.compute`, `service.build_results`, `html.render_html`
- Files inspected: 84

### D1: Declared in pyproject
- Hits: no hits
- Items checked: 11 third-party top-level modules imported anywhere in src/wambatic/, bin/record-fixtures.py, src/tests/ (AST walk including nested imports): aiohttp, cappa, fastapi, httpx, hypothesis, loguru, playwright, plotly, pytest, rich, uvicorn. src/wambatic/ imports only runtime deps; test-only modules are all in the dev group.

### D2: Unused declarations
- Hits:
  - `pyproject.toml:24` - `mypy` (dev) never imported; run only as a tool (`.github/workflows/ci.yml:24`, `.pre-commit-config.yaml:13-18`)
  - `pyproject.toml:26` - `pre-commit` (dev) never imported; run only as a tool
  - `pyproject.toml:28` - `ruff` (dev) never imported; run only as a tool (`.github/workflows/ci.yml:22-23`, `.pre-commit-config.yaml:7-11`)
- Items checked: 14 (7 runtime, 7 dev)

### D3: Lockfile coherence
- Hits: no hits (`uv lock --check` exited 0, "Resolved 60 packages", 10:36 UTC 2026-10-31; no script lockfile-drift hit)
- Items checked: 1

### Doc1: AGENTS.md project structure
- Hits:
  - `AGENTS.md:1-19` - no project-structure section: src/wambatic/{fetch,stats,reports}, src/tests/, bin/, agents/specs/, agents/tasks/ are not described anywhere
  - `AGENTS.md:8` - the `.agents/` submodule is not initialised in this checkout (empty; `git submodule status` shows `-ec0d8ca`), so the layout AGENTS.md describes does not resolve
  - `AGENTS.md:10` - `.claude/rules` links to `../.agents/claude/rules`, which is missing (dangling symlink)
  - `AGENTS.md:11` - every `.claude/skills/*` link points into the empty `.agents/` (dangling symlinks)
  - `AGENTS.md:13` - `@.agents/claude/CLAUDE.md` resolves to nothing
  - `AGENTS.md:18` - the project's own `claude/` directory does not exist
  - `AGENTS.md:19` - linked `.agents/claude/rules/rule-scope.md` does not exist here (empty submodule)
- Items checked: 8

### Doc2: AGENTS.md tools and libraries list
- Hits:
  - `AGENTS.md:1-19` - no tools-and-libraries list: none of the runtime libraries (aiohttp, cappa, fastapi, loguru, plotly, rich, uvicorn) or tools (uv, ruff, mypy, pytest, pre-commit, playwright, hypothesis, httpx) is named; the only possible source, the `@.agents/claude/CLAUDE.md` include (line 13), resolves to nothing
- Items checked: 15

### Doc3: README.md and AGENTS.md consistent
- Hits:
  - `README.md:325` - says "Contributor and agent rules are in AGENTS.md", but AGENTS.md only points into the `.agents` submodule (line 13, empty here) and holds no contributor rules itself
  - `pyproject.toml:5` - `readme = 'AGENTS.md'` makes the agent-instructions file the package's long description instead of the user guide README.md
- Items checked: 4

### Doc5: User docs match implementation
- Hits:
  - `README.md:172` - says the Languages table ends with one `Other` row; the terminal table (`src/wambatic/reports/terminal.py:312-333`) and HTML chart (`src/wambatic/reports/figures.py:525-527`) show only the first `TOP_LANGUAGES_SHOWN` = 10 rows (`src/wambatic/reports/rows.py:30`), so with more than 10 languages the `Other` row is cut; the cap is not documented (the top-contributors cap is, README.md:43)
  - `README.md:41` - lists Trends as always printed; it is printed only with more than one period (`src/wambatic/reports/terminal.py:342-345`), so `--by total` has no Trends section
  - `README.md:222-227` - the global options table leaves out `-h/--help` and `--completion`, both shown by `wambatic --help` (built into cappa)
- Items checked: 90 claims (config table vs settings.py; report/serve option tables vs cli.py; exit statuses; target forms; config layering, `WAMBATIC_CONFIG`, duration format, `~`; cache path/info/clear/override; HTML naming, atomic write, `--out`, `--by total`; web app log lines, 202/job, progress, status codes, `by_author`, /docs, loopback, Host 403, job joining, 1 s polling, exit 130; token fallback/redaction; section order). Offline error paths run to confirm.

### Doc4: Specs match implementation
- Hits:
  - `agents/specs/system/spec.md:48` - says no layer reaches around the one beneath it and only `wambatic.cli` imports every layer / `src/wambatic/reports/service.py:13-16` and `src/wambatic/reports/web.py:23-26` import `wambatic.fetch` directly; the reports spec allows this (`reports/spec.md:28`, review-3 choice 2), so the system spec is the stale one
  - `agents/specs/system/spec.md:83` - says `reports` raises `UsageError` / `src/wambatic/reports/errors.py:5-10` also defines `OutputError`, `ServeError`; `cli.py:387-394` maps both to exit 1; `cli.py:234` and `web.py:534` raise them
  - `agents/specs/system/spec.md:92` - "One opt-in integration test" / `src/tests/fetch/test_live.py:19,36,70` has three live tests, one parametrised over `star_events` and `forks`
  - `agents/specs/reports/spec.md:19` - `errors.py` holds `UsageError`, and the API (`:151`) lists only `UsageError` / `src/wambatic/reports/errors.py:5-10` also holds `OutputError` and `ServeError`
  - `agents/specs/reports/spec.md:117` - makes `SyncJob.state` a field / `src/wambatic/reports/web.py:85` stores `phase` (`queued`, `running`, `done`, `failed`); `state` is a derived property (`web.py:93-98`)
  - `agents/specs/reports/spec.md:195` - `cache info` "opens the file read-only" / `src/wambatic/fetch/cache.py:911` uses plain `sqlite3.connect(path)` (read-write; no `mode=ro` URI)
  - `agents/specs/reports/spec.md:208-209` - every other exception is logged with `logger.exception` and exits 1 / `src/wambatic/cli.py:397-401` returns 1 on `BrokenPipeError` without logging
  - `agents/specs/reports/spec.md:213` and `agents/specs/fetch-and-cache/spec.md:396` - the `AuthError` message tells the user to set `GITHUB_TOKEN` / only the no-token case does (`fetch/errors.py:3`); 401 says `'GitHub rejected the token (401)'` (`fetch/client.py:297`), 403 says `'GitHub denied access (403)...'` (`client.py:319-322`)
  - `agents/specs/fetch-and-cache/spec.md:365` - `GitHubClient.__init__` default `clock = utc_now` / `src/wambatic/fetch/client.py:100` has `clock: ... | None = None`, falling back to `utc_now` at line 107
  - `agents/specs/fetch-and-cache/spec.md:426` - `sync_state` columns listed without `probe` / `src/wambatic/fetch/cache.py:127` has `probe TEXT`; the spec itself adds `probe` (lines 247, 426), so its column list contradicts it
  - `agents/specs/fetch-and-cache/spec.md:436` - stargazer read hidden when its first request is refused with `FORBIDDEN` / `src/wambatic/fetch/base.py:1039-1044` treats `FORBIDDEN` on any page as hidden
  - `agents/specs/fetch-and-cache/spec.md:448` - says the 1.11 `COMMIT_COUNTS_OK` response "was derived by hand... `bin/record-fixtures.sh` is to be re-run" and calls the 2026-10-30 recording current / `src/tests/fixtures/fetch/recorded.py:1` says recorded 2026-10-31; commit `e0a5e0f` re-ran the recorder. The spec also does not name `bnomis/ab2cb` as the stargazer and fork subject
  - `agents/specs/stats/spec.md:122` - `EmptySubjectError` raised when "no requested group is built yet (the message names the steps that build them)" / `src/wambatic/stats/compute.py:162-166` raises it only for empty `groups`, message "no requested group: name at least one metric group"; no message names a step
  - `agents/specs/stats/spec.md:134` - delivery reads every pull request "only when a proxy needs them" / `src/wambatic/stats/compute.py:119` always reads `fetcher.pull_requests(repo, None)` for `delivery`
  - `agents/specs/stats/spec.md:138` - since step 10 `tables['unavailable']` "holds only those proxies" / `src/wambatic/stats/compute.py:249` and `src/wambatic/stats/popularity.py:60-76` also add hidden-stargazer rows (as `stats/spec.md:185` describes)
  - `agents/specs/stats/spec.md:174` - "A deployment within `stats.failure_window` of **now** is counted as not failed" / `src/wambatic/stats/delivery.py:166-169,182` measures the window against the end of `until` (`horizon`), not the current time
  - `agents/specs/stats/spec.md:213,217` - types `stats.bot_logins`, `stats.hotfix_labels` as `list[str]` / `src/wambatic/settings.py:25,29` declares `tuple[str, ...]`
- Claims checked per spec (approximate): system ~30, fetch-and-cache ~75, stats ~60, reports ~80

### Spec review (against specdev SKILL.md)
- Hits:
  - `agents/specs/fetch-and-cache/spec.md` (469 lines) - Spec size (about 200 lines at most; otherwise split)
  - `agents/specs/fetch-and-cache/spec.md:446` - cross-references resolve: `../../../.agents/claude/rules/security.md` does not resolve in this checkout (submodule not initialised); the path is right once it is
  - `agents/specs/reports/spec.md` (315 lines) - Spec size
  - `agents/specs/stats/spec.md` (225 lines) - Spec size
  - `agents/specs/system/spec.md:100-103` - Settings include name, type and default: the environment-variable table has no Type column
  - `agents/specs/implementation-order.md:20` - consistency: step 1 "done" with no task-list link, though `agents/tasks/system/tasks-1.md` exists
  - `agents/specs/implementation-order.md:25,27,29` - consistency: Specs column of steps 6, 8, 10 names specs in plain text where other rows link them
  - `agents/specs/implementation-order.md:65-73` - consistency: step detail puts step 10 before step 9
  - `agents/specs/implementation-order.md:7` - cross-references resolve: `../../.agents/claude/skills/taskdev/SKILL.md` does not resolve in this checkout
  - `agents/specs/index.md` - no hits (lists every spec.md with correct paths, links the implementation order)
  - `agents/specs/system/spec.md` - within size; exactly 8 top-level sections, the limit (not a gap)


## Phase B findings (consolidated)

Each finding below groups the hits of one question, or of one cause seen by several questions. The per-hit locations are in the per-question results above.

### F1: Web server logs unexpected errors without redacting the token

- **Category:** Sec / S
- **Question:** Sec5, S4 (security.md)
- **Severity:** high
- **Location:** `src/wambatic/reports/web.py:76`
- **Description:** `error_response` logs `f'Unexpected error: {error}'` and the traceback with `logger.exception`. The CLI path calls `redact_exception(e)` and `redact_environment_token(...)` first (`cli.py:403-405`); the web path does neither. An unexpected exception whose message carries the token (an aiohttp error quoting a request header, say) would write it to the server log. `diagnose=False` (`logs.py`) keeps locals out of tracebacks, but not exception messages.
- **Recommendation:** Redact in `error_response` the same way as `cli.main`, preferably through one shared helper, and add a regression test that raises an exception containing the token through the web app and checks the log.

### F2: Third-party errors escape as tracebacks instead of domain errors

- **Category:** A
- **Question:** A1, A2
- **Severity:** medium
- **Location:** `src/wambatic/fetch/client.py:211`, `:290`, `:327`, `:333`; `src/wambatic/fetch/cache.py:372-962` (each `execute`/`connect`/`unlink`); `src/wambatic/settings.py:146-147`; `src/wambatic/fetch/auth.py:12-13`; `src/wambatic/reports/service.py:82-83`; `src/wambatic/reports/html.py:125`, `:597`; `src/wambatic/cli.py:231`; `src/wambatic/version.py:3`; `bin/record-fixtures.py:108-109`, `:235-236`
- **Description:** When the retries run out on a network error, `GitHubClient` re-raises the aiohttp `ClientConnectionError`/`TimeoutError`, or raises `aiohttp.ClientResponseError` for an unclassified status. Every `sqlite3.Error` from the cache (a locked or corrupt file, a full disc) escapes untranslated. The config read, `gh auth token`, the cache unlink and the tz lookup each catch only `FileNotFoundError` (or a near equivalent), not `OSError`/`UnicodeDecodeError`. Each of these reaches `cli.main`'s `except Exception`, which prints "Unexpected error" with a traceback and exits 1 instead of a one-line message. This is the case the user is most likely to meet: the network going down mid-sync.
- **Recommendation:** Translate at each layer's boundary: in `GitHubClient.send`/`request`, wrap aiohttp errors in `FetchError` after the retries; in `Cache`, wrap `sqlite3.Error` and `OSError` in a new `CacheError(FetchError)` through one context manager used by every method; widen the four narrow `except` tuples to `OSError` (+ `UnicodeDecodeError` where text is decoded). `bin/record-fixtures.py` is a developer script and can stay as it is (scoped accept markers).

### F3: Settings validation lets an `OverflowError` through

- **Category:** Sec
- **Question:** Sec2
- **Severity:** medium
- **Location:** `src/wambatic/settings.py:74`
- **Description:** `parse_duration('99999999999d')` raises `OverflowError` (checked on 2026-10-31), not `SettingsError`, so `--max-age`/`fetch.max_age` with a huge value exits 1 with a traceback instead of exit 2 with a usage message.
- **Recommendation:** Catch `OverflowError` in `parse_duration` and raise `SettingsError`; add a hypothesis case with very large counts.

### F4: The web report accepts an unbounded date range

- **Category:** Sec
- **Question:** Sec2
- **Severity:** medium
- **Location:** `src/wambatic/reports/web.py:259-267`, `src/wambatic/reports/service.py:111-112`, `src/wambatic/stats/buckets.py:80-82`
- **Description:** `since`/`until` from the query string accept any date from 0001 to 9999. `/report` always computes the DAY period, so one GET builds about 3.6 million buckets per metric. The server binds to loopback by default, which limits who can send that GET, but a stray link can still pin a CPU.
- **Recommendation:** Bound the range at the boundary (for example no earlier than GitHub's founding in 2008 and no later than tomorrow) with a `UsageError` (HTTP 400), in `make_request` so the CLI shares it.

### F5: Stdlib exceptions raised in packages that define domain errors

- **Category:** A
- **Question:** A3 (and the script's `layer-has-domain-error-raises-stdlib`, `mixed-raise-types`)
- **Severity:** medium
- **Location:** the 23 A3 sites listed above
- **Description:** Some of these are reachable from user input and are wrong: `buckets.py:75` (`since` after `until`; `InvalidRangeError` exists for it), `html.py:108-120` (`check_report`), `settings.py:110`, `cache.py:541`, `client.py:222`. Others are caller-mistake guards that the specs themselves specify as `ValueError` (`stats/spec.md:65`, `reports/spec.md:54` and `:63`, `fetch-and-cache/spec.md:178`). See Decision 2.
- **Recommendation:** See Decision 2.

### F6: Two sources of truth for the same setting

- **Category:** A
- **Question:** A5
- **Severity:** medium
- **Location:** `src/wambatic/fetch/base.py:529-540`; `src/wambatic/stats/base.py:46-49`; `src/wambatic/reports/service.py:88-117`, `:170`, `:210-221`; `src/wambatic/reports/web.py:298-303`
- **Description:** `Fetcher.settings` versus an injected client's `settings`; `StatsRequest.tz` versus `settings.timezone` (both written into the JSON output, so they can disagree there); `by_author` passed beside the request that already holds it; `make_app(check_host=...)` versus `settings.report.allow_remote`. In each case which value wins depends on the call site, and nothing checks that the two agree.
- **Recommendation:** Give each value one owner: derive `tz` from settings (or drop `settings.timezone` from the request), read `by_author` from the request, derive `check_host` inside `make_app`, and make `Fetcher` take its settings from the client when one is injected (or refuse a mismatch).

### F7: `match`/`if` chains over enums and literals end in `raise`, not `assert_never`

- **Category:** A
- **Question:** A11 (and the script's `assert-never-missing`)
- **Severity:** medium
- **Location:** `src/wambatic/stats/buckets.py:22`, `:39`; `src/wambatic/fetch/base.py:1272`, `:1276`, `:1278`
- **Description:** A wildcard `case _: raise ValueError` or a fall-through `else` means mypy cannot tell when a new `Granularity` member or resource name is left unhandled.
- **Recommendation:** Handle `TOTAL` explicitly and end with `typing.assert_never(...)`.

### F8: Repeated computation across the five periods of an HTML report

- **Category:** A / P
- **Question:** A14, P3
- **Severity:** medium
- **Location:** `src/wambatic/stats/compute.py:137`, `:155`, `:167`, `:251`; `src/wambatic/reports/service.py:240`; `src/wambatic/reports/html.py:371`, `:491-494`, `:561`, `:577`; `src/wambatic/reports/rows.py:237`; `src/wambatic/reports/figures.py:404`; `src/wambatic/reports/terminal.py:337`; `src/wambatic/fetch/base.py:652`
- **Description:** Each of the five `compute()` calls re-reads every cached record from SQLite, plus repos, provenance and sync state. Then `html.py` builds the initial period's figures, the calendar and the range figures twice each. No measurement shows whether this matters at real sizes. See Decision 3.
- **Recommendation:** See Decision 3.

### F9: Spec and code disagree

- **Category:** Doc
- **Question:** Doc4
- **Severity:** medium
- **Location:** the 17 Doc4 rows above
- **Description:** Most are stale spec text: the layering rule in `system/spec.md:48`, which `reports/spec.md:28` later relaxed; the missing `OutputError`/`ServeError`; `SyncJob.state` versus `phase`; the `probe` column; `list` versus `tuple` types; the 1.11 note about a hand-derived fixture, now re-recorded. Three describe behaviour, and in each the code or the spec has to change: the delivery failure window is measured from the end of `until`, not from "now" (`stats/spec.md:174`); `cache info` opens the database read-write, not read-only (`reports/spec.md:195`); and stargazers count as hidden when *any* page is refused, not only the first (`fetch-and-cache/spec.md:436`).
- **Recommendation:** Update the spec text for the stale rows. For the three behavioural rows, decide which side is right; the read-only `cache info` is a cheap code fix (`sqlite3.connect(f'file:{path}?mode=ro', uri=True)`).

### F10: README drift

- **Category:** Doc
- **Question:** Doc5
- **Severity:** medium
- **Location:** `README.md:41`, `:172`, `:222-227`
- **Description:** Trends is listed as always printed, but it is skipped for `--by total`. The Languages table is capped at `TOP_LANGUAGES_SHOWN` rows, which can cut the `Other` row, and the README does not say so. The global options table leaves out `--help` and `--completion`.
- **Recommendation:** Update the three passages. For Languages, either document the cap or always keep `Other` as the last row.

### F11: AGENTS.md has no structure or tools section, and its links do not resolve here

- **Category:** Doc
- **Question:** Doc1, Doc2, Doc3
- **Severity:** medium
- **Location:** `AGENTS.md:1-19`, `README.md:325`, `pyproject.toml:5`
- **Description:** AGENTS.md is a pointer to the shared rules and nothing else: it has no project layout and no tools list. In this checkout its submodule links are dangling, because `.agents` is not initialised. `README.md:325` sends contributors to AGENTS.md for rules it does not hold. `pyproject.toml` declares `readme = 'AGENTS.md'`, so the package's long description is the agent instructions, not the user guide.
- **Recommendation:** Run `git submodule update --init`. Add a short layout section (`src/wambatic/{fetch,stats,reports}`, `src/tests`, `bin`, `agents/specs`, `agents/tasks`) and a tools list to AGENTS.md. Point `readme` at `README.md`.

### F12: Blocking calls on the event loop

- **Category:** P
- **Question:** P2
- **Severity:** medium
- **Location:** `src/wambatic/reports/service.py:183`, `:198` (`resolve_token`, up to 10 s); `src/wambatic/reports/web.py:310`, `:312`, `:466` (template reads)
- **Description:** In the web server, each sync job runs `gh auth token` with `subprocess.run` on the server's event loop, which stalls every other request for as long as `gh` takes. The template reads are small but repeated on every response.
- **Recommendation:** Run `resolve_token` through `asyncio.to_thread`. Read the templates once (`functools.cache` on `read_template`).

### F13: Mutable module-level containers read from other modules

- **Category:** A
- **Question:** A20 (and the script's `mutable-module-level-exported`)
- **Severity:** low
- **Location:** `src/wambatic/stats/delivery.py:36` (`UNITS`), `src/wambatic/reports/figures.py:40` (`PALETTE`), the four `__all__` lists
- **Description:** A caller can mutate `UNITS` or `PALETTE` and change every later report in the process, which matters in the long-running server.
- **Recommendation:** Wrap in `types.MappingProxyType`. Make the `__all__` lists tuples (ruff accepts either).

### F14: Duplicated record construction between the parsers and the cache

- **Category:** A
- **Question:** A15, A13
- **Severity:** low
- **Location:** the A15 rows (mainly `fetch/base.py` parsers against `fetch/cache.py` row readers and column tuples)
- **Description:** Every record type is assembled once from GraphQL in `base.py` and again from a SQLite row in `cache.py`, and the column lists are written out again in the INSERT statements and write lambdas. Adding a field means editing four places, and missing one fails only at run time.
- **Recommendation:** Derive the column tuples and the row writers from `dataclasses.fields(...)`, so each record's field list exists once.

### F15: Smaller architecture findings

- **Category:** A
- **Question:** A8, A9, A17, A19, A22, A23
- **Severity:** low
- **Location:** the rows above
- **Description:** Accumulator and job-state dataclasses are mutated after construction (A8: `Tally`, `SyncJob`, both deliberate). Some `resolve_`/`check_`/`parse_`/`build_` functions do I/O (A9). The subpackage `__all__` surfaces have no consumers outside their package (A17, see Decision 4). The `except BaseException` clean-up-and-re-raise handlers do not log (A19); that is the right shape, so accept them with a scoped marker. A 404 from `compare` is logged as "history rewritten" (A22). `sync_releases` discards `plan_full_read`'s result (A23); that is harmless, because every releases read is a full one, but the call is made only for its log line.
- **Recommendation:** A8: no change; record the reason in a comment. A9: rename `build_results` to `sync_and_compute` (or similar) and `check_bind` to `warn_on_bind`; the others do I/O inside a library and can stay. A19: scoped accept markers. A22: log the 404 as the reason. A23: `_ = self.plan_full_read(...)`, or a `log_full_read` that returns nothing.

### F16: Standards findings

- **Category:** S
- **Question:** S2, S4
- **Severity:** low
- **Location:** the S2 and S4 rows above
- **Description:** The type aliases `GRANULARITIES` and `FORMATS` are UPPER_SNAKE where every other alias is PascalCase. Four test strategies are lower_snake. Expected domain errors are logged with `logger.error` (`cli.py:385`, `:393`); the coding standard says to always use `logger.exception`, but a traceback for a usage error would be the wrong output for the user. Some test fixtures live in test modules, not in `conftest.py`, and some test and fixture file names do not mirror a source module.
- **Recommendation:** Rename the aliases and strategies. Keep `logger.error` for expected domain errors, and propose a change to the shared coding standard ("exception for unexpected errors only"); this is the rule conflict A19 already describes. Move `restore_logger` (defined twice) and the cache fixtures into `conftest.py`. Leave the `fixtures/fetch/*` names as they are: they mirror the fake GitHub, not a source module.

### F17: Test coverage gaps

- **Category:** T
- **Question:** T1, T2, T3
- **Severity:** low
- **Location:** the T rows above
- **Description:** `bin/record-fixtures.py` has no tests at all (T1, T3). Many pure parsers, row round-trips and table builders have example tests but no property tests (T2).
- **Recommendation:** See Decision 5.

### F18: Dev tools declared but never imported

- **Category:** D
- **Question:** D2
- **Severity:** low
- **Location:** `pyproject.toml:24`, `:26`, `:28`
- **Description:** `mypy`, `pre-commit` and `ruff` are command-line tools, so no code imports them. They are declared so that `uv sync` installs them for CI and pre-commit.
- **Recommendation:** No change. This is expected for tools in a dev group.

### F19: Spec template gaps

- **Category:** Doc
- **Question:** spec review
- **Severity:** low
- **Location:** `agents/specs/fetch-and-cache/spec.md` (469 lines), `reports/spec.md` (315), `stats/spec.md` (225), `system/spec.md:100-103`, `implementation-order.md:7`, `:20`, `:25-29`, `:65-73`
- **Description:** Three specs are over the specdev size guide of about 200 lines. The environment-variable table has no Type column. `implementation-order.md` has inconsistent links and puts step 10 before step 9. Two links into `.agents` do not resolve in this checkout (F11).
- **Recommendation:** Split `fetch-and-cache/spec.md` (fetch and cache are natural halves) when it next changes. Fix the table and the ordering now.

## Files reviewed (Phase B)

Questions A1-A25, S1-S4, P1-P3, Sec1-Sec5, T1-T3 and D1 were applied to every file below. S1 (as a count), S2, S3, S4, Sec1, T1-T3 and D1 also covered every file under `src/tests/`. D2-D3 covered `pyproject.toml` and `uv.lock`; Doc1-Doc5 covered `AGENTS.md`, `README.md` and the four specs.

- `bin/record-fixtures.py`, `bin/record-fixtures.sh`, `bin/activate.sh`
- `src/wambatic/__init__.py`, `__main__.py`, `cli.py`, `logs.py`, `settings.py`, `version.py`
- `src/wambatic/fetch/__init__.py`, `auth.py`, `base.py`, `cache.py`, `client.py`, `errors.py`, `queries.py`, `ratelimit.py`
- `src/wambatic/stats/__init__.py`, `activity.py`, `base.py`, `buckets.py`, `compute.py`, `delivery.py`, `errors.py`, `flow.py`, `percentile.py`, `popularity.py`
- `src/wambatic/reports/__init__.py`, `base.py`, `errors.py`, `figures.py`, `html.py`, `rows.py`, `service.py`, `terminal.py`, `web.py`
- `src/tests/**/*.py` (for the questions named above)
- `agents/specs/system/spec.md`, `fetch-and-cache/spec.md`, `stats/spec.md`, `reports/spec.md`, `index.md`, `implementation-order.md`

`src/gitstat/` holds only stale `__pycache__` files from an earlier package name and no source, so it was not reviewed. It can be deleted.

## Prior findings re-verified

None: this is the first audit, and there is no `summary.md` or `agents/tasks/audit-reviews/`.

## Recommendations

1. **High:** F1, redact the web server's error log.
2. **Medium, user-visible:** F2 (domain errors for network, cache and file failures), F3, F4, F12 (blocking `gh` call in the server), F10 (README).
3. **Medium, correctness and maintainability:** F5 (Decision 2), F6, F7, F9, F11.
4. **Low:** the mechanical hits in `src/wambatic` and `bin` (sort, rename, freeze, add `Raises:` sections, scoped accept markers where noted), F13-F19.
5. **Decided by you:** the test-tree hits (Decision 1), repeated computation (Decision 3), package surfaces (Decision 4), property tests (Decision 5).

## Decisions

### Decision 1: What to do with the mechanical hits in `src/tests/`

- **What is being decided:** how to clear the 445 unaccepted script hits in the test tree, most of them `literal-duplication` (254), `reexport-in-non-init` (69), `non-alphabetical-*` (41) and `mutable-module-level-exported` (16).
- **Background:** the checker applies the same rules to tests as to source. Test data repeats literals by design (the same login or date across cases), keeps GitHub's key order in canned responses, and aliases `UTC = datetime.UTC` for brevity. The only ways to accept a hit are an inline `# auditme: accept[...]` marker on each line, or an AGENTS.md row, which covers in-function imports only. The audit skill's convergence rule means every unaccepted hit stays a finding in every later audit until it is fixed or accepted.
- **What it affects:** the 50 test modules, the next audit's hit count, and possibly the shared audit skill.
- **Options:**
  - **A (recommended): fix the cheap rules, and ask for a skill refinement for the rest.** Fix `aliased-imports` (25) and `typing-deprecated-alias` (18) with search-and-replace, and the `reexport-in-non-init` aliases (69) by writing `datetime.UTC` and the full path at each use. Add a refinement request to the audit skill's `requests.md` to exempt `src/tests/` from `literal-duplication`, `non-alphabetical-*` and `mutable-module-level-exported` for module-level fixture data. The skill change must ship before the next audit (convergence rule 1); until then those hits stay open. Recommended because test data that repeats or keeps GitHub's order is not a defect, and one refinement accepts it everywhere it recurs.
  - **B: fix every hit in the test tree.** Name every repeated literal, sort every dict and list, and freeze every fixture. This is the most churn (hundreds of edits), makes the test data harder to read against GitHub's real responses, and needs no skill change.
  - **C: accept each with an inline marker.** 445 `# auditme: accept[...]` comments. Converges at once without a skill change, but buries the tests in markers.

### Decision 2: `ValueError` in packages that define domain errors

- **What is being decided:** which of the 23 stdlib raises (F5) become domain errors.
- **Background:** the specs specify `ValueError` for caller-mistake guards: `bucket_start` given `TOTAL` (`stats/spec.md:65`), `build_calendar` given a non-DAY result (`reports/spec.md:54`), `html_report` given mismatched results (`reports/spec.md:63`), and unknown resource names (`fetch-and-cache/spec.md:178`). Those guards signal a bug in the caller, not a user condition. Other sites can be reached from user input or from GitHub data: `buckets.py:75` (`since` after `until`), `settings.py:110`, `cache.py:541` and `client.py:222` (a 200 response that is not JSON).
- **What it affects:** `stats/buckets.py`, `stats/base.py`, `fetch/base.py`, `fetch/cache.py`, `fetch/client.py`, `reports/html.py`, `reports/figures.py`, `settings.py`, their tests, and possibly three specs.
- **Options:**
  - **A (recommended): convert the reachable ones, and accept the caller-mistake guards.** Raise `InvalidRangeError`, `SettingsError` and `FetchError` at the reachable sites, and mark each caller-mistake guard `# auditme: accept[layer-has-domain-error-raises-stdlib] caller bug, specified as ValueError in <spec>:<line>`. Recommended because it keeps the specs' contract and gets the user-facing cases right.
  - **B: convert every site to a domain error, and amend the specs.** One error family everywhere, but a caller bug then looks like a user error, and four spec passages change.
  - **C: accept every site.** No code change. The reachable cases keep showing the user a traceback.

### Decision 3: Repeated computation across the five HTML periods

- **What is being decided:** whether to restructure the report pipeline so that each record is read and each figure built only once (F8).
- **Background:** `period_requests` (`reports/spec.md:81-85`) defines an HTML report as five independent `compute()` calls, which keeps them simple and testable. No timing of a large organisation's report has been recorded, so the cost is unmeasured.
- **What it affects:** `stats/compute.py`, `reports/service.py`, `reports/html.py`, `rows.py`, `figures.py`, `terminal.py`, and the reports spec.
- **Options:**
  - **A (recommended): measure first.** Add a `TODO.md` item to time `wambatic report --format html` on a large cached organisation and restructure only if it is slow. Recommended because the design is deliberate, and the review rules ask for a measurement before a change to it.
  - **B: fix it in this audit's task list.** Read the cache once per report and compute the five periods from the same records, and build each figure once. A sizeable change to a spec'd interface, with no measured need.
  - **C: no change.**

### Decision 4: Package `__all__` surfaces that nothing outside the package uses

- **What is being decided:** what to do about A17. Every name re-exported from `wambatic`, `wambatic.fetch`, `wambatic.stats` and `wambatic.reports` is reached through submodule paths, and only `test_package.py` uses the package paths.
- **Background:** `system/spec.md:11` and `:23` define the top-level `wambatic` re-exports as "the public surface other code and the three front ends may rely on". The subpackage `__all__` lists are not in the spec. The coding standard keeps `__init__.py` as the public API and code in `base.py`.
- **What it affects:** the four `__init__.py` files, `src/tests/test_package.py`, AGENTS.md.
- **Options:**
  - **A (recommended): keep the surfaces, and record why.** Add a line to AGENTS.md that the `__init__` re-exports are the promised API for outside code, while the project's own code imports from submodules, so later audits can see the decision. Recommended because the spec promises the surface and removing it gains nothing.
  - **B: trim each subpackage `__all__` to the names the spec promises.** A smaller surface; the trimmed names stop being part of the API.
  - **C: route the front ends through the package paths.** Uses the surface as the spec describes, but means changing imports across `cli.py`, `service.py`, `web.py` and the tests.

### Decision 5: Which property tests to add

- **What is being decided:** how much of the T2 list (F17) goes into this audit's task list.
- **Background:** the project already has hypothesis tests for the commit round-trip, `backoff_delay`, `parse_duration`, `parse_target`, `sparkline` and `is_loopback`. T2 lists 15 more areas.
- **What it affects:** run time of the test suite (every hypothesis test uses 20 examples), and test files under `src/tests/fetch/`, `stats/`, `reports/`.
- **Options:**
  - **A (recommended): the data boundaries only.** Cache row round-trips for every record type, the GraphQL parsers (valid shapes parse, malformed ones raise `FetchError`), `parse_duration` limits (F3) and `parse_date`. Recommended because these are where data from outside enters and where an `OverflowError` already slipped through.
  - **B: the whole T2 list.**
  - **C: none in this audit.**

## Answers

Answered on the review page (https://claude.ai/artifact/Eb7chtX2Vkvnmj7YEdFbTG) on 2026-10-31, 10:48-10:49 UTC. No comments were left.

**Findings:** F1-F19 and M1 (the script hits in `src/wambatic` and `bin`) are all approved for the fix list.

**Decisions:** option B was chosen for every decision. In four of the five that is not the recommended option, and the fix list follows the choice:

| Decision | Chosen | Consequence for the fix list |
|---|---|---|
| 1. Test-tree script hits | B: fix every hit | Every one of the 445 `src/tests/` hits is fixed in code (named constants, sorted literals, frozen fixtures, full paths); no skill refinement request and no accept markers |
| 2. Stdlib raises | B: convert every site, amend the specs | All 23 sites raise a domain error; `stats/spec.md:65`, `reports/spec.md:54` and `:63`, and `fetch-and-cache/spec.md:178` change to name the domain error |
| 3. Repeated computation across the five periods | B: restructure now | Read the cache once per report, compute the five periods from the same records, build each figure once; the reports spec (`period_requests`, `reports/spec.md:81-85`) is amended |
| 4. Package re-exports | B: trim to what the spec promises | Each subpackage `__all__` is cut to the names `system/spec.md:23` promises; the top-level `wambatic` surface stays; `test_package.py` follows |
| 5. Property tests | B: the whole T2 list | Hypothesis tests for every area in T2 |

**Follow-up choices** (asked while writing the task list, 2026-10-31):

- F9, delivery failure window: keep the code. Only events inside the report's range count, so a re-run report never changes; `stats/spec.md:174` is amended to say "the end of the range", as README.md:150 already does.
- F9, hidden stargazers: keep the code. A `FORBIDDEN` on any page means hidden; `fetch-and-cache/spec.md:436` is amended.
- F9, `cache info`: open the database read-only, as the spec says (code fix).
- F10, Languages: always keep one `Other` row after the top languages, in the terminal table and the HTML chart, and mention the cap in README.
- Decision 3 (option B): settle the design in the reports spec through `/specdev` before the task list is written.
- Gates (asked after the answers, at the user's request on 2026-10-31 that "checks [be put] in place (git hooks?) to make sure these audit failures don't happen again"): the audit sweep runs as a **pre-push** hook that fails on any unaccepted hit, and in **CI** through a read-only deploy key for the private `bnomis/agents` repository, which the user adds; ruff rules that match the coding standards and mypy run on every commit.
