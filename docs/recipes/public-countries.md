# Public countries dataset through sqlite-utils

[Recipes](README.md) · [Runnable script](../../examples/recipes/countries_importer.py) ·
[Recorded run](../../benchmarks/countries-importer.json)

This opt-in case uses the real **mledoze/countries** dataset and **sqlite-utils
4.2.1**, rather than invented orders. It reproduces a configuration failure:
flattened native-language columns appear after the first insert batch. Without
`--alter`, the importer fails; with it, the imports succeed. This is documented
importer behavior, **not a claim of a newly discovered or historical upstream bug**.
No maintainer or independent user ran this trial, and no external CI adoption is
claimed.

## Reproduce from a reviewed checkout

Use Python 3.10 or newer and a fresh virtual environment. The measured run used
Python 3.12.14, SQLite 3.53.1, ShapeWitness 0.1.3, and Linux x86-64. ShapeWitness
source files matched main commit `391474f666c51c0fd7c24f3c9d7d7dea8c001590`; the
new recipe is supplied by this checkout. Dependencies remain optional.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --no-deps .
python -m pip install sqlite-utils==4.2.1
mkdir -p .recipe-output
curl --fail --location \
  https://raw.githubusercontent.com/mledoze/countries/c2ac0049c14edcf2436c7aa1b2493222a020b462/countries.json \
  --output .recipe-output/countries-source.json
python examples/recipes/countries_importer.py \
  --source .recipe-output/countries-source.json \
  --output .recipe-output/countries-case --repeats 5
```

Use a new output directory each run. The script has no network access and rejects
any source other than the exact pinned bytes before selection or import. On
Windows, activate the virtual environment using its Scripts directory and download
the same URL with a browser or your usual download tool.

Source SHA-256:
`913e5d716f9dc6b59881ee23488d47f5fda52070d1a34cac5fa327c9e61d8f7c`.
The upstream JSON array is **1,398,155 bytes**. The recipe first converts each array
entry, in existing order, to compact UTF-8 JSON plus LF using Python's
`json.dumps(..., ensure_ascii=False, separators=(",", ":"))`. It does not add
invented records or edit factual values. This conversion is explicit: the
byte-preservation guarantee applies to the resulting JSONL, **not** to the original
pretty-printed JSON array or its numeric token spellings.

Outputs are `full.jsonl`, `selected.jsonl`, `coverage.json`, `summary.json`, and
`NOTICE.txt`. Coverage includes source line numbers, byte offsets and row hashes;
summary includes source/input/fixture digests, versions, options, all timing
samples and assertions. The full dataset and derived fixture are not committed.
Core CI runs offline synthetic tests for the recipe's validation helpers. The
public-data experiment is the separate, opt-in command above, not a claimed CI
run on every commit.

## Observed result

The recorded five-repetition run on 2026-10-10 retained:

| Measurement | Full JSONL | Selected JSONL |
| --- | ---: | ---: |
| Records | 250 | 176 |
| Bytes | 631,420 | 438,177 |
| Covered full-input structural features | 1,683 / 1,683 | 1,683 / 1,683 |
| Flattened SQLite columns | 855 | 855 |
| Successful import median, seconds | 0.772 | 0.700 |
| Expected failing import median, seconds | 0.120 | 0.124 |

That's **29.6% fewer rows and 30.6% fewer bytes**. The diverse language and currency
keys require many witnesses, so this is a modest reduction. The default `json`
number mode, no pins, and a 250-row budget were used. No weaker feature model or
hand-picked subset was substituted to improve the result.

The first **176** source rows cover **1,411 / 1,683** full-input features, scored against the full input's member vocabulary by an
independent oracle. They also
reproduce the same early importer failure. ShapeWitness retains more structural
variation at this budget, but **this failure alone does not establish an advantage
over first-N**, nor does structural coverage prove general importer equivalence.

### What the importer assertions establish

Both full and selected data invoke the actual CLI with:

```sh
python -m sqlite_utils insert countries.db countries input.jsonl \
  --nl --flatten --pk cca3 --batch-size 1 --alter
```

The script uses a fresh temporary database for every import and streams the bytes
through standard input. It checks all 855 column definitions by name (excluding
column ordinal position), all retained rows' values, and all retained SQLite
storage classes. Independent expectations check 250/176 imported rows, the column
count, and Afghanistan's late `name_native_prs_official` value. Its unique `cca3`
code identifies retained records. These are dataset-specific assertions.

Removing `--alter` must yield exit 1 and:

```text
Error: table countries has no column named name_native_prs_official
```

That column first appears with Afghanistan, after Aruba. Both datasets keep this
ordering. The actual failure predicate is checked; a nonzero exit for any other
reason is insufficient. Selecting witnesses preserves original record order, but
changing the upstream order, changing batch size, or removing `--flatten` can
change the failure and inferred schema. This case tests **one explicit importer
configuration**. It does not claim order-independent or batch-independent results.

### Runtime costs and limits

Selection plus exact-byte provenance checks took **1.075 seconds median**,
separately from import. Thus generating a fixture for a single successful import
cost about **1.775 seconds** for those two phases versus **0.772 seconds** for the
full import, before conversion and other checks. It is slower for that one-off use.
The full end-to-end recipe is much slower because it deliberately repeats imports,
queries snapshots and verifies failures.

The first observed selection took 1.111 seconds; first successful full/selected
imports took 0.762/0.700 seconds. Subsequent four-run medians were 1.074 seconds for
selection and 0.788/0.708 seconds for full/selected imports. These are first-observed
and repeated-process observations, not a guaranteed cold-cache/warm-cache split.
Every CLI process and database is new; OS caches are not cleared. Full/selected
order alternates per repetition. No warmup is discarded. Time excludes downloads,
JSON-array conversion, snapshot queries, and temporary-directory setup/cleanup.

Reusing a committed fixture avoids reselection, but the small observed import-time
difference on this single small dataset is not a speed guarantee or a reliable
break-even estimate. The failing import exits on the second row, so reducing later
rows brings essentially no useful failure-runtime saving. The potential benefit
here is a smaller reviewable regression fixture with measured shape coverage, not
faster one-shot import or proof of semantic equivalence. Keep value-sensitive,
cross-row and importer-specific assertions separately.

## Source and licensing

Contains information from
[mledoze/countries at the pinned commit](https://github.com/mledoze/countries/tree/c2ac0049c14edcf2436c7aa1b2493222a020b462),
made available under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
See the [upstream license](https://github.com/mledoze/countries/blob/c2ac0049c14edcf2436c7aa1b2493222a020b462/LICENSE).
The generated full and selected databases carry that license, not this repository's
MIT code license. Keep the generated `NOTICE.txt` with any shared output, and retain
the source and public transformation method. The source includes countries and
territories; inclusion does not assert that every entry is an independent state.

Importer reference:
[sqlite-utils newline-delimited JSON and changing columns](https://sqlite-utils.datasette.io/en/stable/cli.html#inserting-newline-delimited-json).
