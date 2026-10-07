"""Check stable tag, event commit, main ancestry and metadata. Python 3.11+."""
import argparse
import json
import re
import subprocess
from pathlib import Path

TAG_PATTERN = r'refs/tags/v((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))'


def validate(repo, ref, event_sha):
    import tomllib
    match = re.fullmatch(TAG_PATTERN, ref)
    if not match:
        raise ValueError('Expected a stable vMAJOR.MINOR.PATCH tag without leading zeroes')
    if not re.fullmatch(r'[0-9a-f]{40}', event_sha):
        raise ValueError('Expected a full lowercase event commit SHA')
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
    head = git('rev-parse', '--verify', 'HEAD^{commit}')
    tag = git('rev-parse', '--verify', ref + '^{commit}')
    if head != event_sha or tag != event_sha:
        raise ValueError('Checkout, tag and event must identify the same commit')
    main = git('rev-parse', '--verify', 'refs/remotes/origin/main^{commit}')
    ancestry = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', head, main],
                              capture_output=True, text=True)
    if ancestry.returncode != 0:
        raise ValueError('Release commit is not on the fetched main history')
    with (repo / 'pyproject.toml').open('rb') as source:
        project = tomllib.load(source)['project']
    version = match[1]
    if project.get('name') != 'shapewitness' or project.get('version') != version:
        raise ValueError('Tag and package name/version do not match')
    return {'version': version, 'source_commit': head, 'main_commit': main}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=Path)
    parser.add_argument('tag_ref')
    parser.add_argument('event_sha')
    args = parser.parse_args()
    print(json.dumps(validate(args.repository, args.tag_ref, args.event_sha), sort_keys=True))


if __name__ == '__main__':
    main()
