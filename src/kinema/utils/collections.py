"""Collection ツリーの走査・複製・削除。

旧 cineflow `utils.py` から責務分割で移植。
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

import bpy

from ..config import constants as C
from . import naming, props as prop_utils


# ---------------------------------------------------------------------------
# ルート Collection の取得
# ---------------------------------------------------------------------------

def get_preset_root(scene, root_name: str) -> Optional[bpy.types.Collection]:
    """Scene 直下から Preset Root コレクションを取得。無ければ None。"""
    if not root_name:
        return None
    for coll in scene.collection.children:
        if coll.name == root_name:
            return coll
    return None


def get_or_create_instances_root(scene, root_name: str) -> bpy.types.Collection:
    """Instances 用ルートコレクションを取得 or 新規作成して返す。"""
    name = root_name or C.DEFAULT_INSTANCES_ROOT
    for coll in scene.collection.children:
        if coll.name == name:
            return coll
    new_coll = bpy.data.collections.new(name)
    scene.collection.children.link(new_coll)
    return new_coll


# ---------------------------------------------------------------------------
# Camera 探索
# ---------------------------------------------------------------------------

def find_first_camera(coll: bpy.types.Collection) -> Optional[bpy.types.Object]:
    """コレクション配下から最初の Camera を返す。"""
    if coll is None:
        return None
    for obj in coll.all_objects:
        if obj.type == "CAMERA":
            return obj
    return None


# ---------------------------------------------------------------------------
# Preset 走査
# ---------------------------------------------------------------------------

def _read_collection_meta(coll) -> dict:
    """Collection のカスタムプロパティから kinema 情報を読む。"""
    return {
        "tags": str(prop_utils.safe_get(coll, C.KEY_TAGS, "") or ""),
        "has_anim": bool(prop_utils.safe_get(coll, C.KEY_HAS_ANIM, False)),
        "default_lens": prop_utils.safe_get_typed(coll, C.KEY_DEFAULT_LENS, float, 0.0),
        "preview_end": prop_utils.safe_get_typed(coll, C.KEY_PREVIEW_END, int, 0),
        "follow_target": str(prop_utils.safe_get(coll, C.KEY_FOLLOW_TARGET, "") or ""),
        "lookat_target": str(prop_utils.safe_get(coll, C.KEY_LOOKAT_TARGET, "") or ""),
    }


def _split_group(name: str) -> tuple[str, str]:
    """名前を `GROUP_SHORT` 形式とみなしてグループとショート名を分離。"""
    if "_" in name:
        g, s = name.split("_", 1)
        return g, s
    return "", name


def scan_presets(scene, preset_root_name: str) -> list[dict]:
    """Preset Root 直下の子コレクションをスキャンしてフラットな辞書のリストを返す。"""
    root = get_preset_root(scene, preset_root_name)
    if root is None:
        return []
    result: list[dict] = []
    for child in root.children:
        cam = find_first_camera(child)
        group, short = _split_group(child.name)
        result.append({
            "name": child.name,
            "group": group,
            "short_name": short,
            "camera_name": cam.name if cam else "",
            "meta": _read_collection_meta(child),
        })
    result.sort(key=lambda x: (x["group"], x["short_name"]))
    return result


_EMPTY_META = {
    "tags": "", "has_anim": False, "default_lens": 0.0, "preview_end": 0,
    "follow_target": "", "lookat_target": "",
}


def scan_presets_grouped(scene, preset_root_name: str, min_group_size: int = 2) -> list[dict]:
    """scan_presets の結果にグループヘッダを挿入したリストを返す。

    UI 上で「`FOH_LS / FOH_MS` は FOH グループでヘッダ表示」のような視覚分離に使う。
    """
    flat = scan_presets(scene, preset_root_name)
    if not flat:
        return []
    counts = Counter(p["group"] for p in flat if p["group"])

    grouped: list[dict] = []
    last_group: Optional[str] = None
    for p in flat:
        g = p["group"]
        if g and counts[g] >= min_group_size:
            if g != last_group:
                grouped.append({
                    "is_header": True,
                    "name": g,
                    "group": g,
                    "short_name": "",
                    "display_name": g,
                    "camera_name": "",
                    "meta": dict(_EMPTY_META),
                })
                last_group = g
            entry = dict(p)
            entry["is_header"] = False
            entry["display_name"] = p["short_name"]
            grouped.append(entry)
        else:
            entry = dict(p)
            entry["is_header"] = False
            entry["display_name"] = p["name"]
            grouped.append(entry)
            last_group = None
    return grouped


# ---------------------------------------------------------------------------
# 複製
# ---------------------------------------------------------------------------

def duplicate_collection(
    source: bpy.types.Collection,
    parent: bpy.types.Collection,
    base_name: str,
) -> tuple[bpy.types.Collection, Optional[bpy.types.Object]]:
    """source を再帰複製して parent の子に追加。新コレクションと代表カメラを返す。

    base_name が既存と衝突したら自動採番（`_001` 付き）。
    オブジェクトデータも完全コピー（Linked Mode は alpha では未対応）。
    """
    existing = set(bpy.data.collections.keys())
    name = naming.next_unique_name(base_name, existing)
    new_coll = _copy_recursive(source, parent, name)
    cam = find_first_camera(new_coll)
    return new_coll, cam


def _copy_recursive(
    source: bpy.types.Collection,
    parent: bpy.types.Collection,
    new_name: str,
) -> bpy.types.Collection:
    new_coll = bpy.data.collections.new(new_name)
    parent.children.link(new_coll)
    for obj in source.objects:
        new_obj = obj.copy()
        if obj.data:
            new_obj.data = obj.data.copy()
        new_coll.objects.link(new_obj)
    for child in source.children:
        existing = set(bpy.data.collections.keys())
        child_name = naming.next_unique_name(child.name, existing)
        _copy_recursive(child, new_coll, child_name)
    return new_coll


# ---------------------------------------------------------------------------
# 削除
# ---------------------------------------------------------------------------

def remove_collection_recursive(coll: bpy.types.Collection) -> None:
    """コレクションを安全に再帰削除。"""
    if coll is None:
        return
    for child in list(coll.children):
        remove_collection_recursive(child)
    for obj in list(coll.objects):
        try:
            coll.objects.unlink(obj)
        except Exception:
            pass
        if obj.users == 0:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass
    try:
        bpy.data.collections.remove(coll, do_unlink=True)
    except Exception:
        pass
