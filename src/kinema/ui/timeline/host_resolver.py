"""ホスト Area 識別。

`SpaceImageEditor.draw_handler_add` は Image Editor の **全インスタンス**で
描画関数を呼ぶため、kinema 専用に指定された 1 つの Area だけで描画 / 入力を
有効化するための識別ロジックを集約する。

主キー: `Window.as_pointer()` / `Area.as_pointer()`（session 中のみ安定）
二次キー: `Screen.name` + Area index（pointer が無効化された時の復帰用）
"""

from __future__ import annotations

from typing import Optional

import bpy


def claim_area(window: bpy.types.Window, area: bpy.types.Area) -> None:
    """ユーザーが kinema モード ON した時に呼ぶ。pointer + 二次キーを保存する。"""
    wm = bpy.context.window_manager
    if not hasattr(wm, "kinema"):
        return
    st = wm.kinema
    st.host_window_pointer = str(window.as_pointer()) if window else ""
    st.host_area_pointer = str(area.as_pointer()) if area else ""
    if window and window.screen:
        st.host_screen_name = window.screen.name
        try:
            st.host_area_index = list(window.screen.areas).index(area) if area else -1
        except ValueError:
            st.host_area_index = -1
    else:
        st.host_screen_name = ""
        st.host_area_index = -1


def release() -> None:
    """ホスト指定を解除する（kinema モード OFF 時）。"""
    wm = bpy.context.window_manager
    if not hasattr(wm, "kinema"):
        return
    st = wm.kinema
    st.host_window_pointer = ""
    st.host_area_pointer = ""
    st.host_screen_name = ""
    st.host_area_index = -1
    st.timeline_mode_on = False


def is_mode_on() -> bool:
    wm = bpy.context.window_manager
    if not hasattr(wm, "kinema"):
        return False
    return bool(wm.kinema.timeline_mode_on)


def resolve_host_area() -> tuple[Optional[bpy.types.Window], Optional[bpy.types.Area]]:
    """現在のホスト Area を返す。見つからなければ (None, None)。

    主キー (pointer) → 二次キー (screen 名 + area index) の順で解決を試みる。
    主キーで見つかった場合、二次キーを最新値に更新する（self-heal）。
    """
    wm = bpy.context.window_manager
    if not hasattr(wm, "kinema"):
        return None, None
    st = wm.kinema
    if not st.timeline_mode_on:
        return None, None

    target_win_ptr = st.host_window_pointer
    target_area_ptr = st.host_area_pointer

    # 一次キー検索
    for window in wm.windows:
        if str(window.as_pointer()) != target_win_ptr:
            continue
        for area in window.screen.areas:
            if str(area.as_pointer()) == target_area_ptr:
                # self-heal: 二次キーを更新
                st.host_screen_name = window.screen.name
                try:
                    st.host_area_index = list(window.screen.areas).index(area)
                except ValueError:
                    st.host_area_index = -1
                return window, area

    # 二次キー検索
    target_screen = st.host_screen_name
    target_idx = st.host_area_index
    if not target_screen or target_idx < 0:
        return None, None
    for window in wm.windows:
        if not window.screen or window.screen.name != target_screen:
            continue
        areas = list(window.screen.areas)
        if 0 <= target_idx < len(areas):
            area = areas[target_idx]
            if area.type == "IMAGE_EDITOR":
                # pointer を新値で更新（self-heal）
                st.host_window_pointer = str(window.as_pointer())
                st.host_area_pointer = str(area.as_pointer())
                return window, area
    return None, None


def is_host_area(area: Optional[bpy.types.Area], window: Optional[bpy.types.Window] = None) -> bool:
    """area が kinema ホストかどうか。drawer / header の早期 return 用。"""
    if area is None:
        return False
    if not is_mode_on():
        return False
    host_win, host_area = resolve_host_area()
    if host_area is None:
        return False
    return area == host_area
