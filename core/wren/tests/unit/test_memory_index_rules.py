"""`wren memory index` must index rules beside the manifest, never inside it.

``mdl_hash`` is stamped on every schema row at index time and recomputed at
fetch time from ``target/mdl.json`` alone. Folding rule text into the manifest
(as ``manifest["rules"]``) made the two hashes differ for any project with
``knowledge/rules/*.md``, so every schema search came back empty.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from wren.cli import app
from wren.memory import cli as memory_cli

runner = CliRunner()

_MANIFEST = {"catalog": "test", "schema": "public", "models": []}


class _FakeStore:
    """Stands in for MemoryStore — no LanceDB, no embeddings."""

    def __init__(self) -> None:
        self.schema_calls: list[dict] = []
        self.rule_calls: list[list[str]] = []

    def index_schema(self, manifest: dict, *, seed_queries: bool = True) -> dict:
        self.schema_calls.append(manifest)
        return {"schema_items": 0, "seed_queries": 0}

    def index_rule(self, rules, *, replace: bool = True) -> dict:
        self.rule_calls.append(list(rules))
        return {"rule_items": len(rules)}


@pytest.fixture
def fake_store(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(memory_cli, "_get_store", lambda path: store)
    # The memory extra is not installed in the unit-test env; pretend the
    # semantic backend is available so `index` does not take the grep shortcut.
    monkeypatch.setattr("wren.memory.index_backend.resolve_backend", lambda: "lancedb")
    return store


def _write_project(tmp_path: Path, rules: list[str] | None = None) -> Path:
    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    (target / "mdl.json").write_text(json.dumps(_MANIFEST), encoding="utf-8")
    if rules is not None:
        rules_dir = tmp_path / "knowledge" / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        for i, text in enumerate(rules):
            (rules_dir / f"{i:02d}.md").write_text(text + "\n", encoding="utf-8")
    return tmp_path


def test_index_passes_rules_beside_the_manifest(tmp_path, fake_store, monkeypatch):
    project = _write_project(tmp_path, rules=["Amounts are USD."])
    monkeypatch.setattr("wren.context.discover_project_path", lambda: project)

    result = runner.invoke(app, ["memory", "index", "--no-seed", "--no-queries"])

    assert result.exit_code == 0, result.output
    assert fake_store.schema_calls == [_MANIFEST]
    assert "rules" not in fake_store.schema_calls[0]
    assert fake_store.rule_calls == [["Amounts are USD."]]
    assert "Indexed 1 rule item(s)." in result.output


def test_index_with_mdl_leaves_the_rule_index_untouched(tmp_path, fake_store):
    project = _write_project(tmp_path, rules=["Amounts are USD."])
    mdl = project / "target" / "mdl.json"

    result = runner.invoke(
        app, ["memory", "index", "--mdl", str(mdl), "--no-seed", "--no-queries"]
    )

    assert result.exit_code == 0, result.output
    assert "rules" not in fake_store.schema_calls[0]
    # Rules are unknown here (no project lookup), so the existing table must not
    # be replaced with an empty one.
    assert fake_store.rule_calls == []


def test_index_with_no_instructions_leaves_the_rule_index_untouched(
    tmp_path, fake_store, monkeypatch
):
    project = _write_project(tmp_path, rules=["Amounts are USD."])
    monkeypatch.setattr("wren.context.discover_project_path", lambda: project)

    result = runner.invoke(
        app,
        ["memory", "index", "--no-instructions", "--no-seed", "--no-queries"],
    )

    assert result.exit_code == 0, result.output
    assert fake_store.rule_calls == []


def test_index_clears_the_rule_index_when_project_has_no_rules(
    tmp_path, fake_store, monkeypatch
):
    project = _write_project(tmp_path, rules=None)
    monkeypatch.setattr("wren.context.discover_project_path", lambda: project)

    result = runner.invoke(app, ["memory", "index", "--no-seed", "--no-queries"])

    assert result.exit_code == 0, result.output
    assert fake_store.rule_calls == [[]]
