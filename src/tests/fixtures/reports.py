"""The known-good terminal rendering and figures of the stats fixture's org.

`ORG_MONTH_TERMINAL` was generated from `render_terminal` at width 120 for the org by month with
an author breakdown, regenerated when the flow tables were added, then checked by hand on
2026-10-30: every number against the hand-worked totals in `tests.fixtures.stats` (periods,
breakdowns by repository and by author, top contributors, and the flow counts and times by period,
whose arithmetic is in `ORG_FLOW_BY_MONTH_UTC`) and the layout against the reports spec's Terminal
section. The versions in the provenance footer are `{wambatic_version}` and
`{schema_version}`, filled in by the test; trailing spaces are not kept, so the test compares
lines without them.
"""

import datetime

import pytest

import tests.conftest
import tests.fixtures.fetch.server
import tests.fixtures.fetch.upstream
import tests.fixtures.stats
import wambatic.fetch.base
import wambatic.fetch.cache
import wambatic.reports.service
import wambatic.settings

UTC = datetime.UTC


def alpha_upstream() -> tests.fixtures.fetch.upstream.Upstream:
    """A fake GitHub whose repositories match the stats fixture's, so a sync finds them
    unchanged."""
    alpha, _, gamma = tests.fixtures.stats.REPOS
    repos = [
        tests.fixtures.fetch.upstream.FakeRepo(
            repo.name_with_owner,
            [
                tests.fixtures.fetch.upstream.FakeCommit(
                    str(repo.head_oid), datetime.datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
                )
            ],
            pushed_at=repo.pushed_at or tests.fixtures.stats.NOW,
            updated_at=repo.updated_at,
            stars=[
                tests.fixtures.fetch.upstream.FakeStar(star.user_id, star.starred_at)
                for star in tests.fixtures.stats.STAR_EVENTS
                if star.repo == repo.name_with_owner
            ],
            forks=[
                tests.fixtures.fetch.upstream.FakeFork(fork.id, fork.created_at)
                for fork in tests.fixtures.stats.FORKS
                if fork.repo == repo.name_with_owner
            ],
            watchers=repo.watcher_count,
            languages=list(repo.languages) or None,
        )
        for repo in (alpha, gamma)
    ]
    return tests.fixtures.fetch.upstream.Upstream(repos)


def install_replay(
    monkeypatch: pytest.MonkeyPatch,
    make_client: tests.conftest.MakeClient,
    server: tests.fixtures.fetch.server.ReplayServer,
) -> None:
    """Make `service.make_fetcher` build fetchers whose client talks to `server`."""

    def factory(
        token: str, cache: wambatic.fetch.cache.Cache, settings: wambatic.settings.FetchSettings
    ) -> wambatic.fetch.base.Fetcher:
        return wambatic.fetch.base.Fetcher(
            token, cache, settings, client=make_client(server, settings)
        )

    monkeypatch.setattr(wambatic.reports.service, 'make_fetcher', factory)


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

Provenance
computed_at: 2027-01-20T12:00:00+00:00
fetched_at:commits: 2027-02-01T10:00:00+00:00
fetched_at:issues: 2027-02-01T10:00:00+00:00
fetched_at:pull_requests: 2027-02-01T10:00:00+00:00
wambatic_version: {wambatic_version}
schema_version: {schema_version}
"""


# The `activity-commits` and `flow-merge-time` figures of the org by month, as `Figure` fields
# (`dataclasses.asdict`). Generated from `build_figures` once, then checked by hand on 2026-10-30:
# commits 7, 0, 1, 2 and the merge p50 48, none, 37.5, 24 and p90 86.4, none, 37.5, 24 are the
# months of `ORG_BY_MONTH_UTC` and `ORG_FLOW_BY_MONTH_UTC` (November has no merge, so a gap), no
# month is partial so no mark, the first slot is the p50 and the second the p90, and the last
# point of each line is labelled.
ORG_MONTH_FIGURES = {
    'activity-commits': {
        'key': 'activity-commits',
        'group': 'activity',
        'title': 'Commits per period',
        'description': 'Bars of the commits in each period.',
        'data': [
            {
                'type': 'bar',
                'name': 'Commits',
                'x': ['2026-10', '2026-11', '2026-12', '2027-01'],
                'y': [7, 0, 1, 2],
                'marker': {'pattern': {'shape': ['', '', '', '']}},
                'meta': {'slot': 1},
            }
        ],
        'layout': {
            'height': 320,
            'margin': {'l': 64, 'r': 24, 't': 16, 'b': 72},
            'font': {'family': 'system-ui, -apple-system, "Segoe UI", sans-serif'},
            'xaxis': {'type': 'category', 'automargin': True},
            'yaxis': {'title': {'text': 'commits'}, 'automargin': True, 'zeroline': True},
            'barmode': 'group',
            'hovermode': 'x unified',
            'showlegend': False,
            'legend': {'orientation': 'h', 'x': 0, 'y': 1.15},
            'annotations': [],
        },
    },
    'flow-merge-time': {
        'key': 'flow-merge-time',
        'group': 'flow',
        'title': 'Time to merge per period',
        'description': 'Lines of the median and 90th percentile hours to merge '
        'for each period, with a gap where no merge has a value.',
        'data': [
            {
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'p50',
                'x': ['2026-10', '2026-11', '2026-12', '2027-01'],
                'y': [48.0, None, 37.5, 24.0],
                'marker': {'symbol': ['circle', 'circle', 'circle', 'circle']},
                'connectgaps': False,
                'meta': {'slot': 1},
            },
            {
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'p90',
                'x': ['2026-10', '2026-11', '2026-12', '2027-01'],
                'y': [86.4, None, 37.5, 24.0],
                'marker': {'symbol': ['circle', 'circle', 'circle', 'circle']},
                'connectgaps': False,
                'meta': {'slot': 2},
            },
        ],
        'layout': {
            'height': 320,
            'margin': {'l': 64, 'r': 56, 't': 48, 'b': 72},
            'font': {'family': 'system-ui, -apple-system, "Segoe UI", sans-serif'},
            'xaxis': {'type': 'category', 'automargin': True},
            'yaxis': {'title': {'text': 'hours'}, 'automargin': True, 'zeroline': True},
            'barmode': 'group',
            'hovermode': 'x unified',
            'showlegend': True,
            'legend': {'orientation': 'h', 'x': 0, 'y': 1.15},
            'annotations': [
                {
                    'x': '2027-01',
                    'y': 24.0,
                    'xref': 'x',
                    'yref': 'y',
                    'text': 'p50',
                    'showarrow': False,
                    'xanchor': 'left',
                    'xshift': 6,
                },
                {
                    'x': '2027-01',
                    'y': 24.0,
                    'xref': 'x',
                    'yref': 'y',
                    'text': 'p90',
                    'showarrow': False,
                    'xanchor': 'left',
                    'xshift': 6,
                },
            ],
        },
    },
}
