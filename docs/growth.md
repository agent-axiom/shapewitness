# Growth plan: three independent trials, one CI adoption

[Home](../README.md) · [Recipes](recipes/README.md) · [Release checklist](release/README.md)

**Goal:** within 30 days of a verified release containing structural comparison,
aim for three external developers to run a useful fixture experiment and one to
keep it in CI. These are targets, not commitments or evidence of existing adoption.
This document plans promotion; it does not authorize outreach or public posts.

Lead with one task: **turn a JSONL export into a small, byte-preserved fixture, then
review changes in its observed structural features.** Keep domain assertions beside
the fixture. Do not market this as contract validation, representative sampling,
optimal selection, or proof of importer runtime equivalence.

## 1. Make the first case reproducible

Use the committed [synthetic orders](../examples/integrations/orders.jsonl), not a
customer export. From an isolated environment and reviewed checkout, record the
commit, Python version, options, input hashes, reports, and selected bytes. Install
with `python -m pip install --no-deps .`, then run:

```sh
work=$(mktemp -d)
cp examples/integrations/orders.jsonl "$work/baseline.jsonl"
python - "$work" <<'PY'
import json
import sys
from pathlib import Path

work = Path(sys.argv[1])
raw = (work / "baseline.jsonl").read_bytes()
row = json.loads(raw.splitlines()[0])
row.update(id=11, discount_code="FALL")
(work / "current.jsonl").write_bytes(
    raw + (json.dumps(row, separators=(",", ":")) + "\n").encode()
)
PY
for name in baseline current; do
  shapewitness "$work/$name.jsonl" -n 6 --require-complete \
    --output "$work/$name-fixture.jsonl" --report "$work/$name-report.json"
done
```

Expected default-mode results: baseline covers **28/28** features using source
lines **1, 3, 4, 5, 6, 7**; current covers **30/30** using **3, 4, 5, 6, 7, 11**.
The added path/kind pairs are `["discount_code"]` + `string` and
`["discount_code"]` + `missing`; none disappear. Existing rows lack a newly observed
member, which explains the second addition. Feature IDs are report-local and must
not be compared across reports.

In a reviewed source checkout with comparison support, verify the exact delta:

```sh
shapewitness "$work/current.jsonl" -n 0 --baseline "$work/baseline-report.json" \
  --comparison-report "$work/delta.json" --require-unchanged --status json
# Expected exit 4: an observed structural change, not a processing failure.
python - "$work/delta.json" <<'PYCASE'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text())
assert result["added_features"] == [
    {"path": ["discount_code"], "kind": "missing"},
    {"path": ["discount_code"], "kind": "string"},
]
assert result["removed_features"] == []
PYCASE
```

With `set -e`, explicitly handle the expected exit 4 before running the assertion.
A changed report should prompt review, not automatic baseline
acceptance. Use the [real-importer recipe](recipes/real-importers.md) as an optional
second exercise, including its counterexamples. Its assertions cover only the
documented cases; keep application-specific expected outputs and failure checks.

For an external-data example, use the [public countries case](recipes/public-countries.md).
It records actual reduction, importer assertions, selection overhead, and a first-N
baseline. Its modest reduction and early failure are useful limits: this is our
reproducible experiment, not one of the independent trials or external CI adoptions.

## 2. Release in two evidence-gated steps

1. **Structural comparison first.** Compare baseline/current inventories by path
   plus kind. Test added/removed features, reordered report-local IDs, incompatible
   feature models, and malformed reports. Document the actual CLI, report format,
   exit behavior, and CI review policy. Pass exact-commit CI and clean-install
   checks before advertising availability; a source-only feature must be labeled.
2. **SHA-checked pinned rows next.** Let users retain explicit value-sensitive
   cases alongside greedy coverage after the comparison step is stable. Require
   tests for digest mismatch, changed input, budget handling, deterministic output,
   and provenance. Demonstrate a deliberately retained boundary or multi-row case
   with a separate downstream assertion. A pin preserves specified bytes; it does
   not discover all necessary cases. Promote it only after its own verified release.

Do not delay comparison trials for pins, and do not promise unshipped pin behavior.

## 3. Recruit the first three external users

Proposed targets below are hypotheses about fit, not endorsements or existing users.
Before contact, identify a specific person and public workflow demonstrating the
need, verify the appropriate channel, and obtain approval for that outreach.

1. **One sqlite-utils JSONL importer maintainer or user.** Start with a
   [newline-delimited import](https://sqlite-utils.datasette.io/en/stable/cli.html#inserting-newline-delimited-json)
   that encounters late columns or mixed types. Ask them to run the orders case,
   then adapt one synthetic example of their own. Success: an independently run
   fixture with an explicit import assertion and one useful finding or blocker.
2. **One dlt pipeline author using DuckDB.** The
   [documented destination](https://dlthub.com/docs/dlt-ecosystem/destinations/duckdb)
   and existing recipe provide a local starting point. Ask them to check one nested
   normalization case with their own expected outputs. Success: they can explain
   what the fixture preserves and identify any additional value-sensitive tests.
3. **One JSONLKit maintainer or contributor.** Its documented
   [JSONL transformations](https://github.com/tinytoolkit-org/jsonlkit-cli)
   make fixture review a plausible complementary use. Ask whether a small synthetic
   conversion fixture improves a regression test. Success: one reproducible trial
   and candid feedback, even if the tool is not a fit. Do not imply compatibility
   has been tested or replace their validators with structural coverage.

Use one tailored invitation per approved target, linking the case and its limits.
Ask for results or blockers, not stars. Request no private exports; input rows and
report property names can be sensitive. No unsolicited follow-up sequence.

## 4. Convert one useful trial into maintained CI

Choose a willing pilot user's repository. Propose a reviewed change that pins the
release, keeps synthetic input and expected outputs, checks complete fixture
coverage, reviews baseline/current structural changes, and runs the user's actual
parser or transformation assertions. Keep known value, order, and cross-row tests.
Demonstrate both a passing run and a deliberate structural-change failure.

Count adoption only after the owner merges the check and it runs successfully on
their default branch. ShapeWitness's own CI and a demo fork do not count. Record
the external commit/run link and recheck after their next relevant change; do not
claim continued use without evidence.

Track three completed independent trials, their setup time and blockers, retained
rows/bytes under stated options, and the one merged CI check. After three trials or
the initial 30-day window, prioritize the most repeated friction before broader
promotion. With permission, publish one reproducible case report including failures
and limits. If no one retains the workflow, revisit the use case before expanding
outreach. Downloads and stars are secondary signals, not proof of usefulness.
