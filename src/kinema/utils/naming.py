"""自動採番。`Shot_001` 重複時に `Shot_002` を付ける等。

CameraDuplicator.cs の `GetUniqueName` 由来の発想を Blender 流に書き直したもの。
"""

from __future__ import annotations

import re
from typing import Iterable

_SUFFIX_RE = re.compile(r"_(\d{3,})$")


def split_base_and_index(name: str) -> tuple[str, int]:
    """`Shot_007` → ("Shot", 7)、`Cam` → ("Cam", 0) を返す。"""
    m = _SUFFIX_RE.search(name)
    if not m:
        return name, 0
    base = name[: m.start()]
    try:
        idx = int(m.group(1))
    except ValueError:
        idx = 0
    return base, idx


def next_unique_name(base: str, existing: Iterable[str], pad: int = 3) -> str:
    """`existing` 集合と重複しない `<base>_NNN` を返す。

    `base` 自体が空いていれば（重複が無ければ）base を返す。
    そうでなければ `_001 / _002 / ...` を採番する。
    """
    existing_set = set(existing)
    if base not in existing_set:
        return base
    n = 1
    while True:
        candidate = f"{base}_{n:0{pad}d}"
        if candidate not in existing_set:
            return candidate
        n += 1
