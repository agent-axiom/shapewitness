"""Keep installed metadata, public version, CLI and report identity aligned."""
import io
import json
from importlib.metadata import version
from pathlib import Path
import unittest

from shapewitness import __version__, select


class VersionTests(unittest.TestCase):
    def test_installed_metadata_matches_runtime_and_report(self):
        self.assertEqual(version('shapewitness'), __version__)
        self.assertEqual(select(io.BytesIO(b'{}\n')).report['tool_version'], __version__)

    def test_committed_example_report_matches_runtime(self):
        report = json.loads((Path(__file__).parents[1] / 'examples/coverage.json').read_text())
        self.assertEqual(report['tool_version'], __version__)
        self.assertEqual(report['format_version'], 1)


if __name__ == '__main__':
    unittest.main()
