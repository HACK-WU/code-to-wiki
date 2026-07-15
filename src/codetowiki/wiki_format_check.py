# -*- coding: utf-8 -*-
"""Check wiki markdown files against the format spec (R1-R6).

The wiki format requirements are defined in
`skills/code-to-wiki/SKILL.md` (Wiki 格式规范 / 格式自检规则 R1-R6):

    R1  顶部必须有 <cite> 块
    R2  目录条目与 ## 章节一致
    R3  每个章节后需有「章节来源」
    R4  图/表后需有「图示来源」/「图表来源」
    R5  引用路径必须 file:// 前缀
    R6  引用行号区间 #Lx-Ly 准确

This script is a read-only checker by default. It walks the wiki directory
(like `index_builder.iter_markdown_files`), collects violations per file with
line numbers and severities, prints a report, and exits non-zero when errors
are found (useful as a pre-commit / CI gate).

Optional `--fix` reuses the mechanical fixes from
`codetowiki.wiki_incremental.format_validation` (R1/R2/R3/R4/R5 auto-fix; R6 行号
需人工补全) when the package is importable (run with `python -m codetowiki.wiki_format_check`).
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from codetowiki.wiki_incremental.format_validation import (
    SOURCE_HEADER_RE,
    section_needs_source,
)

# ---------------------------------------------------------------------------
# Regexes (kept close to index_builder.py / format_validation.py conventions)
# ---------------------------------------------------------------------------
CITE_RE = re.compile(r"<cite>.*?</cite>", re.DOTALL)
HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)
ENTRY_RE = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\)\s*$", re.MULTILINE)
MERMAID_RE = re.compile(r"```mermaid\n.*?```", re.DOTALL)
TOC_HEADING_RE = re.compile(r"^## 目录\s*$", re.MULTILINE)
TOP_TOC_RE = re.compile(r"^\s*[-*]?\s*\[[^\]]+\]\(#[^)]+\)\s*$", re.MULTILINE)
ANCHOR_LINK_RE = re.compile(r"\[([^\]]+)\]\(#[^)]+\)")

# Source-code style extensions that are expected to carry a `#Lx-Ly` range.
SOURCE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".go", ".java", ".sh",
    ".sql", ".html", ".css", ".rs", ".c", ".cpp", ".h", ".rb", ".php",
    ".yaml", ".yml", ".toml", ".json", ".md",
}

# Sections that are allowed to omit 章节来源 even under strict checking.
@dataclass(frozen=True)
class Violation:
    rule: str
    severity: str  # "error" | "warning"
    line: int
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def iter_markdown_files(wiki_dir: str | Path) -> Iterable[Path]:
    root = Path(wiki_dir)
    yield from sorted(p for p in root.rglob("*.md") if p.is_file())


def _line_of(content: str, pos: int) -> int:
    return content.count("\n", 0, pos) + 1


def _section_blocks(content: str) -> list[tuple[str, int, int, str]]:
    """Split content into (title, start, end, block) per `## ` heading."""
    matches = list(HEADING_RE.finditer(content))
    blocks: list[tuple[str, int, int, str]] = []
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        blocks.append((title, match.start(), end, content[match.start():end]))
    return blocks


def _source_block_end(content: str, start: int) -> int:
    """End of a 章节来源/图表来源 block.

    Mirrors ``index_builder._source_block_end`` so the checker's notion of a
    source-block extent matches what the builder actually indexes: the block
    ends at the next heading, ``<cite>``, or any line ending in "来源".
    """
    nxt = re.search(r"^(?:#{1,6} |\S.*来源\s*$|<cite>)", content[start:], re.MULTILINE)
    return start + nxt.start() if nxt else len(content)


def _toc_titles(content: str) -> list[str]:
    """Return TOC entry titles if a table of contents is present, else []."""
    # Case 1: a dedicated `## 目录` section.
    m = TOC_HEADING_RE.search(content)
    if m:
        end = re.search(r"^## ", content[m.end():], re.MULTILINE)
        block = content[m.end(): m.end() + (end.start() if end else len(content))]
        return [g for g in ANCHOR_LINK_RE.findall(block)]
    # Case 2: an inline anchor-link list between the cite block and the first `## `.
    cite_end = 0
    cite = CITE_RE.search(content)
    if cite:
        cite_end = cite.end()
    head = HEADING_RE.search(content[cite_end:])
    region = content[cite_end: cite_end + (head.start() if head else len(content))]
    links = TOP_TOC_RE.findall(region)
    if len(links) >= 2:
        return [g for g in ANCHOR_LINK_RE.findall(region)]
    return []


# ---------------------------------------------------------------------------
# Per-file checks
# ---------------------------------------------------------------------------
def _check_r1(content: str) -> list[Violation]:
    if CITE_RE.search(content):
        return []
    return [Violation("R1", "error", 1, "缺少 <cite> 引用块（应位于标题之后）")]


def _check_r2(content: str) -> list[Violation]:
    toc = _toc_titles(content)
    if not toc:
        return []
    headings = [t for t in (m.group(1).strip() for m in HEADING_RE.finditer(content)) if t != "目录"]
    toc_set, head_set = set(toc), set(headings)
    violations: list[Violation] = []
    missing_in_toc = head_set - toc_set
    extra_in_toc = toc_set - head_set
    if missing_in_toc:
        violations.append(Violation("R2", "error", 1, f"目录缺少章节: {sorted(missing_in_toc)}"))
    if extra_in_toc:
        violations.append(Violation("R2", "error", 1, f"目录存在多余条目: {sorted(extra_in_toc)}"))
    return violations


def _check_r3(content: str) -> list[Violation]:
    violations: list[Violation] = []
    for title, start, _end, block in _section_blocks(content):
        if section_needs_source(title, block):
            violations.append(Violation("R3", "warning", _line_of(content, start),
                                       f"章节「{title}」缺少「章节来源」"))
    return violations


def _check_r4(content: str) -> list[Violation]:
    violations: list[Violation] = []
    for m in MERMAID_RE.finditer(content):
        following = content[m.end(): m.end() + 300]
        if not re.search(r"^\s*\*{0,2}(图表来源|图示来源)\*{0,2}\s*$", following, re.MULTILINE):
            violations.append(Violation("R4", "error", _line_of(content, m.start()),
                                       "Mermaid 图后缺少「图表来源」/「图示来源」"))
    return violations


def _iter_source_entries(content: str):
    """Yield (match, path, line, in_cite) for citation entries.

    `in_cite` is True for entries inside the top-level <cite> summary block,
    False for entries inside 章节来源/图表来源 detailed source blocks.
    """
    for block in CITE_RE.finditer(content):
        for e in ENTRY_RE.finditer(block.group(0)):
            yield e, e.group(2), _line_of(content, block.start() + e.start()), True
    for header in SOURCE_HEADER_RE.finditer(content):
        end = _source_block_end(content, header.end())
        for e in ENTRY_RE.finditer(content[header.end():end]):
            yield e, e.group(2), _line_of(content, header.end() + e.start()), False


def _check_r5(content: str) -> list[Violation]:
    violations: list[Violation] = []
    for _e, path, line, _in_cite in _iter_source_entries(content):
        if path.startswith(("file://", "#", "http://", "https://", "mailto:")):
            continue
        # Any remaining entry lacks the file:// scheme the builder requires
        # (builder ENTRY_RE only matches `file://...`), so it won't be indexed.
        violations.append(Violation("R5", "error", line, f"引用缺少 file:// 前缀: {path}"))
    return violations


def _check_r6(content: str) -> list[Violation]:
    violations: list[Violation] = []
    for _e, path, line, in_cite in _iter_source_entries(content):
        if in_cite:
            # The top <cite> block is a path-only summary list by convention.
            continue
        clean = path.split("#", 1)[0].strip()
        if clean.endswith("/"):  # directory, no line range applicable
            continue
        if not clean.lower().endswith(tuple(SOURCE_EXT)):
            continue
        if "#L" not in path:
            violations.append(Violation("R6", "warning", line, f"引用缺少行号区间 #Lx-Ly: {clean}"))
    return violations


def check_content(content: str) -> list[Violation]:
    violations: list[Violation] = []
    violations += _check_r1(content)
    violations += _check_r2(content)
    violations += _check_r3(content)
    violations += _check_r4(content)
    violations += _check_r5(content)
    violations += _check_r6(content)
    return violations


def check_file(path: str | Path) -> list[Violation]:
    try:
        content = Path(path).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        return [Violation("R0", "error", 1, f"无法读取文件: {exc}")]
    return check_content(content)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def _format_report(results: dict[str, list[Violation]], strict: bool) -> str:
    total = len(results)
    passed = sum(1 for v in results.values() if not v)
    errors = sum(1 for v in results.values() for x in v if x.severity == "error")
    warns = sum(1 for v in results.values() for x in v if x.severity == "warning")

    lines = ["Wiki 格式检查报告", "=" * 40]
    lines.append(f"文件总数: {total}    ✅ 通过: {passed}    ❌ 错误: {errors}    ⚠️ 警告: {warns}")
    lines.append("")

    icon = {"error": "❌", "warning": "⚠️"}
    for path in sorted(results):
        vs = results[path]
        if not vs:
            continue
        lines.append(f"📄 {path}")
        for v in sorted(vs, key=lambda x: (x.severity != "error", x.line)):
            lines.append(f"   {icon[v.severity]} {v.rule} (行 {v.line}): {v.message}")
        lines.append("")

    if not any(results.values()):
        lines.append("全部文件格式合规 ✅")
    else:
        lines.append("说明: ❌ 错误会令退出码非 0（CI 门禁）；⚠️ 警告默认不阻断，"
                     "可用 --strict 一并视为失败。")
    return "\n".join(lines)


def _try_fix(path: Path, content: str) -> tuple[bool, str]:
    try:
        from codetowiki.wiki_incremental.format_validation import validate_and_fix
    except Exception:  # pragma: no cover - optional dependency
        return False, "（--fix 需要 codetowiki 包，请先安装：pip install codetowiki）"
    fixed, _violations = validate_and_fix(content)
    if fixed != content:
        path.write_text(fixed, encoding="utf-8")
        return True, "已应用机械修复（R1/R2/R3/R4/R5；R6 行号需人工补全）"
    return False, "无需修复"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check wiki format (R1-R6).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--wiki-dir", help="待检查的 wiki 目录（递归扫描 *.md）")
    group.add_argument("--file", help="待检查的单个 wiki 文件")
    parser.add_argument("--fix", action="store_true", help="自动修复可机械修复的问题（需 codetowiki 包）")
    parser.add_argument("--strict", action="store_true", help="警告也视为失败（退出码非 0）")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    args = parser.parse_args(argv)

    results: dict[str, list[Violation]] = {}
    if args.file:
        p = Path(args.file)
        rel = p.as_posix()
        results[rel] = check_file(p)
        if args.fix and results[rel]:
            changed, note = _try_fix(p, p.read_text(encoding="utf-8"))
            results[rel] = check_file(p)  # re-check after fix
            if changed:
                print(f"[fix] {rel}: {note}")
    else:
        for p in iter_markdown_files(args.wiki_dir):
            rel = p.relative_to(args.wiki_dir).as_posix()
            results[rel] = check_file(p)
            if args.fix and results[rel]:
                changed, note = _try_fix(p, p.read_text(encoding="utf-8"))
                results[rel] = check_file(p)
                if changed:
                    print(f"[fix] {rel}: {note}")

    if args.json:
        payload = {
            path: [
                {"rule": v.rule, "severity": v.severity, "line": v.line, "message": v.message}
                for v in vs
            ]
            for path, vs in sorted(results.items())
        }
        sys.stdout.write(__import__("json").dumps(payload, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
    else:
        print(_format_report(results, args.strict))

    has_error = any(v.severity == "error" for vs in results.values() for v in vs)
    has_warn = any(v.severity == "warning" for vs in results.values() for v in vs)

    if has_error:
        return 1
    if args.strict and has_warn:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
