"""Strict parsing, bounded scratch storage, and deterministic greedy coverage.

No network, telemetry, value synthesis, numeric conversion, or random sampling.
The input stream is consumed once; a private SQLite spool supports later passes.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from dataclasses import asdict, dataclass
from typing import Any, BinaryIO, Iterator

# A path segment is a member name, or None for any array element. Unlike dotted
# paths, this distinguishes a literal key "*" from an array wildcard.
Path = tuple[str | None, ...]
Feature = tuple[Path, str]
_NUMBER = object()


class ShapeWitnessError(ValueError):
    """Expected invalid-input, resource-limit, or I/O error (no row values)."""

    def __init__(self, code: str, message: str, line: int | None = None):
        super().__init__(message)
        self.code = code
        self.line = line

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "line": self.line}


@dataclass(frozen=True)
class Limits:
    """Hard input/model bounds; SQLite cache is a target, not a process RSS cap."""

    max_line_bytes: int = 1_048_576
    max_input_bytes: int = 268_435_456
    max_records: int = 100_000
    max_depth: int = 64
    max_nodes_per_record: int = 100_000
    max_features: int = 10_000
    max_path_bytes: int = 4096
    max_associations: int = 2_000_000
    max_spool_bytes: int = 536_870_912
    max_output_bytes: int = 16_777_216

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if type(value) is not int or not 1 <= value < sys.maxsize:
                raise ShapeWitnessError("configuration", f"{name} must be a positive integer smaller than sys.maxsize")
        if self.max_depth > 256:
            raise ShapeWitnessError("configuration", "max_depth cannot exceed 256")
        if self.max_spool_bytes < 65_536:
            raise ShapeWitnessError("configuration", "max_spool_bytes must be at least 65536")


@dataclass(frozen=True)
class Witness:
    """An unchanged physical input line and its location in the byte stream."""

    line: int
    offset: int
    raw: bytes
    sha256: str
    selection_rank: int
    new_feature_ids: tuple[int, ...]
    feature_ids: tuple[int, ...]


@dataclass(frozen=True)
class Result:
    """Selected rows in input order, plus a reproducible JSON-serializable report."""

    rows: tuple[Witness, ...]
    report: dict[str, Any]

    def write_jsonl(self, stream: BinaryIO) -> None:
        """Write original bytes, preserving whitespace and line endings."""
        for row in self.rows:
            stream.write(row.raw)


def _fail_limit(name: str, line: int | None = None) -> None:
    raise ShapeWitnessError("limit", f"{name} exceeded; increase the explicit limit or reduce the input", line)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ShapeWitnessError("duplicate_key", "duplicate object member")
        result[key] = value
    return result


def _nonfinite(_: str) -> Any:
    raise ShapeWitnessError("invalid_json", "non-finite numbers are not JSON")


def _check_string(value: str) -> None:
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ShapeWitnessError("invalid_unicode", "unpaired Unicode surrogate is not supported")


def _parse(raw: bytes, limits: Limits, line: int) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
        if text.startswith("\ufeff"):
            raise ShapeWitnessError("invalid_utf8", "UTF-8 BOM is not accepted")
        # Bound nesting before asking the recursive stdlib parser to allocate.
        depth = 0
        quoted = False
        escaped = False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > limits.max_depth:
                    _fail_limit("max_depth")
            elif char in "]}":
                depth -= 1
        # All JSON numeric lexemes map to a private type marker. We never round
        # a float, overflow an exponent, or convert arbitrarily large integers.
        return json.loads(text, parse_int=lambda _: _NUMBER,
                          parse_float=lambda _: _NUMBER,
                          parse_constant=_nonfinite,
                          object_pairs_hook=_unique_object)
    except UnicodeDecodeError:
        raise ShapeWitnessError("invalid_utf8", "input is not strict UTF-8", line) from None
    except json.JSONDecodeError as exc:
        raise ShapeWitnessError("invalid_json", f"invalid JSON at column {exc.colno}", line) from None
    except RecursionError:
        raise ShapeWitnessError("limit", "JSON parser nesting limit exceeded", line) from None
    except ShapeWitnessError as exc:
        exc.line = line
        raise


def _path_json(path: Path) -> str:
    return json.dumps(path, ensure_ascii=True, separators=(",", ":"))


def _walk(value: Any, limits: Limits, line: int) -> Iterator[tuple[Path, Any]]:
    stack = [((), value)]
    nodes = 0
    while stack:
        path, node = stack.pop()
        nodes += 1
        if nodes > limits.max_nodes_per_record:
            _fail_limit("max_nodes_per_record", line)
        if len(_path_json(path)) > limits.max_path_bytes:
            _fail_limit("max_path_bytes", line)
        if isinstance(node, str):
            try:
                _check_string(node)
            except ShapeWitnessError as exc:
                exc.line = line
                raise
        yield path, node
        if isinstance(node, dict):
            for key, child in node.items():
                try:
                    _check_string(key)
                except ShapeWitnessError as exc:
                    exc.line = line
                    raise
                stack.append((path + (key,), child))
        elif isinstance(node, list):
            stack.extend((path + (None,), child) for child in node)


def _kind(value: Any) -> str:
    if value is _NUMBER:
        return "number"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


def _features(value: Any, union: dict[Path, set[str]], limits: Limits, line: int) -> set[Feature]:
    features: set[Feature] = set()
    for path, node in _walk(value, limits, line):
        kind = _kind(node)
        features.add((path, kind))
        if kind in ("object", "array") and not node:
            features.add((path, "empty-" + kind))
        if isinstance(node, dict):
            for key in union.get(path, set()) - node.keys():
                features.add((path + (key,), "missing"))
        if len(features) > limits.max_features:
            _fail_limit("max_features", line)
    return features


def _connect(path: str, limits: Limits) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    try:
        os.chmod(path, 0o600)
        db.execute("PRAGMA page_size=4096")
        db.execute(f"PRAGMA max_page_count={limits.max_spool_bytes // 4096}")
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("PRAGMA cache_size=-8192")
        db.execute("PRAGMA temp_store=FILE")
        db.executescript("""
            CREATE TABLE records (line INTEGER PRIMARY KEY, offset INTEGER NOT NULL,
                raw BLOB NOT NULL, gain INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE features (id INTEGER PRIMARY KEY, path TEXT NOT NULL,
                kind TEXT NOT NULL, covered INTEGER NOT NULL DEFAULT 0,
                UNIQUE(path, kind));
            CREATE TABLE edges (line INTEGER NOT NULL, feature INTEGER NOT NULL,
                PRIMARY KEY(line, feature)) WITHOUT ROWID;
            CREATE INDEX feature_lines ON edges(feature, line);
        """)
    except BaseException:
        db.close()
        raise
    return db


def select(source: BinaryIO, *, max_rows: int = 20, limits: Limits | None = None,
           skip_blank_lines: bool = False, temp_dir: str | None = None) -> Result:
    """Read JSONL and greedily cover its observed features with at most max_rows.

    Each round picks the row with the most currently uncovered features; ties
    prefer the earliest physical line. Arrays use one wildcard path. Missing
    means an observed member is absent from an existing object at that path.
    An absent/non-object ancestor is not a missing descendant. No optimization
    or representativeness guarantee is made. Input order affects tie-breaking.

    The complete input is validated before any Result is returned. Temporary
    storage is private and removed on success or exceptions. Binary input only.
    """
    limits = limits or Limits()
    limits.validate()
    if type(max_rows) is not int or max_rows < 0 or max_rows > limits.max_records:
        raise ShapeWitnessError("configuration", "max_rows must be between 0 and max_records")
    try:
        with tempfile.TemporaryDirectory(prefix="shapewitness-", dir=temp_dir) as work:
            db = _connect(os.path.join(work, "spool.sqlite3"), limits)
            try:
                return _select(db, source, max_rows, limits, skip_blank_lines)
            finally:
                db.close()
    except sqlite3.DatabaseError as exc:
        if (getattr(exc, "sqlite_errorcode", None) == getattr(sqlite3, "SQLITE_FULL", 13)
                or "database or disk is full" in str(exc)):
            raise ShapeWitnessError("limit", "temporary database is full (max_spool_bytes or available disk space)") from None
        raise ShapeWitnessError("storage", "temporary SQLite storage failed") from None
    except OSError as exc:
        raise ShapeWitnessError("io", f"I/O failure ({type(exc).__name__})") from None


def _select(db: sqlite3.Connection, source: BinaryIO, max_rows: int, limits: Limits,
            skip_blank_lines: bool) -> Result:
    union: dict[Path, set[str]] = {}
    observed: set[Feature] = set()
    total_bytes = total_lines = records = skipped = 0
    input_hash = hashlib.sha256()
    while True:
        raw = source.readline(limits.max_line_bytes + 1)
        if not isinstance(raw, bytes):
            raise ShapeWitnessError("configuration", "source must be a binary stream")
        if not raw:
            break
        total_lines += 1
        if len(raw) > limits.max_line_bytes:
            _fail_limit("max_line_bytes", total_lines)
        offset = total_bytes
        total_bytes += len(raw)
        if total_bytes > limits.max_input_bytes:
            _fail_limit("max_input_bytes", total_lines)
        input_hash.update(raw)
        if not raw.strip(b" \t\r\n"):
            if not skip_blank_lines:
                raise ShapeWitnessError("blank_line", "blank line; use skip_blank_lines to explicitly ignore it", total_lines)
            skipped += 1
            continue
        records += 1
        if records > limits.max_records:
            _fail_limit("max_records", total_lines)
        value = _parse(raw, limits, total_lines)
        for path, node in _walk(value, limits, total_lines):
            observed.add((path, _kind(node)))
            if len(observed) > limits.max_features:
                _fail_limit("max_features", total_lines)
            if isinstance(node, dict):
                union.setdefault(path, set()).update(node.keys())
        db.execute("INSERT INTO records(line,offset,raw) VALUES (?, ?, ?)", (total_lines, offset, raw))
    db.commit()

    # First pass collected the complete observed vocabulary. Second pass adds
    # local missing-member evidence, including keys discovered on later lines.
    feature_ids: dict[Feature, int] = {}
    associations = 0
    for line, raw in db.execute("SELECT line, raw FROM records ORDER BY line"):
        row_features = _features(_parse(raw, limits, line), union, limits, line)
        for feature in sorted(row_features, key=lambda f: (_path_json(f[0]), f[1])):
            if feature not in feature_ids:
                if len(feature_ids) >= limits.max_features:
                    _fail_limit("max_features", line)
                fid = len(feature_ids) + 1
                feature_ids[feature] = fid
                db.execute("INSERT INTO features(id,path,kind) VALUES(?,?,?)",
                           (fid, _path_json(feature[0]), feature[1]))
            associations += 1
            if associations > limits.max_associations:
                _fail_limit("max_associations", line)
            db.execute("INSERT INTO edges VALUES (?, ?)", (line, feature_ids[feature]))
    db.commit()
    # Release the vocabulary before selection; no per-record Python feature
    # matrix is retained. SQLite owns the O(records + associations) disk index.
    del union, observed
    db.execute("UPDATE records SET gain=(SELECT COUNT(*) FROM edges WHERE edges.line=records.line)")
    db.execute("CREATE INDEX candidate_gain ON records(gain DESC, line ASC)")
    selected: list[Witness] = []
    output_bytes = 0
    while len(selected) < max_rows:
        choice = db.execute("SELECT line,length(raw) FROM records WHERE gain>0 ORDER BY gain DESC,line ASC LIMIT 1").fetchone()
        if choice is None:
            break
        candidate, size = choice
        if output_bytes + size > limits.max_output_bytes:
            # Available bytes only decrease; this row will never become feasible.
            db.execute("UPDATE records SET gain=-1 WHERE line=?", (candidate,))
            continue
        line = candidate
        offset, raw = db.execute("SELECT offset,raw FROM records WHERE line=?", (line,)).fetchone()
        all_ids = tuple(r[0] for r in db.execute("SELECT feature FROM edges WHERE line=? ORDER BY feature", (line,)))
        new_ids = tuple(r[0] for r in db.execute("""
            SELECT e.feature FROM edges e JOIN features f ON f.id=e.feature
            WHERE e.line=? AND f.covered=0 ORDER BY e.feature
        """, (line,)))
        for fid in new_ids:
            db.execute("UPDATE records SET gain=gain-1 WHERE line IN (SELECT line FROM edges WHERE feature=?)", (fid,))
        db.execute("UPDATE features SET covered=1 WHERE id IN (SELECT feature FROM edges WHERE line=?)", (line,))
        selected.append(Witness(line, offset, raw, hashlib.sha256(raw).hexdigest(),
                                len(selected) + 1, new_ids, all_ids))
        output_bytes += len(raw)
    selected.sort(key=lambda r: r.line)
    features = [{"id": fid, "path": json.loads(path), "kind": kind, "covered": bool(covered)}
                for fid, path, kind, covered in db.execute("SELECT id,path,kind,covered FROM features ORDER BY id")]
    uncovered = [f["id"] for f in features if not f["covered"]]
    covered = len(features) - len(uncovered)
    stop_reason = ("complete" if not uncovered else "row_budget" if len(selected) >= max_rows
                   else "output_byte_budget")
    report = {
        "format_version": 1,
        "tool_version": "0.1.0",
        "algorithm": "greedy-new-features-first-line-tiebreak-v1",
        "input": {"sha256": input_hash.hexdigest(), "bytes": total_bytes,
                  "physical_lines": total_lines, "records": records, "skipped_blank_lines": skipped},
        "options": {"max_rows": max_rows, "skip_blank_lines": skip_blank_lines, "limits": asdict(limits)},
        "coverage": {"observed_features": len(features), "covered_features": covered,
                     "complete": not uncovered,
                     "fraction": covered / len(features) if features else 1.0,
                     "uncovered_feature_ids": uncovered},
        "selection": {"rows": len(selected), "bytes": output_bytes, "stop_reason": stop_reason},
        "rows": [{"line": r.line, "byte_offset": r.offset, "byte_length": len(r.raw),
                  "sha256": r.sha256, "selection_rank": r.selection_rank,
                  "new_feature_ids": list(r.new_feature_ids), "feature_ids": list(r.feature_ids)} for r in selected],
        "features": features,
    }
    return Result(tuple(selected), report)
