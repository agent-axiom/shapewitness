"""Emit one original row that reproduces a known importer assumption.

Run: python examples/recipes/importer_bug_repro.py > repro.jsonl
This checks a failure predicate after structural selection; it is not a generic
failure minimizer and cannot guarantee an arbitrary bug is selected.
"""
import json
import sys
from pathlib import Path

from shapewitness import select


def broken_importer(event):
    return event["user"]["email"].lower()


def main():
    with (Path(__file__).parents[1] / "events.jsonl").open("rb") as source:
        result = select(source, max_rows=4)
    for witness in result.rows:
        try:
            broken_importer(json.loads(witness.raw))
        except (KeyError, TypeError, AttributeError) as error:
            sys.stdout.buffer.write(witness.raw)
            print(f"Reproduced {type(error).__name__} at original line {witness.line}; "
                  f"sha256={witness.sha256}", file=sys.stderr)
            return
    raise SystemExit("No selected row reproduces this bug; use a targeted search of the original input")


if __name__ == "__main__":
    main()
