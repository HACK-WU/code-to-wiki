# -*- coding: utf-8 -*-
"""Detect source changes that can affect wiki pages."""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Iterable

from .json_utils import load_json
from .pattern_inference import PlacementSuggestion, suggest_placements_batch


@dataclass
class ChangedFile:
    status: str
    path: str
    old_path: str = ""


@dataclass
class MatchResult:
    level: str
    changed_file: str
    wiki_paths: list[str]
    status: str = ""
    old_path: str = ""


@dataclass
class FeatureCluster:
    """A group of new/unmatched files sharing a common ancestor directory."""

    base_dir: str
    files: list[str]
    file_count: int = 0
    # Whether this cluster has any files with PlacementSuggestion
    has_suggestions: bool = False
    suggestions: list[PlacementSuggestion] = field(default_factory=list)


@dataclass
class ChangeReport:
    old_commit: str
    new_commit: str
    total_count: int = 0
    filtered_count: int = 0
    excluded_count: int = 0
    exact_hits: list[MatchResult] = field(default_factory=list)
    dirname_hits: list[MatchResult] = field(default_factory=list)
    parent_hits: list[MatchResult] = field(default_factory=list)
    new_features: list[str] = field(default_factory=list)
    suggested_placements: list[PlacementSuggestion] = field(default_factory=list)
    unmatched_new: list[str] = field(default_factory=list)
    unmatched: list[str] = field(default_factory=list)
    feature_clusters: list[FeatureCluster] = field(default_factory=list)

    @property
    def affected_wikis(self) -> list[str]:
        wikis: set[str] = set()
        for group in (self.exact_hits, self.dirname_hits, self.parent_hits):
            for item in group:
                wikis.update(item.wiki_paths)
        return sorted(wikis)


def _to_exclude(pattern: str) -> str:
    """Turn a configured path pattern into a git exclude (:(exclude)) pathspec.

    - A leading ``*/`` means "at any directory depth" -> git ``**/``.
    - A trailing ``/`` already excludes the whole subtree, so do NOT append
      ``*`` (appending ``*`` would only match immediate children and silently
      miss nested files like ``node_modules/foo/bar.js``).
    """
    if not pattern:
        return ""
    if pattern.startswith("*/"):
        pattern = "**/" + pattern[2:]
    return f":!{pattern}"


def build_pathspec_args(excluded_paths: Iterable[str], noise_paths: Iterable[str]) -> list[str]:
    args: list[str] = []
    for path in excluded_paths:
        exc = _to_exclude(path)
        if exc:
            args.append(exc)
    for pattern in noise_paths:
        if not pattern:
            continue
        # A leading "^" marks a directory to exclude (legacy shorthand).
        raw = pattern[1:] if pattern.startswith("^") else pattern
        exc = _to_exclude(raw)
        if exc:
            args.append(exc)
    return args


def _parse_name_status(stdout: str) -> list[ChangedFile]:
    entries: list[ChangedFile] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") and len(parts) >= 3:
            entries.append(ChangedFile("R", parts[2], parts[1]))
        elif status.startswith("C") and len(parts) >= 3:
            entries.append(ChangedFile("C", parts[2], parts[1]))
        elif len(parts) >= 2:
            entries.append(ChangedFile(status[0], parts[1]))
    return entries


def run_git_diff(
    old_commit: str,
    new_commit: str,
    metadata: dict,
    repo_dir: str = ".",
    apply_filters: bool = True,
) -> list[ChangedFile]:
    pathspec_args = []
    if apply_filters:
        pathspec_args = build_pathspec_args(
            metadata.get("excluded_paths", []),
            metadata.get("noise_paths", []),
        )
    cmd = ["git", "--no-pager", "diff", "--name-status", f"{old_commit}..{new_commit}", "--"]
    if pathspec_args:
        cmd.append(".")
    cmd.extend(pathspec_args)
    result = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return _parse_name_status(result.stdout)


def three_level_match(changed_path: str, source_to_wiki: dict[str, list[str]]) -> MatchResult:
    if changed_path in source_to_wiki:
        return MatchResult("exact", changed_path, sorted(source_to_wiki[changed_path]))

    changed_dir = os.path.dirname(changed_path)
    dirname_wikis: set[str] = set()
    for key, wikis in source_to_wiki.items():
        if key != changed_path and os.path.dirname(key) == changed_dir:
            dirname_wikis.update(wikis)
    if dirname_wikis:
        return MatchResult("dirname", changed_path, sorted(dirname_wikis))

    parent_dir = os.path.dirname(changed_dir)
    if parent_dir:
        parent_wikis: set[str] = set()
        for key, wikis in source_to_wiki.items():
            key_dir = os.path.dirname(key)
            if key_dir.startswith(parent_dir + "/") or key_dir == parent_dir:
                parent_wikis.update(wikis)
        if parent_wikis:
            return MatchResult("parent", changed_path, sorted(parent_wikis))

    return MatchResult("none", changed_path, [])


def _cluster_new_files(
    new_paths: list[str],
    suggestions: list[PlacementSuggestion],
    cluster_depth: int = 2,
) -> list[FeatureCluster]:
    """Group new/unmatched files by shared ancestor directory.

    Groups files that share the same directory prefix at cluster_depth levels
    (e.g. 'packages/fta_web' groups all files under packages/fta_web/...).
    Single-file directories still form their own cluster.
    """
    if not new_paths:
        return []

    # Group by ancestor dir at cluster_depth
    dir_groups: dict[str, list[str]] = {}
    for path in new_paths:
        parts = PurePosixPath(path).parts
        if len(parts) >= cluster_depth + 1:
            ancestor = "/".join(parts[:cluster_depth + 1])
        elif len(parts) >= 2:
            ancestor = "/".join(parts[:2])
        else:
            ancestor = parts[0] if parts else ""
        dir_groups.setdefault(ancestor, []).append(path)

    clusters: list[FeatureCluster] = []
    for base_dir, files in sorted(dir_groups.items()):
        cluster_suggestions = [s for s in suggestions if s.source_path in files]
        clusters.append(
            FeatureCluster(
                base_dir=base_dir,
                files=sorted(files),
                file_count=len(files),
                has_suggestions=bool(cluster_suggestions),
                suggestions=cluster_suggestions,
            )
        )
    return clusters


def classify_changes(
    git_entries: list[ChangedFile],
    source_to_wiki: dict[str, list[str]],
    old_commit: str,
    new_commit: str,
    total_count: int | None = None,
    repo_prefix: str = "",
) -> ChangeReport:
    report = ChangeReport(
        old_commit=old_commit,
        new_commit=new_commit,
        total_count=total_count if total_count is not None else len(git_entries),
        filtered_count=len(git_entries),
    )
    report.excluded_count = max(report.total_count - report.filtered_count, 0)

    for entry in git_entries:
        match_path = entry.old_path if entry.status == "R" and entry.old_path else entry.path
        result = three_level_match(match_path, source_to_wiki)
        result.status = entry.status
        result.old_path = entry.old_path
        if result.level == "exact":
            report.exact_hits.append(result)
        elif result.level == "dirname":
            report.dirname_hits.append(result)
        elif result.level == "parent":
            report.parent_hits.append(result)
        elif entry.status in ("A", "C", "R"):
            report.new_features.append(entry.path)
        else:
            report.unmatched.append(f"{entry.path} ({entry.status})")
    # Run pattern inference on new features to suggest wiki placements
    new_paths: list[str] = []
    if any(e.status in ("A", "C", "R") for e in git_entries):
        new_paths = [e.path for e in git_entries if e.status in ("A", "C", "R") and three_level_match(e.path, source_to_wiki).level == "none"]
        if new_paths:
            suggestions, unmatched_new = suggest_placements_batch(
                new_paths, source_to_wiki, repo_prefix=repo_prefix
            )
            report.suggested_placements = suggestions
            report.unmatched_new = unmatched_new
    # Cluster new files by shared directory for AI feature analysis
    report.feature_clusters = _cluster_new_files(
        new_paths,
        report.suggested_placements,
    )
    return report


def lookup_wikis(
    source_to_wiki: dict[str, list[str]],
    files: list[str],
) -> tuple[list[tuple[str, int, list[str]]], list[str]]:
    """Given a list of file paths, return ranked wiki pages sorted by hit count.

    Returns:
        (ranked, unmatched) where ranked is list of (wiki_path, hit_count, matched_files)
        sorted by hit_count descending, and unmatched is list of file paths not in source_to_wiki.
    """
    wiki_hits: dict[str, list[str]] = {}
    unmatched: list[str] = []
    for f in files:
        if f in source_to_wiki:
            for wiki in source_to_wiki[f]:
                wiki_hits.setdefault(wiki, []).append(f)
        else:
            unmatched.append(f)
    ranked = sorted(
        [(wiki, len(hits), sorted(hits)) for wiki, hits in wiki_hits.items()],
        key=lambda x: x[1],
        reverse=True,
    )
    return ranked, unmatched


def format_lookup(ranked: list[tuple[str, int, list[str]]], input_summary: str = "", unmatched: list[str] | None = None) -> str:
    """Format ranked wiki lookup results."""
    lines: list[str] = []
    if input_summary:
        lines.append(input_summary)
        lines.append("")
    if not ranked:
        lines.append("未找到相关 Wiki 页面。")
        if unmatched:
            lines.append("")
            lines.append(f"未匹配文件 ({len(unmatched)}):")
            lines.extend(f"  - {f}" for f in unmatched)
        return "\n".join(lines)
    lines.append(f"共 {len(ranked)} 篇 Wiki 页面受影响：")
    lines.append("")
    for wiki, count, matched in ranked:
        file_list = ", ".join(matched) if len(matched) <= 3 else ", ".join(matched[:3]) + f" ... +{len(matched) - 3}"
        lines.append(f"  [{count:>3} 文件]  {wiki}")
        lines.append(f"          ↳ {file_list}")
        lines.append("")
    if unmatched:
        lines.append(f"未匹配文件 ({len(unmatched)}):")
        lines.extend(f"  - {f}" for f in unmatched)
    return "\n".join(lines)


def detect_changes(old_commit: str, new_commit: str, metadata: dict, repo_dir: str = ".") -> ChangeReport:
    source_to_wiki = metadata.get("source_to_wiki") or {}
    if not source_to_wiki:
        raise ValueError("metadata.json does not contain source_to_wiki; run build-index first")
    repo_prefix = metadata.get("repo_prefix", "")
    all_entries = run_git_diff(old_commit, new_commit, metadata, repo_dir, apply_filters=False)
    filtered_entries = run_git_diff(old_commit, new_commit, metadata, repo_dir, apply_filters=True)
    return classify_changes(filtered_entries, source_to_wiki, old_commit, new_commit, len(all_entries), repo_prefix=repo_prefix)


def report_to_dict(report: ChangeReport) -> dict:
    data = asdict(report)
    data["affected_wikis"] = report.affected_wikis
    return data


def format_report(report: ChangeReport) -> str:
    lines = [
        f"Wiki incremental change analysis ({report.old_commit} -> {report.new_commit})",
        "",
        f"Changed files: {report.filtered_count} (excluded {report.excluded_count}, total {report.total_count})",
        f"Affected wiki pages: {len(report.affected_wikis)}",
        "",
    ]
    rows: list[tuple[str, str, str]] = []
    for label, group in (
        ("[精确]", report.exact_hits),
        ("[dirname]", report.dirname_hits),
        ("[父目录]", report.parent_hits),
    ):
        for item in group:
            for wiki in item.wiki_paths:
                rows.append((label, wiki, item.changed_file))
    if rows:
        lines.extend(["| 级别 | Wiki 页面 | 变更文件 |", "|------|-----------|----------|"])
        lines.extend(f"| {level} | {wiki} | {path} |" for level, wiki, path in rows)
        lines.append("")
    if report.new_features:
        lines.append(f"新功能文件 ({len(report.new_features)}):")
        lines.extend(f"- {path}" for path in report.new_features)
        lines.append("")
    if report.feature_clusters:
        lines.append(f"新功能文件簇 ({len(report.feature_clusters)}):")
        lines.append("| 基础目录 | 文件数 | 可推断 | 文件列表 |")
        lines.append("|----------|--------|--------|----------|")
        for fc in report.feature_clusters:
            files_preview = ", ".join(fc.files[:5])
            if len(fc.files) > 5:
                files_preview += f" ... +{len(fc.files) - 5}"
            lines.append(
                f"| {fc.base_dir} | {fc.file_count} | {'✓' if fc.has_suggestions else '✗'} | {files_preview} |"
            )
        lines.append("")
    if report.suggested_placements:
        lines.append(f"可推断放置位置 ({len(report.suggested_placements)}):")
        lines.append("| 源文件 | 建议 Wiki 目录 | 置信度 | 策略 | 关联页面 |")
        lines.append("|--------|---------------|--------|------|----------|")
        for s in report.suggested_placements:
            related = ", ".join(s.related_wikis[:2])
            if len(s.related_wikis) > 2:
                related += f" (+{len(s.related_wikis) - 2})"
            lines.append(
                f"| {s.source_path} | {s.suggested_wiki_dir} | {s.confidence}% | {s.strategy} | {related or '-'} |"
            )
        lines.append("")
    if report.unmatched_new:
        lines.append(f"需人工判断 ({len(report.unmatched_new)}):")
        lines.extend(f"- {path}" for path in report.unmatched_new)
        lines.append("")
    if report.unmatched:
        lines.append(f"未覆盖变更 ({len(report.unmatched)}):")
        lines.extend(f"- {path}" for path in report.unmatched)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect wiki pages affected by a commit range.")
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--new-commit", required=True)
    parser.add_argument("--old-commit")
    parser.add_argument("--repo-dir", default=".")
    args = parser.parse_args(argv)

    metadata = load_json(args.metadata)
    old_commit = args.old_commit or metadata.get("source", {}).get("commit_id")
    if not old_commit:
        raise SystemExit("old commit is required or metadata.source.commit_id must exist")
    report = detect_changes(old_commit, args.new_commit, metadata, args.repo_dir)
    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
