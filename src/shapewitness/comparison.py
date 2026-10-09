"""Compare full observed inventories, never report-local feature IDs or values."""
from __future__ import annotations

import json
import re
import sys
from typing import Any, BinaryIO

from .core import Feature, ShapeWitnessError, _check_string, _path_json

_JSON_MODEL = "json-structure-v1"
_SYNTAX_MODEL = "json-structure-number-syntax-v1"
_COMMON_KINDS = {"object", "array", "string", "boolean", "null", "missing",
                 "empty-object", "empty-array"}
_MAX_REPORT_BYTES = 16_777_216


def _invalid() -> ShapeWitnessError:
    # Reports may contain private property names. Do not echo their contents.
    return ShapeWitnessError("invalid_report", "invalid observed-feature inventory report")


def _inventory(report: Any) -> tuple[str, str, set[Feature]]:
    if not isinstance(report, dict):
        raise _invalid()
    version = report.get("format_version")
    options = report.get("options")
    if type(version) is not int or not isinstance(options, dict):
        raise _invalid()
    if version == 1:
        model = _JSON_MODEL
        if (report.get("feature_model", model) != model
                or options.get("number_mode", "json") != "json"):
            raise ShapeWitnessError("incompatible_report", "report format and feature model are incompatible")
        kinds = _COMMON_KINDS | {"number"}
    elif version == 2:
        model = _SYNTAX_MODEL
        if report.get("feature_model") != model or options.get("number_mode") != "syntax":
            raise ShapeWitnessError("incompatible_report", "report format and feature model are incompatible")
        kinds = _COMMON_KINDS | {"integer", "float"}
    else:
        raise ShapeWitnessError("incompatible_report", "unsupported report format version")
    features, coverage, source = report.get("features"), report.get("coverage"), report.get("input")
    if not isinstance(features, list) or not isinstance(coverage, dict) or not isinstance(source, dict):
        raise _invalid()
    count = coverage.get("observed_features")
    digest = source.get("sha256")
    if (type(count) is not int or count != len(features)
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
        raise _invalid()
    inventory: set[Feature] = set()
    ids: set[int] = set()
    for entry in features:
        if not isinstance(entry, dict):
            raise _invalid()
        fid, path, kind = entry.get("id"), entry.get("path"), entry.get("kind")
        if (type(fid) is not int or fid < 1 or fid in ids
                or not isinstance(path, list)
                or any(segment is not None and not isinstance(segment, str) for segment in path)
                or not isinstance(kind, str) or kind not in kinds):
            raise _invalid()
        try:
            for segment in path:
                if segment is not None:
                    _check_string(segment)
        except ShapeWitnessError:
            raise _invalid() from None
        feature = (tuple(path), kind)
        if feature in inventory:
            raise _invalid()
        ids.add(fid)
        inventory.add(feature)
    return model, digest, inventory


def read_report(source: BinaryIO, *, max_bytes: int = _MAX_REPORT_BYTES) -> dict[str, Any]:
    """Read a bounded strict JSON inventory report; never echo private contents.

    Validates the inventory fields used by comparison, not row provenance or the
    authenticity of a stored report. The default bound is 16 MiB.
    """
    if type(max_bytes) is not int or not 1 <= max_bytes < sys.maxsize:
        raise ShapeWitnessError("configuration", "max_bytes must be a positive integer smaller than sys.maxsize")
    chunks = []
    size = 0
    while True:
        try:
            chunk = source.read(max_bytes + 1 - size)
        except OSError as exc:
            raise ShapeWitnessError("io", f"I/O failure ({type(exc).__name__})") from None
        if not isinstance(chunk, bytes):
            raise ShapeWitnessError("configuration", "report source must be a binary stream")
        size += len(chunk)
        if size > max_bytes:
            raise ShapeWitnessError("limit", "max_report_bytes exceeded")
        if not chunk:
            break
        chunks.append(chunk)
    raw = b"".join(chunks)

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise _invalid()
            value[key] = item
        return value

    def nonfinite(_: str) -> Any:
        raise _invalid()

    try:
        report = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)
    except (UnicodeError, ValueError, RecursionError):
        raise _invalid() from None
    _inventory(report)
    return report


def compare_reports(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic added/removed observed features by path and kind.

    The full inventories are compared even when selection coverage is partial or
    max_rows=0. Feature IDs, selected rows, values and frequencies are not compared.
    Each report's missing-member features use its own observed key vocabulary.
    Unsupported formats and different feature models fail closed. Equal inventories
    do not imply compatible schemas, equivalent importer behavior or unchanged data.
    """
    before_model, before_hash, before = _inventory(baseline)
    after_model, after_hash, after = _inventory(current)
    if before_model != after_model:
        raise ShapeWitnessError("incompatible_report", "baseline and current feature models differ")

    def ordered(features: set[Feature]) -> list[dict[str, Any]]:
        return [{"path": list(path), "kind": kind}
                for path, kind in sorted(features, key=lambda item: (_path_json(item[0]), item[1]))]

    added, removed = after - before, before - after
    return {
        "format_version": 1,
        "comparison_model": "observed-structure-diff-v1",
        "feature_model": before_model,
        "baseline": {"input_sha256": before_hash, "observed_features": len(before)},
        "current": {"input_sha256": after_hash, "observed_features": len(after)},
        "changed": bool(added or removed),
        "added_features": ordered(added),
        "removed_features": ordered(removed),
        "unchanged_features": len(before & after),
    }
