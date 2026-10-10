"""Reproduce a real sqlite-utils import with a pinned public countries dataset.

No network access: supply the exact upstream countries.json with --source.
The public-data case is opt-in; synthetic helper tests run in the core suite.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

from shapewitness import __version__, select

COMMIT = 'c2ac0049c14edcf2436c7aa1b2493222a020b462'
SOURCE_URL = f'https://raw.githubusercontent.com/mledoze/countries/{COMMIT}/countries.json'
SOURCE_SHA256 = '913e5d716f9dc6b59881ee23488d47f5fda52070d1a34cac5fa327c9e61d8f7c'
LICENSE_URL = 'https://opendatacommons.org/licenses/odbl/1-0/'
EXPECTED_ERROR = 'table countries has no column named name_native_prs_official'
NOTICE = f'''Contains information from mledoze/countries ({COMMIT}),
made available under the Open Database License (ODbL) 1.0:
{LICENSE_URL}
Source: {SOURCE_URL}
Upstream license: https://github.com/mledoze/countries/blob/{COMMIT}/LICENSE
The generated full.jsonl and selected.jsonl are derived databases under ODbL 1.0,
not the code repository's MIT license. Transformation: JSON array entries in source
order, serialized as compact UTF-8 JSON with ensure_ascii=False and a final LF per
record; selected.jsonl retains exact lines from full.jsonl. The complete method is
examples/recipes/countries_importer.py. No factual values are intentionally edited.
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def convert_source(raw):
    if digest(raw) != SOURCE_SHA256:
        raise ValueError('Upstream SHA-256 mismatch; obtain the exact pinned file')
    rows = json.loads(raw)
    if not isinstance(rows, list) or len(rows) != 250:
        raise ValueError('Expected the pinned 250-entry JSON array')
    return b''.join((json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')
                    .encode('utf-8') for row in rows)


def select_checked(data):
    result = select(io.BytesIO(data), max_rows=250)
    if not result.report['coverage']['complete']:
        raise AssertionError('Incomplete structural coverage')
    lines = data.splitlines(keepends=True)
    for row in result.rows:
        if (row.raw != lines[row.line - 1]
                or data[row.offset:row.offset + len(row.raw)] != row.raw
                or row.sha256 != digest(row.raw)):
            raise AssertionError('Selected-row provenance mismatch')
    return result, b''.join(row.raw for row in result.rows)


def import_once(data, *, alter):
    # Time the actual CLI process, including startup and SQLite writes; snapshot
    # queries and temporary-directory setup/cleanup are outside this interval.
    with tempfile.TemporaryDirectory(prefix='countries-import-') as work:
        db_path = Path(work) / 'countries.db'
        command = [sys.executable, '-m', 'sqlite_utils', 'insert', str(db_path),
                   'countries', '-', '--nl', '--flatten', '--pk', 'cca3',
                   '--batch-size', '1', *(['--alter'] if alter else [])]
        start = time.perf_counter()
        proc = subprocess.run(command, input=data, capture_output=True, timeout=120)
        seconds = time.perf_counter() - start
        if not alter:
            stderr = proc.stderr.decode('utf-8', errors='replace')
            if proc.returncode != 1 or EXPECTED_ERROR not in stderr:
                raise AssertionError(f'Expected the specific late-column failure: {stderr}')
            return seconds, {'returncode': proc.returncode, 'error': EXPECTED_ERROR}
        if proc.returncode:
            raise AssertionError(proc.stderr.decode('utf-8', errors='replace'))
        with closing(sqlite3.connect(db_path)) as db:
            # Column order is not compared: column discovery order may differ.
            schema = sorted(tuple(row[1:]) for row in db.execute('PRAGMA table_info(countries)'))
            names = [row[0] for row in schema]
            quoted = [f'"{name.replace(chr(34), chr(34) * 2)}"' for name in names]
            values = {row[0]: tuple(row[1:]) for row in db.execute(
                'SELECT cca3, ' + ', '.join(quoted) + ' FROM countries')}
            storage = {row[0]: tuple(row[1:]) for row in db.execute(
                'SELECT cca3, ' + ', '.join(f'typeof({name})' for name in quoted)
                + ' FROM countries')}
        return seconds, {'schema': schema, 'values': values, 'storage': storage}


def assert_equivalent(full, selected, ids):
    if full['schema'] != selected['schema']:
        raise AssertionError('Column definitions differ')
    for kind in ('values', 'storage'):
        if {key: full[kind][key] for key in ids} != selected[kind]:
            raise AssertionError(f'Retained {kind} differ')
    # Independent expectations catch some shared failures too.
    names = [row[0] for row in selected['schema']]
    if len(names) != 855 or len(full['values']) != 250 or len(selected['values']) != 176:
        raise AssertionError('Pinned import dimensions changed')
    if selected['values']['AFG'][names.index('name_native_prs_official')] != 'جمهوری اسلامی افغانستان':
        raise AssertionError('Expected late native-name field was not imported')


def inventory(report):
    return {(tuple(feature['path']), feature['kind']) for feature in report['features']}



def row_inventory(data):
    """Independent default-mode oracle, using the FULL input's member vocabulary.

    Evaluating a prefix as a separate input would miss absent-member features
    introduced later. This oracle is outside selection/import timing intervals.
    """
    def walk(value, path=()):
        yield path, value
        if isinstance(value, dict):
            for key, child in value.items():
                yield from walk(child, path + (key,))
        elif isinstance(value, list):
            for child in value:
                yield from walk(child, path + (None,))

    values = [json.loads(line) for line in data.splitlines()]
    vocabulary = {}
    for value in values:
        for path, node in walk(value):
            if isinstance(node, dict):
                vocabulary.setdefault(path, set()).update(node)
    kinds = {type(None): 'null', bool: 'boolean', int: 'number', float: 'number',
             str: 'string', list: 'array', dict: 'object'}
    rows = []
    for value in values:
        features = set()
        for path, node in walk(value):
            kind = kinds[type(node)]
            features.add((path, kind))
            if isinstance(node, (dict, list)) and not node:
                features.add((path, 'empty-' + kind))
            if isinstance(node, dict):
                features.update((path + (key,), 'missing')
                                for key in vocabulary[path] - node.keys())
        rows.append(features)
    return rows


def run(source, output, repeats=5):
    if output.exists():
        raise FileExistsError('Use a new output directory')
    if repeats < 1:
        raise ValueError('repeats must be positive')
    if importlib.metadata.version('sqlite-utils') != '4.2.1':
        raise ValueError('This case requires sqlite-utils==4.2.1')
    # Fail closed before output or import if the source has changed.
    raw = source.read_bytes()
    data = convert_source(raw)
    selection_seconds = []
    for _ in range(repeats):
        start = time.perf_counter()
        result, selected = select_checked(data)
        selection_seconds.append(time.perf_counter() - start)
    ids = {json.loads(row.raw)['cca3'] for row in result.rows}
    if len(ids) != 176 or result.report['coverage']['observed_features'] != 1683:
        raise AssertionError('Pinned selection dimensions changed')
    per_row_features = row_inventory(data)
    full_inventory = set().union(*per_row_features)
    selected_inventory = set().union(*(per_row_features[row.line - 1] for row in result.rows))
    if full_inventory != inventory(result.report) or selected_inventory != full_inventory:
        raise AssertionError('Independent full-vocabulary coverage check failed')
    head = b''.join(data.splitlines(keepends=True)[:len(result.rows)])
    head_inventory = set().union(*per_row_features[:len(result.rows)])
    timings = {key: [] for key in ('full_success', 'selected_success', 'full_failure', 'selected_failure')}
    # Alternate order per repetition, use fresh databases every time, retain all
    # samples, and make no statistical significance or general speed claim.
    for repetition in range(repeats):
        inputs = [('full', data), ('selected', selected)]
        if repetition % 2:
            inputs.reverse()
        snapshots = {}
        for name, content in inputs:
            seconds, snapshots[name] = import_once(content, alter=True)
            timings[f'{name}_success'].append(seconds)
            seconds, failure = import_once(content, alter=False)
            timings[f'{name}_failure'].append(seconds)
        assert_equivalent(snapshots['full'], snapshots['selected'], ids)
    # A first-N baseline also preserves this early failure. Do not imply this
    # failure predicate needed structural selection to find it.
    _, head_failure = import_once(head, alter=False)
    summary = {
        'source': {'url': SOURCE_URL, 'commit': COMMIT, 'sha256': digest(raw),
                   'bytes': len(raw), 'license': LICENSE_URL},
        'environment': {'python': platform.python_version(), 'platform': platform.platform(),
                        'sqlite': sqlite3.sqlite_version, 'sqlite_utils': '4.2.1',
                        'shapewitness': __version__},
        'options': {'max_rows': 250, 'number_mode': 'json', 'pins': [],
                    'importer': 'insert --nl --flatten --pk cca3 --batch-size 1 [--alter]'},
        'full': {'rows': 250, 'bytes': len(data), 'sha256': digest(data)},
        'selected': {'rows': len(result.rows), 'bytes': len(selected), 'sha256': digest(selected),
                     'source_lines': [row.line for row in result.rows]},
        'coverage': result.report['coverage'],
        'first_n_baseline': {'rows': len(result.rows), 'bytes': len(head),
                            'covered_full_features': len(head_inventory),
                            'observed_full_features': len(full_inventory),
                            'same_failure_reproduced': head_failure == failure},
        'assertions': {'column_definitions_equal': True, 'retained_values_equal': True,
                       'retained_storage_classes_equal': True, 'columns': 855,
                       'full_and_selected_failure': failure},
        'seconds': {'selection_and_provenance': selection_seconds, **timings},
        'median_seconds': {key: statistics.median(value) for key, value in
                           {'selection_and_provenance': selection_seconds, **timings}.items()},
        'first_observed_seconds': {key: value[0] for key, value in
                                   {'selection_and_provenance': selection_seconds, **timings}.items()},
        'subsequent_median_seconds': {key: statistics.median(value[1:]) for key, value in
                                     {'selection_and_provenance': selection_seconds, **timings}.items()
                                     if len(value) > 1},
        'timing_scope': 'CLI startup plus import into fresh SQLite DB; no download, selection or snapshot queries',
        'selection_timing_scope': 'Selection plus raw-byte provenance checks; excludes JSON-array conversion',
        'timing_method': 'No discarded warmup. Alternate full/selected order. First observed is not a cold-machine guarantee.',
        'limitations': ['Demonstrable configuration failure, not a historical upstream bug.',
                        'No external adoption or independent user trial is claimed.',
                        'First-N also reproduces this early failure.',
                        'Complete structure coverage does not establish general importer equivalence.',
                        'One small dataset and one local environment; timings are not general speed claims.'],
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / 'NOTICE.txt').write_text(NOTICE, encoding='utf-8')
    (output / 'full.jsonl').write_bytes(data)
    (output / 'selected.jsonl').write_bytes(selected)
    (output / 'coverage.json').write_text(json.dumps(result.report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New output directory')
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output, args.repeats), indent=2, ensure_ascii=False))
