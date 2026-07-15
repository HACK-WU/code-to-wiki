# -*- coding: utf-8 -*-
"""Build source/wiki citation indexes from wiki markdown files.

This is a *reference index* (pure local JSON). It parses ``<cite>`` blocks and
章节来源 / 图表来源 citations from wiki markdown and produces two bidirectional
mappings:

    source_to_wiki: {source_path: [wiki_path, ...]}
    wiki_to_source: {wiki_path: [source_path, ...]}

No external knowledge base / semantic index is involved.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .json_utils import atomic_save_json, load_json

CITE_BLOCK_RE = re.compile(r"<cite>.*?</cite>", re.DOTALL)
ENTRY_RE = re.compile(r"^- \[([^\]]+)\]\(file://([^)]+)\)\s*$", re.MULTILINE)
SOURCE_HEADER_RE = re.compile(r"^\*{0,2}(章节来源|图表来源|图示来源)\*{0,2}\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)
MERMAID_RE = re.compile(r"```mermaid\n.*?```", re.DOTALL)

# Generic defaults shared by every project. Project-specific excludes should be
# supplied via an existing metadata.json (--metadata) so they are preserved.
DEFAULT_EXCLUDED_PATHS = [
    "node_modules/",
    "vendor/",
    "dist/",
    "build/",
    "__pycache__/",
    "*/migrations/",
    "*/tests/",
    "*/test/",
    "*/__init__.py",
]
DEFAULT_NOISE_PATHS = ["*.pyc", "^docs/"]


@dataclass(frozen=True)
class Citation:
    """A single wiki-to-source citation."""

    wiki_path: str
    source_path: str
    type: str
    section_name: str = ""


def clean_source_path(path: str) -> str:
    return path.split("#", 1)[0].strip()


def iter_markdown_files(wiki_dir: str | Path) -> Iterable[Path]:
    root = Path(wiki_dir)
    yield from sorted(p for p in root.rglob("*.md") if p.is_file())


def _nearest_heading(content: str, pos: int) -> str:
    section = ""
    for match in HEADING_RE.finditer(content[:pos]):
        section = match.group(1).strip()
    return section


def _nearest_mermaid_section(content: str, pos: int) -> str:
    last_start = -1
    for match in MERMAID_RE.finditer(content[:pos]):
        last_start = match.start()
    if last_start < 0:
        return _nearest_heading(content, pos)
    return _nearest_heading(content, last_start)


def _source_block_end(content: str, start: int) -> int:
    next_heading = re.search(r"^(?:#{1,6} |\S.*来源\s*$|<cite>)", content[start:], re.MULTILINE)
    if next_heading:
        return start + next_heading.start()
    return len(content)


def parse_citations(wiki_path: str, wiki_content: str) -> list[Citation]:
    citations: list[Citation] = []

    for block in CITE_BLOCK_RE.finditer(wiki_content):
        for entry in ENTRY_RE.finditer(block.group(0)):
            source_path = clean_source_path(entry.group(2))
            if source_path:
                citations.append(Citation(wiki_path, source_path, "cite"))

    for header in SOURCE_HEADER_RE.finditer(wiki_content):
        label = header.group(1)
        start = header.end()
        end = _source_block_end(wiki_content, start)
        block = wiki_content[start:end]
        cite_type = "chart_source" if label in ("图表来源", "图示来源") else "section_source"
        section = _nearest_mermaid_section(wiki_content, header.start()) if cite_type == "chart_source" else _nearest_heading(wiki_content, header.start())
        for entry in ENTRY_RE.finditer(block):
            source_path = clean_source_path(entry.group(2))
            if source_path:
                citations.append(Citation(wiki_path, source_path, cite_type, section))

    return citations


def build_indexes(citations: list[Citation]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    source_to_wiki: dict[str, set[str]] = {}
    wiki_to_source: dict[str, set[str]] = {}
    for citation in citations:
        source_to_wiki.setdefault(citation.source_path, set()).add(citation.wiki_path)
        wiki_to_source.setdefault(citation.wiki_path, set()).add(citation.source_path)
    return (
        {key: sorted(value) for key, value in sorted(source_to_wiki.items())},
        {key: sorted(value) for key, value in sorted(wiki_to_source.items())},
    )


def _current_commit(repo_dir: str | Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def build_index(
    wiki_dir: str | Path,
    commit_id: str,
    base_metadata: dict | None = None,
    repo_url: str = "",
    branch: str = "",
    repo_prefix: str = "",
) -> dict:
    root = Path(wiki_dir)
    if not root.exists():
        raise FileNotFoundError(f"wiki directory not found: {root}")

    warnings: list[str] = []
    citations: list[Citation] = []
    wiki_count = 0

    for path in iter_markdown_files(root):
        wiki_count += 1
        wiki_path = path.relative_to(root).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            warnings.append(f"skip {wiki_path}: {exc}")
            continue
        citations.extend(parse_citations(wiki_path, content))

    source_to_wiki, wiki_to_source = build_indexes(citations)
    metadata = dict(base_metadata or {})
    metadata.setdefault("wiki_path", root.as_posix())
    source = dict(metadata.get("source") or {})
    source["commit_id"] = commit_id
    source["repo_url"] = repo_url or source.get("repo_url", "")
    source["branch"] = branch or source.get("branch", "")
    metadata["source"] = source
    metadata.setdefault("excluded_paths", list(DEFAULT_EXCLUDED_PATHS))
    metadata.setdefault("noise_paths", list(DEFAULT_NOISE_PATHS))
    if repo_prefix:
        metadata["repo_prefix"] = repo_prefix
    else:
        metadata.setdefault("repo_prefix", "")
    stats = dict(metadata.get("stats") or {})
    stats.update(
        {
            "wiki_count": wiki_count,
            "source_count": len(source_to_wiki),
            "citation_count": len(citations),
        }
    )
    metadata["stats"] = stats
    metadata["source_to_wiki"] = source_to_wiki
    metadata["wiki_to_source"] = wiki_to_source
    if warnings:
        metadata["warnings"] = warnings
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build wiki source citation indexes.")
    parser.add_argument("--wiki-dir", required=True)
    parser.add_argument("--commit")
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--metadata")
    parser.add_argument("--output")
    parser.add_argument("--repo-url", default="", help="source code repository URL")
    parser.add_argument("--branch", default="", help="source code branch name")
    parser.add_argument("--repo-prefix", default="", help="optional leading path to strip when inferring wiki placement")
    args = parser.parse_args(argv)

    base = load_json(args.metadata) if args.metadata else None
    commit = args.commit or _current_commit(args.repo_dir)
    metadata = build_index(
        args.wiki_dir, commit, base, repo_url=args.repo_url, branch=args.branch, repo_prefix=args.repo_prefix
    )
    if args.output:
        atomic_save_json(metadata, args.output)
    else:
        sys.stdout.buffer.write(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
