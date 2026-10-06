"""Reproducible synthetic structural-coverage comparison, not a speed claim.

Run: python scripts/compare_sampling.py --output benchmarks/synthetic.json
Selection is timed on an already-loaded byte corpus. Coverage evaluation is an
independent oracle outside timings. Head and reservoir do not validate or report.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import random
import statistics
import sys
import time
from pathlib import Path

from shapewitness import select

ROOT = Path(__file__).resolve().parents[1]


def corpus():
    rows = [{"id": i, "user": {"name": "Synthetic", "email": "user@example.test"},
             "tags": ["ordinary"], "total": 10} for i in range(990)]
    rows += [
        {"id": 990, "user": None, "tags": [], "total": None},
        {"id": 991, "tags": [1, True, None]},
        {"id": 992, "user": {}, "tags": [{"label": "synthetic"}, {}], "total": "unknown"},
        {"id": 993, "user": {"name": "Synthetic"}, "tags": [], "total": 0},
        {"id": 994, "user": [], "tags": {}, "total": False},
        {"id": 995, "user": {"email": None}, "tags": [[], [1]], "total": {}},
        {"id": 996, "user": "unknown", "tags": None, "total": []},
        {}, None, [1, "synthetic", None],
    ]
    return b"".join(json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows)


def walk(value, path=()):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, path + (key,))
    elif isinstance(value, list):
        for child in value:
            yield from walk(child, path + (None,))


def oracle(raw_lines):
    values = [json.loads(line) for line in raw_lines]
    union = {}
    for value in values:
        for path, node in walk(value):
            if isinstance(node, dict):
                union.setdefault(path, set()).update(node)
    row_features = []
    kinds = {type(None): "null", bool: "boolean", int: "number", float: "number",
             str: "string", list: "array", dict: "object"}
    for value in values:
        features = set()
        for path, node in walk(value):
            kind = kinds[type(node)]
            features.add((path, kind))
            if isinstance(node, (dict, list)) and not node:
                features.add((path, "empty-" + kind))
            if isinstance(node, dict):
                features.update((path + (key,), "missing") for key in union[path] - node.keys())
        row_features.append(features)
    return row_features


def head(data, count):
    stream = io.BytesIO(data)
    selected = []
    for index in range(count):
        if not stream.readline():
            break
        selected.append(index)
    return selected


def reservoir(data, count, seed):
    rng = random.Random(seed)
    selected = []
    for index, _ in enumerate(io.BytesIO(data)):
        if index < count:
            selected.append(index)
        else:
            replacement = rng.randrange(index + 1)
            if replacement < count:
                selected[replacement] = index
    return sorted(selected)


def timed(call, repeats):
    times = []
    result = None
    for _ in range(repeats):
        start = time.perf_counter()
        result = call()
        times.append(time.perf_counter() - start)
    return result, {"median_seconds": statistics.median(times), "min_seconds": min(times),
                    "max_seconds": max(times), "repeats": repeats}


def compare(data, budget=8, seeds=20, repeats=5):
    raw_lines = data.splitlines(keepends=True)
    features = oracle(raw_lines)
    universe = set().union(*features)
    def coverage(indices):
        return len(set().union(*(features[i] for i in indices)))
    first, head_time = timed(lambda: head(data, budget), repeats)
    witness, witness_time = timed(lambda: select(io.BytesIO(data), max_rows=budget), repeats)
    selected = [row.line - 1 for row in witness.rows]
    assert witness.report['coverage']['covered_features'] == coverage(selected)
    random_runs = []
    for seed in range(seeds):
        indices, timing = timed(lambda: reservoir(data, budget, seed), repeats)
        random_runs.append({"seed": seed, "selected_lines": [i + 1 for i in indices],
                            "covered_features": coverage(indices), **timing})
    return {
        "format_version": 1,
        "environment": {"python": platform.python_version(), "platform": platform.system(),
                        "machine": platform.machine(), "timer": "perf_counter"},
        "dataset": {"generator": "scripts/compare_sampling.py:corpus", "synthetic": True,
                    "records": len(raw_lines), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                    "description": "990 same-shape ordinary rows followed by 10 deliberately varied edge-case rows"},
        "budget": budget, "observed_features": len(universe),
        "head": {"selected_rows": len(first), "selected_lines": [i + 1 for i in first],
                 "covered_features": coverage(first), **head_time},
        "shapewitness": {"selected_rows": len(selected), "selected_lines": [i + 1 for i in selected],
                         "covered_features": coverage(selected), **witness_time},
        "reservoir": {"seeds": seeds, "coverage_min": min(r['covered_features'] for r in random_runs),
                      "coverage_median": statistics.median(r['covered_features'] for r in random_runs),
                      "coverage_max": max(r['covered_features'] for r in random_runs),
                      "median_seconds": statistics.median(r['median_seconds'] for r in random_runs),
                      "runs": random_runs},
        "limitations": [
            "Synthetic tail-heavy structure intentionally demonstrates a case that favors structural selection.",
            "Timing includes selection on bytes already in memory; corpus generation and coverage evaluation are excluded.",
            "Head reads only the requested prefix; reservoir scans the corpus; neither validates or produces provenance.",
            "ShapeWitness validates, discovers missing-member vocabulary, spools, selects, and builds a report.",
            "This is not a statistical representativeness, fairness, throughput, or universal speed comparison.",
            "Random results are the disclosed fixed seeds, not a population confidence interval.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dataset-output', type=Path)
    parser.add_argument('--repeats', type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 100:
        parser.error('--repeats must be between 1 and 100')
    data = corpus()
    if args.dataset_output:
        args.dataset_output.write_bytes(data)
    rendered = json.dumps(compare(data, repeats=args.repeats), indent=2, sort_keys=True) + '\n'
    if args.output:
        args.output.write_text(rendered, encoding='utf-8')
    else:
        sys.stdout.write(rendered)


if __name__ == '__main__':
    main()
