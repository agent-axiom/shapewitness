"""A bounded-process smoke test, not a benchmark or universal memory guarantee."""
import subprocess
import sys
import tracemalloc
import unittest
from dataclasses import replace

from shapewitness import Limits, ShapeWitnessError
from shapewitness.core import _walk


class TraversalResourceTests(unittest.TestCase):
    def test_wide_container_checks_node_limit_without_expanding_siblings(self):
        # The decoded value is deliberately allocated before tracing: this
        # measures traversal overhead, not total parsing or process memory.
        for value in ([None] * 100_000, {str(i): None for i in range(50_000)}):
            with self.subTest(container=type(value).__name__):
                tracemalloc.start()
                try:
                    with self.assertRaises(ShapeWitnessError) as error:
                        list(_walk(value, replace(Limits(), max_nodes_per_record=2), 1))
                    _, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                self.assertEqual(error.exception.code, 'limit')
                self.assertEqual(error.exception.line, 1)
                self.assertIn('max_nodes_per_record', str(error.exception))
                self.assertLess(peak, 1024 * 1024)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux address-space limit test')
class ResourceTests(unittest.TestCase):
    def test_30_mib_input_under_192_mib_address_space(self):
        script = '''
import resource
resource.setrlimit(resource.RLIMIT_AS, (192 * 1024 * 1024, 192 * 1024 * 1024))
from shapewitness import select
class Repeated:
    remaining = 15000
    row = b'{"message":"' + b'x' * 2048 + b'","id":1}\\n'
    def readline(self, size):
        if self.remaining == 0:
            return b''
        self.remaining -= 1
        return self.row
result = select(Repeated(), max_rows=5)
assert result.report['input']['records'] == 15000
assert result.report['input']['bytes'] > 30 * 1024 * 1024 / 1.1
assert result.report['coverage']['complete']
assert len(result.rows) == 1
'''
        proc = subprocess.run([sys.executable, '-c', script], capture_output=True, timeout=90)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())


if __name__ == '__main__':
    unittest.main()
