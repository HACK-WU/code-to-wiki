"""Tests for codetowiki.wiki_incremental.format_validation and wiki_format_check."""

from __future__ import annotations

from pathlib import Path

from codetowiki.wiki_incremental.format_validation import validate_and_fix
from codetowiki.wiki_format_check import _try_fix, check_content

# 缺少 file:// scheme（R5），validate_and_fix 会将其补全，可稳定触发一次修复
_FIXABLE = "# 标题\n\n<cite>\n- [m](src/x.py)\n</cite>\n\n## 简介\n\n章节来源\n- [m](src/x.py#L1-L5)\n"


def test_r1_adds_missing_cite() -> None:
    content = "# 标题\n\n## 简介\n\n章节来源\n- [m](file://src/x.py#L1-L5)\n"
    fixed, violations = validate_and_fix(content)
    assert any(v.rule == "R1" for v in violations)
    assert "<cite>" in fixed


def test_r5_adds_file_scheme() -> None:
    content = "# 标题\n\n<cite>\n- [m](src/x.py)\n</cite>\n\n## 简介\n\n章节来源\n- [m](src/x.py#L1-L5)\n"
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


# --- _try_fix: --dry-run 预览 & 备份行为 ------------------------------------


def test_try_fix_dry_run_does_not_write_or_backup(tmp_path: Path) -> None:
    """dry_run=True 时应返回 diff，且不写盘、不生成 .bak。"""
    target = tmp_path / "01-x.md"
    target.write_text(_FIXABLE, encoding="utf-8")
    changed, note = _try_fix(target, _FIXABLE, dry_run=True)
    assert changed is True
    assert note.startswith("---") or "file://" in note  # unified diff 内容
    # 原文件保持不变，且未生成备份
    assert target.read_text(encoding="utf-8") == _FIXABLE
    assert not (tmp_path / "01-x.md.bak").exists()


def test_try_fix_writes_and_creates_backup(tmp_path: Path) -> None:
    """dry_run=False 时应写入修复结果并备份原文件。"""
    target = tmp_path / "01-x.md"
    target.write_text(_FIXABLE, encoding="utf-8")
    changed, note = _try_fix(target, _FIXABLE, dry_run=False)
    assert changed is True
    assert "备份" in note
    backup = tmp_path / "01-x.md.bak"
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == _FIXABLE  # 备份保留原始内容
    assert target.read_text(encoding="utf-8") != _FIXABLE  # 目标已被修复
    assert "file://" in target.read_text(encoding="utf-8")


def test_try_fix_no_change_returns_false(tmp_path: Path) -> None:
    """无需修复的内容返回 (False, '无需修复')，不产生备份。"""
    clean = (
        "# 标题\n\n<cite>\n- [m](file://src/x.py)\n</cite>\n\n"
        "## 目录\n1. [简介](#简介)\n\n"
        "## 简介\n\n章节来源\n- [m](file://src/x.py#L1-L5)\n"
    )
    target = tmp_path / "01-x.md"
    target.write_text(clean, encoding="utf-8")
    changed, note = _try_fix(target, clean, dry_run=False)
    assert changed is False
    assert note == "无需修复"
    assert not (tmp_path / "01-x.md.bak").exists()
