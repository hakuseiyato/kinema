"""yato_visibility_kit との橋渡しユーティリティ。

設計方針:
  - kinema は visibility_kit を **optional dependency** として扱う
  - visibility_kit が未登録でも kinema 単体で動く（grace degrade）
  - 検出は `bpy.context.scene` に `yato_vis` PropertyGroup があるかで判定

Phase 1 では「読み出し」だけ提供する（cuts → shots への移行で
yato_vis.groups[].cast_markers を読み取る）。
Phase 2 で「書き戻し」と「bake トリガ」も実装する。
"""

from __future__ import annotations

from typing import Optional

import bpy


def is_available(scene) -> bool:
    """yato_visibility_kit がこの scene に登録されているかチェック。"""
    return hasattr(scene, "yato_vis")


def get_settings(scene):
    """`scene.yato_vis` を安全に取得。未登録なら None。"""
    return getattr(scene, "yato_vis", None)


def list_groups(scene) -> list:
    """yato_vis.groups[] のリストを返す。未登録なら空リスト。"""
    st = get_settings(scene)
    if st is None:
        return []
    try:
        return list(st.groups)
    except Exception:
        return []


def group_appears_in_marker(group, marker_name: str) -> bool:
    """Group が指定 marker_name のショットに出演するか判定。"""
    try:
        for c in group.cast_markers:
            if c.marker_name == marker_name:
                return True
    except Exception:
        pass
    return False


def resolve_solo_target(group) -> Optional[str]:
    """Group の Solo target Object 名を返す。

    優先順:
      1. group.bound_object（kinema 風 single object bind）
      2. 最初の COLLECTION メンバの solo_target

    Solo target 不在なら None。
    """
    try:
        bo = getattr(group, "bound_object", None)
        if bo is not None:
            return bo.name
    except Exception:
        pass
    try:
        for m in group.members:
            if m.member_type == "COLLECTION":
                target = getattr(m, "solo_target", None)
                if target is not None:
                    return target.name
    except Exception:
        pass
    return None


def collect_cast_for_marker(scene, marker_name: str) -> list[dict]:
    """指定 marker_name の Shot に出演する全 Group を返す。

    Returns: [{"group_name": str, "solo_target_name": str | ""}], ...
    """
    out: list[dict] = []
    for g in list_groups(scene):
        if not group_appears_in_marker(g, marker_name):
            continue
        solo = resolve_solo_target(g) or ""
        try:
            gname = g.name
        except Exception:
            continue
        out.append({"group_name": gname, "solo_target_name": solo})
    return out


def all_group_names(scene) -> list[str]:
    """全 Group 名を返す。Cast マトリクス UI 用。"""
    names: list[str] = []
    for g in list_groups(scene):
        try:
            names.append(g.name)
        except Exception:
            continue
    return names


# 再帰防止フラグ（モジュールレベルで先に宣言する必要がある）
_bake_in_progress: bool = False


def import_vk_cast_ops():
    """yato_visibility_kit.ops.cast_ops を Blender の Extensions / legacy
    両対応で import する。

    Blender 4.2+ の Extensions システムでは `bl_ext.user_default.<addon>` /
    `bl_ext.<repo>.<addon>` の module 名で登録されているため、`import
    yato_visibility_kit` は ModuleNotFoundError になる。

    sys.modules を走査して、登録済みの module を優先的に拾う設計にする。
    """
    import sys
    import importlib

    # 1) sys.modules に既に居る yato_visibility_kit のフルパスを探す
    candidates_in_sys: list[str] = []
    for name in list(sys.modules.keys()):
        # `bl_ext.user_default.yato_visibility_kit` / `yato_visibility_kit` 両対応
        if name == "yato_visibility_kit" or name.endswith(".yato_visibility_kit"):
            candidates_in_sys.append(name)
    # 2) sys.modules に無くても、よく使われる候補も試す
    fallback_paths: list[str] = [
        "bl_ext.user_default.yato_visibility_kit",
        "bl_ext.blender_org.yato_visibility_kit",
        "yato_visibility_kit",
    ]
    for base in candidates_in_sys + fallback_paths:
        ops_name = base + ".ops.cast_ops"
        # sys.modules ヒット
        if ops_name in sys.modules:
            return sys.modules[ops_name]
        # import 試行
        try:
            return importlib.import_module(ops_name)
        except ImportError:
            continue
        except Exception as exc:
            print(f"[kinema:vkb] unexpected error importing '{ops_name}': {exc}")
            continue
    return None


def request_bake_for_group(scene, group_name: str, force: bool = False) -> bool:
    """指定 Group の visibility を shots[] に基づいて bake する。

    kinema.shots[N].cast 変更時の update callback から呼ぶ。
    yato_vis が無ければ no-op。bake 中の再帰防止はモジュール変数で。

    `force=True`: yato_vis.cast_auto_bake が OFF でも強制 bake（明示ボタン用）。
    silent fail パスは全て System Console にログを出して原因切り分け可能に。
    """
    global _bake_in_progress
    st = get_settings(scene)
    if st is None:
        print(f"[kinema:vkb] skip bake '{group_name}': yato_vis 未登録")
        return False
    if not force and not getattr(st, "cast_auto_bake", True):
        print(f"[kinema:vkb] skip bake '{group_name}': cast_auto_bake が OFF")
        return False
    if _bake_in_progress:
        print(f"[kinema:vkb] skip bake '{group_name}': 再帰中")
        return False
    if not group_name:
        print("[kinema:vkb] skip bake: group_name が空")
        return False
    target = None
    for g in list_groups(scene):
        try:
            if g.name == group_name:
                target = g
                break
        except Exception:
            continue
    if target is None:
        print(f"[kinema:vkb] skip bake '{group_name}': yato_vis.groups に該当無し")
        return False
    cast_ops_mod = import_vk_cast_ops()
    if cast_ops_mod is None or not hasattr(cast_ops_mod, "bake_group_cast"):
        print(f"[kinema:vkb] skip bake '{group_name}': cast_ops module import 不能")
        return False
    try:
        _bake_in_progress = True
        result = cast_ops_mod.bake_group_cast(scene, target)
        if isinstance(result, tuple) and len(result) >= 2:
            cleared, inserted = result[0], result[1]
            print(f"[kinema:vkb] bake '{group_name}': cleared {cleared}, inserted {inserted}")
        else:
            print(f"[kinema:vkb] bake '{group_name}': done")
        return True
    except Exception as exc:
        print(f"[kinema:vkb] bake FAILED for '{group_name}': {exc}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        _bake_in_progress = False
