"""Tests for the codetowiki top-level CLI (cleanup-citations / sync-index)."""

from __future__ import annotations

import json
from pathlib import Path

from codetowiki.cli import main


def _write_wiki(wiki_dir: Path, name: str, sources: list[str]) -> None:
    body = "\n".join(f"- [{s}](file://{s})" for s in sources)
    (wiki_dir / name).write_text(f"# 标题\n\n<cite>\n{body}\n</cite>\n", encoding="utf-8")


# --- cleanup-citations -----------------------------------------------------


def test_cleanup_citations_removes_dead_citation(tmp_path: Path) -> None:
    wiki = tmp_path / "w.md"
    wiki.write_text(
        "# T\n\n<cite>\n- [old](file://src/old.py)\n- [keep](file://src/keep.py)\n</cite>\n",
        encoding="utf-8",
    )
    rc = main(["cleanup-citations", "--file", str(wiki), "--dead", "src/old.py"])
    assert rc == 0
    out = wiki.read_text(encoding="utf-8")
    assert "src/old.py" not in out
    assert "src/keep.py" in out


def test_cleanup_citations_renames_path(tmp_path: Path) -> None:
    wiki = tmp_path / "w.md"
    wiki.write_text(
        "# T\n\n<cite>\n- [a](file://src/a.py)\n</cite>\n",
        encoding="utf-8",
    )
    rc = main(["cleanup-citations", "--file", str(wiki), "--renamed", "src/a.py:src/b.py"])
    assert rc == 0
    out = wiki.read_text(encoding="utf-8")
    assert "src/b.py" in out
    assert "src/a.py" not in out


def test_cleanup_citations_writes_to_output_without_overwriting_source(tmp_path: Path) -> None:
    src = tmp_path / "w.md"
    src.write_text(
        "# T\n\n<cite>\n- [old](file://src/old.py)\n</cite>\n",
        encoding="utf-8",
    )
    out_file = tmp_path / "out.md"
    rc = main(
        [
            "cleanup-citations",
            "--file",
            str(src),
            "--dead",
            "src/old.py",
            "--output",
            str(out_file),
        ]
    )
    assert rc == 0
    assert "src/old.py" not in out_file.read_text(encoding="utf-8")
    assert "src/old.py" in src.read_text(encoding="utf-8")


def test_cleanup_citations_renamed_without_colon_is_ignored(tmp_path: Path) -> None:
    wiki = tmp_path / "w.md"
    wiki.write_text(
        "# T\n\n<cite>\n- [a](file://src/a.py)\n</cite>\n",
        encoding="utf-8",
    )
    rc = main(["cleanup-citations", "--file", str(wiki), "--renamed", "src/a.py"])
    assert rc == 0
    assert "src/a.py" in wiki.read_text(encoding="utf-8")


# --- sync-index ------------------------------------------------------------


def test_sync_index_adds_new_citation_and_updates_commit(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    _write_wiki(wiki_dir, "w.md", ["src/a.py", "src/b.py"])
    meta = {
        "source_to_wiki": {"src/a.py": ["w.md"]},
        "wiki_to_source": {"w.md": ["src/a.py"]},
        "source": {"commit_id": "old"},
    }
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    rc = main(
        [
            "sync-index",
            "--metadata",
            str(meta_path),
            "--wiki-dir",
            str(wiki_dir),
            "--wikis",
            "w.md",
            "--commit",
            "newsha",
        ]
    )
    assert rc == 0

    updated = json.loads(meta_path.read_text(encoding="utf-8"))
    assert updated["source"]["commit_id"] == "newsha"
    assert "src/b.py" in updated["wiki_to_source"]["w.md"]
    assert "w.md" in updated["source_to_wiki"]["src/b.py"]


def test_sync_index_default_output_overwrites_metadata(tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    _write_wiki(wiki_dir, "w.md", ["src/a.py"])
    meta = {
        "source_to_wiki": {},
        "wiki_to_source": {},
        "source": {"commit_id": "old"},
    }
    meta_path = tmp_path / "metadata.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    rc = main(
        [
            "sync-index",
            "--metadata",
            str(meta_path),
            "--wiki-dir",
            str(wiki_dir),
            "--wikis",
            "w.md",
            "--commit",
            "newsha",
        ]
    )
    assert rc == 0
    updated = json.loads(meta_path.read_text(encoding="utf-8"))
    assert updated["wiki_to_source"]["w.md"] == ["src/a.py"]
