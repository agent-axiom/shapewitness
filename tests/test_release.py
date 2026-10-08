import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MANIFEST = load('verify_release_manifest')
TAG = load('validate_release_tag')
SHA = 'a' * 40


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'dist').mkdir()
        self.entries = []
        for name in ('shapewitness-0.1.0-py3-none-any.whl', 'shapewitness-0.1.0.tar.gz'):
            data = ('synthetic ' + name).encode()
            (self.root / 'dist' / name).write_bytes(data)
            self.entries.append({'filename': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        self.manifest = {'package': 'shapewitness', 'version': '0.1.0',
                         'source_commit': SHA, 'artifacts': self.entries}
        self.save()

    def save(self):
        (self.root / 'release-manifest.json').write_text(json.dumps(self.manifest))

    def test_exact_artifacts_pass(self):
        self.assertEqual(MANIFEST.verify(self.root, '0.1.0', SHA), self.manifest)

    def test_wrong_identity_rejected(self):
        for version, commit in [('0.1.1', SHA), ('0.1.0', 'b' * 40), ('01.1.0', SHA), ('0.1.0', 'main')]:
            with self.subTest(version=version, commit=commit), self.assertRaises(ValueError):
                MANIFEST.verify(self.root, version, commit)

    def test_same_size_tampering_rejected(self):
        path = self.root / 'dist' / self.entries[0]['filename']
        data = path.read_bytes()
        path.write_bytes(b'X' + data[1:])
        with self.assertRaisesRegex(ValueError, 'digest'):
            MANIFEST.verify(self.root, '0.1.0', SHA)

    def test_size_change_rejected(self):
        (self.root / 'dist' / self.entries[0]['filename']).write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'size/type'):
            MANIFEST.verify(self.root, '0.1.0', SHA)

    def test_unexpected_file_rejected(self):
        (self.root / 'dist' / 'extra.txt').write_text('extra')
        with self.assertRaisesRegex(ValueError, 'Unexpected'):
            MANIFEST.verify(self.root, '0.1.0', SHA)

    def test_duplicate_and_traversal_rejected(self):
        self.manifest['artifacts'] = [self.entries[0], self.entries[0]]
        self.save()
        with self.assertRaises(ValueError):
            MANIFEST.verify(self.root, '0.1.0', SHA)
        self.manifest['artifacts'] = self.entries
        self.entries[0]['filename'] = '../outside.whl'
        self.save()
        with self.assertRaises(ValueError):
            MANIFEST.verify(self.root, '0.1.0', SHA)


@unittest.skipIf(sys.version_info < (3, 11), 'Tag gate runs on Python 3.12/tomllib')
class TagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-b', 'main')
        (self.repo / 'pyproject.toml').write_text('[project]\nname="shapewitness"\nversion="0.1.0"\n')
        self.git('add', '.')
        self.commit('initial')
        self.head = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', self.head)
        self.git('tag', 'v0.1.0')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()

    def commit(self, message):
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', message)

    def test_lightweight_and_annotated_tags(self):
        self.assertEqual(TAG.validate(self.repo, 'refs/tags/v0.1.0', self.head)['version'], '0.1.0')
        self.git('tag', '-d', 'v0.1.0')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'tag', '-a', 'v0.1.0', '-m', 'tag')
        self.assertEqual(TAG.validate(self.repo, 'refs/tags/v0.1.0', self.head)['source_commit'], self.head)

    def test_strict_semver(self):
        for tag in ('v01.2.3', 'v1.02.3', 'v1.2.03', 'v1.2', 'v1.2.3rc1', 'v1.2.3-beta.1',
                    'v1.2.3+build', 'latest', 'v1.2.3/other', 'v1.2.3\n'):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                TAG.validate(self.repo, 'refs/tags/' + tag, self.head)

    def test_event_commit_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'same commit'):
            TAG.validate(self.repo, 'refs/tags/v0.1.0', SHA)

    def test_metadata_mismatch(self):
        self.git('tag', 'v0.1.1')
        with self.assertRaisesRegex(ValueError, 'name/version'):
            TAG.validate(self.repo, 'refs/tags/v0.1.1', self.head)

    def test_unmerged_commit_rejected(self):
        self.git('checkout', '-b', 'feature')
        (self.repo / 'extra').write_text('feature')
        self.git('add', '.')
        self.commit('feature')
        head = self.git('rev-parse', 'HEAD')
        self.git('tag', '-f', 'v0.1.0')
        with self.assertRaisesRegex(ValueError, 'main history'):
            TAG.validate(self.repo, 'refs/tags/v0.1.0', head)

    def test_main_ancestor_accepted(self):
        (self.repo / 'extra').write_text('new main')
        self.git('add', '.')
        self.commit('advance main')
        main = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', main)
        self.git('checkout', self.head)
        self.assertEqual(TAG.validate(self.repo, 'refs/tags/v0.1.0', self.head)['main_commit'], main)


@unittest.skipIf(sys.version_info < (3, 11), 'Distribution inspection uses tomllib')
class DistributionVersionTests(unittest.TestCase):
    def test_literal_version_is_read_without_importing(self):
        reader = load('check_distribution').literal_version
        self.assertEqual(reader('"""Version."""\n__version__ = "0.1.1"\n'), '0.1.1')

    def test_executable_or_ambiguous_version_source_is_rejected(self):
        reader = load('check_distribution').literal_version
        for source in ('__version__ = str(1)', '__version__ = 1',
                       '__version__ = "0.1.1"\n__version__ = "0.1.2"',
                       '__version__ = "0.1.1"\n__version__ += "x"',
                       '__version__ = "0.1.1"\nimport os', 'other = "0.1.1"'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                reader(source)


class PublisherTests(unittest.TestCase):
    def test_candidate_checks_are_version_independent_and_include_importers(self):
        readiness = (ROOT / '.github/workflows/release-readiness.yml').read_text()
        self.assertNotIn('shapewitness-0.1.0', readiness)
        self.assertIn('uvx --no-index --from dist/*.whl', readiness)
        self.assertIn('pipx run --no-cache --spec dist/*.whl', readiness)
        publisher = (ROOT / '.github/workflows/publish.yml').read_text().split('\n  publish:\n')[0]
        for workflow in (readiness, publisher):
            self.assertIn('python -m unittest discover -s tests/integration -v', workflow)
            self.assertIn('python examples/recipes/importer_regression.py sqlite-utils', workflow)
            self.assertIn('python examples/recipes/importer_regression.py dlt', workflow)

    def test_inlined_checks_match_helpers(self):
        text = (ROOT / '.github/workflows/publish.yml').read_text()
        for marker, filename in [('TAG_VALIDATOR', 'validate_release_tag'), ('VERIFIER', 'verify_release_manifest')]:
            body = text.split('          # INLINED_' + marker + '_START\n', 1)[1]
            body = body.split('          # INLINED_' + marker + '_END\n', 1)[0]
            plain = ''.join(line[10:] + '\n' for line in body.splitlines())
            self.assertEqual(plain, (ROOT / 'scripts' / (filename + '.py')).read_text())
        self.assertEqual(text.count('\njobs:\n'), 1)
        for job in ('validate', 'test', 'build', 'publish'):
            self.assertEqual(text.count('\n  ' + job + ':\n'), 1)
        self.assertNotIn('workflow_dispatch:', text)
        self.assertNotIn('id-token:', text)
        self.assertIn("- 'v*'", text)
        self.assertIn('github.event.created', text)
        self.assertIn('!github.event.forced', text)
        self.assertIn('attestations: false', text)
        self.assertIn('skip-existing: false', text)
        before, after = text.split('\n  publish:\n', 1)
        self.assertNotIn('PYPI_API_TOKEN', before)
        self.assertNotIn('actions/checkout@', after)
        self.assertIn('artifact-ids: ${{ needs.build.outputs.artifact_id }}', after)
        self.assertIn('password: ${{ secrets.PYPI_API_TOKEN }}', after)


if __name__ == '__main__':
    unittest.main()
