# -*- coding: utf-8 -*-
"""Tests for codetowiki.wiki_incremental.index_builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codetowiki.wiki_incremental.index_builder import (
    DEFAULT_EXCLUDED_PATHS,
    DEFAULT_NOISE_PATHS,
    build_index,
    build_indexes,
    parse_citations,
)


def test_default_excluded_paths_are_project_agnostic() -> None:
    """No project-specific (bk-monitor) entries should leak into defaults."""
    joined = " ".join(DEFAULT_EXCLUDED_PATHS + DEFAULT_NOISE_PATHS)
    assert "bkmonitor" not in joined
    assert "bklog" not in joined
    # Universal noise rules are still present.
    assert "*/migrations/" in DEFAULT_EXCLUDED_PATHS
    assert "*/tests/" in DEFAULT_EXCLUDED_PATHS
    assert "*.pyc" in DEFAULT_NOISE_PATHS


def test_parse_citations_extracts_cite_and_section_source() -> None:
    content = (
        "# 标题\n\n"
        "<cite>\n**本文引用的文件**\n"
        "- [mod](file://src/core.py)\n"
        "</cite>\n\n"
        "## 简介\n\n"
        "章节来源\n"
        "- [mod](file://src/core.py#L1-L10)\n"
    )
    citations = parse_citations("01-x.md", content)
    types = {c.type for c in citations}
    assert "cite" in types
    assert "section_source" in types
    assert all(c.source_path == "src/core.py" for c in citations)


def test_build_indexes_is_bidirectional() -> None:
    citations = [
        __import__("codetowiki.wiki_incremental.index_builder", fromlist=["Citation"]).Citation(
            "a.md", "src/x.py", "cite"
        ),
        __import__("codetowiki.wiki_incremental.index_builder", fromlist=["Citation"]).Citation(
            "a.md", "src/y.py", "cite"
        ),
    ]
    s2w, w2s = build_indexes(citations)
    assert s2w["src/x.py"] == ["a.md"]
    assert w2s["a.md"] == ["src/x.py", "src/y.py"]


def test_build_index_writes_metadata(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "01-x.md").write_text(
        "# 标题\n\n"
        "<cite>\n**本文引用的文件**\n- [m](file://src/core.py)\n</cite>\n\n"
        "## 简介\n\n章节来源\n- [m](file://src/core.py#L1-L5)\n",
        encoding="utf-8",
    )
    out = tmp_path / "metadata.json"
    metadata = build_index(wiki, commit_id="abc123", base_metadata=None, repo_url="<repo>", branch="main")
    assert metadata["source_to_wiki"] == {"src/core.py": ["01-x.md"]}
    assert metadata["wiki_to_source"] == {"01-x.md": ["src/core.py"]}
    assert metadata["source"]["commit_id"] == "abc123"
    assert metadata["source"]["repo_url"] == "<repo>"
    # Defaults applied (generic).
    assert "bkmonitor" not in " ".join(metadata["excluded_paths"])


def test_build_index_preserves_existing_config(tmp_path: Path) -> None:
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "01-x.md").write_text(
        "# 标题\n\n<cite>\n- [m](file://src/core.py)\n</cite>\n", encoding="utf-8"
    )
    base = {"excluded_paths": ["custom/"], "noise_paths": ["*.log"]}
    metadata = build_index(wiki, commit_id="abc", base_metadata=base)
    assert metadata["excluded_paths"] == ["custom/"]
    assert metadata["noise_paths"] == ["*.log"]
