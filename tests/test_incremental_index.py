"""Tests for incremental_index_update incremental refresh & NEG-10 stale-link pruning."""

from __future__ import annotations

from pathlib import Path

from codetowiki.wiki_incremental.incremental_index import (
    incremental_index_update,
    safe_index_update,
)


def _meta(wiki_to_source: dict[str, list[str]]) -> dict:
    source_to_wiki: dict[str, list[str]] = {}
    for wiki, sources in wiki_to_source.items():
        for src in sources:
            source_to_wiki.setdefault(src, [])
            if wiki not in source_to_wiki[src]:
                source_to_wiki[src].append(wiki)
                source_to_wiki[src].sort()
    return {
        "wiki_to_source": {k: sorted(v) for k, v in wiki_to_source.items()},
        "source_to_wiki": source_to_wiki,
        "commit_id": "old",
    }


def _write_wiki(wiki_dir: Path, name: str, source_paths: list[str]) -> None:
    body = "\n".join(f"- [m](file://{s})" for s in source_paths)
    (wiki_dir / name).write_text(f"# 标题\n\n<cite>\n{body}\n</cite>\n", encoding="utf-8")


# --- NEG-10: 裁剪指向已删除/失效 wiki 的残留条目 ---------------------------


def test_prune_stale_links_counts_orphan_source(tmp_path: Path) -> None:
    """source_to_wiki 中存在指向已删除 wiki 的残留条目时应被裁剪并计数。"""
    meta = _meta(
        {
            "01-a.md": ["src/x.py"],
            # 02-b.md 将被传入 affected_wikis 但文件不存在 → 视为已删除
        }
    )
    # 残留条目：src/y.py 仍指向不再存在的 03-ghost.md
    meta["source_to_wiki"]["src/y.py"] = ["03-ghost.md"]

    # 传入一个已删除的 wiki（文件不存在）
    updated = incremental_index_update(meta, ["02-b.md"], "newcommit", tmp_path)

    # 02-b.md 不存在 → 从 wiki_to_source 移除
    assert "02-b.md" not in updated["wiki_to_source"]
    # 残留 src/y.py 指向的 03-ghost.md 不在 wiki_to_source → 被裁剪
    assert "src/y.py" not in updated["source_to_wiki"]
    # 有效链接 src/x.py 保留（仅保留仍存在的 01-a.md）
    assert updated["source_to_wiki"]["src/x.py"] == ["01-a.md"]
    # 计数正确
    assert updated["stats"]["pruned_stale_links"] == 1


def test_prune_stale_links_only_partial_removal(tmp_path: Path) -> None:
    """某 source 同时被有效 wiki 与失效 wiki 引用时，仅移除失效部分。"""
    meta = _meta({"01-a.md": ["src/x.py"], "02-b.md": ["src/x.py"]})
    # src/x.py 额外残留一个失效 wiki
    meta["source_to_wiki"]["src/x.py"] = ["01-a.md", "02-b.md", "03-ghost.md"]

    # 删除 02-b.md（文件不存在）
    updated = incremental_index_update(meta, ["02-b.md"], "newcommit", tmp_path)

    # src/x.py 整条仍有有效 wiki（01-a.md）被保留；失效的 03-ghost.md 链接被过滤掉
    assert updated["source_to_wiki"]["src/x.py"] == ["01-a.md"]
    # 整条未被删除 → 不计入 pruned_stale_links
    assert updated.get("stats", {}).get("pruned_stale_links", 0) == 0


def test_no_stale_links_means_no_pruned_stat(tmp_path: Path) -> None:
    """全是有效链接、无残留时，stats 不应出现 pruned_stale_links。"""
    meta = _meta({"01-a.md": ["src/x.py"]})
    updated = incremental_index_update(meta, [], "newcommit", tmp_path)
    assert "pruned_stale_links" not in updated.get("stats", {})
    assert updated["source_to_wiki"]["src/x.py"] == ["01-a.md"]


# --- 增量新增/移除引用 -----------------------------------------------------


def test_incremental_adds_new_citation(tmp_path: Path) -> None:
    """affected wiki 文件存在且新增引用时，source_to_wiki 应追加新 source。"""
    meta = _meta({"01-a.md": ["src/x.py"]})
    _write_wiki(tmp_path, "01-a.md", ["src/x.py", "src/z.py"])

    updated = incremental_index_update(meta, ["01-a.md"], "newcommit", tmp_path)

    assert updated["wiki_to_source"]["01-a.md"] == ["src/x.py", "src/z.py"]
    assert "src/z.py" in updated["source_to_wiki"]
    assert "01-a.md" in updated["source_to_wiki"]["src/z.py"]
    assert updated["source_to_wiki"]["src/x.py"] == ["01-a.md"]
    assert updated.get("stats", {}).get("pruned_stale_links", 0) == 0


def test_incremental_removes_citation_when_wiki_updated(tmp_path: Path) -> None:
    """affected wiki 更新后移除某引用，source_to_wiki 应同步清除该映射。"""
    meta = _meta({"01-a.md": ["src/x.py", "src/y.py"]})
    _write_wiki(tmp_path, "01-a.md", ["src/x.py"])  # y.py 不再被引用

    updated = incremental_index_update(meta, ["01-a.md"], "newcommit", tmp_path)

    assert updated["wiki_to_source"]["01-a.md"] == ["src/x.py"]
    assert "src/y.py" not in updated["source_to_wiki"]
    assert updated["source_to_wiki"]["src/x.py"] == ["01-a.md"]


# --- safe_index_update 兜底 -------------------------------------------------


def test_safe_index_update_matches_incremental(tmp_path: Path) -> None:
    """正常输入下 safe_index_update 的结果应与 incremental_index_update 一致。"""
    meta = _meta({"01-a.md": ["src/x.py"]})
    _write_wiki(tmp_path, "01-a.md", ["src/x.py", "src/z.py"])

    direct = incremental_index_update(meta, ["01-a.md"], "newcommit", tmp_path)
    safe = safe_index_update(meta, ["01-a.md"], "newcommit", tmp_path)
    assert safe == direct
    assert safe["source_to_wiki"]["src/z.py"] == ["01-a.md"]
