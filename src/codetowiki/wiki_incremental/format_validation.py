# -*- coding: utf-8 -*-
"""Lightweight wiki format validation and mechanical fixes."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Sections explicitly marked as having no source are exempt from R3 (must be
# kept in sync with wiki_format_check.NO_SOURCE_NOTE_RE).
NO_SOURCE_NOTE_RE = re.compile(r"无\s*[“\"]?章节来源[”\"]?|本节为概念性内容|不直接分析具体文件")
SECTION_SOURCE_RE = re.compile(r"^\*{0,2}章节来源\*{0,2}\s*$", re.MULTILINE)
SOURCE_HEADER_RE = re.compile(r"^\*{0,2}(章节来源|图表来源|图示来源)\*{0,2}\s*$", re.MULTILINE)
EXEMPT_SECTIONS = {"目录"}


def section_needs_source(title: str, block: str) -> bool:
    """Whether a wiki section block is missing its 章节来源 marker.

    Shared by the validator (R3 check) and the auto-fixer so the two never
    drift apart. A section is exempt if it is the 目录, contains an explicit
    "no source" note, or already has a 章节来源 heading.
    """
    if title in EXEMPT_SECTIONS:
        return False
    if NO_SOURCE_NOTE_RE.search(block):
        return False
    if SECTION_SOURCE_RE.search(block):
        return False
    return True


@dataclass
class Violation:
    rule: str
    message: str
    fixed: bool


def _has_cite_block(content: str) -> bool:
    return bool(re.search(r"<cite>.*?</cite>", content, re.DOTALL))


def _add_cite(content: str) -> str:
    cite = "\n<cite>\n**本文引用的文件**\n</cite>\n"
    if re.search(r"\n## ", content):
        return re.sub(r"(\n## )", cite + r"\1", content, count=1)
    return content.rstrip() + cite + "\n"


def _fix_missing_file_scheme(content: str) -> str:
    def repl(match: re.Match[str]) -> str:
        label, path = match.group(1), match.group(2)
        if path.startswith(("file://", "#", "http://", "https://", "mailto:")):
            return match.group(0)
        # Builder ENTRY_RE only matches file://...; any other entry would be
        # silently dropped from the index, so prefix it.
        return f"- [{label}](file://{path})"

    return re.sub(r"^- \[([^\]]+)\]\(([^)]+)\)\s*$", repl, content, flags=re.MULTILINE)


def _toc_titles(content: str) -> list[str]:
    toc = re.search(r"^## 目录\n((?:.*\n)*?)(?=^## |\Z)", content, re.MULTILINE)
    if not toc:
        return []
    return re.findall(r"\[([^\]]+)\]\(#[^)]+\)", toc.group(1))


def _headings(content: str) -> list[str]:
    return [h for h in re.findall(r"^## (.+)$", content, re.MULTILINE) if h != "目录"]


def _section_blocks(content: str) -> list[tuple[str, int, int, str]]:
    matches = list(re.finditer(r"^## (.+)$", content, re.MULTILINE))
    blocks: list[tuple[str, int, int, str]] = []
    for idx, match in enumerate(matches):
        title = match.group(1)
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        blocks.append((title, match.start(), end, content[match.start() : end]))
    return blocks


def _fix_section_sources(content: str) -> tuple[str, list[str]]:
    missing: list[str] = []
    for title, _start, end, block in reversed(_section_blocks(content)):
        if not section_needs_source(title, block):
            continue
        missing.append(title)
        insert = "\n章节来源\n"
        content = content[:end].rstrip() + insert + content[end:]
    missing.reverse()
    return content, missing


def _fix_chart_sources(content: str) -> tuple[str, int]:
    count = 0
    for match in reversed(list(re.finditer(r"```mermaid\n.*?```", content, re.DOTALL))):
        following = content[match.end() : match.end() + 200]
        if re.search(r"^\s*\*{0,2}(图表来源|图示来源)\*{0,2}\s*$", following, re.MULTILINE):
            continue
        content = content[: match.end()] + "\n\n图表来源\n" + content[match.end() :]
        count += 1
    return content, count


def _to_anchor(title: str) -> str:
    """Turn a section title into a safe in-page anchor.

    Chinese text and alphanumeric characters are passed through;
    parentheses and other markdown-link-breaking characters are removed.
    """
    return title.replace("#", "").replace("(", "").replace(")", "").replace("[", "").replace("]", "").strip()


def _fix_toc(content: str) -> str:
    headings = _headings(content)
    if not headings:
        return content
    toc_block = "## 目录\n" + "\n".join(f"{idx}. [{title}](#{_to_anchor(title)})" for idx, title in enumerate(headings, 1)) + "\n"
    if re.search(r"^## 目录\n", content, re.MULTILINE):
        return re.sub(r"^## 目录\n(?:.*\n)*?(?=^## |\Z)", toc_block + "\n", content, count=1, flags=re.MULTILINE)
    return re.sub(r"(?=^## )", toc_block + "\n", content, count=1, flags=re.MULTILINE)


MAX_FIX_ROUNDS = 3


def _validate_one_round(wiki_content: str) -> tuple[str, list[Violation]]:
    """Single-pass R1/R5/R3/R4/R2 validation and fixing."""
    content = wiki_content
    violations: list[Violation] = []

    if not _has_cite_block(content):
        violations.append(Violation("R1", "缺少 cite 标签", True))
        content = _add_cite(content)

    fixed_refs = _fix_missing_file_scheme(content)
    if fixed_refs != content:
        violations.append(Violation("R5", "引用缺少 file:// 前缀", True))
        content = fixed_refs

    content, missing_sections = _fix_section_sources(content)
    if missing_sections:
        violations.append(Violation("R3", f"缺少章节来源: {missing_sections}", True))

    content, missing_charts = _fix_chart_sources(content)
    if missing_charts:
        violations.append(Violation("R4", f"缺少图表来源: {missing_charts}", True))

    headings = _headings(content)
    toc_titles = _toc_titles(content)
    if toc_titles and toc_titles != headings:
        violations.append(Violation("R2", "目录与章节不一致", True))
        content = _fix_toc(content)

    return content, violations


def validate_and_fix(wiki_content: str) -> tuple[str, list[Violation]]:
    """R1-R5 multi-round validation; up to 3 rounds to converge cascading fixes.

    R6 (#Lx-Ly 行号) 无法机械修复，需人工核对源码补全。
    """
    content = wiki_content
    all_violations: list[Violation] = []

    for _ in range(MAX_FIX_ROUNDS):
        content, round_violations = _validate_one_round(content)
        all_violations.extend(round_violations)
        if not round_violations:
            break

    return content, all_violations
