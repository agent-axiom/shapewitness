"""Compare actual importer behavior for one public, synthetic JSONL fixture.

Run: python examples/recipes/importer_regression.py sqlite-utils
     python examples/recipes/importer_regression.py dlt
Optional development dependencies are in tests/integration/requirements.txt.
This is a recipe for the documented orders schema, not a generic equivalence tool.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile

from shapewitness import select

FIXTURE = Path(__file__).resolve().parents[1] / 'integrations/orders.jsonl'


def checked_fixture(data, max_rows=20, *, number_mode='json'):
    result = select(io.BytesIO(data), max_rows=max_rows, number_mode=number_mode)
    if not result.report['coverage']['complete']:
        raise ValueError('Incomplete structural coverage; increase the row budget')
    if result.report['input']['sha256'] != hashlib.sha256(data).hexdigest():
        raise AssertionError('Input digest mismatch')
    lines = data.splitlines(keepends=True)
    if len(result.rows) != len(result.report['rows']):
        raise AssertionError('Selected-row report count mismatch')
    for row, entry in zip(result.rows, result.report['rows']):
        if (row.raw != lines[row.line - 1]
                or data[row.offset:row.offset + len(row.raw)] != row.raw
                or row.sha256 != hashlib.sha256(row.raw).hexdigest()
                or entry['line'] != row.line
                or entry['byte_offset'] != row.offset
                or entry['byte_length'] != len(row.raw)
                or entry['sha256'] != row.sha256):
            raise AssertionError('Selected-row provenance mismatch')
    return result, b''.join(row.raw for row in result.rows)


def sqlite_snapshot(data, work, batch_size=1, alter=True):
    database = Path(work) / 'orders.db'
    # A fresh DB and a real CLI invocation, not a mocked sqlite-utils import.
    subprocess.run([
        sys.executable, '-m', 'sqlite_utils', 'insert', str(database), 'orders', '-',
        '--nl', '--pk', 'id', '--batch-size', str(batch_size),
        *(['--alter'] if alter else []),
    ], input=data, capture_output=True, check=True, timeout=60)
    with closing(sqlite3.connect(database)) as db:
        schema = [list(row) for row in db.execute('PRAGMA table_info(orders)')]
        columns = [row[1] for row in schema]
        db.row_factory = sqlite3.Row
        rows = [dict(row) for row in db.execute('SELECT * FROM orders ORDER BY id')]
        # SQLite affinity can change retained values even if the JSON bytes match.
        storage = [list(row) for row in db.execute(
            'SELECT id, ' + ', '.join('typeof("' + name.replace('"', '""') + '")'
                                      for name in columns) + ' FROM orders ORDER BY id')]
    return {'schema': schema, 'rows': rows, 'children': [], 'storage': storage}


def dlt_snapshot(data, work):
    work = Path(work).resolve()
    source = work / 'input.jsonl'
    source.write_bytes(data)
    # Run each pipeline in a separate process/context. Never reuse a developer's
    # pipeline state or credentials, and disable optional dlt telemetry before import.
    # Keep OS necessities, rather than inheriting dlt configuration/secrets from
    # a developer's environment. The input file contains this recipe's data only.
    environment = {key: os.environ[key] for key in
                   ('PATH', 'SYSTEMROOT', 'WINDIR', 'TMPDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL')
                   if key in os.environ}
    environment.update({'RUNTIME__DLTHUB_TELEMETRY': 'false',
                   'DLT_DATA_DIR': str(work / 'state'), 'DLT_PROJECT_DIR': str(work),
                   'DLT_LOCAL_DIR': str(work), 'RUNTIME__LOG_LEVEL': 'ERROR',
                   'HOME': str(work), 'USERPROFILE': str(work)})
    proc = subprocess.run([
        sys.executable, str(Path(__file__).with_name('dlt_import.py')), str(source),
    ], cwd=work, env=environment, capture_output=True, check=True, timeout=90)
    return json.loads(proc.stdout)


def assert_retained_behavior(full, reduced, retained_ids):
    if full['schema'] != reduced['schema']:
        raise AssertionError('Importer schema differs for full and selected input')
    expected_rows = [row for row in full['rows'] if row['id'] in retained_ids]
    if expected_rows != reduced['rows']:
        raise AssertionError('Imported values differ for retained records')
    expected_children = [row for row in full['children'] if row['id'] in retained_ids]
    if expected_children != reduced['children']:
        raise AssertionError('Normalized child rows differ for retained records')
    expected_storage = [row for row in full['storage'] if row[0] in retained_ids]
    if expected_storage != reduced['storage']:
        raise AssertionError('SQLite storage classes differ for retained records')


def compare(importer, data, max_rows=20, *, number_mode='json'):
    result, fixture = checked_fixture(data, max_rows, number_mode=number_mode)
    # This recipe requires a unique business ID for comparisons across fresh loads.
    records = [json.loads(line) for line in data.splitlines()]
    ids = [record['id'] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError('This recipe requires unique id values')
    retained_ids = {json.loads(row.raw)['id'] for row in result.rows}
    snapshot = {'sqlite-utils': sqlite_snapshot, 'dlt': dlt_snapshot}[importer]
    with tempfile.TemporaryDirectory(prefix='shapewitness-importers-') as root:
        full_dir, reduced_dir = Path(root) / 'full', Path(root) / 'selected'
        full_dir.mkdir()
        reduced_dir.mkdir()
        full = snapshot(data, full_dir)
        reduced = snapshot(fixture, reduced_dir)
    assert_retained_behavior(full, reduced, retained_ids)
    return result, full, reduced


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('importer', choices=('sqlite-utils', 'dlt'))
    parser.add_argument('--number-mode', choices=('json', 'syntax'), default='json')
    args = parser.parse_args()
    result, _, _ = compare(args.importer, FIXTURE.read_bytes(), number_mode=args.number_mode)
    print(json.dumps({'importer': args.importer,
                      'input_records': result.report['input']['records'],
                      'selected_lines': [row.line for row in result.rows],
                      'observed_features': result.report['coverage']['observed_features'],
                      'structural_coverage_complete': True,
                      'retained_import_behavior_matches': True,
                      'input_sha256': result.report['input']['sha256']}, sort_keys=True))


if __name__ == '__main__':
    main()
