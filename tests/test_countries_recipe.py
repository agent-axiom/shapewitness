"""Offline, dependency-free guards for the opt-in external countries recipe."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shapewitness import select

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'countries_importer', ROOT / 'examples/recipes/countries_importer.py')
recipe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recipe)


class CountriesRecipeTests(unittest.TestCase):
    def test_hash_mismatch_rejected_before_import_or_output(self):
        with tempfile.TemporaryDirectory() as work:
            source = Path(work) / 'source.json'
            source.write_bytes(b'[]')
            output = Path(work) / 'output'
            with patch.object(recipe.importlib.metadata, 'version', return_value='4.2.1'), \
                    patch.object(recipe, 'import_once') as importer:
                with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                    recipe.run(source, output)
                importer.assert_not_called()
                self.assertFalse(output.exists())

    def test_source_conversion_is_documented_and_deterministic(self):
        rows = [{'id': i, 'name': 'été', 'amount': 1.5} for i in range(250)]
        raw = json.dumps(rows).encode()
        with patch.object(recipe, 'SOURCE_SHA256', recipe.digest(raw)):
            result = recipe.convert_source(raw)
        self.assertEqual(result.splitlines()[0], '{"id":0,"name":"été","amount":1.5}'.encode())
        self.assertEqual([json.loads(row) for row in result.splitlines()], rows)
        self.assertTrue(result.endswith(b'\n'))

    def test_source_dimensions_checked_after_digest(self):
        for raw in (b'[]', b'{}'):
            with self.subTest(raw=raw), patch.object(recipe, 'SOURCE_SHA256', recipe.digest(raw)):
                with self.assertRaisesRegex(ValueError, '250-entry'):
                    recipe.convert_source(raw)

    def test_selection_preserves_raw_bytes_and_offsets(self):
        raw = b'{"id":1}\r\n{ "id":2, "extra": null }'
        result, selected = recipe.select_checked(raw)
        self.assertEqual(selected, raw)
        self.assertEqual([row.line for row in result.rows], [1, 2])

    def test_incomplete_selection_rejected(self):
        result = select(io.BytesIO(b'{"x":1}\n'), max_rows=0)
        with patch.object(recipe, 'select', return_value=result):
            with self.assertRaisesRegex(AssertionError, 'Incomplete'):
                recipe.select_checked(b'{"x":1}\n')

    def test_inventory_compares_path_kind_not_local_ids(self):
        def report(number):
            return {'features': [{'id': number, 'path': ['x', None], 'kind': 'string'}]}
        self.assertEqual(recipe.inventory(report(1)), recipe.inventory(report(99)))

    def test_invalid_repeats_and_version_rejected(self):
        with self.assertRaisesRegex(ValueError, 'positive'):
            recipe.run(Path('unused'), Path('unused'), repeats=0)
        with patch.object(recipe.importlib.metadata, 'version', return_value='0.0.0'):
            with self.assertRaisesRegex(ValueError, 'sqlite-utils==4.2.1'):
                recipe.run(Path('unused'), Path('unused'))

    def test_schema_mismatch_is_not_hidden(self):
        with self.assertRaisesRegex(AssertionError, 'Column definitions'):
            recipe.assert_equivalent({'schema': []}, {'schema': [('x',)]}, set())

    def test_retained_values_and_storage_must_match(self):
        full = {'schema': [], 'values': {'id': (1,)}, 'storage': {'id': ('integer',)}}
        for kind in ('values', 'storage'):
            selected = {**full, kind: {'id': ('different',)}}
            with self.subTest(kind=kind), self.assertRaisesRegex(AssertionError, kind):
                recipe.assert_equivalent(full, selected, {'id'})

    def test_prefix_coverage_uses_full_vocabulary(self):
        data = b'{"a":1}\n{"b":2}\n'
        per_row = recipe.row_inventory(data)
        self.assertEqual(per_row[0], {((), 'object'), (('a',), 'number'), (('b',), 'missing')})
        report = select(io.BytesIO(data), max_rows=2).report
        self.assertEqual(set().union(*per_row), recipe.inventory(report))
