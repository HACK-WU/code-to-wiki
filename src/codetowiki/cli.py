"""Unified command line entrypoint for CodeToWiki.

Subcommands:
    build-index   Build the source<->wiki reference index into metadata.json
    detect        Detect wiki pages affected by a commit range
    lookup        Ranked wiki lookup by file paths or commit
    wiki-format   Check (or auto-fix) wiki markdown against the R1-R6 format spec
    init          Scaffold a metadata.json skeleton for a new project
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import __version__
from .wiki_incremental import cli as inc_cli
from .wiki_incremental.index_builder import DEFAULT_EXCLUDED_PATHS, DEFAULT_NOISE_PATHS
from .wiki_incremental.json_utils import atomic_save_json, load_json
from .wiki_incremental.citation_cleanup import cleanup_dead_citations
from .wiki_incremental.incremental_index import incremental_index_update, save_metadata
from .wiki_format_check import main as format_main


def _cmd_init(args: argparse.Namespace) -> int:
    output = Path(args.output)
    skeleton = {
        "project": args.project_name,
        "wiki_path": args.wiki_dir,
        "excluded_paths": list(DEFAULT_EXCLUDED_PATHS),
        "noise_paths": list(DEFAULT_NOISE_PATHS),
        "source": {
            "repo_url": args.repo_url or "",
            "branch": args.branch or "",
            "commit_id": "",
        },
        "source_to_wiki": {},
        "wiki_to_source": {},
        "repo_prefix": args.repo_prefix,
        "stats": {},
    }
    atomic_save_json(skeleton, output)
    print(f"已生成 metadata 骨架: {output}")
    print(f"  project      : {args.project_name}")
    print(f"  wiki_dir     : {args.wiki_dir}")
    print(f"  excluded_paths: {len(DEFAULT_EXCLUDED_PATHS)} 条默认规则")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="codetowiki", description="CodeToWiki: code -> indexed wiki (reference index)"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the codetowiki version and exit",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build-index / detect / lookup delegate to the incremental helper CLI
    for name, help_text in (
        ("build-index", "Build source/wiki indexes into metadata.json"),
        ("detect", "Detect wiki pages affected by a commit range"),
        ("lookup", "Ranked wiki lookup by file paths or commit"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--metadata", required=(name != "build-index"))
        sub.add_argument("--wiki-dir")
        sub.add_argument("--commit")
        sub.add_argument("--repo-dir", default=".")
        sub.add_argument("--repo-url", default="")
        sub.add_argument("--branch", default="")
        sub.add_argument("--repo-prefix", default="")
        sub.add_argument("--output")
        sub.add_argument("--new-commit")
        sub.add_argument("--old-commit")
        sub.add_argument("--files", nargs="*", default=[])

    fmt_parser = subparsers.add_parser("wiki-format", help="Check/fix wiki markdown (R1-R6)")
    fmt_group = fmt_parser.add_mutually_exclusive_group(required=True)
    fmt_group.add_argument("--wiki-dir", help="待检查的 wiki 目录（递归扫描 *.md）")
    fmt_group.add_argument("--file", help="待检查的单个 wiki 文件")
    fmt_parser.add_argument("--fix", action="store_true")
    fmt_parser.add_argument("--strict", action="store_true")
    fmt_parser.add_argument("--json", action="store_true")

    init_parser = subparsers.add_parser("init", help="Scaffold a metadata.json skeleton")
    init_parser.add_argument("--project-name", required=True, help="Project name")
    init_parser.add_argument("--wiki-dir", required=True, help="Wiki document directory")
    init_parser.add_argument("--repo-url", default="", help="Source code repository URL")
    init_parser.add_argument("--branch", default="", help="Source code branch name")
    init_parser.add_argument(
        "--repo-prefix", default="", help="Optional leading path to strip when inferring wiki placement"
    )
    init_parser.add_argument("--output", default="metadata.json", help="Output metadata.json path")

    cc_parser = subparsers.add_parser("cleanup-citations", help="Clean dead/renamed source citations from a wiki file")
    cc_parser.add_argument("--file", required=True, help="Wiki markdown file to clean")
    cc_parser.add_argument(
        "--dead", nargs="*", default=[], help="Deleted source paths whose citations should be removed"
    )
    cc_parser.add_argument(
        "--renamed", nargs="*", default=[], help="Renamed source paths as old:new (replace citation paths)"
    )
    cc_parser.add_argument("--output", default=None, help="Output file (default: overwrite --file)")

    si_parser = subparsers.add_parser("sync-index", help="Incrementally sync metadata indexes for affected wikis")
    si_parser.add_argument("--metadata", required=True, help="Path to metadata.json")
    si_parser.add_argument("--wiki-dir", required=True, help="Wiki document directory")
    si_parser.add_argument("--wikis", nargs="+", required=True, help="Affected wiki files to re-index")
    si_parser.add_argument("--commit", required=True, help="New commit id to record in metadata.source.commit_id")
    si_parser.add_argument("--output", default=None, help="Output metadata path (default: overwrite --metadata)")

    args = parser.parse_args(argv)
    cmd = args.command

    if cmd in ("build-index", "detect", "lookup"):
        inc_argv = [cmd]
        if getattr(args, "metadata", None):
            inc_argv += ["--metadata", args.metadata]
        if getattr(args, "wiki_dir", None):
            inc_argv += ["--wiki-dir", args.wiki_dir]
        if getattr(args, "repo_dir", None):
            inc_argv += ["--repo-dir", args.repo_dir]
        if getattr(args, "commit", None):
            inc_argv += ["--commit", args.commit]
        if getattr(args, "repo_url", None):
            inc_argv += ["--repo-url", args.repo_url]
        if getattr(args, "branch", None):
            inc_argv += ["--branch", args.branch]
        if getattr(args, "repo_prefix", None):
            inc_argv += ["--repo-prefix", args.repo_prefix]
        if getattr(args, "output", None):
            inc_argv += ["--output", args.output]
        if getattr(args, "new_commit", None):
            inc_argv += ["--new-commit", args.new_commit]
        if getattr(args, "old_commit", None):
            inc_argv += ["--old-commit", args.old_commit]
        if getattr(args, "files", None):
            inc_argv += ["--files", *args.files]
        return inc_cli.main(inc_argv)

    if cmd == "wiki-format":
        fmt_argv = []
        if args.wiki_dir:
            fmt_argv += ["--wiki-dir", args.wiki_dir]
        if args.file:
            fmt_argv += ["--file", args.file]
        if args.fix:
            fmt_argv.append("--fix")
        if args.strict:
            fmt_argv.append("--strict")
        if args.json:
            fmt_argv.append("--json")
        return format_main(fmt_argv)

    if cmd == "cleanup-citations":
        content = Path(args.file).read_text(encoding="utf-8")
        renamed = {}
        for item in args.renamed:
            old, _, new = item.partition(":")
            if old and new:
                renamed[old] = new
        cleaned = cleanup_dead_citations(content, dead_files=list(args.dead), renamed_files=renamed)
        out = args.output or args.file
        Path(out).write_text(cleaned, encoding="utf-8")
        print(f"已清理引用: {out}")
        return 0

    if cmd == "sync-index":
        metadata = load_json(args.metadata)
        updated = incremental_index_update(metadata, args.wikis, args.commit, args.wiki_dir)
        out = args.output or args.metadata
        save_metadata(updated, out)
        print(f"已同步索引: {out}")
        return 0

    if cmd == "init":
        return _cmd_init(args)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
