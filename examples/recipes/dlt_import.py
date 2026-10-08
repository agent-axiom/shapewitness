"""Isolated local dlt/DuckDB worker for importer_regression.py.

This projection is specific to orders and orders__items. Adapt it deliberately
when your pipeline produces other tables. Generated load IDs are not stable;
child records are compared using the business ID and original array index.
"""
import json
import os
from pathlib import Path
import sys


def main():
    os.environ['RUNTIME__DLTHUB_TELEMETRY'] = 'false'
    import dlt
    import duckdb

    source = Path(sys.argv[1]).resolve()
    work = source.parent
    with duckdb.connect(str(work / 'destination.duckdb')) as db:
        pipeline = dlt.pipeline(
            pipeline_name='orders_regression', pipelines_dir=str(work / 'pipelines'),
            destination=dlt.destinations.duckdb(db), dataset_name='fixture_data',
        )
        with source.open(encoding='utf-8') as stream:
            info = pipeline.run((json.loads(line) for line in stream), table_name='orders')
        info.raise_on_failed_jobs()
        columns = db.execute(
            "SELECT table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns WHERE table_schema='fixture_data' "
            "ORDER BY table_name, ordinal_position"
        ).fetchall()
        schema = [row for row in columns if not row[0].startswith('_dlt')
                  and not row[1].startswith('_dlt')]
        # Fail if new normalized tables appear instead of silently ignoring them.
        tables = {row[0] for row in schema}
        if not tables <= {'orders', 'orders__items'}:
            raise AssertionError('Extend this recipe for the new normalized table')
        names = [row[1] for row in schema if row[0] == 'orders']
        quoted = lambda name: '"' + name.replace('"', '""') + '"'
        rows = [dict(zip(names, row)) for row in db.execute(
            'SELECT ' + ', '.join(map(quoted, names)) + ' FROM fixture_data.orders ORDER BY id'
        ).fetchall()]
        children = []
        if 'orders__items' in tables:
            names = [row[1] for row in schema if row[0] == 'orders__items']
            values = db.execute(
                'SELECT o.id, i._dlt_list_idx, ' + ', '.join('i.' + quoted(n) for n in names)
                + ' FROM fixture_data.orders__items AS i JOIN fixture_data.orders AS o'
                + ' ON i._dlt_parent_id=o._dlt_id ORDER BY o.id, i._dlt_list_idx'
            ).fetchall()
            children = [dict(zip(['id', 'index'] + names, row)) for row in values]
    print(json.dumps({'schema': schema, 'rows': rows, 'children': children, 'storage': []},
                     sort_keys=True))


if __name__ == '__main__':
    main()
