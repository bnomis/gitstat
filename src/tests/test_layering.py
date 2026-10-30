import ast
import pathlib

SOURCE = pathlib.Path(__file__).parents[1] / 'wambatic'
COMPOSITION_ROOTS = ('wambatic.cli', 'wambatic.__main__')
PLOTLY_IMPORTER = 'wambatic.reports.html'


def all_imports(path: pathlib.Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def wambatic_imports(path: pathlib.Path) -> set[str]:
    return {
        name for name in all_imports(path) if name == 'wambatic' or name.startswith('wambatic.')
    }


def module_name(path: pathlib.Path, package_dir: pathlib.Path) -> str:
    parts = path.relative_to(package_dir.parent).with_suffix('').parts
    return '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)


def is_within(name: str, package: str) -> bool:
    return name == package or name.startswith(f'{package}.')


def violations(package_dir: pathlib.Path) -> list[str]:
    found: list[str] = []
    for path in sorted(package_dir.rglob('*.py')):
        module = module_name(path, package_dir)
        if module != PLOTLY_IMPORTER and any(
            is_within(name, 'plotly') for name in sorted(all_imports(path))
        ):
            found.append(f'{module} imports plotly')
        for name in sorted(wambatic_imports(path)):
            if is_within(module, 'wambatic.fetch') and not any(
                is_within(name, allowed)
                for allowed in ('wambatic.fetch', 'wambatic.settings', 'wambatic.version')
            ):
                found.append(f'{module} imports {name}')
            elif is_within(module, 'wambatic.stats') and not any(
                is_within(name, allowed)
                for allowed in (
                    'wambatic.stats',
                    'wambatic.fetch',
                    'wambatic.settings',
                    'wambatic.version',
                )
            ):
                found.append(f'{module} imports {name}')
            elif is_within(module, 'wambatic.reports') and not any(
                is_within(name, allowed)
                for allowed in (
                    'wambatic.reports',
                    'wambatic.stats',
                    'wambatic.settings',
                    'wambatic.version',
                )
            ):
                found.append(f'{module} imports {name}')
            elif module in ('wambatic.settings', 'wambatic.version'):
                found.append(f'{module} imports {name}')
            elif is_within(name, 'wambatic.cli') and module not in COMPOSITION_ROOTS:
                found.append(f'{module} imports {name}')
    return found


def test_layering() -> None:
    assert violations(SOURCE) == []


def test_detects_fetch_importing_reports(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'wambatic'
    (package / 'fetch').mkdir(parents=True)
    (package / 'fetch' / 'probe.py').write_text('import wambatic.reports\n')
    assert violations(package) == ['wambatic.fetch.probe imports wambatic.reports']


def test_detects_stats_importing_reports_or_the_logs_module(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'wambatic'
    (package / 'stats').mkdir(parents=True)
    (package / 'stats' / 'probe.py').write_text('import wambatic.reports\nimport wambatic.logs\n')
    (package / 'stats' / 'fine.py').write_text(
        'import wambatic.fetch.base\nimport wambatic.settings\nimport wambatic.stats.base\n'
    )
    assert violations(package) == [
        'wambatic.stats.probe imports wambatic.logs',
        'wambatic.stats.probe imports wambatic.reports',
    ]


def test_detects_reports_importing_fetch_or_the_cli(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'wambatic'
    (package / 'reports').mkdir(parents=True)
    (package / 'reports' / 'probe.py').write_text(
        'import wambatic.cli\nimport wambatic.fetch.base\nimport wambatic.logs\n'
    )
    (package / 'reports' / 'fine.py').write_text(
        'import wambatic.reports.base\nimport wambatic.settings\nimport wambatic.stats.base\n'
        'import wambatic.version\n'
    )
    assert violations(package) == [
        'wambatic.reports.probe imports wambatic.cli',
        'wambatic.reports.probe imports wambatic.fetch.base',
        'wambatic.reports.probe imports wambatic.logs',
    ]


def test_only_the_composition_root_may_import_the_cli(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'wambatic'
    package.mkdir()
    (package / 'logs.py').write_text('import wambatic.cli\n')
    (package / '__main__.py').write_text('import wambatic.cli\n')
    (package / 'cli.py').write_text(
        'import wambatic.fetch.base\nimport wambatic.logs\nimport wambatic.reports.base\n'
        'import wambatic.stats\nimport wambatic.cli\n'
    )
    assert violations(package) == ['wambatic.logs imports wambatic.cli']


def test_only_the_html_module_may_import_plotly(tmp_path: pathlib.Path) -> None:
    package = tmp_path / 'wambatic'
    (package / 'reports').mkdir(parents=True)
    (package / 'reports' / 'html.py').write_text('import plotly.offline\n')
    (package / 'reports' / 'figures.py').write_text('import plotly.graph_objects\n')
    (package / 'stats').mkdir()
    (package / 'stats' / 'probe.py').write_text('from plotly import io\n')
    (package / 'logs.py').write_text('import plotlyish\n')
    assert violations(package) == [
        'wambatic.reports.figures imports plotly',
        'wambatic.stats.probe imports plotly',
    ]
