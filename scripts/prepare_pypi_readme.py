"""Generate the package description with absolute links; no network access."""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'docs' / 'release' / 'PYPI_README.md'
BASE = 'https://github.com/agent-axiom/shapewitness/blob/main/'


def rendered():
    def replace(match):
        target = match.group(1)
        if '://' in target or target.startswith(('#', 'mailto:')):
            return match.group(0)
        return '](' + BASE + target + ')'
    return re.sub(r'\]\(([^)]+)\)', replace, (ROOT / 'README.md').read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    expected = rendered()
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding='utf-8') != expected:
            raise SystemExit('Package description is stale: run python scripts/prepare_pypi_readme.py')
        print('Package description matches README; local links are absolute')
    else:
        TARGET.write_text(expected, encoding='utf-8')


if __name__ == '__main__':
    main()
