# Spec Index

| Spec | Path | Description |
|------|------|-------------|
| [Fetch and cache](fetch-and-cache/spec.md) | `src/gitstat/fetch/` | GitHub GraphQL/REST clients, auth, rate limits, SQLite cache |
| [Stats](stats/spec.md) | `src/gitstat/stats/` | Metric computation, time bucketing, subjects (user, repo, org) |
| [Reports](reports/spec.md) | `src/gitstat/reports/`, `src/gitstat/cli.py` | Terminal, static HTML and local web app front ends |

Build order: fetch-and-cache, stats, reports. Each spec lists its prerequisites.
