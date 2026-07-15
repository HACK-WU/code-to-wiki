# -*- coding: utf-8 -*-
"""Clean stale source citations from wiki markdown."""

from __future__ import annotations

import os
import re


def cleanup_dead_citations(
    wiki_content: str,
    dead_files: list[str],
    renamed_files: dict[str, str],
) -> str:
    result = wiki_content
    for dead_path in dead_files:
        pattern = re.compile(
            r"^- \[[^\]]+\]\(file://" + re.escape(dead_path) + r"(?:#[^)]*)?\)\s*\n?",
            re.MULTILINE,
        )
        result = pattern.sub("", result)

    for old_path, new_path in renamed_files.items():
        path_pattern = re.compile(r"(file://)" + re.escape(old_path) + r"(#[^)]*)?")
        result = path_pattern.sub(lambda m: f"{m.group(1)}{new_path}{m.group(2) or ''}", result)
        old_name = os.path.basename(old_path)
        new_name = os.path.basename(new_path)
        # 替换完整路径名称（如 - [src/module/views.py](file://...)）
        # 无论 basename 是否变化，全路径名始终需要替换
        fullname_pattern = re.compile(r"(^- \[)" + re.escape(old_path) + r"((?::[^\]]+)?\]\(file://)", re.MULTILINE)
        result = fullname_pattern.sub(lambda m: f"{m.group(1)}{new_path}{m.group(2)}", result)
        if old_name != new_name:
            # 替换仅 basename 的名称（如 - [views.py](file://...)）
            name_pattern = re.compile(r"(^- \[)" + re.escape(old_name) + r"((?::[^\]]+)?\]\(file://)", re.MULTILINE)
            result = name_pattern.sub(lambda m: f"{m.group(1)}{new_name}{m.group(2)}", result)

    result = re.sub(r"<cite>\s*\*\*本文引用的文件\*\*\s*</cite>\s*", "", result)
    # 移除所有引用条目已被清理的空来源块（支持 markdown 标题 # 和粗体 ** 两种格式）
    SOURCE_HEADER_RE = re.compile(
        r"^(?:#{1,6}\s*)?\*{0,2}(章节来源|图表来源|图示来源)\*{0,2}\s*$",
        re.MULTILINE,
    )
    CITATION_RE = re.compile(r"^- \[[^\]]+\]\(file://", re.MULTILINE)
    REF_LINE_RE = re.compile(r"^(?:#{1,6}\s*)?\*{0,2}(?:章节来源|图表来源|图示来源)\*{0,2}\s*$")

    def _cleanup_empty_blocks(text: str) -> str:
        """Remove source blocks that have no citation entries remaining."""
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            m = SOURCE_HEADER_RE.match(stripped)
            if m:
                block_end = i + 1
                block_has_content = False  # True if block has non-citation prose content
                # Find end of this source block
                while block_end < len(lines):
                    bstripped = lines[block_end].strip()
                    if bstripped == "":
                        block_end += 1
                    elif REF_LINE_RE.match(bstripped) or lines[block_end].startswith("#"):
                        break
                    elif CITATION_RE.match(bstripped):
                        block_end += 1
                    else:
                        # Non-empty, non-citation, non-header content — block has real prose
                        block_has_content = True
                        break
                else:
                    block_end = len(lines)

                # Check if block is empty (no citation entries)
                block_lines = lines[i:block_end]
                has_citation = any(CITATION_RE.match(ln.strip()) for ln in block_lines)
                if not has_citation and not block_has_content:
                    # Remove trailing empty lines before next meaningful line
                    while block_end < len(lines) and lines[block_end].strip() == "":
                        block_end += 1
                    lines = lines[:i] + lines[block_end:]
                    continue
            i += 1
        return "\n".join(lines)

    result = _cleanup_empty_blocks(result)
    return result
