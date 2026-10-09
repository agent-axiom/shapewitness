"""Fail-closed main-CI/version gate; only the publish action receives the PyPI token."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPOSITORY = 'agent-axiom/shapewitness'
WORKFLOWS = {'.github/workflows/ci.yml': 'CI',
             '.github/workflows/release-readiness.yml': 'Release readiness'}
VERSION_PATTERN = r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'


def version_tuple(version):
    if not isinstance(version, str) or not re.fullmatch(VERSION_PATTERN, version):
        raise ValueError('Expected a stable three-component version without leading zeroes')
    return tuple(map(int, version.split('.')))


def event_commit(event):
    run = event.get('workflow_run', {})
    if (event.get('action') != 'completed'
            or event.get('repository', {}).get('full_name') != REPOSITORY
            or run.get('head_repository', {}).get('full_name') != REPOSITORY
            or run.get('event') != 'push' or run.get('head_branch') != 'main'
            or run.get('path') not in WORKFLOWS
            or run.get('name') != WORKFLOWS[run['path']]
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'):
        raise ValueError('Expected successful trusted main-push CI completion')
    sha = run.get('head_sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Expected an immutable full commit SHA')
    return sha


def all_ci_successful(runs, sha):
    """Use the newest run, including in-progress/failed reruns, for each workflow."""
    for path in WORKFLOWS:
        matches = [run for run in runs if run.get('path') == path
                   and run.get('name') == WORKFLOWS[path]
                   and run.get('head_sha') == sha and run.get('head_branch') == 'main'
                   and run.get('event') == 'push'
                   and run.get('head_repository', {}).get('full_name') == REPOSITORY]
        if not matches:
            return False
        latest = max(matches, key=lambda run: (run['id'], run.get('run_attempt', 1)))
        if latest.get('status') != 'completed' or latest.get('conclusion') != 'success':
            return False
    return True


def read_json(url, token=None, missing_ok=False):
    headers = {'Accept': 'application/json', 'User-Agent': 'shapewitness-release-gate'}
    if token:
        # Never send the GitHub read token to PyPI or a caller-selected host.
        if not url.startswith('https://api.github.com/repos/' + REPOSITORY + '/'):
            raise ValueError('Unexpected authenticated API destination')
        headers['Authorization'] = 'Bearer ' + token
        headers['X-GitHub-Api-Version'] = '2022-11-28'
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        raise


def fetch_ci(sha):
    query = urlencode({'branch': 'main', 'event': 'push', 'head_sha': sha, 'per_page': 100})
    runs = []
    for path in WORKFLOWS:
        url = ('https://api.github.com/repos/' + REPOSITORY + '/actions/workflows/'
               + path.rsplit('/', 1)[1] + '/runs?' + query)
        result = read_json(url, os.environ['GH_TOKEN'])
        page = result['workflow_runs']
        if result['total_count'] != len(page):
            raise ValueError('Incomplete CI history; refusing to select an older successful run')
        runs.extend(page)
    return runs


def source_identity(repo, sha):
    import tomllib

    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()

    if git('rev-parse', '--verify', 'HEAD^{commit}') != sha:
        raise ValueError('Checkout does not match the successful CI commit')
    main = git('rev-parse', '--verify', 'refs/remotes/origin/main^{commit}')
    ancestry = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', sha, main],
                              capture_output=True, text=True)
    if ancestry.returncode != 0:
        raise ValueError('Release commit is not on fetched main history')
    project = tomllib.loads((repo / 'pyproject.toml').read_text())['project']
    previous = tomllib.loads(git('show', sha + '^1:pyproject.toml'))['project']
    if project.get('name') != 'shapewitness' or previous.get('name') != 'shapewitness':
        raise ValueError('Unexpected package identity')
    version, old = project['version'], previous['version']
    current_tuple, old_tuple = version_tuple(version), version_tuple(old)
    if current_tuple < old_tuple:
        raise ValueError('Release version must not decrease')
    return version, current_tuple > old_tuple


def published_release(document, version):
    """Complete existing releases are no-ops; partial releases require investigation."""
    version_tuple(version)
    if document is None:
        return False
    info = document.get('info', {})
    if info.get('name') != 'shapewitness' or info.get('version') != version:
        raise ValueError('PyPI returned an unexpected package identity')
    expected = {f'shapewitness-{version}-py3-none-any.whl', f'shapewitness-{version}.tar.gz'}
    files = document.get('urls', [])
    if len(files) != 2 or {item.get('filename') for item in files} != expected:
        raise ValueError('Existing PyPI release is partial or unexpected; never rebuild/reupload it')
    return True


def gate(event, runs, version, changed, document):
    sha = event_commit(event)
    version_tuple(version)
    result = {'source_commit': sha, 'version': version, 'publish': False}
    if not all_ci_successful(runs, sha):
        result['reason'] = 'Waiting for successful CI and Release readiness on this exact main commit'
    elif not changed:
        result['reason'] = 'Version unchanged from the first parent; nothing to publish'
    elif published_release(document, version):
        result['reason'] = 'Version already exists on PyPI; nothing to publish'
    else:
        result.update(publish=True, reason='New version and both exact-commit workflows succeeded')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=Path, nargs='?')
    parser.add_argument('--ready-to-upload', nargs=2, metavar=('VERSION', 'COMMIT'))
    args = parser.parse_args()
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    sha = event_commit(event)
    if args.ready_to_upload:
        version, expected_sha = args.ready_to_upload
        if sha != expected_sha:
            raise ValueError('Upload identity differs from CI identity')
        changed = True  # The earlier source gate already verified the version bump.
    elif args.repository is not None:
        version, changed = source_identity(args.repository, sha)
    else:
        parser.error('repository or --ready-to-upload is required')
    version_tuple(version)
    runs = fetch_ci(sha)
    document = None
    if changed and all_ci_successful(runs, sha):
        document = read_json('https://pypi.org/pypi/shapewitness/' + version + '/json', missing_ok=True)
    result = gate(event, runs, version, changed, document)
    print(json.dumps(result, sort_keys=True))
    with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
        for key in ('version', 'source_commit', 'publish'):
            value = str(result[key]).lower() if key == 'publish' else result[key]
            output.write(key + '=' + value + '\n')
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
        summary.write('ShapeWitness ' + version + ': ' + result['reason'] + '\n')


if __name__ == '__main__':
    main()
