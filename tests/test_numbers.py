"""Opt-in number syntax coverage without numeric conversion or new dependencies."""
from __future__ import annotations

import hashlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from shapewitness import Limits, ShapeWitnessError, select


def run(data: bytes, **kwargs):
    return select(io.BytesIO(data), **kwargs)


def feature_set(report):
    return {(tuple(feature['path']), feature['kind']) for feature in report['features']}


def row_features(result, row):
    features = {feature['id']: (tuple(feature['path']), feature['kind'])
                for feature in result.report['features']}
    return {features[fid] for fid in row.feature_ids}


class NumberSyntaxTests(unittest.TestCase):
    def test_lexeme_boundaries(self):
        cases = {
            'integer': (b'0', b'-0', b'1', b'-1', b'100000000000000000000000000001'),
            'float': (b'0.0', b'-0.0', b'1.0', b'1.25', b'-1.25', b'1e0', b'1E0',
                      b'1e+0', b'1e-0', b'-0E+0', b'1.0e0', b'1e9999999', b'1e-9999999'),
            'boolean': (b'true', b'false'),
            'string': (b'"1"', b'"1.0"', b'"1e0"'),
            'null': (b'null',),
        }
        for kind, tokens in cases.items():
            for token in tokens:
                with self.subTest(token=token):
                    result = run(token + b'\n', number_mode='syntax')
                    self.assertEqual(feature_set(result.report), {((), kind)})
                    self.assertEqual(result.rows[0].raw, token + b'\n')
                    self.assertTrue(result.report['coverage']['complete'])

    def test_same_mathematical_value_has_two_syntax_features(self):
        data = b'1\n1.0\n1e0\n-0\n-0.0\n'
        syntax = run(data, number_mode='syntax')
        self.assertEqual(feature_set(syntax.report), {((), 'integer'), ((), 'float')})
        self.assertEqual([row.line for row in syntax.rows], [1, 2])
        self.assertEqual([row.line for row in run(data).rows], [1])

    def test_versioned_report_only_for_opt_in(self):
        for data in (b'', b'null\n', b'{"n":1}\n{"n":1.0}\n'):
            with self.subTest(data=data):
                default = run(data)
                explicit = run(data, number_mode='json')
                self.assertEqual(default, explicit)
                self.assertEqual(json.dumps(default.report, sort_keys=True),
                                 json.dumps(explicit.report, sort_keys=True))
                self.assertEqual(default.report['format_version'], 1)
                self.assertNotIn('feature_model', default.report)
                self.assertNotIn('number_mode', default.report['options'])
                syntax = run(data, number_mode='syntax')
                self.assertEqual(syntax.report['format_version'], 2)
                self.assertEqual(syntax.report['feature_model'], 'json-structure-number-syntax-v1')
                self.assertEqual(syntax.report['options']['number_mode'], 'syntax')
                self.assertEqual(syntax.report['algorithm'], default.report['algorithm'])

    def test_extreme_numbers_preserve_bytes_and_provenance(self):
        # Exceeds the usual integer-conversion digit cap and float precision/range.
        numeric = (b' \t{"big":' + b'9' * 10000 + b', "precise":0.' + b'1234567890' * 1000
                   + b',"huge":1e' + b'9' * 10000 + b',"tiny":-1e-' + b'9' * 10000 + b'} \r\n')
        lines = [b' \r\n', numeric, b'\n', b'false']
        data = b''.join(lines)
        result = run(data, number_mode='syntax', skip_blank_lines=True)
        self.assertEqual([row.line for row in result.rows], [2, 4])
        self.assertEqual([row.offset for row in result.rows], [len(lines[0]), sum(map(len, lines[:3]))])
        self.assertEqual([row.raw for row in result.rows], [numeric, b'false'])
        output = io.BytesIO()
        result.write_jsonl(output)
        self.assertEqual(output.getvalue(), numeric + b'false')
        self.assertEqual(result.report['input']['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(result.report['input']['bytes'], len(data))
        self.assertEqual(result.report['input']['physical_lines'], 4)
        self.assertEqual(result.report['input']['skipped_blank_lines'], 2)
        self.assertIn((('big',), 'integer'), feature_set(result.report))
        for key in ('precise', 'huge', 'tiny'):
            self.assertIn(((key,), 'float'), feature_set(result.report))
        for row, entry in zip(result.rows, result.report['rows']):
            self.assertEqual(row.sha256, hashlib.sha256(row.raw).hexdigest())
            self.assertEqual(entry['sha256'], row.sha256)
            self.assertEqual(entry['byte_offset'], row.offset)
            self.assertEqual(entry['byte_length'], len(row.raw))

    def test_nested_arrays_and_local_missing_members(self):
        data = b'{"a":[{"n":1},{},{"n":1.0},false]}\n{"a":null}\n{}\n'
        result = run(data, number_mode='syntax')
        by_line = {row.line: row_features(result, row) for row in result.rows}
        for kind in ('integer', 'float', 'missing'):
            self.assertIn((('a', None, 'n'), kind), by_line[1])
        self.assertIn((('a', None), 'boolean'), by_line[1])
        self.assertIn((('a',), 'null'), by_line[2])
        self.assertIn((('a',), 'missing'), by_line[3])
        self.assertNotIn((('a', None, 'n'), 'missing'), by_line[2])
        self.assertNotIn((('a', None, 'n'), 'missing'), by_line[3])
        self.assertNotIn('number', {kind for _, kind in feature_set(result.report)})

    def test_invalid_mode_is_rejected_before_reading_input(self):
        class Unreadable:
            def readline(self, size):
                raise AssertionError('invalid configuration must not read input')

        for mode in ('', 'JSON', 'number', 'TOP_SECRET', None, True, False, 1, [], {}):
            with self.subTest(mode=mode):
                with self.assertRaises(ShapeWitnessError) as error:
                    select(Unreadable(), number_mode=mode)
                self.assertEqual(error.exception.code, 'configuration')
                self.assertIsNone(error.exception.line)
                self.assertNotIn('TOP_SECRET', str(error.exception))

    def test_invalid_json_remains_strict_and_private(self):
        cases = [(b'01', 'invalid_json'), (b'-01', 'invalid_json'),
                 (b'+1', 'invalid_json'), (b'.1', 'invalid_json'),
                 (b'1.', 'invalid_json'), (b'1e', 'invalid_json'),
                 (b'1e+', 'invalid_json'), (b'--1', 'invalid_json'),
                 (b'NaN', 'invalid_json'), (b'Infinity', 'invalid_json'),
                 (b'-Infinity', 'invalid_json'),
                 (b'{"TOP_SECRET":1,"TOP_SECRET":1.0}', 'duplicate_key'),
                 (b'{"TOP_SECRET":1e+}', 'invalid_json'),
                 (b'{"TOP_SECRET":"\\ud800"}', 'invalid_unicode'),
                 (b'{"TOP_SECRET":"\xff"}', 'invalid_utf8')]
        for bad, code in cases:
            with self.subTest(bad=bad):
                with self.assertRaises(ShapeWitnessError) as error:
                    run(b'1\n' + bad + b'\n', number_mode='syntax')
                self.assertEqual(error.exception.code, code)
                self.assertEqual(error.exception.line, 2)
                self.assertNotIn('TOP_SECRET', json.dumps(error.exception.as_dict()))

    def test_discovery_pass_counts_syntax_before_later_invalid_input(self):
        # With the default marker both valid rows have the same discovery feature.
        # The syntax discovery pass must instead reach the cap on physical line 2.
        with self.assertRaises(ShapeWitnessError) as error:
            run(b'1\n1.0\nTOP_SECRET\n', number_mode='syntax', max_rows=1,
                limits=replace(Limits(), max_features=1))
        self.assertEqual(error.exception.code, 'limit')
        self.assertEqual(error.exception.line, 2)
        self.assertIn('max_features', str(error.exception))
        self.assertNotIn('TOP_SECRET', str(error.exception))

    def test_syntax_feature_and_association_limits(self):
        data = b'[1,1.0,1e0,2]\n'
        for name in ('max_features', 'max_associations'):
            with self.subTest(name=name):
                limits = replace(Limits(), **{name: 2})
                self.assertTrue(run(data, limits=limits).report['coverage']['complete'])
                with self.assertRaises(ShapeWitnessError) as error:
                    run(data, number_mode='syntax', limits=limits)
                self.assertEqual(error.exception.code, 'limit')
                self.assertIn(name, str(error.exception))
                self.assertEqual(error.exception.line, 1)
                complete = run(data, number_mode='syntax', limits=replace(Limits(), **{name: 3}))
                self.assertEqual(complete.report['coverage']['observed_features'], 3)
                self.assertTrue(complete.report['coverage']['complete'])

    def test_partial_budgets_expose_uncovered_syntax(self):
        cases = [(dict(max_rows=0), 'row_budget', []),
                 (dict(max_rows=1), 'row_budget', [1]),
                 (dict(limits=replace(Limits(), max_output_bytes=2)), 'output_byte_budget', [1])]
        for options, stop_reason, lines in cases:
            with self.subTest(options=options):
                result = run(b'1\n1.0\n', number_mode='syntax', **options)
                self.assertEqual([row.line for row in result.rows], lines)
                self.assertFalse(result.report['coverage']['complete'])
                self.assertEqual(result.report['selection']['stop_reason'], stop_reason)
                uncovered = {feature['id'] for feature in result.report['features'] if not feature['covered']}
                self.assertEqual(uncovered, set(result.report['coverage']['uncovered_feature_ids']))
                self.assertEqual(len(uncovered), 2 - len(lines))
                self.assertIn(((), 'float'), {(tuple(f['path']), f['kind'])
                                             for f in result.report['features'] if f['id'] in uncovered})

    def test_nonseekable_stream(self):
        class Pipe:
            def __init__(self):
                self.stream = io.BytesIO(b'1\n1.0\n')

            def readline(self, size):
                return self.stream.readline(size)

        result = select(Pipe(), number_mode='syntax')
        self.assertEqual([row.line for row in result.rows], [1, 2])
        self.assertTrue(result.report['coverage']['complete'])


class NumberSyntaxOracleTests(unittest.TestCase):
    def test_seeded_independent_feature_and_selection_oracle(self):
        rng = random.Random(38591)

        def generate(depth=0):
            if depth < 3:
                category = rng.randrange(8)
                if category == 0:
                    return [generate(depth + 1) for _ in range(rng.randrange(4))]
                if category == 1:
                    return {key: generate(depth + 1) for key in ('a', 'b', '*', '', 'a.b')
                            if rng.randrange(2)}
            return rng.choice([None, True, False, rng.randrange(-9, 10),
                               0.0, -0.0, 1.25, 1e200, -2e-100, 'text'])

        def walk(node, path=()):
            yield path, node
            if type(node) is dict:
                for key, child in node.items():
                    yield from walk(child, path + (key,))
            elif type(node) is list:
                for child in node:
                    yield from walk(child, path + (None,))

        for case in range(30):
            # Force all three Python numeric/bool categories into every corpus.
            values = [False, 1, 1.0, {'items': [{'n': 1}, {}, {'n': 1.0}]}]
            values += [generate() for _ in range(rng.randrange(4, 16))]
            lines = [json.dumps(value, separators=(',', ':'), allow_nan=False).encode() + b'\n'
                     for value in values]
            vocabulary = {}
            for value in values:
                for path, node in walk(value):
                    if type(node) is dict:
                        vocabulary.setdefault(path, set()).update(node)
            all_features = []
            kinds = {type(None): 'null', bool: 'boolean', int: 'integer', float: 'float',
                     str: 'string', list: 'array', dict: 'object'}
            for value in values:
                features = set()
                for path, node in walk(value):
                    kind = kinds[type(node)]
                    features.add((path, kind))
                    if type(node) in (dict, list) and not node:
                        features.add((path, 'empty-' + kind))
                    if type(node) is dict:
                        features.update((path + (key,), 'missing') for key in vocabulary[path] - node.keys())
                all_features.append(features)
            observed = set().union(*all_features)
            for budget in (0, 1, 4, len(values)):
                with self.subTest(case=case, budget=budget):
                    result = run(b''.join(lines), max_rows=budget, number_mode='syntax')
                    self.assertEqual(result, run(b''.join(lines), max_rows=budget, number_mode='syntax'))
                    self.assertEqual(feature_set(result.report), observed)
                    self.assertLessEqual(len(result.rows), budget)
                    self.assertEqual([row.line for row in result.rows], sorted(row.line for row in result.rows))
                    by_id = {f['id']: (tuple(f['path']), f['kind']) for f in result.report['features']}
                    covered = set()
                    for row in sorted(result.rows, key=lambda r: r.selection_rank):
                        best = max(range(len(values)), key=lambda i: (len(all_features[i] - covered), -i))
                        self.assertEqual(row.line, best + 1)
                        gain = all_features[best] - covered
                        self.assertTrue(gain)
                        self.assertEqual({by_id[fid] for fid in row.feature_ids}, all_features[best])
                        self.assertEqual({by_id[fid] for fid in row.new_feature_ids}, gain)
                        self.assertEqual(row.raw, lines[best])
                        covered |= all_features[best]
                    self.assertEqual(result.report['coverage']['covered_features'], len(covered))
                    self.assertEqual({by_id[fid] for fid in result.report['coverage']['uncovered_feature_ids']},
                                     observed - covered)
                    self.assertEqual(result.report['coverage']['complete'], covered == observed)
                    if budget == len(values):
                        self.assertTrue(result.report['coverage']['complete'])


class NumberSyntaxCliTests(unittest.TestCase):
    def cli(self, *args, data=b'1\n1.0\n', **kwargs):
        return subprocess.run([sys.executable, '-m', 'shapewitness', *args], input=data,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)

    def test_require_complete_and_versioned_report(self):
        with tempfile.TemporaryDirectory() as work:
            report = Path(work) / 'report.json'
            proc = self.cli('--number-mode', 'syntax', '-n', '1', '--require-complete',
                            '--report', str(report), '--status', 'json')
            self.assertEqual(proc.returncode, 3, proc.stderr)
            self.assertEqual(proc.stdout, b'1\n')
            self.assertFalse(json.loads(proc.stderr)['complete'])
            document = json.loads(report.read_bytes())
            self.assertEqual(document['format_version'], 2)
            self.assertEqual(document['feature_model'], 'json-structure-number-syntax-v1')
            self.assertEqual(document['options']['number_mode'], 'syntax')
            self.assertEqual(document['coverage']['observed_features'], 2)
            self.assertEqual(document['coverage']['covered_features'], 1)
            self.assertEqual(len(document['coverage']['uncovered_feature_ids']), 1)
        complete = self.cli('--number-mode', 'syntax', '-n', '2', '--require-complete', '--status', 'json')
        self.assertEqual(complete.returncode, 0, complete.stderr)
        self.assertEqual(complete.stdout, b'1\n1.0\n')
        self.assertTrue(json.loads(complete.stderr)['complete'])

    def test_default_and_explicit_json_are_byte_identical(self):
        data = b'{"n":1}\r\n{"n":1.0}\n{"n":1e0}\n{"n":false}\n{}'
        results = []
        for arguments in ((), ('--number-mode', 'json')):
            with tempfile.TemporaryDirectory() as work:
                report = Path(work) / 'report.json'
                proc = self.cli(*arguments, '--report', str(report), '--status', 'json', data=data)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                results.append((proc.stdout, proc.stderr, report.read_bytes()))
        self.assertEqual(results[0], results[1])
        document = json.loads(results[0][2])
        self.assertEqual(document['format_version'], 1)
        self.assertNotIn('feature_model', document)
        self.assertNotIn('number_mode', document['options'])

    def test_invalid_syntax_input_and_limits_create_no_outputs(self):
        cases = [(b'1\n{"TOP_SECRET":1e+}\n', (), 'invalid_json'),
                 (b'[1,1.0]\n', ('--max-features', '2'), 'limit'),
                 (b'[1,1.0]\n', ('--max-associations', '2'), 'limit')]
        for data, arguments, code in cases:
            with self.subTest(code=code, arguments=arguments), tempfile.TemporaryDirectory() as work:
                output = Path(work) / 'output.jsonl'
                report = Path(work) / 'report.json'
                proc = self.cli('--number-mode', 'syntax', *arguments, '--output', str(output),
                                '--report', str(report), '--status', 'json', data=data)
                self.assertEqual(proc.returncode, 2, proc.stderr)
                self.assertEqual(proc.stdout, b'')
                self.assertFalse(output.exists())
                self.assertFalse(report.exists())
                self.assertEqual(json.loads(proc.stderr)['error']['code'], code)
                self.assertNotIn(b'TOP_SECRET', proc.stderr)

    def test_invalid_mode_and_help(self):
        proc = self.cli('--number-mode', 'invalid')
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b'')
        self.assertIn(b'--number-mode', proc.stderr)
        self.assertIn(b'--number-mode', self.cli('--help').stdout)

    def test_syntax_hash_seed_independence(self):
        data = b'{"b":[{"x":1},{"x":1e0},{}],"a":2}\n{"a":null}\n{"c":true}\n{"b":[1.0,1]}\n'
        outputs = []
        for seed in ('1', '101', 'random'):
            with tempfile.TemporaryDirectory() as work:
                report = Path(work) / 'report.json'
                proc = self.cli('--number-mode', 'syntax', '--report', str(report), '--status', 'json',
                                data=data, env={**os.environ, 'PYTHONHASHSEED': seed})
                self.assertEqual(proc.returncode, 0, proc.stderr)
                outputs.append((proc.stdout, proc.stderr, report.read_bytes()))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])


if __name__ == '__main__':
    unittest.main()
