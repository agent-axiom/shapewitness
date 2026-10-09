"""Pipeline-friendly command line interface. Data goes to stdout; status to stderr."""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import ExitStack
from dataclasses import fields
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .core import Limits, ShapeWitnessError, select
from .comparison import compare_reports, read_report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select original JSONL rows that cover observed shapes. Offline and deterministic.")
    parser.add_argument("input", nargs="?", default="-", help="JSONL file, or - for stdin (default)")
    parser.add_argument("-n", "--max-rows", type=int, default=20, help="row budget (default: 20; 0 reports only)")
    parser.add_argument("-o", "--output", help="create a JSONL file; default: stdout")
    parser.add_argument("--report", help="create a deterministic JSON coverage/provenance report")
    parser.add_argument("--status", choices=("human", "json", "quiet"), default="human", help="stderr status format")
    parser.add_argument("--require-complete", action="store_true", help="exit 3 if the selected rows leave observed features uncovered")
    parser.add_argument("--baseline", help="compare the full observed inventory with this saved coverage report")
    parser.add_argument("--comparison-report", help="create a separate structural comparison JSON report (requires --baseline)")
    parser.add_argument("--require-unchanged", action="store_true", help="exit 4 on added/removed observed features (requires --baseline)")
    parser.add_argument("--skip-blank-lines", action="store_true", help="explicitly ignore blank lines (default: reject)")
    parser.add_argument("--number-mode", choices=("json", "syntax"), default="json",
                        help="group numbers (json, default), or distinguish integer and fractional/exponent syntax (report format 2)")
    parser.add_argument("--temp-dir", help="parent directory for the private, auto-removed SQLite spool")
    parser.add_argument("--version", action="version", version=f"shapewitness {__version__}")
    limits = parser.add_argument_group("resource limits (bytes include line endings)")
    defaults = Limits()
    for field in fields(defaults):
        limits.add_argument("--" + field.name.replace("_", "-"), type=int,
                           default=getattr(defaults, field.name), help=f"default: {getattr(defaults, field.name)}")
    return parser


def _status(mode: str, value: dict[str, Any], human: str) -> None:
    if mode == "json":
        print(json.dumps(value, ensure_ascii=True, sort_keys=True), file=sys.stderr)
    elif mode != "quiet" or value.get("ok") is False:
        print(human, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        limits = Limits(**{field.name: getattr(args, field.name) for field in fields(Limits)})
        limits.validate()
        if (args.comparison_report or args.require_unchanged) and not args.baseline:
            raise ShapeWitnessError("configuration", "comparison-report and require-unchanged require baseline")
        # Reject collisions before consuming stdin; do not overwrite input,
        # existing artifacts, symlinks, or a second output path alias.
        destinations = [Path(p) for p in (args.output, args.report, args.comparison_report) if p]
        resolved = [p.resolve() for p in destinations]
        if len(set(resolved)) != len(resolved):
            raise ShapeWitnessError("output_exists", "output paths must be different")
        for destination in destinations:
            if os.path.lexists(destination):
                raise ShapeWitnessError("output_exists", "an output path already exists; choose a new path")
        baseline = None
        if args.baseline:
            with open(args.baseline, "rb") as source:
                baseline = read_report(source)
        with ExitStack() as stack:
            source = sys.stdin.buffer if args.input == "-" else stack.enter_context(open(args.input, "rb"))
            result = select(source, max_rows=args.max_rows, limits=limits,
                            skip_blank_lines=args.skip_blank_lines, temp_dir=args.temp_dir,
                            number_mode=args.number_mode)
        comparison = compare_reports(baseline, result.report) if baseline is not None else None
        # Input/limit failures never emit data or create outputs. Exclusive open
        # prevents clobbering files created by another process after our check.
        # If an I/O failure occurs while writing, a partial output can remain.
        if args.output:
            with open(args.output, "xb") as target:
                result.write_jsonl(target)
        else:
            result.write_jsonl(sys.stdout.buffer)
            sys.stdout.buffer.flush()
        if args.report:
            with open(args.report, "x", encoding="utf-8", newline="\n") as target:
                json.dump(result.report, target, ensure_ascii=True, indent=2, sort_keys=True)
                target.write("\n")
        if args.comparison_report:
            with open(args.comparison_report, "x", encoding="utf-8", newline="\n") as target:
                json.dump(comparison, target, ensure_ascii=True, indent=2, sort_keys=True)
                target.write("\n")
        coverage = result.report["coverage"]
        summary = {"ok": True, "input_records": result.report["input"]["records"],
                   "selected_rows": len(result.rows), **coverage,
                   "stop_reason": result.report["selection"]["stop_reason"]}
        drift = ""
        if comparison is not None:
            summary["comparison"] = {"changed": comparison["changed"],
                                     "added_features": len(comparison["added_features"]),
                                     "removed_features": len(comparison["removed_features"])}
            drift = (f"; +{summary['comparison']['added_features']} / "
                     f"-{summary['comparison']['removed_features']} observed features")
        _status(args.status, summary,
                f"shapewitness: {len(result.rows)}/{summary['input_records']} rows; "
                f"{coverage['covered_features']}/{coverage['observed_features']} observed features; "
                f"{summary['stop_reason']}{drift}")
        if args.require_complete and not coverage["complete"]:
            return 3
        return 4 if args.require_unchanged and comparison["changed"] else 0
    except ShapeWitnessError as exc:
        error = {"ok": False, "error": exc.as_dict()}
        at = f" on line {exc.line}" if exc.line else ""
        _status(args.status, error, f"shapewitness: {exc.code}{at}: {exc}")
        return 2
    except BrokenPipeError:
        # Avoid Python's second flush traceback when a downstream pipe closes.
        try:
            fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(fd, sys.stdout.fileno())
            os.close(fd)
        except (OSError, AttributeError):
            pass
        return 1
    except OSError as exc:
        error = ShapeWitnessError("io", f"I/O failure ({type(exc).__name__})")
        _status(args.status, {"ok": False, "error": error.as_dict()}, f"shapewitness: {error}")
        return 2
    except KeyboardInterrupt:
        return 130
