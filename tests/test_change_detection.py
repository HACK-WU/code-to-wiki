# -*- coding: utf-8 -*-
"""Tests for change_detection path filtering and shared R3 helper."""

from __future__ import annotations

from codetowiki.wiki_incremental.change_detection import (
    ChangedFile,
    build_pathspec_args,
    classify_changes,
)
from codetowiki.wiki_incremental.format_validation import section_needs_source
from codetowiki.wiki_incremental.index_builder import (
    DEFAULT_EXCLUDED_PATHS,
    DEFAULT_NOISE_PATHS,
)


def test_excluded_directory_does_not_get_trailing_star() -> None:
    """Regression: directory excludes must use a whole-subtree pathspec.

    The old code emitted `:!node_modules/*`, whose `*` cannot cross `/`, so
    nested files like `node_modules/foo/bar.js` were never excluded.
    """
    args = build_pathspec_args(DEFAULT_EXCLUDED_PATHS, [])
    assert ":!node_modules/" in args
    assert ":!node_modules/*" not in args
    assert ":!dist/" in args
    assert ":!__pycache__/" in args


def test_wildcard_prefix_expands_to_any_depth() -> None:
    """`*/tests/` should exclude tests dirs at any depth, not just top-level."""
    args = build_pathspec_args(DEFAULT_EXCLUDED_PATHS, [])
    assert ":!**/tests/" in args
    assert ":!**/migrations/" in args
    # file-style patterns keep their glob
    assert ":!**/__init__.py" in args


def test_noise_paths_are_excluded() -> None:
    args = build_pathspec_args([], DEFAULT_NOISE_PATHS)
    assert ":!*.pyc" in args
    assert ":!docs/" in args  # "^docs/" shorthand -> whole docs subtree


def test_section_needs_source_exempt_cases() -> None:
    assert section_needs_source("目录", "任意内容") is False
    assert section_needs_source("简介", "本节无章节来源，为概念性内容") is False
    assert section_needs_source("简介", "章节来源\n- [m](file://x.py)") is False


def test_section_needs_source_requires_marker() -> None:
    assert section_needs_source("简介", "正文没有来源") is True


def test_rename_new_path_enters_new_features() -> None:
    """A renamed file whose OLD path is unknown should be treated as a new
    feature so it is surfaced for placement inference / review."""
    source_to_wiki = {"src/core/user.py": ["wiki/后端/用户模块.md"]}
    entries = [ChangedFile("R", "src/core/account.py", "legacy/old.py")]
    report = classify_changes(entries, source_to_wiki, "old", "new")
    # old path is unmapped -> rename falls through and the NEW path is recorded
    assert "src/core/account.py" in report.new_features
    # the old path is not reported as a loose unmatched entry
    assert report.unmatched == []


def test_rename_of_mapped_file_stays_exact_hit() -> None:
    """A rename of a file already mapped by its OLD path remains an exact hit
    (wiki page needs syncing) and is not double-counted as a new feature."""
    source_to_wiki = {
        "src/core/user.py": ["wiki/后端/用户模块.md"],
        "src/core/account.py": ["wiki/后端/账户模块.md"],
    }
    entries = [ChangedFile("R", "src/core/account.py", "src/core/user.py")]
    report = classify_changes(entries, source_to_wiki, "old", "new")
    assert any("用户模块.md" in w for r in report.exact_hits for w in r.wiki_paths)
    assert report.new_features == []
