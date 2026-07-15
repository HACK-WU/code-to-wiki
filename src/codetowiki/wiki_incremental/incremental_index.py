# -*- coding: utf-8 -*-
"""Incrementally refresh metadata indexes after wiki changes."""

from __future__ import annotations

import copy
from pathlib import Path

from .index_builder import build_index, parse_citations
from .json_utils import atomic_save_json


def incremental_index_update(
    metadata: dict,
    affected_wikis: list[str],
    new_commit: str,
    wiki_dir: str | Path,
) -> dict:
    updated = copy.deepcopy(metadata)
    source_to_wiki: dict[str, list[str]] = updated.setdefault("source_to_wiki", {})
    wiki_to_source: dict[str, list[str]] = updated.setdefault("wiki_to_source", {})
    root = Path(wiki_dir)

    for wiki_path in affected_wikis:
        old_sources = set(wiki_to_source.get(wiki_path, []))
        full_path = root / wiki_path
        if full_path.exists():
            content = full_path.read_text(encoding="utf-8")
            new_sources = {citation.source_path for citation in parse_citations(wiki_path, content)}
        else:
            new_sources = set()

        added = new_sources - old_sources
        removed = old_sources - new_sources

        if new_sources:
            wiki_to_source[wiki_path] = sorted(new_sources)
        else:
            wiki_to_source.pop(wiki_path, None)

        for src in removed:
            wikis = source_to_wiki.get(src)
            if not wikis:
                continue
            if wiki_path in wikis:
                wikis.remove(wiki_path)
            if not wikis:
                source_to_wiki.pop(src, None)

        for src in added:
            source_to_wiki.setdefault(src, [])
            if wiki_path not in source_to_wiki[src]:
                source_to_wiki[src].append(wiki_path)
                source_to_wiki[src].sort()

    updated.setdefault("source", {})["commit_id"] = new_commit
    stats = updated.setdefault("stats", {})
    stats["source_count"] = len(source_to_wiki)
    stats["wiki_count"] = len(wiki_to_source)
    stats["citation_count"] = sum(len(sources) for sources in wiki_to_source.values())
    return updated


def safe_index_update(
    metadata: dict,
    affected_wikis: list[str],
    new_commit: str,
    wiki_dir: str | Path,
) -> dict:
    try:
        return incremental_index_update(metadata, affected_wikis, new_commit, wiki_dir)
    except Exception:
        return build_index(wiki_dir, new_commit, metadata)


def save_metadata(metadata: dict, output_path: str | Path) -> None:
    atomic_save_json(metadata, output_path)
