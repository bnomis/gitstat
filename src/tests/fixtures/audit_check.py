"""A short sample of the audit checker's JSON-lines output, for bin/audit-check.py."""

import json

HITS = [
    {
        'accepted': False,
        'accepted_reason': '',
        'evidence': 'typing.List',
        'line': 3,
        'path': 'src/wambatic/stats/base.py',
        'rule': 'typing-deprecated-alias',
        'variant': 'List',
    },
    {
        'accepted': True,
        'accepted_reason': 'logged by error_response()',
        'evidence': 'except Exception as e:',
        'line': 146,
        'path': 'src/wambatic/reports/web.py',
        'rule': 'silent-broad-except',
        'variant': 'except Exception',
    },
    {
        'accepted': False,
        'accepted_reason': '',
        'evidence': 'import hypothesis.strategies as st',
        'line': 8,
        'path': 'src/tests/reports/test_base.py',
        'rule': 'aliased-imports',
        'variant': 'import X as Y',
    },
    {
        'accepted': False,
        'accepted_reason': '',
        'evidence': 'typing.Dict',
        'line': 12,
        'path': 'src/wambatic_extra/base.py',
        'rule': 'typing-deprecated-alias',
        'variant': 'Dict',
    },
    {
        'accepted': False,
        'accepted_reason': '',
        'evidence': 'uv.lock',
        'line': None,
        'path': None,
        'rule': 'lockfile-stale',
        'variant': 'uv lock --check',
    },
]

JSONL = ''.join(f'{json.dumps(hit)}\n' for hit in HITS) + '\n'
