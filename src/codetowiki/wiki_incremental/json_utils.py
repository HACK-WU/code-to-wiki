"""JSON helpers with an optional orjson fast path."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    import orjson  # type: ignore
except ImportError:  # pragma: no cover - depends on local environment
    orjson = None


class MetadataError(Exception):
    """metadata.json 缺失、不可读或不是合法 JSON。"""


class GitError(Exception):
    """底层 git 操作失败（如不在仓库内、commit 不存在）。"""


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:  # 缺失/权限不足/路径是目录等"不可读"场景（NEG-01）
        raise MetadataError(
            f"找不到 metadata 文件: {path}\n请先运行 `codetowiki build-index` 或 `codetowiki init` 生成 metadata.json。"
        ) from exc
    try:
        if orjson is not None:
            return orjson.loads(data)
        return json.loads(data.decode("utf-8"))
    except ValueError as exc:  # JSONDecodeError / UnicodeDecodeError 均为 ValueError 子类
        raise MetadataError(
            f"metadata 解析失败（不是合法的 JSON）: {path}\n"
            f"请检查文件是否被手改损坏，或用 `codetowiki init` 重新生成骨架。\n"
            f"原始错误: {exc}"
        ) from exc


def dumps_json(data: dict[str, Any]) -> bytes:
    if orjson is not None:
        return orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")


def atomic_save_json(data: dict[str, Any], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dumps_json(data))
            f.write(b"\n")
        os.replace(tmp_name, target)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
