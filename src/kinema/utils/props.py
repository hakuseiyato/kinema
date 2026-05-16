"""Blender ID Datablock のカスタムプロパティ読み書きヘルパ。

`coll["kn_default_lens"] = 35.0` のような直接アクセスは ReferenceError や
KeyError を投げる場合があるため、安全に扱う層を 1 つ挟む。
"""

from __future__ import annotations

from typing import Any, Callable


def safe_get(obj, key: str, default: Any = None) -> Any:
    """カスタムプロパティを安全に読む。

    obj が None / 削除済み / キー不在の場合は default を返す。
    """
    if obj is None:
        return default
    try:
        val = obj.get(key)
    except Exception:
        return default
    return default if val is None else val


def safe_set(obj, key: str, value: Any) -> bool:
    """カスタムプロパティを安全に書く。成功で True。"""
    if obj is None:
        return False
    try:
        obj[key] = value
        return True
    except Exception:
        return False


def safe_get_typed(obj, key: str, conv: Callable[[Any], Any], default: Any) -> Any:
    """型変換つきの安全な読み取り。conv が例外を吐いた場合も default を返す。"""
    val = safe_get(obj, key, None)
    if val is None:
        return default
    try:
        return conv(val)
    except Exception:
        return default
