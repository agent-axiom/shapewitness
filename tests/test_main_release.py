import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location('main_release', ROOT / 'scripts/validate_main_release.py')
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
SHA = 'a' * 40


def run(path='.github/workflows/ci.yml', **changes):
    result = {'id': 10, 'run_attempt': 1, 'path': path, 'name': GATE.WORKFLOWS[path],
              'head_sha': SHA, 'head_branch': 'main', 'event': 'push',
              'head_repository': {'full_name': GATE.REPOSITORY},
              'status': 'completed', 'conclusion': 'success'}
    result.update(changes)
    return result


def event():
    return {'action': 'completed', 'repository': {'full_name': GATE.REPOSITORY},
            'workflow_run': run()}


def release(files=None):
    if files is None:
        files = ['shapewitness-0.1.2-py3-none-any.whl', 'shapewitness-0.1.2.tar.gz']
    return {'info': {'name': 'shapewitness', 'version': '0.1.2'},
            'urls': [{'filename': filename} for filename in files]}


class MainCiGateTests(unittest.TestCase):
    def setUp(self):
        self.runs = [run(path) for path in GATE.WORKFLOWS]

    def test_new_version_requires_both_successful_exact_commit_workflows(self):
        result = GATE.gate(event(), self.runs, '0.1.2', True, None)
        self.assertTrue(result['publish'])
        self.assertEqual(result['source_commit'], SHA)
        self.assertFalse(GATE.gate(event(), self.runs[:1], '0.1.2', True, None)['publish'])

    def test_each_non_success_state_blocks(self):
        for state in ('failure', 'cancelled', 'timed_out', 'skipped', 'neutral', 'action_required', None):
            for index in (0, 1):
                with self.subTest(state=state, workflow=index):
                    runs = copy.deepcopy(self.runs)
                    runs[index]['conclusion'] = state
                    self.assertFalse(GATE.all_ci_successful(runs, SHA))
        runs = copy.deepcopy(self.runs)
        runs[1]['status'] = 'in_progress'
        self.assertFalse(GATE.all_ci_successful(runs, SHA))

    def test_pr_fork_other_branch_wrong_sha_or_workflow_cannot_satisfy_gate(self):
        for field, value in [('event', 'pull_request'), ('head_branch', 'feature'),
                             ('head_sha', 'b' * 40), ('path', '.github/workflows/fake.yml'),
                             ('name', 'Fake'), ('head_repository', {'full_name': 'other/fork'})]:
            with self.subTest(field=field):
                runs = copy.deepcopy(self.runs)
                runs[0][field] = value
                self.assertFalse(GATE.all_ci_successful(runs, SHA))
                bad = event()
                bad['workflow_run'][field] = value
                if field == 'head_sha':
                    bad['workflow_run'][field] = 'main'
                with self.assertRaises(ValueError):
                    GATE.event_commit(bad)

    def test_untrusted_or_failed_event_rejected(self):
        for value in ('failure', 'cancelled', None):
            bad = event()
            bad['workflow_run']['conclusion'] = value
            with self.assertRaises(ValueError):
                GATE.event_commit(bad)
        for field, value in [('action', 'requested'), ('repository', {'full_name': 'other/fork'})]:
            bad = event()
            bad[field] = value
            with self.assertRaises(ValueError):
                GATE.event_commit(bad)

    def test_latest_failed_or_pending_run_cannot_use_older_green_run(self):
        for changes in ({'id': 11, 'conclusion': 'failure'},
                        {'id': 11, 'status': 'queued', 'conclusion': None},
                        {'id': 10, 'run_attempt': 2, 'conclusion': 'failure'}):
            self.assertFalse(GATE.all_ci_successful(self.runs + [run(**changes)], SHA))
        self.assertTrue(GATE.all_ci_successful(self.runs + [run(id=9, conclusion='failure')], SHA))

    def test_unchanged_or_published_version_is_idempotent(self):
        for changed, document in [(False, None), (True, release())]:
            self.assertFalse(GATE.gate(event(), self.runs, '0.1.2', changed, document)['publish'])

    def test_partial_or_unexpected_release_fails_closed(self):
        for files in ([], ['shapewitness-0.1.2.tar.gz'],
                      ['shapewitness-0.1.2.tar.gz'] * 2,
                      ['shapewitness-0.1.2.tar.gz', 'other.whl']):
            with self.subTest(files=files), self.assertRaisesRegex(ValueError, 'partial or unexpected'):
                GATE.gate(event(), self.runs, '0.1.2', True, release(files))
        document = release()
        document['info']['name'] = 'other'
        with self.assertRaises(ValueError):
            GATE.published_release(document, '0.1.2')

    def test_only_stable_versions(self):
        for version in ('01.2.3', '1.02.3', '1.2', '1.2.3rc1', '../other', '1.2.3\n', None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                GATE.version_tuple(version)

    def test_only_pypi_404_means_missing(self):
        for code in (401, 403, 429, 500, 503):
            with patch.object(GATE, 'urlopen', side_effect=HTTPError('url', code, 'error', {}, None)):
                with self.assertRaises(HTTPError):
                    GATE.read_json('https://pypi.org/pypi/shapewitness/0.1.2/json', missing_ok=True)
        with patch.object(GATE, 'urlopen', side_effect=HTTPError('url', 404, 'missing', {}, None)):
            self.assertIsNone(GATE.read_json('https://pypi.org/pypi/shapewitness/0.1.2/json', missing_ok=True))
        with patch.object(GATE, 'urlopen', side_effect=URLError('network')):
            with self.assertRaises(URLError):
                GATE.read_json('https://pypi.org/pypi/shapewitness/0.1.2/json', missing_ok=True)

    def test_no_github_token_to_pypi_and_incomplete_history_is_rejected(self):
        with self.assertRaises(ValueError):
            GATE.read_json('https://pypi.org/pypi/shapewitness/json', token='synthetic-test-token')
        with patch.dict(GATE.os.environ, {'GH_TOKEN': 'synthetic-test-token'}):
            with patch.object(GATE, 'read_json', return_value={'total_count': 101, 'workflow_runs': self.runs}):
                with self.assertRaisesRegex(ValueError, 'Incomplete CI history'):
                    GATE.fetch_ci(SHA)


@unittest.skipIf(sys.version_info < (3, 11), 'Release gate uses Python 3.12/tomllib')
class MainSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git('init', '-b', 'main')
        self.write_version('0.1.1')
        self.commit('initial')
        self.write_version('0.1.2')
        self.commit('release')
        self.sha = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', self.sha)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True,
                                       stderr=subprocess.DEVNULL).strip()

    def write_version(self, version):
        (self.repo / 'pyproject.toml').write_text('[project]\nname="shapewitness"\nversion="' + version + '"\n')

    def commit(self, message):
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', message)

    def test_version_increase_and_exact_source(self):
        self.assertEqual(GATE.source_identity(self.repo, self.sha), ('0.1.2', True))
        with self.assertRaisesRegex(ValueError, 'Checkout'):
            GATE.source_identity(self.repo, SHA)

    def test_same_version_commit_is_skipped(self):
        (self.repo / 'README').write_text('docs only')
        self.commit('docs')
        sha = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', sha)
        self.assertEqual(GATE.source_identity(self.repo, sha), ('0.1.2', False))

    def test_unmerged_commit_is_rejected(self):
        self.git('checkout', '-b', 'feature')
        self.write_version('0.1.3')
        self.commit('unmerged')
        with self.assertRaisesRegex(ValueError, 'main history'):
            GATE.source_identity(self.repo, self.git('rev-parse', 'HEAD'))

    def test_version_decrease_is_rejected(self):
        self.write_version('0.1.0')
        self.commit('decrease')
        sha = self.git('rev-parse', 'HEAD')
        self.git('update-ref', 'refs/remotes/origin/main', sha)
        with self.assertRaisesRegex(ValueError, 'decrease'):
            GATE.source_identity(self.repo, sha)

    def test_main_can_advance_without_changing_selected_release_commit(self):
        (self.repo / 'README').write_text('later main')
        self.commit('advance main')
        self.git('update-ref', 'refs/remotes/origin/main', self.git('rev-parse', 'HEAD'))
        self.git('checkout', self.sha)
        self.assertEqual(GATE.source_identity(self.repo, self.sha), ('0.1.2', True))


if __name__ == '__main__':
    unittest.main()
