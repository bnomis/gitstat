"""The known-good terminal rendering of the stats fixture's org.

`ORG_MONTH_TERMINAL` was generated from `render_terminal` at width 120 for the org by month with
an author breakdown, regenerated when the flow tables were added, then checked by hand on
2026-10-30: every number against the hand-worked totals in `tests.fixtures.stats` (periods,
breakdowns by repository and by author, top contributors, and the flow counts and times by period,
whose arithmetic is in `ORG_FLOW_BY_MONTH_UTC`) and the layout against the reports spec's Terminal
section. The versions in the provenance footer are `{wambatic_version}` and
`{schema_version}`, filled in by the test; trailing spaces are not kept, so the test compares
lines without them.
"""

ORG_MONTH_TERMINAL = """\
org octo-org, 2026-10-01 to 2027-01-31, by month, UTC
Activity by period

  Period    Commits   Contributors   Active days   Added   Deleted   Net
 ────────────────────────────────────────────────────────────────────────
  2026-10         7              3             5      73        39   +34
  2026-11         0              0             0       0         0     0
  2026-12         1              1             1       7         3    +4
  2027-01         2              2             2      10         6    +4
 ────────────────────────────────────────────────────────────────────────
  Total          10              3             8      90        48   +42


Trends
commits        █▁▂▃  0 to 7
contributors   █▁▃▆  0 to 3
active_days    █▁▂▄  0 to 5
lines_added    █▁▂▂  0 to 73
lines_deleted  █▁▂▂  0 to 39
lines_net      █▁▂▂  0 to +34
prs_opened     █▁▁▅  1 to 5
prs_merged     █▁▂▂  0 to 5
issues_opened  █▃▁▃  0 to 3
issues_closed  █▃▁▁  0 to 3

By repository

  Name             Commits   Added   Deleted   Net
 ──────────────────────────────────────────────────
  octo-org/alpha         6      43        13   +30
  octo-org/beta          4      47        35   +12


By author

  Name              Commits   Added   Deleted   Net
 ───────────────────────────────────────────────────
  Octocat                 4      22         5   +17
  hubot                   3      35        12   +23
  dependabot[bot]         1      30        30     0
  monalisa                1       0         0     0
  unattributed            1       3         1    +2


Top contributors

  Login          Commits   Added   Deleted   Net   Active days
 ──────────────────────────────────────────────────────────────
  Octocat              4      22         5   +17             3
  hubot                3      35        12   +23             3
  monalisa             1       0         0     0             1
  unattributed         1       3         1    +2             1


Flow by period

  Period    PRs opened   PRs merged   Issues opened   Issues closed
 ───────────────────────────────────────────────────────────────────
  2026-10            5            5               3               3
  2026-11            1            0               1               1
  2026-12            1            1               0               0
  2027-01            3            1               1               0
 ───────────────────────────────────────────────────────────────────
  Total             10            7               5               4


Flow times by period

  Period    Review p50   Review p90   Merge p50   Merge p90   Close p50   Close p90   PR size p50
 ─────────────────────────────────────────────────────────────────────────────────────────────────
  2026-10         12.0         21.6        48.0        86.4        48.0       201.6            15
  2026-11            -            -           -           -        12.0        12.0             -
  2026-12          2.0          2.0        37.5        37.5           -           -             5
  2027-01         12.5         21.7        24.0        24.0           -           -            15

hours; - no data

Unavailable

  Metric      Reason
 ────────────────────────────────────────────────────────────────────────────────
  stars       stars come from star_events, which step 8 fetches
  forks       forks has no fetch resource yet; it is specified before step 8
  watchers    watchers has no fetch resource yet; it is specified before step 8
  languages   languages has no fetch resource yet; it is specified before step 8


Provenance
computed_at: 2027-01-20T12:00:00+00:00
fetched_at:commits: 2027-02-01T10:00:00+00:00
fetched_at:issues: 2027-02-01T10:00:00+00:00
fetched_at:pull_requests: 2027-02-01T10:00:00+00:00
wambatic_version: {wambatic_version}
schema_version: {schema_version}
"""
