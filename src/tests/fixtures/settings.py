import datetime
import pathlib

import gitstat.settings

CONFIG_JSON = """
{
  "fetch": {
    "cache_path": "~/gitstat/cache.sqlite3",
    "full_refresh_after": "2w",
    "include_forks": true,
    "max_age": "1h",
    "on_rate_limit": "fail",
    "workers": 8
  },
  "report": {"format": "json", "out_dir": "reports", "web_port": 9000},
  "stats": {
    "bot_logins": ["ci[bot]"],
    "deploy_workflow": "deploy",
    "failure_window": "3d",
    "timezone": "Europe/London"
  }
}
"""

CONFIG_SETTINGS = gitstat.settings.Settings(
    fetch=gitstat.settings.FetchSettings(
        cache_path=pathlib.Path.home() / 'gitstat/cache.sqlite3',
        full_refresh_after=datetime.timedelta(weeks=2),
        include_forks=True,
        max_age=datetime.timedelta(hours=1),
        on_rate_limit='fail',
        workers=8,
    ),
    report=gitstat.settings.ReportSettings(
        format='json', out_dir=pathlib.Path('reports'), web_port=9000
    ),
    stats=gitstat.settings.StatsSettings(
        bot_logins=('ci[bot]',),
        deploy_workflow='deploy',
        failure_window=datetime.timedelta(days=3),
        timezone='Europe/London',
    ),
)
