# Spec Index

| Spec | Path | Description |
|------|------|-------------|
| [System](system/spec.md) | `src/gitstat/` | Architecture, data flow, stack, build order and settings across components |
| [Fetch and cache](fetch-and-cache/spec.md) | `src/gitstat/fetch/` | GitHub GraphQL/REST clients, auth, rate limits, SQLite cache |
| [Stats](stats/spec.md) | `src/gitstat/stats/` | Metric computation, time bucketing, subjects (user, repo, org) |
| [Reports](reports/spec.md) | `src/gitstat/reports/`, `src/gitstat/cli.py` | Terminal, static HTML and local web app front ends |

Read the system spec first. Each component spec lists its prerequisites.

Sequencing of the work is in [Implementation order](implementation-order.md).
