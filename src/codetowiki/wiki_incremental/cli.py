# -*- coding: utf-8 -*-
"""Command line entrypoint for wiki incremental update helpers."""

from __future__ import annotations

import argparse
import subprocess

from . import change_detection, index_builder
from .json_utils import load_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wiki-incremental", description="Wiki incremental update helpers (reference index)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-index", help="Build source/wiki indexes into metadata.json")
    build_parser.add_argument("--wiki-dir", required=True)
    build_parser.add_argument("--commit")
    build_parser.add_argument("--repo-dir", default=".")
    build_parser.add_argument("--repo-url", default="")
    build_parser.add_argument("--branch", default="")
    build_parser.add_argument("--repo-prefix", default="")
    build_parser.add_argument("--metadata")
    build_parser.add_argument("--output")

    detect_parser = subparsers.add_parser("detect", help="Detect wiki pages affected by a commit range")
    detect_parser.add_argument("--metadata", required=True)
    detect_parser.add_argument("--new-commit", required=True)
    detect_parser.add_argument("--old-commit")
    detect_parser.add_argument("--repo-dir", default=".")

    lookup_parser = subparsers.add_parser("lookup", help="Ranked wiki lookup by file paths or commit")
    lookup_parser.add_argument("--metadata", required=True)
    lookup_parser.add_argument("--files", nargs="*", default=[], help="File paths to look up")
    lookup_parser.add_argument("--new-commit", help="New commit hash (diff against parent or --old-commit)")
    lookup_parser.add_argument("--old-commit", help="Old commit hash for range comparison")
    lookup_parser.add_argument("--repo-dir", default=".")

    args = parser.parse_args(argv)
    if args.command == "build-index":
        return index_builder.main(
            [
                "--wiki-dir",
                args.wiki_dir,
                "--repo-dir",
                args.repo_dir,
                *(["--commit", args.commit] if args.commit else []),
                *(["--repo-url", args.repo_url] if args.repo_url else []),
                *(["--branch", args.branch] if args.branch else []),
                *(["--repo-prefix", args.repo_prefix] if args.repo_prefix else []),
                *(["--metadata", args.metadata] if args.metadata else []),
                *(["--output", args.output] if args.output else []),
            ]
        )
    if args.command == "detect":
        return change_detection.main(
            [
                "--metadata",
                args.metadata,
                "--new-commit",
                args.new_commit,
                "--repo-dir",
                args.repo_dir,
                *(["--old-commit", args.old_commit] if args.old_commit else []),
            ]
        )
    if args.command == "lookup":
        return _run_lookup(args)
    return 1


def _run_lookup(args: argparse.Namespace) -> int:
    metadata = load_json(args.metadata)
    source_to_wiki = metadata.get("source_to_wiki") or {}
    if not source_to_wiki:
        raise SystemExit("metadata.json does not contain source_to_wiki; run build-index first")

    files: list[str] = list(args.files) if args.files else []
    summary_parts: list[str] = []

    if args.new_commit:
        old = args.old_commit or f"{args.new_commit}~1"
        result = subprocess.run(
            ["git", "--no-pager", "diff", "--name-only", f"{old}..{args.new_commit}"],
            cwd=args.repo_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(result.stderr.strip() or "git diff failed")
        commit_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
        summary_parts.append(f"commit {old}..{args.new_commit}: {len(commit_files)} 个文件")
        files.extend(commit_files)

    # 去重：同一文件可能同时出现在 --files 和 commit diff 中
    files = list(dict.fromkeys(files)) if files else files

    if not args.new_commit and not files:
        raise SystemExit("必须提供 --files 或 --new-commit")
    if files and args.new_commit and args.files:
        summary_parts.insert(0, f"指定文件: {len(args.files)} 个")
    elif not args.new_commit:
        summary_parts.append(f"指定文件: {len(files)} 个")
    summary = " + ".join(summary_parts)

    ranked, unmatched = change_detection.lookup_wikis(source_to_wiki, files)
    print(change_detection.format_lookup(ranked, summary, unmatched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
