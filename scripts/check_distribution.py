"""Inspect local release candidates without uploading or reading credentials.

Run with Python 3.11+: python scripts/check_distribution.py dist
"""
import argparse
import ast
import configparser
import email.parser
import hashlib
import json
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def literal_version(source):
    """Read the version from source/archives without importing or executing it."""
    statements = [node for node in ast.parse(source).body
                  if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                          and isinstance(node.value.value, str))]
    if len(statements) != 1 or not isinstance(statements[0], ast.Assign):
        raise ValueError('Expected exactly one literal __version__ assignment')
    assignment = statements[0]
    if (len(assignment.targets) != 1 or not isinstance(assignment.targets[0], ast.Name)
            or assignment.targets[0].id != '__version__'):
        raise ValueError('Expected exactly one literal __version__ assignment')
    if not isinstance(assignment.value, ast.Constant) or not isinstance(assignment.value.value, str):
        raise ValueError('__version__ must be a literal string')
    return assignment.value.value


def inspect(directory):
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
    name, version = config['name'], config['version']
    assert literal_version((ROOT / 'src/shapewitness/_version.py').read_bytes()) == version, 'Source version drift'
    wheels = list(directory.glob('*.whl'))
    sdists = list(directory.glob('*.tar.gz'))
    assert len(wheels) == len(sdists) == 1, 'Use a clean candidate directory with one wheel and one sdist'
    wheel, sdist = wheels[0], sdists[0]
    assert wheel.name == f'{name}-{version}-py3-none-any.whl'
    assert sdist.name == f'{name}-{version}.tar.gz'
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_path = f'{name}-{version}.dist-info/METADATA'
        metadata = email.parser.BytesParser().parsebytes(archive.read(metadata_path))
        assert metadata['Name'] == name and metadata['Version'] == version
        assert literal_version(archive.read('shapewitness/_version.py')) == version, 'Wheel runtime version drift'
        assert metadata['Requires-Python'] == '>=3.10'
        assert metadata['License-Expression'] == 'MIT'
        assert not metadata.get_all('Requires-Dist'), 'Unexpected runtime dependency'
        assert metadata['Description-Content-Type'] == 'text/markdown'
        assert '](docs/' not in metadata.get_payload(), 'Relative package-description link'
        entrypoints = configparser.ConfigParser()
        entrypoints.read_string(archive.read(f'{name}-{version}.dist-info/entry_points.txt').decode())
        assert entrypoints['console_scripts']['shapewitness'] == 'shapewitness.cli:main'
        assert 'shapewitness/comparison.py' in names
        assert 'shapewitness/py.typed' in names
        assert any(path.endswith('/licenses/LICENSE') for path in names)
        assert not any(path.startswith(('tests/', 'examples/', '.')) for path in names)
    with tarfile.open(sdist, 'r:gz') as archive:
        names = set(archive.getnames())
        prefix = f'{name}-{version}/'
        for required in ('LICENSE', 'AGENTS.md', 'README.md', 'docs/release/PYPI_README.md',
                         'docs/release/publish.yml.example', 'src/shapewitness/core.py',
                         'src/shapewitness/_version.py', 'src/shapewitness/comparison.py',
                         'examples/recipes/structural_regression.py',
                         'examples/regression/baseline-report.json', 'examples/regression/baseline.jsonl',
                         'examples/regression/current.jsonl', 'examples/regression/current.witness.jsonl',
                         'examples/regression/drifted.jsonl', 'examples/regression/pins.json',
                         'tests/test_comparison.py', 'tests/test_pins.py',
                         'docs/recipes/structural-regression.md',
                         'examples/recipes/pytest_fixtures.py', 'tests/test_core.py',
                         'examples/integrations/orders.jsonl',
                         'examples/recipes/importer_regression.py', 'examples/recipes/dlt_import.py',
                         'tests/integration/test_importers.py', 'tests/integration/requirements.txt',
                         'scripts/compare_sampling.py', 'benchmarks/synthetic.jsonl'):
            assert prefix + required in names, f'Missing sdist member: {required}'
        source_version = archive.extractfile(prefix + 'src/shapewitness/_version.py').read()
        assert literal_version(source_version) == version, 'Source archive runtime version drift'
        assert not any('/.venv/' in path or '/.release-venv/' in path or '/.git/' in path for path in names)
    return {'package': name, 'version': version, 'runtime_dependencies': [],
            'artifacts': [{'filename': path.name, 'bytes': path.stat().st_size,
                           'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                          for path in (wheel, sdist)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.directory), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
