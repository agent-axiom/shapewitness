"""Inventories compare semantic identities, not local IDs or selected witnesses."""
import copy
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shapewitness import ShapeWitnessError, compare_reports, read_report, select


def report(data=b'{}\n{"x":1}\n', **kwargs):
    return select(io.BytesIO(data), **kwargs).report


class ComparisonTests(unittest.TestCase):
    def test_reordered_rows_and_ids_do_not_change_inventory(self):
        before = report(b'{"x":1}\n{"y":null}\n')
        after = report(b'{"y":null}\n{"x":900}\n')
        self.assertNotEqual(before['features'], after['features'])
        result = compare_reports(before, after)
        self.assertFalse(result['changed'])
        self.assertEqual(result['added_features'], [])
        self.assertEqual(result['removed_features'], [])
        self.assertEqual(result['unchanged_features'], len(before['features']))
        self.assertNotEqual(result['baseline']['input_sha256'], result['current']['input_sha256'])

    def test_selection_budget_and_coverage_are_not_inventory(self):
        before = report(max_rows=0)
        after = report(max_rows=2)
        self.assertFalse(before['coverage']['complete'])
        self.assertTrue(after['coverage']['complete'])
        self.assertFalse(compare_reports(before, after)['changed'])

    def test_type_change_addition_removal_and_local_missing(self):
        before = report(b'{"x":1,"removed":null}\n{}\n')
        after = report(b'{"x":"1","added":true}\n{}\n')
        result = compare_reports(before, after)
        self.assertEqual(result['added_features'], [
            {'path': ['added'], 'kind': 'boolean'}, {'path': ['added'], 'kind': 'missing'},
            {'path': ['x'], 'kind': 'string'}])
        self.assertEqual(result['removed_features'], [
            {'path': ['removed'], 'kind': 'missing'}, {'path': ['removed'], 'kind': 'null'},
            {'path': ['x'], 'kind': 'number'}])
        self.assertTrue(result['changed'])
        self.assertEqual(result['unchanged_features'], 3)

    def test_paths_are_unambiguous_and_ordered(self):
        result = compare_reports(report(b''), report(b'{"*":null,"a.b":{},"a":{"b":[]},"":1,"x":[null]}\n'))
        actual = {(tuple(f['path']), f['kind']) for f in result['added_features']}
        for feature in ((('*',), 'null'), (('a.b',), 'object'), (('a', 'b'), 'array'),
                        (('',), 'number'), (('x', None), 'null')):
            self.assertIn(feature, actual)
        keys = [(json.dumps(f['path'], ensure_ascii=True, separators=(',', ':')), f['kind'])
                for f in result['added_features']]
        self.assertEqual(keys, sorted(keys))

    def test_missing_is_relative_to_each_input_vocabulary(self):
        result = compare_reports(report(b'{}\n'), report(b'{}\n{"new":1}\n'))
        self.assertEqual(result['added_features'], [
            {'path': ['new'], 'kind': 'missing'}, {'path': ['new'], 'kind': 'number'}])
        # This does not mean that old rows changed, or that a schema was violated.
        self.assertEqual(result['removed_features'], [])

    def test_empty_and_numeric_modes(self):
        self.assertFalse(compare_reports(report(b''), report(b''))['changed'])
        self.assertFalse(compare_reports(report(b'1\n'), report(b'1.5\n'))['changed'])
        result = compare_reports(report(b'1\n', number_mode='syntax'),
                                 report(b'1.0\n', number_mode='syntax'))
        self.assertEqual(result['added_features'], [{'path': [], 'kind': 'float'}])
        self.assertEqual(result['removed_features'], [{'path': [], 'kind': 'integer'}])
        for data in (b'', b'null\n', b'1\n'):
            with self.subTest(data=data), self.assertRaises(ShapeWitnessError) as raised:
                compare_reports(report(data), report(data, number_mode='syntax'))
            self.assertEqual(raised.exception.code, 'incompatible_report')

    def test_does_not_mutate_reports(self):
        before, after = report(), report(b'false\n')
        snapshots = copy.deepcopy((before, after))
        compare_reports(before, after)
        self.assertEqual((before, after), snapshots)

    def test_seeded_set_oracle_and_id_permutations(self):
        rng = random.Random(121)
        choices = [{}, {'a': None}, {'a': []}, {'a': [False, {}]}, {'b': 1}, {'b': 'x'}]
        for _ in range(50):
            values = [[rng.choice(choices) for _ in range(rng.randrange(8))] for _ in range(2)]
            reports = [report(b''.join(json.dumps(v).encode() + b'\n' for v in rows), max_rows=0)
                       for rows in values]
            sets = [{(tuple(f['path']), f['kind']) for f in r['features']} for r in reports]
            for r in reports:
                rng.shuffle(r['features'])
                for index, f in enumerate(r['features']):
                    f['id'] = 100 + index
            result = compare_reports(*reports)
            self.assertEqual({(tuple(f['path']), f['kind']) for f in result['added_features']}, sets[1] - sets[0])
            self.assertEqual({(tuple(f['path']), f['kind']) for f in result['removed_features']}, sets[0] - sets[1])
            self.assertEqual(result['changed'], sets[0] != sets[1])

    def test_invalid_and_incompatible_reports_fail_closed(self):
        source = report()
        bad = [None, [], {}, {**source, 'format_version': True},
               {**source, 'format_version': 999}, {**source, 'feature_model': 'unknown'},
               {**source, 'options': {'number_mode': 'syntax'}}, {**source, 'features': {}},
               {**source, 'coverage': {'observed_features': True}},
               {**source, 'coverage': {'observed_features': 999}},
               {**source, 'input': {'sha256': 'x'}},
               {**source, 'features': [*source['features'], source['features'][0]]}]
        mutations = [('id', True), ('id', -1), ('id', '1'), ('path', 'secret'),
                     ('path', [False]), ('path', [['secret']]), ('path', ['\ud800']),
                     ('kind', 'float'), ('kind', []), ('kind', 'secret')]
        for key, value in mutations:
            altered = copy.deepcopy(source)
            altered['features'][0][key] = value
            bad.append(altered)
        duplicate = copy.deepcopy(source)
        duplicate['features'][1] = {**duplicate['features'][0], 'id': 999}
        bad.append(duplicate)
        duplicate_id = copy.deepcopy(source)
        duplicate_id['features'][1]['id'] = duplicate_id['features'][0]['id']
        bad.append(duplicate_id)
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ShapeWitnessError) as raised:
                compare_reports(source, value)
            self.assertIn(raised.exception.code, ('invalid_report', 'incompatible_report'))
            self.assertNotIn('secret', str(raised.exception))
        syntax = report(number_mode='syntax')
        del syntax['feature_model']
        with self.assertRaises(ShapeWitnessError):
            compare_reports(syntax, syntax)

    def test_report_reader_handles_short_reads_and_trailing_data(self):
        class Chunked(io.BytesIO):
            def read(self, size=-1):
                return super().read(min(size, 17))
        raw = json.dumps(report()).encode()
        self.assertEqual(read_report(Chunked(raw)), report())
        with self.assertRaises(ShapeWitnessError) as raised:
            read_report(Chunked(raw + b' {}'))
        self.assertEqual(raised.exception.code, 'invalid_report')
        with self.assertRaises(ShapeWitnessError) as raised:
            read_report(Chunked(raw + b' ' * 100), max_bytes=len(raw) + 50)
        self.assertEqual(raised.exception.code, 'limit')

    def test_report_io_errors_do_not_echo_source_details(self):
        class Broken:
            def read(self, size):
                raise OSError('private marker')
        with self.assertRaises(ShapeWitnessError) as raised:
            read_report(Broken())
        self.assertEqual(raised.exception.code, 'io')
        self.assertNotIn('private marker', str(raised.exception))
        self.assertTrue(raised.exception.__suppress_context__)

    def test_bounded_strict_report_reader(self):
        encoded = json.dumps(report()).encode()
        self.assertEqual(read_report(io.BytesIO(encoded), max_bytes=len(encoded)), report())
        with self.assertRaises(ShapeWitnessError) as raised:
            read_report(io.BytesIO(encoded), max_bytes=len(encoded)-1)
        self.assertEqual(raised.exception.code, 'limit')
        for raw in (b'{', b'NaN', b'{"secret":1,"secret":2}', b'\xff', b'\xef\xbb\xbf{}',
                    b'[' * 2000 + b']' * 2000, b'1' * 10000):
            with self.subTest(raw=raw[:40]), self.assertRaises(ShapeWitnessError) as raised:
                read_report(io.BytesIO(raw))
            self.assertEqual(raised.exception.code, 'invalid_report')
            self.assertNotIn('secret', str(raised.exception))
        with self.assertRaises(ShapeWitnessError):
            read_report(io.StringIO('{}'))
        for value in (0, -1, True, '1', sys.maxsize, 10 ** 100):
            with self.assertRaises(ShapeWitnessError):
                read_report(io.BytesIO(encoded), max_bytes=value)


class ComparisonCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = self.root / 'baseline.json'
        self.baseline.write_text(json.dumps(report()), encoding='utf-8')

    def cli(self, *args, data=b'{}\n{"x":null}\n', **kwargs):
        return subprocess.run([sys.executable, '-m', 'shapewitness', '--baseline', str(self.baseline),
                               '--status', 'json', *args], input=data, capture_output=True, **kwargs)

    def test_gate_and_separate_report(self):
        comparison, inventory = self.root / 'delta.json', self.root / 'current.json'
        process = self.cli('--require-unchanged', '--comparison-report', str(comparison),
                           '--report', str(inventory), '-n', '0')
        self.assertEqual(process.returncode, 4, process.stderr)
        self.assertEqual(process.stdout, b'')
        delta = json.loads(comparison.read_text())
        self.assertTrue(delta['changed'])
        self.assertEqual(json.loads(process.stderr)['comparison'],
                         {'changed': True, 'added_features': 1, 'removed_features': 1})
        self.assertEqual(json.loads(inventory.read_text()), report(b'{}\n{"x":null}\n', max_rows=0))
        self.assertEqual(self.cli('--require-unchanged', data=b'{"x":4}\n{}\n').returncode, 0)
        self.assertEqual(self.cli().returncode, 0)
        # Existing selection gate has precedence when both gates fail.
        self.assertEqual(self.cli('--require-complete', '--require-unchanged', '-n', '0').returncode, 3)

    def test_failure_creates_no_outputs(self):
        output, inventory, delta = [self.root / name for name in ('out.jsonl', 'current.json', 'delta.json')]
        args = ('--output', str(output), '--report', str(inventory), '--comparison-report', str(delta))
        process = self.cli(*args, '--number-mode', 'syntax')
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stderr)['error']['code'], 'incompatible_report')
        self.assertEqual(process.stdout, b'')
        self.assertFalse(any(p.exists() for p in (output, inventory, delta)))
        self.baseline.write_bytes(b'{"private":')
        process = self.cli(*args)
        self.assertEqual(process.returncode, 2)
        self.assertNotIn(b'private', process.stderr)
        self.assertFalse(any(p.exists() for p in (output, inventory, delta)))

    def test_output_aliases_and_existing_paths(self):
        output = self.root / 'output'
        process = self.cli('--report', str(output), '--comparison-report', str(output))
        self.assertEqual(process.returncode, 2)
        self.assertFalse(output.exists())
        saved = self.baseline.read_bytes()
        process = self.cli('--comparison-report', str(self.baseline))
        self.assertEqual(process.returncode, 2)
        self.assertEqual(self.baseline.read_bytes(), saved)

    def test_flags_require_baseline(self):
        for flag in (['--require-unchanged'], ['--comparison-report', str(self.root / 'unused')]):
            process = subprocess.run([sys.executable, '-m', 'shapewitness', '--status', 'json', *flag],
                                     input=b'{}\n', capture_output=True)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(json.loads(process.stderr)['error']['code'], 'configuration')
        self.assertFalse((self.root / 'unused').exists())

    def test_hash_seed_independence(self):
        outputs = []
        for index, seed in enumerate(('1', '999', 'random')):
            path = self.root / f'delta-{index}.json'
            process = self.cli('--comparison-report', str(path),
                               data=b'{"z":true,"a":{},"b":[{"x":null},{}]}\n',
                               env={**os.environ, 'PYTHONHASHSEED': seed})
            self.assertEqual(process.returncode, 0, process.stderr)
            outputs.append((process.stdout, process.stderr, path.read_bytes()))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])


if __name__ == '__main__':
    unittest.main()
