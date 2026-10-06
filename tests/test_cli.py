import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def cli(self, *args, data=b'{}\n{"x":null}\n', **kw):
        return subprocess.run([sys.executable, '-m', 'shapewitness', *args], input=data,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)

    def test_streams_and_report(self):
        with tempfile.TemporaryDirectory() as work:
            report = str(Path(work) / 'coverage.json')
            proc = self.cli('--report', report, '--status', 'json')
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(proc.stdout, b'{}\n{"x":null}\n')
            self.assertTrue(json.loads(proc.stderr)['complete'])
            self.assertTrue(json.loads(Path(report).read_text())['coverage']['complete'])

    def test_require_complete(self):
        proc = self.cli('-n', '1', '--require-complete', '--status', 'json')
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(json.loads(proc.stderr)['complete'])
        self.assertNotEqual(proc.stdout, b'')

    def test_invalid_late_row_writes_nothing(self):
        with tempfile.TemporaryDirectory() as work:
            output = str(Path(work) / 'out.jsonl')
            report = str(Path(work) / 'report.json')
            proc = self.cli('--output', output, '--report', report, '--status', 'json', data=b'{}\ninvalid\n')
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stdout, b'')
            self.assertFalse(Path(output).exists())
            self.assertFalse(Path(report).exists())
            self.assertEqual(json.loads(proc.stderr)['error']['line'], 2)

    def test_refuses_existing_output_and_aliases(self):
        with tempfile.TemporaryDirectory() as work:
            output = Path(work) / 'out.jsonl'
            output.write_text('keep me')
            proc = self.cli('--output', str(output))
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(output.read_text(), 'keep me')
            proc = self.cli('--output', str(Path(work) / 'new'), '--report', str(Path(work) / './new'))
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stdout, b'')

    def test_broken_output_parent(self):
        with tempfile.TemporaryDirectory() as work:
            proc = self.cli('--output', str(Path(work) / 'absent' / 'out'), '--status', 'json')
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stderr)['error']['code'], 'io')

    def test_hash_seed_independence(self):
        data = b'{"b":[{"x":1},{}],"a":2}\n{"a":null}\n{"c":true}\n'
        outputs = []
        for seed in ('1', '101', 'random'):
            with tempfile.TemporaryDirectory() as work:
                path = Path(work) / 'report.json'
                proc = self.cli('--report', str(path), '--status', 'json', data=data,
                                env={**os.environ, 'PYTHONHASHSEED': seed})
                self.assertEqual(proc.returncode, 0, proc.stderr)
                outputs.append((proc.stdout, path.read_bytes()))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])

    def test_quiet_and_version(self):
        proc = self.cli('--status', 'quiet')
        self.assertEqual(proc.stderr, b'')
        self.assertEqual(self.cli('--version').stdout.strip(), b'shapewitness 0.1.0')
        self.assertIn(b'--max-associations', self.cli('--help').stdout)

    def test_limits_and_empty(self):
        proc = self.cli('--max-records', '1', '-n', '1')
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(proc.stdout, b'')
        proc = self.cli('--require-complete', data=b'')
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b'')


if __name__ == '__main__':
    unittest.main()
