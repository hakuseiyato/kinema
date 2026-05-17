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

def _read_object_meta(obj) -> dict:
    """Camera オブジェクト（または所属コレクション）からカスタムプロパティを読む。"""
    meta = {
        "tags": "",
        "has_anim": False,
        "default_lens": 0.0,
        "preview_end": 0,
        "follow_target": "",
        "lookat_target": "",
    }
    # Camera obj 自体に書かれていたら優先
    for src in (obj, getattr(obj, "data", None)):
        if src is None:
            continue
        for key, field, conv in (
            (C.KEY_TAGS,          "tags",          lambda v: str(v)),
            (C.KEY_HAS_ANIM,      "has_anim",      lambda v: bool(v)),
            (C.KEY_DEFAULT_LENS,  "default_lens",  lambda v: float(v)),
            (C.KEY_PREVIEW_END,   "preview_end",   lambda v: int(v)),
            (C.KEY_FOLLOW_TARGET, "follow_target", lambda v: str(v)),
            (C.KEY_LOOKAT_TARGET, "lookat_target", lambda v: str(v)),
        ):
            val = prop_utils.safe_get(src, key, None)
            if val is not None:
                try:
                    meta[field] = conv(val)
                except Exception:
                    pass
    # アニメーション有無の動的検出
    if not meta["has_anim"]:
        for src in (obj, getattr(obj, "data", None), obj.parent):
            if src is None:
                continue
            adata = getattr(src, "animation_data", None)
            if adata is not None and adata.action is not None:
                meta["has_anim"] = True
                break
    return meta


_EMPTY_META = {
    "tags": "", "has_anim": False, "default_lens": 0.0, "preview_end": 0,
    "follow_target": "", "lookat_target": "",
}


def scan_presets(scene, preset_root_name: str) -> list[dict]:
    """Preset Root 配下の **全 Camera オブジェクト** を Preset として返す。

    設計変更（Yato さん要望）:
      - 「コレクション = Preset」を廃止
      - 「Camera オブジェクト 1 つ = Preset 1 件」に統一
      - コレクション階層は所属を表す「グループ」として表示にのみ使う
      - 同じコレクションに複数 Camera があれば全部 Preset として一覧化

    返値:
      name        : Camera オブジェクト名
      depth       : 階層深さ（root 直下なら 0）
      parent_path : 所属コレクション名のリスト（root を除く）
      group       : "/".join(parent_path)
      short_name  : name と同じ
      camera_name : name と同じ
      meta        : カメラから読んだメタ情報
    """
    root = get_preset_root(scene, preset_root_name)
    if root is None:
        return []
    result: list[dict] = []
    _walk_cameras(root, parent_path=[], depth=-1, result=result, skip_self=True)
    # group + name でソート
    result.sort(key=lambda x: (x["group"], x["name"]))
    return result


def _walk_cameras(coll, parent_path, depth, result, skip_self=False):
    """coll を再帰的に走査して、各 Camera オブジェクトを result に追記。"""
    # root 自身は parent_path に追加しない（skip_self）
    current_path = parent_path if skip_self else parent_path + [coll.name]
    current_depth = depth if skip_self else depth + 1

    # この coll の直下にある Camera を Preset として登録
    for obj in coll.objects:
        if obj.type != "CAMERA":
            continue
        result.append({
            "name": obj.name,
            "depth": current_depth,
            "parent_path": list(current_path),
            "group": "/".join(current_path),
            "short_name": obj.name,
            "camera_name": obj.name,
            "meta": _read_object_meta(obj),
        })

    # 子コレクションを再帰
    for child in coll.children:
        _walk_cameras(child, current_path, current_depth, result, skip_self=False)


# 旧 API 互換
def scan_presets_grouped(scene, preset_root_name, min_group_size=2):  # noqa: ARG001
    """互換シム。"""
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


def duplicate_camera_as_instance(
    cam_obj: bpy.types.Object,
    parent_coll: bpy.types.Collection,
    root_scope: Optional[bpy.types.Collection],
    base_name: Optional[str] = None,
) -> tuple[bpy.types.Collection, bpy.types.Object]:
    """Camera オブジェクト + 関連オブジェクト（親チェーン・constraint target）を
    複製し、parent_coll の配下に新規サブコレクションを作って入れる。

    Cineflow の `duplicate_camera_preset` を移植したもの。Preset Root を
    Camera オブジェクト単位で扱う新仕様で、Load の中核処理になる。

    Args:
        cam_obj: 複製元の Camera。Preset Root 配下にあること。
        parent_coll: 新規サブコレクションを link する先（通常 Instances Root）。
        root_scope: 関連オブジェクト探索の範囲制限（通常 Preset Root）。None で
            無制限（cam_obj に到達可能な全オブジェクト）。
        base_name: 新規サブコレクションの名前ベース。None で cam_obj.name を使う。

    Returns:
        (新規サブコレクション, 複製された Camera オブジェクト)
    """
    if cam_obj is None or cam_obj.type != "CAMERA":
        raise ValueError("duplicate_camera_as_instance: cam_obj は Camera 必須")

    name_base = base_name or cam_obj.name
    existing = set(bpy.data.collections.keys())
    new_coll_name = naming.next_unique_name(name_base, existing)
    new_coll = bpy.data.collections.new(new_coll_name)
    parent_coll.children.link(new_coll)

    # 関連オブジェクト収集（範囲制限あり）
    in_scope = set(root_scope.all_objects) if root_scope is not None else None
    related: set = {cam_obj}
    p = cam_obj.parent
    while p is not None and (in_scope is None or p in in_scope):
        related.add(p)
        p = p.parent
    for obj in list(related):
        for con in obj.constraints:
            tgt = getattr(con, "target", None)
            if tgt is not None and (in_scope is None or tgt in in_scope):
                related.add(tgt)

    # 複製 + マップ作成
    obj_map: dict = {}
    for orig in related:
        new_obj = orig.copy()
        if orig.data is not None:
            new_obj.data = orig.data.copy()
        new_coll.objects.link(new_obj)
        obj_map[orig] = new_obj

    # 親リワイヤ + constraint target リワイヤ
    for orig, dup in obj_map.items():
        if orig.parent is not None and orig.parent in obj_map:
            dup.parent = obj_map[orig.parent]
        for con in dup.constraints:
            tgt = getattr(con, "target", None)
            if tgt is not None and tgt in obj_map:
                con.target = obj_map[tgt]

    new_cam = obj_map[cam_obj]
    return new_coll, new_cam


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
