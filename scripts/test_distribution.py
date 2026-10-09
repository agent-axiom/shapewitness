"""Install one built artifact and test its installed code, never the source tree."""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--kind', choices=('wheel', 'sdist'), required=True)
    args = parser.parse_args()
    pattern = '*.whl' if args.kind == 'wheel' else '*.tar.gz'
    artifacts = list(args.directory.glob(pattern))
    if len(artifacts) != 1:
        parser.error('expected exactly one artifact of the requested kind')
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--force-reinstall',
                    str(artifacts[0].resolve())], check=True, env=env)
    # A fresh cwd and cleared PYTHONPATH keep import resolution honest. Test data
    # and scripts are read from this checkout, while the library is installed.
    with tempfile.TemporaryDirectory(prefix='shapewitness-installed-') as directory:
        def run(*command):
            subprocess.run([sys.executable, *command], check=True, cwd=directory, env=env)
        run('-c', 'from pathlib import Path; import shapewitness; '
            'assert not Path(shapewitness.__file__).resolve().is_relative_to(Path(' + repr(str(ROOT / 'src')) + ')); '
            'print("Installed library:", shapewitness.__file__)')
        run('-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-v')
        run('-m', 'shapewitness', str(ROOT / 'examples/events.jsonl'), '-n', '4',
            '--require-complete', '--status', 'json')


if __name__ == '__main__':
    main()
