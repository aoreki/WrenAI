"""extract_rule_items must split rule strings on ``##`` level-2 headings."""

import pytest

from wren.memory.schema_indexer import extract_rule_items


def test_extract_rule_items_splits_on_level2_headings() -> None:
    # One rule string holding three ``##`` sections. The leading split
    # fragment (empty) is skipped; heading-only sections are kept as rules
    # just like sections with a body.
    manifest = {
        "rules": [
            "# 一级标题\n## 规则一\n第一条：销售额按日统计。\n## 规则二\n第二条：只取已支付订单。\n## 只有标题没有正文",
        ]
    }
    items = extract_rule_items(manifest)
    assert [i["rule_name"] for i in items] == ["# 一级标题","规则一", "规则二", "只有标题没有正文"]
    assert items[1]["text"] == "规则一\n第一条：销售额按日统计。"
    assert items[2]["text"] == "规则二\n第二条：只取已支付订单。"
    assert items[3]["text"] == "只有标题没有正文"
    assert {"rule_name", "text", "indexed_at"} <= set(items[0])


def test_extract_rule_items_accumulates_across_rules_and_empty_section() -> None:
    # Each element of ``rules`` contributes its own sections; a missing, null,
    # or empty section is a no-op.
    manifest = {
        "rules": [
            "## 规则一\n第一条：A。",
            "## 规则二\n第二条：B。",
        ]
    }
    items = extract_rule_items(manifest)
    assert [i["rule_name"] for i in items] == ["规则一", "规则二"]
    assert extract_rule_items({}) == []
    assert extract_rule_items({"rules": None}) == []
    assert extract_rule_items({"rules": []}) == []


def test_extract_rule_items_raises_on_non_list_rules() -> None:
    with pytest.raises(ValueError, match=r"manifest\['rules'\] must be a list"):
        extract_rule_items({"rules": "not-a-list"})
