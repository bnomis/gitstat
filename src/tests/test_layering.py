import ast
import pathlib

SOURCE = pathlib.Path(__file__).parents[1] / 'gitstat'
COMPOSITION_ROOTS = ('gitstat.cli', 'gitstat.__main__')


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
            elif is_within(module, 'gitstat.reports') and not any(
                is_within(name, allowed)
                for allowed in (
                    'gitstat.reports',
                    'gitstat.stats',
                    'gitstat.settings',
                    'gitstat.version',
                )
            ):
                found.append(f'{module} imports {name}')
            elif module in ('gitstat.settings', 'gitstat.version'):
                found.append(f'{module} imports {name}')
            elif is_within(name, 'gitstat.cli') and module not in COMPOSITION_ROOTS:
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


def test_detects_reports_importing_fetch_or_the_cli(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'gitstat'
    (package / 'reports').mkdir(parents=True)
    (package / 'reports' / 'probe.py').write_text(
        'import gitstat.cli\nimport gitstat.fetch.base\nimport gitstat.logs\n'
    )
    (package / 'reports' / 'fine.py').write_text(
        'import gitstat.reports.base\nimport gitstat.settings\nimport gitstat.stats.base\n'
        'import gitstat.version\n'
    )
    assert violations(package) == [
        'gitstat.reports.probe imports gitstat.cli',
        'gitstat.reports.probe imports gitstat.fetch.base',
        'gitstat.reports.probe imports gitstat.logs',
    ]


def test_only_the_composition_root_may_import_the_cli(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'gitstat'
    package.mkdir()
    (package / 'logs.py').write_text('import gitstat.cli\n')
    (package / '__main__.py').write_text('import gitstat.cli\n')
    (package / 'cli.py').write_text(
        'import gitstat.fetch.base\nimport gitstat.logs\nimport gitstat.reports.base\n'
        'import gitstat.stats\nimport gitstat.cli\n'
    )
    assert violations(package) == ['gitstat.logs imports gitstat.cli']
