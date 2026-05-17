"""Collection ツリーの走査・複製・削除。

旧 cineflow `utils.py` から責務分割で移植。
"""

from __future__ import annotations

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


_EMPTY_META = {
    "tags": "", "has_anim": False, "default_lens": 0.0, "preview_end": 0,
    "follow_target": "", "lookat_target": "",
}


def scan_presets(scene, preset_root_name: str) -> list[dict]:
    """Preset Root 配下を **再帰スキャン**し、Camera を含むコレクションを Preset として返す。

    - 階層は Outliner の構造をそのまま反映する
    - 親コレクションに Camera が無ければそれは「グループ」として `parent_path` を持つ
      子 Preset から参照される（UI でインデント表示する）
    - `_` 分割やヒューリスティックなグループ化は行わない（Yato さん要望）

    返値の各エントリのキー:
      name        : コレクション名そのまま
      depth       : Preset Root 直下を 0 とした階層深さ
      parent_path : 親コレクション名のリスト（root を除く）
      group       : "/".join(parent_path)（UI 表示用、ルート直下なら ""）
      short_name  : name と同じ（互換のため残す）
      camera_name : 代表カメラ名
      meta        : カスタムプロパティから読んだ辞書
    """
    root = get_preset_root(scene, preset_root_name)
    if root is None:
        return []
    result: list[dict] = []
    _walk_presets(root, parent_path=[], depth=-1, result=result, skip_self=True)
    return result


def _walk_presets(coll, parent_path, depth, result, skip_self=False):
    """coll を再帰的に走査して Camera を含むコレクションを result に追記。

    skip_self=True で root 自身は Preset として登録しない（ルート用フラグ）。
    """
    # 直接の objects に Camera があるか
    has_direct_camera = any(obj.type == "CAMERA" for obj in coll.objects)
    cam = find_first_camera(coll) if has_direct_camera else None

    if has_direct_camera and not skip_self:
        result.append({
            "name": coll.name,
            "depth": depth,
            "parent_path": list(parent_path),
            "group": "/".join(parent_path),
            "short_name": coll.name,
            "camera_name": cam.name if cam else "",
            "meta": _read_collection_meta(coll),
        })

    # Camera を含むコレクションは Preset 確定とみなし、その内側は再帰しない。
    # （プリセット内部のサブコレクションは「補助オブジェクトのまとまり」と解釈）
    if has_direct_camera and not skip_self:
        return

    # Camera を含まないコレクション、または root 自身は「グループ」として子を辿る
    next_path = parent_path if skip_self else parent_path + [coll.name]
    for child in coll.children:
        _walk_presets(child, next_path, depth + 1, result, skip_self=False)


# 旧 API 互換（main_panel から呼ばれていたら）
def scan_presets_grouped(scene, preset_root_name, min_group_size=2):  # noqa: ARG001
    """互換シム。新仕様では re-encode 不要なので scan_presets と同じものを返す。"""
    return scan_presets(scene, preset_root_name)


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
    # Blender が内部的に名前を変えた場合（new_coll.name != new_name）に備えて、
    # 戻り値の実名のみを信用する。
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
