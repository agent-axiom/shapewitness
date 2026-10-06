# A compact pytest fixture

[Recipes](README.md) · [Source](../../examples/recipes/pytest_fixtures.py)

## Pain

A checked-in export is large, while its first few rows miss the missing/null user
cases that break an importer. Keep a small, explainable fixture for a focused test.

## Run

```sh
python -m pip install . pytest
python -m pytest -q examples/recipes/pytest_fixtures.py
# 1 passed
```

The session-scoped fixture selects four real rows from `examples/events.jsonl`,
asserts complete observed structural coverage, and writes the unchanged JSONL and
report into pytest's temporary directory. The test checks application expectations
for each selected source row; failures identify the original line.

## Adapt

Replace the example export and `user_email` with your parser. Keep the coverage
assertion when your requirement is all observed shapes. If new data adds a shape,
review the budget and expected behavior rather than regenerating expected answers
blindly. Pin the fixture input and retain the report beside it when committing.

Structural diversity does not cover every business-value branch. Add explicit
value-boundary, enum, ordering, and relationship tests for your domain.
