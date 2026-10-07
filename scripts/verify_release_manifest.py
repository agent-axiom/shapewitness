"""Verify the exact two validated distribution files without executing them."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def verify(root, version, commit):
    if not re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', version):
        raise ValueError('Expected a stable three-component version')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Expected a full lowercase commit SHA')
    manifest_path = root / 'release-manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 65536:
        raise ValueError('Invalid release manifest file')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (manifest.get('package') != 'shapewitness' or manifest.get('version') != version
            or manifest.get('source_commit') != commit):
        raise ValueError('Release identity does not match the tag')
    expected = {f'shapewitness-{version}-py3-none-any.whl', f'shapewitness-{version}.tar.gz'}
    artifacts = manifest.get('artifacts', [])
    if len(artifacts) != 2 or {entry.get('filename') for entry in artifacts} != expected:
        raise ValueError('Expected exactly the validated wheel and source archive')
    dist = root / 'dist'
    if dist.is_symlink() or {p.name for p in dist.iterdir()} != expected:
        raise ValueError('Unexpected files in the publishing directory')
    for entry in artifacts:
        path = dist / entry['filename']
        if (path.is_symlink() or not path.is_file() or
                path.stat().st_size != entry.get('bytes') or path.stat().st_size > 64 * 1024 * 1024):
            raise ValueError('Distribution size/type does not match the manifest')
        digest = hashlib.sha256()
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        if digest.hexdigest() != entry.get('sha256'):
            raise ValueError('Distribution digest does not match the validated artifact')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('version')
    parser.add_argument('commit')
    args = parser.parse_args()
    verify(args.directory, args.version, args.commit)
    print(f'Verified exact distribution bytes: shapewitness {args.version} at {args.commit}')


if __name__ == '__main__':
    main()
