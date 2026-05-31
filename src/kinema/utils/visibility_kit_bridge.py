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
