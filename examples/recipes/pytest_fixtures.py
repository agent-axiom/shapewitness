"""Run: python -m pytest -q examples/recipes/pytest_fixtures.py"""
import json
from pathlib import Path

import pytest

from shapewitness import select


@pytest.fixture(scope="session")
def event_fixture(tmp_path_factory):
    """Keep the exact rows and their explanation together for test debugging."""
    with (Path(__file__).parents[1] / "events.jsonl").open("rb") as source:
        result = select(source, max_rows=4)
    assert result.report["coverage"]["complete"], "Increase the fixture row budget"
    directory = tmp_path_factory.mktemp("event-witnesses")
    with (directory / "events.jsonl").open("xb") as target:
        result.write_jsonl(target)
    (directory / "coverage.json").write_text(json.dumps(result.report), encoding="utf-8")
    return result


def user_email(event):
    """Example application behavior; missing and null users have no email."""
    user = event.get("user")
    return user.get("email") if isinstance(user, dict) else None


def test_importer_handles_observed_user_shapes(event_fixture):
    expected = {1: "ada@example.test", 3: None, 4: None, 5: None}
    for witness in event_fixture.rows:
        event = json.loads(witness.raw)
        assert user_email(event) == expected[event["id"]], f"source line {witness.line}"
