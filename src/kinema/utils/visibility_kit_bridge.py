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


def force_viewport_refresh(scene) -> None:
    """bake 後の viewport 即時反映を確実にするための複合 refresh。

    `scene.frame_set` 1 つだけだと環境/タイミング次第で
    visibility が viewport に反映されないことがある（hide_viewport の
    fcurve eval は anim eval だが、UI redraw は別系統）。
    以下 3 段階を全て叩いて確実に反映させる:
      1. animation 再評価 (frame_set)
      2. depsgraph update
      3. 全 3D Viewport の tag_redraw
    """
    import bpy
    # 1. animation 再評価
    try:
        current = scene.frame_current
        scene.frame_set(current)
    except Exception as exc:
        print(f"[kinema:vkb] frame_set failed: {exc}")
    # 2. depsgraph 更新（明示）
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        if dg is not None:
            dg.update()
    except Exception:
        pass
    # 3. 全 3D Viewport の tag_redraw
    try:
        wm = bpy.context.window_manager
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


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


def request_bake_all_groups(scene, force: bool = False) -> int:
    """全 Group を bake する（cast entry 変更時の確実反映用）。

    **なぜ全 Group を bake するか**:
    `request_bake_for_group` は 1 group しか触らない。Shot に新規 cast entry を
    追加すると、その group のキーは正しく入るが、`cast に未登録の他 group`
    （= 本来この shot では非表示にしたい group）は誰も hide キーを打たないため
    可視のまま残ってしまう。
    bake_group_cast は内部で「全 marker × 全 obj」を走査して cast に無ければ
    hidden=True を出すので、全 group に対して走らせれば、shot 切替時に確実に
    「cast の入った group だけが見える」状態になる。

    Returns: bake 成功した group 数。
    """
    global _bake_in_progress
    st = get_settings(scene)
    if st is None:
        return 0
    if not force and not getattr(st, "cast_auto_bake", True):
        return 0
    if _bake_in_progress:
        return 0
    cast_ops_mod = import_vk_cast_ops()
    if cast_ops_mod is None or not hasattr(cast_ops_mod, "bake_group_cast"):
        return 0
    baked = 0
    try:
        _bake_in_progress = True
        for g in list_groups(scene):
            try:
                cast_ops_mod.bake_group_cast(scene, g)
                baked += 1
            except Exception as exc:
                try:
                    gname = g.name
                except Exception:
                    gname = "?"
                print(f"[kinema:vkb] bake_all error on '{gname}': {exc}")
        print(f"[kinema:vkb] bake_all: {baked} groups baked")
        return baked
    finally:
        _bake_in_progress = False
