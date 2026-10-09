"""Exact source-row pins, deterministic completion, and fail-before-output guards."""
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

from shapewitness import Limits, Pin, ShapeWitnessError, compare_reports, read_report, select


def pin(line, raw):
    return Pin(line, hashlib.sha256(raw).hexdigest())


def run(data, **kwargs):
    return select(io.BytesIO(data), **kwargs)


class PinTests(unittest.TestCase):
    def test_retain_same_shaped_problem_row(self):
        rows = [b'{"qty":1}\n', b'{"qty":0}\n']
        self.assertEqual([r.line for r in run(b''.join(rows)).rows], [1])
        result = run(b''.join(rows), pins=[pin(2, rows[1])])
        self.assertEqual([r.line for r in result.rows], [2])
        self.assertEqual(result.rows[0].raw, rows[1])
        self.assertEqual(result.rows[0].selection_reason, 'pinned')
        self.assertTrue(result.report['coverage']['complete'])
        self.assertEqual(result.report['rows'][0]['selection_reason'], 'pinned')

    def test_multiple_pins_zero_gain_and_source_order(self):
        rows = [b'{"x":1}\n', b'{"x":2}\n', b'{"y":true}\n', b'null\n']
        data = b''.join(rows)
        result = run(data, pins=[pin(2, rows[1]), pin(1, rows[0])], max_rows=4)
        reordered = run(data, pins=[pin(1, rows[0]), pin(2, rows[1])], max_rows=4)
        self.assertEqual(result, reordered)
        self.assertEqual([r.line for r in result.rows], [1, 2, 3, 4])
        self.assertEqual([r.selection_rank for r in result.rows], [1, 2, 3, 4])
        self.assertEqual(result.rows[1].new_feature_ids, ())
        self.assertEqual([r.selection_reason for r in result.rows], ['pinned', 'pinned', 'greedy', 'greedy'])
        all_new = [fid for r in result.rows for fid in r.new_feature_ids]
        self.assertEqual(len(all_new), len(set(all_new)))
        self.assertEqual(set(all_new), {f['id'] for f in result.report['features'] if f['covered']})
        self.assertEqual(result.report['options']['pins'], [
            {'line': 1, 'sha256': pin(1, rows[0]).sha256}, {'line': 2, 'sha256': pin(2, rows[1]).sha256}])

    def test_pins_first_but_output_original_order(self):
        rows = [b'{"x":null}\n', b' \t{"x":1.0}\r\n', b'false']
        result = run(b''.join(rows), pins=[pin(3, rows[2])])
        self.assertEqual([r.line for r in result.rows], [1, 2, 3])
        self.assertEqual([r.selection_rank for r in result.rows], [2, 3, 1])
        stream = io.BytesIO(); result.write_jsonl(stream)
        self.assertEqual(stream.getvalue(), b''.join(rows))
        for row, entry in zip(result.rows, result.report['rows']):
            self.assertEqual(row.offset, sum(map(len, rows[:row.line - 1])))
            self.assertEqual(row.sha256, hashlib.sha256(rows[row.line - 1]).hexdigest())
            self.assertEqual(entry['byte_length'], len(row.raw))
        self.assertEqual(result.report['input']['sha256'], hashlib.sha256(b''.join(rows)).hexdigest())

    def test_pin_budget_is_hard_and_greedy_remaining_is_partial(self):
        rows = [b'{"x":1}\n', b'false\n', b'null\n']
        data = b''.join(rows)
        required = [pin(1, rows[0]), pin(2, rows[1])]
        for options in ({'max_rows': 1}, {'limits': replace(Limits(), max_output_bytes=sum(map(len, rows[:2])) - 1)}):
            with self.subTest(options=options), self.assertRaises(ShapeWitnessError) as raised:
                run(data, pins=required, **options)
            self.assertEqual(raised.exception.code, 'pin_budget')
        row_limited = run(data, pins=required, max_rows=2)
        self.assertEqual(row_limited.report['selection']['stop_reason'], 'row_budget')
        self.assertEqual([r.line for r in row_limited.rows], [1, 2])
        byte_limited = run(data, pins=required, limits=replace(Limits(), max_output_bytes=sum(map(len, rows[:2]))))
        self.assertEqual(byte_limited.report['selection']['stop_reason'], 'output_byte_budget')
        self.assertEqual([r.line for r in byte_limited.rows], [1, 2])
        self.assertFalse(byte_limited.report['coverage']['complete'])
        with self.assertRaises(ShapeWitnessError):
            run(data, pins=required, max_rows=0)

    def test_skip_greedy_row_that_cannot_fit_after_pins(self):
        rows = [b'{"long":{"a":1,"b":2,"c":3,"d":4}}\n', b'null\n', b'false\n']
        result = run(b''.join(rows), pins=[pin(3, rows[2])],
                     limits=replace(Limits(), max_output_bytes=len(rows[1]) + len(rows[2])))
        self.assertEqual([r.line for r in result.rows], [2, 3])
        self.assertEqual(result.report['selection']['stop_reason'], 'output_byte_budget')

    def test_missing_skipped_and_changed_pins(self):
        data = b'{}\n \r\nnull\n'
        cases = [(Pin(99, '0' * 64), 'pin_not_found', 99),
                 (pin(2, b' \r\n'), 'pin_not_found', 2),
                 (pin(1, b'{}\r\n'), 'pin_mismatch', 1),
                 (pin(3, b'false\n'), 'pin_mismatch', 3)]
        for required, code, line in cases:
            with self.subTest(required=required), self.assertRaises(ShapeWitnessError) as raised:
                run(data, pins=[required], skip_blank_lines=True)
            self.assertEqual((raised.exception.code, raised.exception.line), (code, line))
        result = run(data, pins=[pin(3, b'null\n')], skip_blank_lines=True)
        self.assertEqual([r.line for r in result.rows], [1, 3])
        self.assertEqual(result.rows[1].offset, len(b'{}\n \r\n'))

    def test_full_input_and_limits_validated_even_with_complete_pins(self):
        for data, options, code in [(b'{}\nprivate-invalid\n', {}, 'invalid_json'),
                                    (b'{}\n{}\n', {'max_rows': 1, 'limits': replace(Limits(), max_records=1)}, 'limit')]:
            with self.subTest(data=data), self.assertRaises(ShapeWitnessError) as raised:
                run(data, pins=[pin(1, b'{}\n')], **options)
            self.assertEqual(raised.exception.code, code)
            self.assertNotIn('private-invalid', str(raised.exception))

    def test_bad_pin_configuration_never_reads_source(self):
        class Unreadable:
            def readline(self, size):
                self.fail_if_called = True
                raise AssertionError('should not consume input')
        invalid = [None, {}, '', b'', (p for p in []), [None], [1],
                   [Pin(True, 'a' * 64)], [Pin(0, 'a' * 64)], [Pin(sys.maxsize, 'a' * 64)],
                   [Pin(1, None)], [Pin(1, 'A' * 64)], [Pin(1, 'a' * 63)],
                   [Pin(1, 'a' * 64), Pin(1, 'b' * 64)]]
        for required in invalid:
            with self.subTest(pins=required), self.assertRaises(ShapeWitnessError) as raised:
                select(Unreadable(), pins=required)
            self.assertEqual(raised.exception.code, 'configuration')

    def test_empty_pins_preserve_default_reports(self):
        for mode in ('json', 'syntax'):
            data = b'{"n":1}\n{"n":1.0}\n'
            self.assertEqual(run(data, number_mode=mode), run(data, number_mode=mode, pins=[]))
            self.assertEqual(run(data, number_mode=mode).report['format_version'], 1 if mode == 'json' else 2)
            self.assertNotIn('selection_reason', run(data, number_mode=mode).report['rows'][0])

    def test_format_three_preserves_both_feature_models(self):
        rows = [b'1\n', b'1.0\n']
        for mode, model in [('json', 'json-structure-v1'), ('syntax', 'json-structure-number-syntax-v1')]:
            old = run(b''.join(rows), number_mode=mode)
            pinned = run(b''.join(rows), number_mode=mode, pins=[pin(2, rows[1])])
            self.assertEqual(pinned.report['format_version'], 3)
            self.assertEqual(pinned.report['feature_model'], model)
            self.assertEqual(pinned.report['options']['number_mode'], mode)
            self.assertEqual(pinned.report['algorithm'], 'pinned-first-greedy-new-features-first-line-tiebreak-v1')
            self.assertFalse(compare_reports(old.report, pinned.report)['changed'])
            self.assertFalse(compare_reports(pinned.report, old.report)['changed'])
            self.assertEqual(read_report(io.BytesIO(json.dumps(pinned.report).encode())), pinned.report)
        with self.assertRaises(ShapeWitnessError):
            compare_reports(run(b''.join(rows)).report,
                            run(b''.join(rows), number_mode='syntax', pins=[pin(2, rows[1])]).report)
        for model, mode in [('unknown', 'json'), ('json-structure-v1', 'syntax'),
                            ('json-structure-number-syntax-v1', 'json')]:
            altered = run(b''.join(rows), pins=[pin(2, rows[1])]).report
            altered['feature_model'], altered['options']['number_mode'] = model, mode
            with self.assertRaises(ShapeWitnessError):
                compare_reports(altered, altered)

    def test_seeded_pinned_greedy_selection_oracle(self):
        rng = random.Random(133)
        values = [{}, {'x': None}, {'x': 1}, {'x': 1.0}, {'y': []}, {'y': [True, {}]}, False]
        for mode in ('json', 'syntax'):
            for _ in range(40):
                raws = [(json.dumps(rng.choice(values)) + '\n').encode() for _ in range(rng.randrange(1, 9))]
                data = b''.join(raws)
                chosen = sorted(rng.sample(range(1, len(raws) + 1), rng.randrange(1, len(raws) + 1)))
                # Force every row once to obtain the reported incidence matrix;
                # compare its semantic identities with independent feature oracle tests.
                full = run(data, pins=[pin(i + 1, raw) for i, raw in enumerate(raws)], number_mode=mode)
                incidence = {r.line: set(r.feature_ids) for r in full.rows}
                budget = rng.randrange(len(chosen), len(raws) + 1)
                byte_budget = sum(len(raws[line - 1]) for line in chosen) + rng.randrange(1, 60)
                covered, expected = set(), list(chosen)
                size = sum(len(raws[line - 1]) for line in chosen)
                for line in chosen:
                    covered.update(incidence[line])
                while len(expected) < budget:
                    candidates = [(len(features - covered), -line, line)
                                  for line, features in incidence.items()
                                  if line not in expected and size + len(raws[line - 1]) <= byte_budget]
                    if not candidates or max(candidates)[0] == 0:
                        break
                    line = max(candidates)[2]
                    expected.append(line); covered.update(incidence[line]); size += len(raws[line - 1])
                result = run(data, pins=[pin(line, raws[line - 1]) for line in reversed(chosen)],
                             max_rows=budget, limits=replace(Limits(), max_output_bytes=byte_budget), number_mode=mode)
                self.assertEqual([r.line for r in sorted(result.rows, key=lambda row: row.selection_rank)], expected)
                self.assertEqual(result.report['selection']['bytes'], size)
                self.assertEqual({f['id'] for f in result.report['features'] if f['covered']}, covered)


class PinCliTests(unittest.TestCase):
    def cli(self, *args, data=b'{"n":1}\n{"n":0}\n', **kwargs):
        return subprocess.run([sys.executable, '-m', 'shapewitness', '--status', 'json', *args],
                              input=data, capture_output=True, **kwargs)

    def test_pin_output_and_report(self):
        digest = pin(2, b'{"n":0}\n').sha256
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            process = self.cli('--pin-row', '2:' + digest, '--report', str(path), '-n', '1', '--require-complete')
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout, b'{"n":0}\n')
            report = json.loads(path.read_text())
            self.assertEqual(report['format_version'], 3)
            self.assertEqual(report['rows'][0]['selection_reason'], 'pinned')

    def test_failures_create_no_outputs(self):
        for flags, code in [(['--pin-row', '2:' + '0' * 64], 'pin_mismatch'),
                            (['--pin-row', '99:' + '0' * 64], 'pin_not_found'),
                            (['--pin-row', '2:' + pin(2, b'{"n":0}\n').sha256, '-n', '0'], 'pin_budget'),
                            (['--pin-row', 'private-invalid'], 'configuration')]:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as directory:
                output, report = Path(directory) / 'data.jsonl', Path(directory) / 'report.json'
                process = self.cli(*flags, '--output', str(output), '--report', str(report))
                self.assertEqual(process.returncode, 2)
                self.assertEqual(json.loads(process.stderr)['error']['code'], code)
                self.assertNotIn(b'private-invalid', process.stderr)
                self.assertEqual(process.stdout, b'')
                self.assertFalse(output.exists()); self.assertFalse(report.exists())

    def test_repeat_pin_and_hash_seed_determinism(self):
        data = b'{"n":1}\n{"n":0}\nnull\n'
        arguments = ['--pin-row', '2:' + pin(2, b'{"n":0}\n').sha256,
                     '--pin-row', '1:' + pin(1, b'{"n":1}\n').sha256]
        outputs = []
        for seed in ('1', '222', 'random'):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'report.json'
                process = self.cli(*arguments, '--report', str(path), data=data,
                                   env={**os.environ, 'PYTHONHASHSEED': seed})
                self.assertEqual(process.returncode, 0, process.stderr)
                outputs.append((process.stdout, process.stderr, path.read_bytes()))
        self.assertEqual(outputs[0], outputs[1]); self.assertEqual(outputs[1], outputs[2])


if __name__ == '__main__':
    unittest.main()
