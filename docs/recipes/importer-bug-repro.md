# An exact importer bug repro

[Recipes](README.md) · [Source](../../examples/recipes/importer_bug_repro.py)

## Pain

An importer assumes every user has an email. A large export fails, but attaching the
entire export to an issue is inconvenient and can leak private information.

## Run

```sh
python examples/recipes/importer_bug_repro.py > repro.jsonl
# stderr: Reproduced KeyError at original line 3; sha256=...
```

The script first selects structural witnesses, then runs the deliberately faulty
importer on each selected row. It emits the first row that actually reproduces the
failure, unchanged, with its original line and digest on stderr. The example uses
synthetic data that is safe to inspect in the repository.

## Adapt

Replace `broken_importer` and its expected exception with the precise failure
predicate. Confirm the smaller input still fails in a fresh environment. A generic
exception is not evidence of the same bug; record the relevant assertion or error.
If no selected row reproduces it, search the original data using that predicate.

ShapeWitness is a structural selector, not a generic failure minimizer. A bug based
on a particular value, ordering, or multiple records can be lost. Review and redact
any real row before sharing it, then rerun the failure check: redaction changes bytes
and the original digest will no longer match.
