import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecipeTests(unittest.TestCase):
    def test_etl_recipe(self):
        proc = subprocess.run([sys.executable, str(ROOT / 'examples/recipes/etl_regression.py')],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('4 reviewed outputs match', proc.stdout)

    def test_repro_is_original_failing_row(self):
        proc = subprocess.run([sys.executable, str(ROOT / 'examples/recipes/importer_bug_repro.py')],
                              capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        original = (ROOT / 'examples/events.jsonl').read_bytes().splitlines(keepends=True)[2]
        self.assertEqual(proc.stdout, original)
        self.assertIn(b'original line 3', proc.stderr)
        self.assertIn(hashlib.sha256(original).hexdigest().encode(), proc.stderr)
        with self.assertRaises(KeyError):
            json.loads(proc.stdout)['user']['email']


class ComparisonTests(unittest.TestCase):
    def test_committed_corpus_is_generated_exactly(self):
        runner = load_script('compare_sampling')
        data = runner.corpus()
        self.assertEqual(data, (ROOT / 'benchmarks/synthetic.jsonl').read_bytes())
        saved = json.loads((ROOT / 'benchmarks/synthetic.json').read_text())
        self.assertEqual(saved['dataset']['sha256'], hashlib.sha256(data).hexdigest())
        result = runner.compare(data, seeds=3, repeats=1)
        self.assertEqual(result['observed_features'], 47)
        self.assertEqual(result['head']['covered_features'], 8)
        self.assertEqual(result['shapewitness']['covered_features'], 43)
        self.assertEqual(result['shapewitness']['selected_rows'], 8)
        self.assertLess(result['shapewitness']['covered_features'], result['observed_features'])
        self.assertEqual(result['shapewitness']['selected_lines'], saved['shapewitness']['selected_lines'])
        for entry in result['reservoir']['runs']:
            self.assertEqual(len(entry['selected_lines']), 8)
            self.assertEqual(len(set(entry['selected_lines'])), 8)
            self.assertEqual(entry['selected_lines'], saved['reservoir']['runs'][entry['seed']]['selected_lines'])


class DescriptionTests(unittest.TestCase):
    def test_package_description_is_current(self):
        generator = load_script('prepare_pypi_readme')
        self.assertEqual(generator.rendered(), generator.TARGET.read_text(encoding='utf-8'))
        self.assertLess(len((ROOT / 'README.md').read_text().splitlines()), 100)

    def test_readiness_cannot_publish(self):
        self.assertTrue((ROOT / 'docs/release/publish.yml.example').exists())
        self.assertTrue((ROOT / '.github/workflows/publish.yml').exists())
        readiness = (ROOT / '.github/workflows/release-readiness.yml').read_text()
        self.assertNotIn('id-token:', readiness)
        self.assertNotIn('gh-action-pypi-publish', readiness)


if __name__ == '__main__':
    unittest.main()
