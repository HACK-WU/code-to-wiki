# -*- coding: utf-8 -*-
"""Infer Wiki directory placement for new source files based on existing mapping patterns.

Extracts path-prefix rules from source_to_wiki and uses them to suggest where
new (unmapped) source files should be placed in the Wiki directory structure.

The optional ``repo_prefix`` lets a project drop a redundant top-level directory
(e.g. a repo whose source paths all start with ``src/``) so the inferred rules
operate on the meaningful 2-level prefix. When ``repo_prefix`` is empty (the
default), paths are used as-is.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import PurePosixPath


@dataclass
class PlacementRule:
    """A single inferred mapping rule from source prefix to Wiki top-level directory."""

    source_prefix: str
    wiki_dir: str
    confidence: int  # 0-100, percentage of dominant wiki dir
    sample_count: int


@dataclass
class PlacementSuggestion:
    """Suggestion for where a new source file should be placed in Wiki."""

    source_path: str
    suggested_wiki_dir: str
    confidence: int
    rule: PlacementRule
    # Whether the file should extend an existing page or create a new one
    strategy: str = "new_page"  # "new_page" | "extend_existing"
    related_wikis: list[str] = field(default_factory=list)


def _strip_repo_prefix(path: str, prefix: str = "") -> tuple[str, ...]:
    """Strip an optional leading ``prefix`` (e.g. 'src/') from a source path."""
    parts = PurePosixPath(path).parts
    if prefix:
        prefix_parts = PurePosixPath(prefix).parts
        if len(parts) >= len(prefix_parts) and parts[: len(prefix_parts)] == prefix_parts:
            parts = parts[len(prefix_parts):]
    return parts


def infer_rules(
    source_to_wiki: dict[str, list[str]],
    min_confidence: int = 60,
    min_samples: int = 3,
    repo_prefix: str = "",
) -> list[PlacementRule]:
    """Extract placement rules from existing source_to_wiki mapping.

    Uses 2-level source path prefixes (after stripping ``repo_prefix``) to find
    dominant Wiki top-level directories.

    Args:
        source_to_wiki: Existing mapping from source file paths to Wiki page paths.
        min_confidence: Minimum percentage for a rule to be considered reliable (0-100).
        min_samples: Minimum number of mapping occurrences required.
        repo_prefix: Optional leading path to ignore when computing prefixes.

    Returns:
        List of PlacementRule sorted by confidence descending.
    """
    prefix_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for src, wikis in source_to_wiki.items():
        parts = _strip_repo_prefix(src, repo_prefix)
        if len(parts) < 2:
            continue
        src_prefix = "/".join(parts[:2])
        for w in wikis:
            w_top = PurePosixPath(w).parts[0]
            prefix_counts[src_prefix][w_top] += 1

    rules: list[PlacementRule] = []
    for src_prefix, wiki_counts in prefix_counts.items():
        total = sum(wiki_counts.values())
        if total < min_samples:
            continue
        top_wiki = max(wiki_counts, key=wiki_counts.get)
        top_count = wiki_counts[top_wiki]
        pct = top_count * 100 // total
        if pct >= min_confidence:
            rules.append(
                PlacementRule(
                    source_prefix=src_prefix,
                    wiki_dir=top_wiki,
                    confidence=pct,
                    sample_count=total,
                )
            )

    # Sort by confidence descending, then by sample_count descending
    rules.sort(key=lambda r: (-r.confidence, -r.sample_count))
    return rules


def suggest_placement(
    new_source_path: str,
    rules: list[PlacementRule],
    source_to_wiki: dict[str, list[str]],
    repo_prefix: str = "",
) -> PlacementSuggestion | None:
    """Suggest Wiki placement for a new (unmapped) source file.

    Tries to match the file's path prefix against inferred rules.
    If matched, also checks for related existing Wiki pages in the same
    directory that cover sibling source files (for potential extend_existing).

    Args:
        new_source_path: Path of the new source file (e.g. 'src/apm/core/new_feature.py').
        rules: Pre-computed placement rules from infer_rules().
        source_to_wiki: Existing source_to_wiki mapping for context lookup.
        repo_prefix: Optional leading path to ignore when computing prefixes.

    Returns:
        PlacementSuggestion if a rule matches, None otherwise.
    """
    parts = _strip_repo_prefix(new_source_path, repo_prefix)
    if len(parts) < 2:
        return None

    src_prefix = "/".join(parts[:2])

    # Find matching rule (first match, rules are sorted by confidence)
    matched_rule: PlacementRule | None = None
    for rule in rules:
        if rule.source_prefix == src_prefix:
            matched_rule = rule
            break

    if matched_rule is None:
        return None

    # Check for related existing Wiki pages (same source prefix -> same wiki dir)
    related_wikis: set[str] = set()
    for src, wikis in source_to_wiki.items():
        src_parts = _strip_repo_prefix(src, repo_prefix)
        if len(src_parts) >= 2 and "/".join(src_parts[:2]) == src_prefix:
            for w in wikis:
                if PurePosixPath(w).parts[0] == matched_rule.wiki_dir:
                    related_wikis.add(w)

    # Determine strategy: if there are closely related pages, suggest extending
    strategy = "extend_existing" if related_wikis else "new_page"

    return PlacementSuggestion(
        source_path=new_source_path,
        suggested_wiki_dir=matched_rule.wiki_dir,
        confidence=matched_rule.confidence,
        rule=matched_rule,
        strategy=strategy,
        related_wikis=sorted(related_wikis),
    )


def suggest_placements_batch(
    new_source_paths: list[str],
    source_to_wiki: dict[str, list[str]],
    min_confidence: int = 60,
    min_samples: int = 3,
    repo_prefix: str = "",
) -> tuple[list[PlacementSuggestion], list[str]]:
    """Batch-suggest Wiki placements for multiple new source files.

    Args:
        new_source_paths: List of new source file paths.
        source_to_wiki: Existing source_to_wiki mapping.
        min_confidence: Minimum confidence threshold for rules.
        min_samples: Minimum sample count for rules.
        repo_prefix: Optional leading path to ignore when computing prefixes.

    Returns:
        Tuple of (suggestions, unmatched_paths).
    """
    rules = infer_rules(source_to_wiki, min_confidence, min_samples, repo_prefix)
    suggestions: list[PlacementSuggestion] = []
    unmatched: list[str] = []

    for path in new_source_paths:
        suggestion = suggest_placement(path, rules, source_to_wiki, repo_prefix)
        if suggestion:
            suggestions.append(suggestion)
        else:
            unmatched.append(path)

    return suggestions, unmatched
