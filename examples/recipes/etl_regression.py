"""Run: python examples/recipes/etl_regression.py. No extra dependencies."""
import json
from pathlib import Path

from shapewitness import select


ROOT = Path(__file__).parents[1]


def transform(event):
    """A deliberately small ETL contract with explicit missing/null behavior."""
    if "user" not in event:
        user_state = "missing"
    elif event["user"] is None:
        user_state = "null"
    else:
        user_state = "present" if event["user"] else "empty"
    if "total" not in event:
        total_state = "missing"
    elif event["total"] is None:
        total_state = "null"
    elif isinstance(event["total"], (int, float)) and not isinstance(event["total"], bool):
        total_state = "number"
    else:
        total_state = "text"
    return {"id": event["id"], "user_state": user_state,
            "total_state": total_state, "tag_count": len(event["tags"])}


def main():
    with (ROOT / "events.jsonl").open("rb") as source:
        result = select(source, max_rows=4)
    if not result.report["coverage"]["complete"]:
        raise SystemExit("Fixture budget no longer covers the input; review the new shapes")
    actual = [transform(json.loads(row.raw)) for row in result.rows]
    expected = json.loads((ROOT / "recipes" / "etl_expected.json").read_text())
    if actual != expected:
        raise SystemExit("ETL result differs from the reviewed golden output")
    print(f"ETL regression: {len(actual)} reviewed outputs match; source lines "
          + ", ".join(str(row.line) for row in result.rows))


if __name__ == "__main__":
    main()
