from __future__ import annotations

import hashlib
import io
import json
import random
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from shapewitness import Limits, ShapeWitnessError, select


def run(data: bytes, **kwargs):
    return select(io.BytesIO(data), **kwargs)


def feature_set(report):
    return {(tuple(f['path']), f['kind']) for f in report['features']}


class SelectionTests(unittest.TestCase):
    def test_example(self):
        data = (Path(__file__).parents[1] / 'examples/events.jsonl').read_bytes()
        result = run(data, max_rows=4)
        self.assertEqual([row.line for row in result.rows], [1, 3, 4, 5])
        self.assertTrue(result.report['coverage']['complete'])
        self.assertEqual(result.report['coverage']['observed_features'], 19)
        self.assertEqual(result.report['input']['sha256'], hashlib.sha256(data).hexdigest())

    def test_original_bytes_and_extreme_numbers(self):
        data = b' {"huge":' + b'9' * 10000 + b', "precise":0.123456789012345678901234567890,"exp":1e9999999} \r\nnull'
        result = run(data)
        output = io.BytesIO()
        result.write_jsonl(output)
        self.assertEqual(output.getvalue(), data)
        self.assertEqual(result.rows[1].offset, data.index(b'null'))
        self.assertEqual(result.rows[0].sha256, hashlib.sha256(result.rows[0].raw).hexdigest())

    def test_null_missing_empty_distinct(self):
        result = run(b'{"x":null}\n{}\n{"x":{}}\n{"x":[]}\n')
        features = feature_set(result.report)
        self.assertIn((('x',), 'null'), features)
        self.assertIn((('x',), 'missing'), features)
        self.assertIn((('x',), 'empty-object'), features)
        self.assertIn((('x',), 'empty-array'), features)
        self.assertEqual(len(result.rows), 4)

    def test_missing_discovered_later_and_parent_local(self):
        result = run(b'{"a":{}}\n{"a":{"b":1}}\n{}\n{"a":null}\n')
        ids = {f['id']: (f['path'], f['kind']) for f in result.report['features']}
        row_features = {row.line: [ids[i] for i in row.feature_ids] for row in result.rows}
        self.assertIn((['a', 'b'], 'missing'), row_features[1])
        self.assertIn((['a'], 'missing'), row_features[3])
        self.assertNotIn((['a', 'b'], 'missing'), row_features[3])
        self.assertNotIn((['a', 'b'], 'missing'), row_features[4])

    def test_array_wildcards_and_mixed_members(self):
        result = run(b'{"x":[{"a":1},{"b":2},3,null],"*":1,"":true,"a.b":4,"a/b":5}\n')
        features = feature_set(result.report)
        self.assertIn((('x', None, 'a'), 'missing'), features)
        self.assertIn((('x', None, 'b'), 'missing'), features)
        self.assertIn((('x', None), 'number'), features)
        self.assertIn((('*',), 'number'), features)
        self.assertIn((('',), 'boolean'), features)
        self.assertNotIn((('a', 'b'), 'number'), features)

    def test_scalars_and_top_level_arrays(self):
        result = run(b'null\nfalse\n1\n"text"\n[]\n{}\n[false,2]\n')
        features = feature_set(result.report)
        for kind in ('null', 'boolean', 'number', 'string', 'array', 'object', 'empty-array', 'empty-object'):
            self.assertIn(((), kind), features)
        self.assertIn(((None,), 'boolean'), features)

    def test_deterministic_tie_earliest_and_source_order(self):
        data = b'{"x":1}\n{"x":2}\n{"y":1,"z":[]}\n'
        first = run(data, max_rows=2)
        self.assertEqual(first, run(data, max_rows=2))
        self.assertEqual([r.line for r in first.rows], [1, 3])
        self.assertEqual(first.rows[1].selection_rank, 1)
        self.assertEqual(first.rows[0].selection_rank, 2)

    def test_output_byte_budget_skips_large_candidates(self):
        data = b'{"long":"abcdef","x":1}\nnull\n'
        result = run(data, limits=replace(Limits(), max_output_bytes=5))
        self.assertEqual([r.line for r in result.rows], [2])
        self.assertEqual(result.report['selection']['stop_reason'], 'output_byte_budget')
        self.assertFalse(result.report['coverage']['complete'])

    def test_empty_input_and_zero_budget(self):
        self.assertTrue(run(b'').report['coverage']['complete'])
        result = run(b'null\n', max_rows=0)
        self.assertFalse(result.report['coverage']['complete'])
        self.assertEqual(result.rows, ())
        self.assertEqual(result.report['selection']['stop_reason'], 'row_budget')

    def test_skip_blanks_preserves_physical_locations(self):
        result = run(b'\nnull\n \r\n{}', skip_blank_lines=True)
        self.assertEqual([r.line for r in result.rows], [2, 4])
        self.assertEqual([r.offset for r in result.rows], [1, 9])
        self.assertEqual(result.report['input']['skipped_blank_lines'], 2)

    def test_nonseekable(self):
        class Pipe:
            def __init__(self):
                self.stream = io.BytesIO(b'{}\n{"x":1}\n')
            def readline(self, size):
                return self.stream.readline(size)
        self.assertTrue(select(Pipe()).report['coverage']['complete'])

    def test_escaped_unicode_surrogate_pair(self):
        self.assertTrue(run(b'{"\\ud83d\\ude00":"\\ud83d\\ude00"}\n').report['coverage']['complete'])


class ValidationTests(unittest.TestCase):
    def test_strict_input(self):
        cases = [(b'\n', 'blank_line'), (b'{}\n \n', 'blank_line'),
                 (b'NaN\n', 'invalid_json'), (b'Infinity\n', 'invalid_json'),
                 (b'{"x":1,"x":2}\n', 'duplicate_key'),
                 (b'{"x":1,"\\u0078":2}\n', 'duplicate_key'),
                 (b'{"nested":{"a":1,"a":2}}\n', 'duplicate_key'),
                 (b'{} {}\n', 'invalid_json'), (b'{\n}\n', 'invalid_json'),
                 (b'\xff\n', 'invalid_utf8'), (b'\xef\xbb\xbf{}\n', 'invalid_utf8'),
                 (b'"\\ud800"\n', 'invalid_unicode'),
                 (b'{"\\udc00":1}\n', 'invalid_unicode'),
                 (b'01\n', 'invalid_json'), (b'1.\n', 'invalid_json'),
                 (b'"literal\x01"\n', 'invalid_json')]
        for data, code in cases:
            with self.subTest(data=data):
                with self.assertRaises(ShapeWitnessError) as error:
                    run(data)
                self.assertEqual(error.exception.code, code)
                self.assertIsNotNone(error.exception.line)

    def test_no_row_content_in_errors(self):
        with self.assertRaises(ShapeWitnessError) as error:
            run(b'{"TOP_SECRET":1,"TOP_SECRET":2}\n')
        self.assertNotIn('TOP_SECRET', str(error.exception))

    def test_each_limit(self):
        cases = [('max_line_bytes', 4, b'null\n'),
                 ('max_input_bytes', 6, b'null\n{}\n'),
                 ('max_records', 1, b'null\n{}\n'),
                 ('max_depth', 1, b'{"x":{}}\n'),
                 ('max_nodes_per_record', 2, b'[1,2]\n'),
                 ('max_features', 2, b'{"x":null,"y":true}\n'),
                 ('max_path_bytes', 4, b'{"abcdef":0}\n'),
                 ('max_associations', 1, b'{"x":1}\n')]
        for name, cap, data in cases:
            with self.subTest(name=name):
                with self.assertRaises(ShapeWitnessError) as error:
                    run(data, max_rows=1, limits=replace(Limits(), **{name: cap}))
                self.assertEqual(error.exception.code, 'limit')
                self.assertIn(name, str(error.exception))

    def test_spool_bound_and_cleanup(self):
        with tempfile.TemporaryDirectory() as work:
            with self.assertRaises(ShapeWitnessError) as error:
                run((b'{"x":"' + b'a' * 1024 + b'"}\n') * 200,
                    limits=replace(Limits(), max_spool_bytes=65536), temp_dir=work)
            self.assertEqual(error.exception.code, 'limit')
            self.assertIn('max_spool_bytes', str(error.exception))
            self.assertEqual(list(Path(work).iterdir()), [])
            with self.assertRaises(ShapeWitnessError):
                run(b'{invalid}\n', temp_dir=work)
            self.assertEqual(list(Path(work).iterdir()), [])

    def test_invalid_configuration(self):
        for limits in (replace(Limits(), max_depth=257), replace(Limits(), max_records=0),
                       replace(Limits(), max_spool_bytes=10), replace(Limits(), max_features=True)):
            with self.assertRaises(ShapeWitnessError):
                run(b'null', limits=limits)
        for budget in (-1, True, 100001):
            with self.assertRaises(ShapeWitnessError):
                run(b'null', max_rows=budget)
        with self.assertRaises(ShapeWitnessError):
            select(io.StringIO('null'))

    def test_depth_brackets_inside_strings_are_ignored(self):
        run(b'{"x":"[[[[\\\""}\n', limits=replace(Limits(), max_depth=1))


class PropertyTests(unittest.TestCase):
    def test_seeded_generated_corpora(self):
        # Independent feature oracle, intentionally simple and recursive.
        rng = random.Random(7341)
        def generate(depth=0):
            choices = [None, True, False, rng.randrange(10), 'text']
            if depth < 3:
                choices += [[generate(depth + 1) for _ in range(rng.randrange(3))],
                            {k: generate(depth + 1) for k in ('a', 'b', '*') if rng.randrange(2)}]
            return rng.choice(choices)
        def walk(value, path=()):
            yield path, value
            if isinstance(value, dict):
                for k, v in value.items():
                    yield from walk(v, path + (k,))
            if isinstance(value, list):
                for v in value:
                    yield from walk(v, path + (None,))
        for _ in range(50):
            values = [generate() for _ in range(rng.randrange(1, 25))]
            lines = [json.dumps(v, separators=(',', ':')).encode() + b'\n' for v in values]
            vocabulary = {}
            for value in values:
                for path, node in walk(value):
                    if isinstance(node, dict):
                        vocabulary.setdefault(path, set()).update(node)
            all_features = []
            for value in values:
                fs = set()
                for path, node in walk(value):
                    kind = {type(None): 'null', bool: 'boolean', int: 'number', str: 'string', dict: 'object', list: 'array'}[type(node)]
                    fs.add((path, kind))
                    if isinstance(node, (dict, list)) and not node:
                        fs.add((path, 'empty-' + kind))
                    if isinstance(node, dict):
                        fs.update((path + (k,), 'missing') for k in vocabulary[path] - node.keys())
                all_features.append(fs)
            for budget in (0, 1, 4, len(values)):
                result = run(b''.join(lines), max_rows=budget)
                self.assertEqual(result, run(b''.join(lines), max_rows=budget))
                self.assertLessEqual(len(result.rows), budget)
                self.assertEqual(feature_set(result.report), set().union(*all_features))
                covered = set()
                for row in sorted(result.rows, key=lambda r: r.selection_rank):
                    gain = all_features[row.line - 1] - covered
                    self.assertTrue(gain)
                    self.assertEqual(row.raw, lines[row.line - 1])
                    best = max(range(len(values)), key=lambda i: (len(all_features[i] - covered), -i))
                    self.assertEqual(row.line, best + 1)
                    self.assertEqual(len(row.new_feature_ids), len(gain))
                    covered |= all_features[row.line - 1]
                self.assertEqual(result.report['coverage']['covered_features'], len(covered))
                if budget == len(values):
                    self.assertTrue(result.report['coverage']['complete'])


if __name__ == '__main__':
    unittest.main()
