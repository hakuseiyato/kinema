"""Timeline 上の Modal Operator スケルトン。

beta1 の最小実装:
  - 左クリック: Shot ストリップを選択（active_clip_uid を更新）
  - プレイヘッドエリア（下マージン）クリック: scene.frame_current 更新

beta2 で予定:
  - ドラッグでクリップ移動 / トリム / カット
  - キーマップ統合
"""

from __future__ import annotations

import bpy

from . import host_resolver, drawer


def _x_to_frame(x_in_region: float, scroll_frame: int, ppf: float) -> int:
    """Region X 座標を frame 番号に変換。"""
    return int(scroll_frame + (x_in_region - drawer.LEFT_MARGIN) / max(ppf, 0.01))


def _y_to_track_index(y_in_region: float, region_height: int) -> int:
    """Region Y 座標を track index に変換（上から 0, 1, 2 ...）。"""
    body_top = region_height - drawer.TOP_MARGIN
    if y_in_region >= body_top:
        return -1
    if y_in_region < drawer.BOTTOM_MARGIN:
        return -1
    rel = body_top - y_in_region
    return int(rel // drawer.TRACK_HEIGHT)


class KINEMA_OT_timeline_click(bpy.types.Operator):
    """タイムライン上でのクリック処理。

    UNDO は付けない（プレイヘッド移動など軽量操作のため）。クリップ操作で
    PropertyGroup を変更する操作のみ別 Operator に分離する。
    """
    bl_idname = "kinema.timeline_click"
    bl_label = "Kinema Timeline Click"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return host_resolver.is_host_area(context.area, context.window)

    def invoke(self, context, event):
        area = context.area
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region is None:
            return {"CANCELLED"}

        # Region 相対座標
        x = event.mouse_region_x
        y = event.mouse_region_y
        if x < drawer.LEFT_MARGIN:
            # 左マージン（トラック名エリア）は何もしない
            return {"PASS_THROUGH"}

        scene = context.scene
        st = scene.kinema
        view = st.timeline_view
        frame = _x_to_frame(x, view.scroll_frame, view.pixels_per_frame)

        # プレイヘッド移動エリア（下マージン）
        if y < drawer.BOTTOM_MARGIN:
            scene.frame_current = max(0, frame)
            area.tag_redraw()
            return {"FINISHED"}

        # Shot ヒットテスト
        track_idx = _y_to_track_index(y, region.height)
        tracks = list(st.tracks)
        if 0 <= track_idx < len(tracks):
            target_track_uid = tracks[track_idx].uid
            hit_clip = None
            for clip in st.shot_clips:
                if clip.track_uid != target_track_uid:
                    continue
                if clip.frame_start <= frame < clip.frame_end:
                    hit_clip = clip
                    break
            if hit_clip is not None:
                st.active_clip_uid = hit_clip.uid
                area.tag_redraw()
                return {"FINISHED"}

        # 何にもヒットしなかった → 選択解除
        st.active_clip_uid = ""
        area.tag_redraw()
        return {"FINISHED"}


_ADDON_KEYMAP = None


def register() -> None:
    global _ADDON_KEYMAP
    bpy.utils.register_class(KINEMA_OT_timeline_click)
    # キーマップに左クリックを割り当て
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is None:
        return
    km = kc.keymaps.new(name="Image", space_type="IMAGE_EDITOR")
    kmi = km.keymap_items.new(
        KINEMA_OT_timeline_click.bl_idname,
        type="LEFTMOUSE",
        value="PRESS",
    )
    _ADDON_KEYMAP = (km, kmi)


def unregister() -> None:
    global _ADDON_KEYMAP
    if _ADDON_KEYMAP is not None:
        km, kmi = _ADDON_KEYMAP
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
        _ADDON_KEYMAP = None
    try:
        bpy.utils.unregister_class(KINEMA_OT_timeline_click)
    except Exception:
        pass
