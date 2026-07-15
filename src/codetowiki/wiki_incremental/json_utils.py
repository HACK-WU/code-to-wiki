# -*- coding: utf-8 -*-
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


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "rb") as f:
        data = f.read()
    if orjson is not None:
        return orjson.loads(data)
    return json.loads(data.decode("utf-8"))


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
