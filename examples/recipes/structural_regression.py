"""Run: python -m pytest -q examples/recipes/structural_regression.py.

Synthetic, reviewed artifacts live in examples/regression. Pytest is an optional
recipe dependency. ShapeWitness still has no runtime dependencies.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from shapewitness import Pin, compare_reports, read_report, select


DATA = Path(__file__).resolve().parents[1] / "regression"
BASELINE = DATA / "baseline-report.json"
CURRENT = DATA / "current.jsonl"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(value, target, indent=2, sort_keys=True)
        target.write("\n")


@pytest.fixture(scope="session")
def reviewed_baseline():
    # This is a committed review decision, not a baseline generated from today's
    # input inside the test. read_report validates inventory fields, not trust.
    with BASELINE.open("rb") as source:
        return read_report(source)


@pytest.fixture(scope="session")
def reviewed_pins():
    manifest = read_json(DATA / "pins.json")
    assert manifest["source"] == CURRENT.name
    # Never replace these expected digests with hashes of the current input.
    return tuple(Pin(line=entry["line"], sha256=entry["sha256"])
                 for entry in manifest["pins"])


@pytest.fixture(scope="session")
def artifacts(tmp_path_factory):
    configured = os.environ.get("SHAPEWITNESS_REGRESSION_ARTIFACTS")
    if configured:
        directory = Path(configured)
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return tmp_path_factory.mktemp("structural-regression")


@pytest.fixture
def artifact_dir(artifacts, request):
    directory = artifacts / request.node.name.replace("[", "-").replace("]", "")
    # Exclusive creation keeps stale files from being mistaken for this run.
    directory.mkdir()
    return directory


@pytest.fixture(scope="session")
def selected_current(artifacts, reviewed_pins, reviewed_baseline):
    with CURRENT.open("rb") as source:
        result = select(source, pins=reviewed_pins, max_rows=3)
    directory = artifacts / "current"
    directory.mkdir()
    with (directory / "witness.jsonl").open("xb") as target:
        result.write_jsonl(target)
    write_json(directory / "report.json", result.report)
    write_json(directory / "comparison.json",
               compare_reports(reviewed_baseline, result.report))
    return result


def import_order(order):
    """Example application behavior: zero quantity has no unit price.

    This is a deliberately small importer for the synthetic schema, not a
    validator for arbitrary orders. Replace it with your application's importer.
    """
    quantity = order["quantity"]
    return {
        "id": order["id"],
        "currency": order["currency"],
        "unit_cents": None if quantity == 0 else order["total_cents"] // quantity,
        "note_state": ("missing" if "note" not in order
                       else "null" if order["note"] is None else "text"),
        "tags": order["tags"],
    }


def broken_unit_price(order):
    """Deliberately omit the zero-quantity branch to expose the known bug."""
    return order["total_cents"] // order["quantity"]


def run_cli(source, directory, pins, *, max_rows=3, extra=()):
    outputs = {name: directory / name for name in
               ("witness.jsonl", "report.json", "comparison.json")}
    command = [
        sys.executable, "-m", "shapewitness", str(source),
        "-n", str(max_rows), "--output", str(outputs["witness.jsonl"]),
        "--report", str(outputs["report.json"]), "--baseline", str(BASELINE),
        "--comparison-report", str(outputs["comparison.json"]),
        "--require-complete", "--require-unchanged", "--status", "json",
    ]
    for pin in pins:
        command.extend(("--pin-row", f"{pin.line}:{pin.sha256}"))
    completed = subprocess.run(command + list(extra), capture_output=True,
                               check=False, timeout=30)
    # Keep the gate status alongside its artifacts, including expected failures.
    (directory / "status.json").write_bytes(completed.stderr)
    (directory / "exit-code.txt").write_text(str(completed.returncode) + "\n",
                                            encoding="ascii")
    assert completed.stdout == b"", "JSONL belongs in the requested output file"
    return completed, outputs


def test_reviewed_baseline_is_tied_to_its_original_input(reviewed_baseline):
    original = (DATA / "baseline.jsonl").read_bytes()
    assert hashlib.sha256(original).hexdigest() == reviewed_baseline["input"]["sha256"]
    regenerated = select(io.BytesIO(original), max_rows=3)
    assert not compare_reports(reviewed_baseline, regenerated.report)["changed"]
    assert reviewed_baseline["coverage"]["observed_features"] == 11


def test_current_inventory_and_reviewed_fixture(selected_current, reviewed_baseline,
                                                reviewed_pins):
    result = selected_current
    comparison = compare_reports(reviewed_baseline, result.report)
    assert comparison["changed"] is False
    assert comparison["added_features"] == comparison["removed_features"] == []
    assert comparison["baseline"]["input_sha256"] != comparison["current"]["input_sha256"]
    assert result.report["coverage"]["complete"] is True
    assert [row.line for row in result.rows] == [2, 3, 5]
    assert b"".join(row.raw for row in result.rows) == (DATA / "current.witness.jsonl").read_bytes()
    assert result.report["format_version"] == 3
    assert result.report["feature_model"] == "json-structure-v1"
    assert [row["selection_reason"] for row in result.report["rows"]] == ["greedy", "greedy", "pinned"]
    pinned = result.rows[-1]
    assert pinned.selection_rank == 1  # Selected first, emitted in source order.
    assert pinned.sha256 == reviewed_pins[0].sha256
    original = CURRENT.read_bytes()
    for row in result.rows:
        assert original[row.offset:row.offset + len(row.raw)] == row.raw
        assert hashlib.sha256(row.raw).hexdigest() == row.sha256


def test_application_importer_handles_the_reviewed_rows(selected_current):
    actual = [import_order(json.loads(row.raw)) for row in selected_current.rows]
    assert actual == [
        {"id": "order-002", "currency": "USD", "unit_cents": 500,
         "note_state": "null", "tags": []},
        {"id": "order-003", "currency": "USD", "unit_cents": 300,
         "note_state": "missing", "tags": ["rush"]},
        {"id": "order-005", "currency": "USD", "unit_cents": None,
         "note_state": "text", "tags": ["standard"]},
    ]


def test_complete_unpinned_shapes_can_miss_the_known_bug(selected_current,
                                                        reviewed_baseline):
    with CURRENT.open("rb") as source:
        unpinned = select(source, max_rows=3)
    assert unpinned.report["coverage"]["complete"] is True
    assert not compare_reports(reviewed_baseline, unpinned.report)["changed"]
    assert [row.line for row in unpinned.rows] == [1, 2, 3]
    # The buggy implementation looks fine on the complete unpinned fixture.
    assert [broken_unit_price(json.loads(row.raw)) for row in unpinned.rows] == [700, 500, 300]
    pinned_order = json.loads(selected_current.rows[-1].raw)
    assert pinned_order["id"] == "order-005"
    with pytest.raises(ZeroDivisionError):
        broken_unit_price(pinned_order)
    assert import_order(pinned_order)["unit_cents"] is None


def test_cli_current_inventory_gate_passes(artifact_dir, reviewed_pins):
    completed, outputs = run_cli(CURRENT, artifact_dir, reviewed_pins)
    assert completed.returncode == 0, completed.stderr.decode("utf-8")
    assert read_json(outputs["comparison.json"])["changed"] is False
    assert outputs["witness.jsonl"].read_bytes() == (DATA / "current.witness.jsonl").read_bytes()
    with outputs["report.json"].open("rb") as source:
        assert read_report(source)["format_version"] == 3


def test_cli_deliberate_drift_emits_reviewable_delta_and_exit_4(artifact_dir,
                                                             reviewed_pins):
    # Four rows cover this changed inventory, so exit 3 (coverage) cannot mask
    # the structural-drift gate. The pinned fifth source line is unchanged.
    completed, outputs = run_cli(DATA / "drifted.jsonl", artifact_dir,
                                 reviewed_pins, max_rows=4)
    assert completed.returncode == 4, completed.stderr.decode("utf-8")
    comparison = read_json(outputs["comparison.json"])
    assert comparison["changed"] is True
    assert comparison["added_features"] == [
        {"path": ["discount_code"], "kind": "missing"},
        {"path": ["discount_code"], "kind": "string"},
    ]
    assert comparison["removed_features"] == [{"path": ["note"], "kind": "null"}]
    assert read_json(outputs["report.json"])["coverage"]["complete"] is True
    assert outputs["witness.jsonl"].exists()  # Gate failures still leave review artifacts.


@pytest.mark.parametrize("change", ["value", "crlf", "missing-final-lf"])
def test_pin_detects_same_shape_byte_drift(change, artifact_dir, reviewed_pins,
                                          reviewed_baseline):
    lines = CURRENT.read_bytes().splitlines(keepends=True)
    if change == "value":
        lines[-1] = lines[-1].replace(b'"quantity":0', b'"quantity":1')
    elif change == "crlf":
        lines[-1] = lines[-1][:-1] + b"\r\n"
    else:
        lines[-1] = lines[-1][:-1]
    altered = b"".join(lines)
    # None of these changes affects the inventory. The saved pin catches them.
    assert not compare_reports(reviewed_baseline,
                               select(io.BytesIO(altered), max_rows=3).report)["changed"]
    source = artifact_dir / "altered.jsonl"
    source.write_bytes(altered)
    completed, outputs = run_cli(source, artifact_dir, reviewed_pins)
    assert completed.returncode == 2, completed.stderr.decode("utf-8")
    assert json.loads(completed.stderr)["error"]["code"] == "pin_mismatch"
    assert not any(path.exists() for path in outputs.values())


def test_missing_pinned_row_fails_before_outputs(artifact_dir, reviewed_pins):
    source = artifact_dir / "missing.jsonl"
    source.write_bytes(b"".join(CURRENT.read_bytes().splitlines(keepends=True)[:-1]))
    completed, outputs = run_cli(source, artifact_dir, reviewed_pins)
    assert completed.returncode == 2, completed.stderr.decode("utf-8")
    assert json.loads(completed.stderr)["error"]["code"] == "pin_not_found"
    assert not any(path.exists() for path in outputs.values())


@pytest.mark.parametrize("budget", ["rows", "bytes"])
def test_pins_respect_budgets_before_outputs(budget, artifact_dir, reviewed_pins):
    completed, outputs = run_cli(
        CURRENT, artifact_dir, reviewed_pins,
        max_rows=0 if budget == "rows" else 3,
        extra=("--max-output-bytes", "10") if budget == "bytes" else (),
    )
    assert completed.returncode == 2, completed.stderr.decode("utf-8")
    assert json.loads(completed.stderr)["error"]["code"] == "pin_budget"
    assert not any(path.exists() for path in outputs.values())
