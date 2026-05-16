"""PointerProperty 参照の None 安全アクセスヘルパ。

Blender の PointerProperty は参照先 ID が削除されると自動で None になるが、
ReferenceError を投げるパスもあるため、try/except で握り潰した値を返す。
dispatcher / UI / drawer すべてこの helper を経由してアクセスする。
"""

from __future__ import annotations

from typing import Optional

import bpy


def safe_object(ref) -> Optional[bpy.types.Object]:
    """PointerProperty(Object) の参照を安全に取得する。

    参照切れ / ReferenceError / 名前不在のいずれでも None を返す。
    """
    if ref is None:
        return None
    try:
        # name にアクセスして生存確認（削除済みだと ReferenceError）
        _ = ref.name
    except ReferenceError:
        return None
    except Exception:
        return None
    # bpy.data.objects に居ない場合（別 .blend からの残骸など）も None 扱い
    if ref.name not in bpy.data.objects:
        return None
    return ref


def safe_collection(ref) -> Optional[bpy.types.Collection]:
    """PointerProperty(Collection) の参照を安全に取得する。"""
    if ref is None:
        return None
    try:
        _ = ref.name
    except ReferenceError:
        return None
    except Exception:
        return None
    if ref.name not in bpy.data.collections:
        return None
    return ref


def is_camera_object(obj) -> bool:
    """obj が有効な Camera オブジェクトか。"""
    obj = safe_object(obj)
    return obj is not None and obj.type == "CAMERA"
