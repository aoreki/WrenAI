"""extract_rule_items must split rule strings on ``##`` level-2 headings."""

import pytest

from wren.memory.schema_indexer import extract_rule_items, manifest_hash


def test_extract_rule_items_splits_on_level2_headings() -> None:
    # One rule string holding three ``##`` sections. The leading split
    # fragment (empty) is skipped; heading-only sections are kept as rules
    # just like sections with a body.
    rules = [
        "# 一级标题\n## 规则一\n第一条：销售额按日统计。\n## 规则二\n第二条：只取已支付订单。\n## 只有标题没有正文",
    ]
    items = extract_rule_items(rules)
    assert [i["rule_name"] for i in items] == [
        "# 一级标题",
        "规则一",
        "规则二",
        "只有标题没有正文",
    ]
    assert items[1]["text"] == "规则一\n第一条：销售额按日统计。"
    assert items[2]["text"] == "规则二\n第二条：只取已支付订单。"
    assert items[3]["text"] == "只有标题没有正文"
    assert {"rule_name", "text", "indexed_at"} <= set(items[0])


def test_extract_rule_items_accumulates_across_rules_and_empty_section() -> None:
    # Each element of ``rules`` contributes its own sections; a missing, null,
    # or empty section is a no-op.
    items = extract_rule_items(
        [
            "## 规则一\n第一条：A。",
            "## 规则二\n第二条：B。",
        ]
    )
    assert [i["rule_name"] for i in items] == ["规则一", "规则二"]
    assert extract_rule_items(None) == []
    assert extract_rule_items([]) == []


def test_extract_rule_items_raises_on_non_list_rules() -> None:
    with pytest.raises(ValueError, match="rules must be a list, got str"):
        extract_rule_items("not-a-list")


def test_extract_rule_items_raises_on_non_string_entry() -> None:
    with pytest.raises(ValueError, match="rules entries must be strings, got int"):
        extract_rule_items([42])  # type: ignore[list-item]


def test_rules_never_enter_manifest_hash() -> None:
    """Regression: rules are indexed beside the manifest, not inside it.

    ``mdl_hash`` is stamped on every schema row at index time and recomputed at
    fetch time from ``target/mdl.json`` alone. If rule text were folded into the
    manifest (as it used to be), the two hashes would differ whenever a project
    has ``knowledge/rules/*.md`` and every schema search would return nothing.
    """
    manifest = {"catalog": "test", "schema": "public", "models": []}
    assert manifest_hash(manifest) == manifest_hash(dict(manifest))
    assert manifest_hash(manifest) != manifest_hash({**manifest, "rules": ["x"]})
