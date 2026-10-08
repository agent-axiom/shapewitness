"""Optional real-importer regression suite; no mocks in successful imports.

python -m pip install -r tests/integration/requirements.txt
python -m unittest discover -s tests/integration -v

This directory intentionally has no __init__.py, so the dependency-free core
suite does not import optional packages. Missing dependencies fail this suite.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from shapewitness import ShapeWitnessError

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'importer_regression', ROOT / 'examples/recipes/importer_regression.py')
recipe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recipe)


class FixtureTests(unittest.TestCase):
    def test_provenance_with_crlf_and_no_final_newline(self):
        source = recipe.FIXTURE.read_bytes().replace(b'\n', b'\r\n').rstrip(b'\r\n')
        # Give the last row a new shape so that its missing final newline survives.
        source += b'\r\n{"id":11,"last":true}'
        result, fixture = recipe.checked_fixture(source)
        self.assertEqual(result.rows[-1].raw, b'{"id":11,"last":true}')
        self.assertTrue(fixture.startswith(result.rows[0].raw))
        self.assertIn(b'\r\n', fixture)
        self.assertFalse(fixture.endswith(b'\n'))

    def test_incomplete_fixture_never_runs_importer(self):
        with patch.object(recipe, 'sqlite_snapshot') as importer:
            with self.assertRaisesRegex(ValueError, 'Incomplete structural coverage'):
                recipe.compare('sqlite-utils', recipe.FIXTURE.read_bytes(), max_rows=1)
            importer.assert_not_called()

    def test_late_duplicate_json_key_never_runs_importer(self):
        with patch.object(recipe, 'sqlite_snapshot') as importer:
            with self.assertRaises(ShapeWitnessError) as error:
                recipe.compare('sqlite-utils', b'{"id":1}\n{"id":2,"id":3}\n')
            self.assertEqual(error.exception.code, 'duplicate_key')
            self.assertEqual(error.exception.line, 2)
            importer.assert_not_called()


class SqliteUtilsTests(unittest.TestCase):
    def test_full_and_selected_imports_match(self):
        result, full, reduced = recipe.compare('sqlite-utils', recipe.FIXTURE.read_bytes())
        self.assertEqual([r.line for r in result.rows], [1, 3, 4, 5, 6, 7])
        self.assertEqual(result.report['coverage']['observed_features'], 28)
        self.assertEqual((len(full['rows']), len(reduced['rows'])), (10, 6))
        rows = {row['id']: row for row in reduced['rows']}
        # Reviewed behavior assertions complement full-vs-selected comparisons.
        self.assertEqual(json.loads(rows[3]['items']), [])
        self.assertIsNone(rows[4]['customer'])
        self.assertIsNone(rows[4]['active'])
        self.assertEqual(json.loads(rows[5]['customer']), {})
        self.assertEqual(json.loads(rows[5]['items'])[0]['note'], 'gift')
        self.assertEqual(rows[5]['discount'], 1.5)
        self.assertEqual(rows[6]['total'], 'pending')
        self.assertIsNone(json.loads(rows[7]['customer'])['email'])

    def test_late_column_still_requires_alter_for_selected_fixture(self):
        data = recipe.FIXTURE.read_bytes()
        _, fixture = recipe.checked_fixture(data)
        for label, source in (('full', data), ('selected', fixture)):
            with self.subTest(source=label), tempfile.TemporaryDirectory() as work:
                with self.assertRaises(subprocess.CalledProcessError) as error:
                    recipe.sqlite_snapshot(source, work, alter=False)
                self.assertIn(b'no column named discount', error.exception.stderr)

    def test_number_shape_does_not_preserve_batch_type_inference(self):
        data = b'{"id":1,"amount":1}\n{"id":2,"amount":1.5}\n'
        result, fixture = recipe.checked_fixture(data)
        self.assertEqual(len(result.rows), 1)
        with tempfile.TemporaryDirectory() as root:
            dirs = [Path(root) / name for name in ('full', 'selected')]
            for directory in dirs:
                directory.mkdir()
            full = recipe.sqlite_snapshot(data, dirs[0], batch_size=100)
            reduced = recipe.sqlite_snapshot(fixture, dirs[1], batch_size=100)
        self.assertEqual(full['schema'][1][2], 'REAL')
        self.assertEqual(reduced['schema'][1][2], 'INTEGER')
        with self.assertRaisesRegex(AssertionError, 'schema differs'):
            recipe.assert_retained_behavior(full, reduced, {1})

    def test_duplicate_primary_key_failure_can_disappear(self):
        data = b'{"id":1,"value":"first"}\n{"id":1,"value":"second"}\n'
        result, fixture = recipe.checked_fixture(data)
        self.assertEqual(len(result.rows), 1)
        with tempfile.TemporaryDirectory() as root:
            dirs = [Path(root) / name for name in ('full', 'selected')]
            for directory in dirs:
                directory.mkdir()
            with self.assertRaises(subprocess.CalledProcessError) as error:
                recipe.sqlite_snapshot(data, dirs[0])
            self.assertIn(b'UNIQUE constraint failed: orders.id', error.exception.stderr)
            self.assertEqual(len(recipe.sqlite_snapshot(fixture, dirs[1])['rows']), 1)


class DltTests(unittest.TestCase):
    def test_normalized_schema_and_retained_children_match(self):
        result, full, reduced = recipe.compare('dlt', recipe.FIXTURE.read_bytes())
        self.assertEqual([r.line for r in result.rows], [1, 3, 4, 5, 6, 7])
        self.assertEqual((len(full['rows']), len(reduced['rows'])), (10, 6))
        rows = {row['id']: row for row in reduced['rows']}
        self.assertEqual(rows[1]['customer__email'], 'ada@example.test')
        self.assertIsNone(rows[3]['customer__email'])
        self.assertIsNone(rows[4]['active'])
        self.assertEqual(rows[6]['total__v_text'], 'pending')
        self.assertIsNone(rows[6]['total'])
        self.assertEqual(rows[5]['discount'], 1.5)
        self.assertEqual(reduced['children'], [
            {'id': 1, 'index': 0, 'sku': 'book', 'qty': 1, 'note': None},
            {'id': 1, 'index': 1, 'sku': 'pen', 'qty': 2, 'note': None},
            {'id': 4, 'index': 0, 'sku': 'cup', 'qty': 1, 'note': None},
            {'id': 5, 'index': 0, 'sku': 'card', 'qty': 2, 'note': 'gift'},
            {'id': 7, 'index': 0, 'sku': 'book', 'qty': None, 'note': None},
        ])

    def test_number_shape_can_lose_dlt_variant_column(self):
        data = b'{"id":1,"amount":1}\n{"id":2,"amount":1.5}\n'
        result, fixture = recipe.checked_fixture(data)
        self.assertEqual(len(result.rows), 1)
        with tempfile.TemporaryDirectory() as root:
            dirs = [Path(root) / name for name in ('full', 'selected')]
            for directory in dirs:
                directory.mkdir()
            full = recipe.dlt_snapshot(data, dirs[0])
            reduced = recipe.dlt_snapshot(fixture, dirs[1])
        self.assertIn(['orders', 'amount__v_double', 'DOUBLE', 'YES'], full['schema'])
        self.assertNotIn(['orders', 'amount__v_double', 'DOUBLE', 'YES'], reduced['schema'])
        with self.assertRaisesRegex(AssertionError, 'schema differs'):
            recipe.assert_retained_behavior(full, reduced, {1})


if __name__ == '__main__':
    unittest.main()
