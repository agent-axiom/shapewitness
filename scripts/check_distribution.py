"""Inspect local release candidates without uploading or reading credentials.

Run with Python 3.11+: python scripts/check_distribution.py dist
"""
import argparse
import configparser
import email.parser
import hashlib
import json
import tarfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inspect(directory):
    config = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
    name, version = config['name'], config['version']
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
        assert metadata['Requires-Python'] == '>=3.10'
        assert metadata['License-Expression'] == 'MIT'
        assert not metadata.get_all('Requires-Dist'), 'Unexpected runtime dependency'
        assert metadata['Description-Content-Type'] == 'text/markdown'
        assert '](docs/' not in metadata.get_payload(), 'Relative package-description link'
        entrypoints = configparser.ConfigParser()
        entrypoints.read_string(archive.read(f'{name}-{version}.dist-info/entry_points.txt').decode())
        assert entrypoints['console_scripts']['shapewitness'] == 'shapewitness.cli:main'
        assert 'shapewitness/py.typed' in names
        assert any(path.endswith('/licenses/LICENSE') for path in names)
        assert not any(path.startswith(('tests/', 'examples/', '.')) for path in names)
    with tarfile.open(sdist, 'r:gz') as archive:
        names = set(archive.getnames())
        prefix = f'{name}-{version}/'
        for required in ('LICENSE', 'AGENTS.md', 'README.md', 'docs/release/PYPI_README.md',
                         'docs/release/publish.yml.example', 'src/shapewitness/core.py',
                         'examples/recipes/pytest_fixtures.py', 'tests/test_core.py',
                         'scripts/compare_sampling.py', 'benchmarks/synthetic.jsonl'):
            assert prefix + required in names, f'Missing sdist member: {required}'
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
