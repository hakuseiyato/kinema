"""Active Instance 設定のコピペで使う純粋ロジック層（bpy 非依存）。

`_copy_fields` / `_paste_fields` は target を辞書経由で受け取り、
属性に対して getattr/setattr するだけ。bpy への依存は呼び出し側に逃がす。
"""

from __future__ import annotations

from typing import Any, Iterable


def copy_fields(fields: Iterable[tuple[str, str]], targets: dict) -> dict:
    """fields=((kind, attr), ...) と targets={kind: obj} から辞書を作る。"""
    out: dict = {}
    for kind, attr in fields:
        target = targets.get(kind)
        if target is None:
            continue
        try:
            val = getattr(target, attr, None)
            # RNA 配列 → list 化
            if hasattr(val, "__iter__") and not isinstance(val, str):
                val = list(val)
            out[f"{kind}.{attr}"] = val
        except Exception:
            pass
    return out


def paste_fields(
    fields: Iterable[tuple[str, str]], targets: dict, data: dict,
) -> int:
    """データ辞書から targets に setattr。成功した数を返す。"""
    count = 0
    for kind, attr in fields:
        target = targets.get(kind)
        if target is None:
            continue
        key = f"{kind}.{attr}"
        if key not in data:
            continue
        try:
            setattr(target, attr, data[key])
            count += 1
        except Exception:
            pass
    return count


def copy_object_ref(
    ref_def: tuple[str, str], targets: dict,
) -> dict:
    """PointerProperty を名前文字列としてエクスポート。"""
    kind, attr = ref_def
    target = targets.get(kind)
    if target is None:
        return {}
    try:
        obj = getattr(target, attr, None)
        name = obj.name if obj is not None else ""
    except Exception:
        return {}
    return {f"{kind}.{attr}__name": name}


def paste_object_ref(
    ref_def: tuple[str, str], targets: dict, data: dict, resolve_obj: Any,
) -> int:
    """名前文字列から resolve_obj(name) で解決して setattr。

    resolve_obj は `lambda name: bpy.data.objects.get(name) or None` を期待。
    """
    kind, attr = ref_def
    target = targets.get(kind)
    if target is None:
        return 0
    key = f"{kind}.{attr}__name"
    if key not in data:
        return 0
    name = data[key]
    obj = resolve_obj(name) if name else None
    try:
        setattr(target, attr, obj)
        return 1
    except Exception:
        return 0
