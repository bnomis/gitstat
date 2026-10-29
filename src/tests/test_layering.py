import ast
import pathlib

SOURCE = pathlib.Path(__file__).parents[1] / 'gitstat'


def gitstat_imports(path: pathlib.Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return {name for name in found if name == 'gitstat' or name.startswith('gitstat.')}


def module_name(path: pathlib.Path, package_dir: pathlib.Path) -> str:
    parts = path.relative_to(package_dir.parent).with_suffix('').parts
    return '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)


def is_within(name: str, package: str) -> bool:
    return name == package or name.startswith(f'{package}.')


def violations(package_dir: pathlib.Path) -> list[str]:
    found: list[str] = []
    for path in sorted(package_dir.rglob('*.py')):
        module = module_name(path, package_dir)
        for name in sorted(gitstat_imports(path)):
            if is_within(module, 'gitstat.fetch') and not any(
                is_within(name, allowed)
                for allowed in ('gitstat.fetch', 'gitstat.settings', 'gitstat.version')
            ):
                found.append(f'{module} imports {name}')
            elif is_within(module, 'gitstat.stats') and not any(
                is_within(name, allowed)
                for allowed in (
                    'gitstat.stats',
                    'gitstat.fetch',
                    'gitstat.settings',
                    'gitstat.version',
                )
            ):
                found.append(f'{module} imports {name}')
            elif module in ('gitstat.settings', 'gitstat.version'):
                found.append(f'{module} imports {name}')
    return found


def test_layering() -> None:
    assert violations(SOURCE) == []


def test_detects_fetch_importing_reports(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'gitstat'
    (package / 'fetch').mkdir(parents=True)
    (package / 'fetch' / 'probe.py').write_text('import gitstat.reports\n')
    assert violations(package) == ['gitstat.fetch.probe imports gitstat.reports']


def test_detects_stats_importing_reports_or_the_logs_module(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'gitstat'
    (package / 'stats').mkdir(parents=True)
    (package / 'stats' / 'probe.py').write_text('import gitstat.reports\nimport gitstat.logs\n')
    (package / 'stats' / 'fine.py').write_text(
        'import gitstat.fetch.base\nimport gitstat.settings\nimport gitstat.stats.base\n'
    )
    assert violations(package) == [
        'gitstat.stats.probe imports gitstat.logs',
        'gitstat.stats.probe imports gitstat.reports',
    ]
