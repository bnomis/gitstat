#!/usr/bin/env python
"""List the audit checker's unaccepted hits, optionally only some rules or paths.

Runs the auditme checker from the `.agents` submodule over the repository and writes each
`accepted: false` hit as `path:line rule variant`. Exits 1 when a hit remains, 0 when none does,
and 2 when the checker cannot run (an empty `.agents`, or the checker failing).
"""

import argparse
import collections.abc
import json
import pathlib
import subprocess
import sys
import typing

import loguru

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKER = pathlib.Path('.agents/claude/skills/auditme/checks/audit.py')
FILL_SUBMODULE = 'git submodule update --init'


def parse_args(argv: collections.abc.Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='audit-check',
        description='List the audit checker hits that are not accepted.',
    )
    parser.add_argument(
        '--rule',
        action='append',
        default=[],
        metavar='NAME',
        help='Count only hits of this rule (repeatable)',
    )
    parser.add_argument(
        '--path',
        action='append',
        default=[],
        metavar='PREFIX',
        help='Count only hits under this path, relative to the repository root (repeatable)',
    )
    return parser.parse_args(argv)


def missing_checker_message(root: pathlib.Path) -> str | None:
    """Why the checker cannot run, or None when it is in place."""
    if (root / CHECKER).is_file():
        return None
    return f'{root / CHECKER} not found: .agents is empty; run `{FILL_SUBMODULE}`'


def under(path: str | None, prefixes: collections.abc.Sequence[str]) -> bool:
    if path is None:
        return False
    return any(
        path == prefix.rstrip('/') or path.startswith(f'{prefix.rstrip("/")}/')
        for prefix in prefixes
    )


def unaccepted(
    jsonl: str,
    rules: collections.abc.Sequence[str],
    paths: collections.abc.Sequence[str],
) -> list[dict[str, typing.Any]]:
    """The unaccepted hits in the checker's output, restricted to `rules` and `paths` when given."""
    hits = [json.loads(line) for line in jsonl.splitlines() if line.strip()]
    return [
        hit
        for hit in hits
        if not hit['accepted']
        and (not rules or hit['rule'] in rules)
        and (not paths or under(hit['path'], paths))
    ]


def format_hit(hit: dict[str, typing.Any]) -> str:
    path = '-' if hit['path'] is None else hit['path']
    line = '-' if hit['line'] is None else hit['line']
    return f'{path}:{line} {hit["rule"]} {hit["variant"]}'


def report(
    jsonl: str,
    rules: collections.abc.Sequence[str],
    paths: collections.abc.Sequence[str],
    out: typing.TextIO,
) -> int:
    hits = unaccepted(jsonl, rules, paths)
    for hit in hits:
        out.write(f'{format_hit(hit)}\n')
    return 1 if hits else 0


def run_checker(root: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['python3', str(root / CHECKER), str(root)],
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )


def main(
    argv: collections.abc.Sequence[str] | None = None,
    root: pathlib.Path = ROOT,
) -> int:
    args = parse_args(argv)
    message = missing_checker_message(root)
    if message is not None:
        loguru.logger.error(message)
        return 2
    result = run_checker(root)
    if result.returncode != 0:
        loguru.logger.error(f'{CHECKER} exited with status {result.returncode}')
        return 2
    return report(result.stdout, args.rule, args.path, sys.stdout)


if __name__ == '__main__':
    sys.exit(main())
