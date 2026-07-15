# -*- coding: utf-8 -*-
"""Tests for codetowiki.wiki_incremental.format_validation and wiki_format_check."""

from __future__ import annotations

from codetowiki.wiki_incremental.format_validation import validate_and_fix
from codetowiki.wiki_format_check import check_content


def test_r1_adds_missing_cite() -> None:
    content = "# 标题\n\n## 简介\n\n章节来源\n- [m](file://src/x.py#L1-L5)\n"
    fixed, violations = validate_and_fix(content)
    assert any(v.rule == "R1" for v in violations)
    assert "<cite>" in fixed


def test_r5_adds_file_scheme() -> None:
    content = (
        "# 标题\n\n<cite>\n- [m](src/x.py)\n</cite>\n\n"
        "## 简介\n\n章节来源\n- [m](src/x.py#L1-L5)\n"
    )
    fixed, violations = validate_and_fix(content)
    assert any(v.rule == "R5" for v in violations)
    assert "file://src/x.py" in fixed


def test_r3_adds_section_source() -> None:
    content = "# 标题\n\n<cite>\n- [m](file://src/x.py)\n</cite>\n\n## 简介\n\n正文\n"
    fixed, violations = validate_and_fix(content)
    assert any(v.rule == "R3" for v in violations)
    assert "章节来源" in fixed


def test_clean_content_has_no_violations() -> None:
    content = (
        "# 标题\n\n<cite>\n- [m](file://src/x.py)\n</cite>\n\n"
        "## 目录\n1. [简介](#简介)\n\n"
        "## 简介\n\n章节来源\n- [m](file://src/x.py#L1-L5)\n"
    )
    fixed, violations = validate_and_fix(content)
    assert violations == []
    assert fixed == content


def test_check_content_r1_error() -> None:
    violations = check_content("# 标题\n\n## 简介\n")
    assert any(v.rule == "R1" and v.severity == "error" for v in violations)
