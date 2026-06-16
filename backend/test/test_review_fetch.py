"""评论拉取与格式化单元测试。"""

from datetime import date

from app.agent.tools import build_reviews_scope_note, format_review_line


def test_format_review_line():
    line = format_review_line(
        region="华东",
        order_date=date(2025, 9, 15),
        channel="线上",
        product_category="数码配件",
        sentiment="negative",
        rating=2,
        comment="物流太慢了。",
    )
    assert line.startswith("[华东|2025-09-15|线上|数码配件|negative|2星]")
    assert "物流太慢了" in line


def test_build_reviews_scope_note_with_filters():
    note = build_reviews_scope_note(
        [
            {"column": "order_date", "operator": "year", "value": 2025},
            {"column": "order_date", "operator": "month", "value": 9},
            {"column": "region", "operator": "==", "value": "华东"},
        ],
        "",
    )
    assert "2025年" in note
    assert "9月" in note
    assert "区域=华东" in note
    assert "可直接用于归因" in note


def test_build_reviews_scope_note_without_filters():
    note = build_reviews_scope_note(
        [],
        "2025-01-01 至 2025-12-31",
    )
    assert "分析时间范围" in note or "2025" in note
