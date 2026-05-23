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


def next_serial_from(name: str, existing: Iterable[str], pad: int = 3) -> str:
    """`name` のベース名を抽出して、次の連番を採番する（suffix 増殖を防ぐ）。

    例:
      - "Hero" + {"Hero"}                     → "Hero_001"
      - "Hero_001" + {"Hero", "Hero_001"}     → "Hero_002"
      - "Hero_005" + {existing 全部}          → 既存最大値の次
      - "Hero_001_001" のような二重 suffix も "Hero" を base として再採番

    Duplicate Operator で「複製元の名前 → 次の連番」を直感的に決める用途。
    """
    base, _idx = split_base_and_index(name)
    existing_set = set(existing)

    # base 自体が空いていれば base
    if base not in existing_set:
        # ただし "Hero_001" を元にして "Hero" を返すのは不自然なので、
        # ベース重複 + 連番済みなら次の番号を返す
        # 単純化: 元の名前 (name) が "Hero" のときは "Hero" を返す
        if name == base:
            return base

    # `base_NNN` 形式の existing から最大 index を探す
    max_idx = 0
    import re as _re
    pat = _re.compile(rf"^{_re.escape(base)}_(\d{{{pad},}})$")
    for ex in existing_set:
        m = pat.match(ex)
        if m:
            max_idx = max(max_idx, int(m.group(1)))

    n = max_idx + 1
    while True:
        candidate = f"{base}_{n:0{pad}d}"
        if candidate not in existing_set:
            return candidate
        n += 1
