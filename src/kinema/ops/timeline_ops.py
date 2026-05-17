"""Timeline 関連 Operator: モード切替・Shot 追加/削除・トラック初期化など。"""

from __future__ import annotations

import uuid

import bpy
from bpy.props import IntProperty, StringProperty

from ..ui.timeline import host_resolver
from ..utils import refs
from ._base import KinemaOperator


def _ensure_default_track(st) -> object:
    """Shot 用デフォルトトラックが無ければ作る。"""
    for t in st.tracks:
        if t.kind == "SHOT":
            return t
    new_track = st.tracks.add()
    new_track.uid = uuid.uuid4().hex
    new_track.name = "Cam V1"
    new_track.kind = "SHOT"
    new_track.order = 0
    return new_track


class KINEMA_OT_toggle_timeline_mode(KinemaOperator):
    """kinema タイムラインモードを ON/OFF する。

    ON 時: 押した時の Image Editor をホスト Area として登録、描画開始。
    OFF 時: ホスト指定を解除して通常 Image Editor に戻す。
    """
    bl_idname = "kinema.toggle_timeline_mode"
    bl_label = "Toggle Kinema Timeline Mode"
    bl_description = "この Image Editor を kinema タイムラインビューに切り替える"

    def run(self, context):
        wm = context.window_manager
        if not hasattr(wm, "kinema"):
            self.report({"ERROR"}, "WindowManager.kinema が未登録です")
            return {"CANCELLED"}
        st = wm.kinema

        if st.timeline_mode_on:
            # OFF
            host_resolver.release()
            self.report({"INFO"}, "Kinema Timeline OFF")
        else:
            # ON: 現在の area / window をホストに指定
            area = context.area
            window = context.window
            if area is None or area.type != host_resolver.HOST_AREA_TYPE:
                self.report(
                    {"ERROR"},
                    "Video Sequencer から実行してください（Editor を切替→Sequencer）",
                )
                return {"CANCELLED"}
            host_resolver.claim_area(window, area)
            st.timeline_mode_on = True
            self.report({"INFO"}, "Kinema Timeline ON")

        # 描画再起動
        for w in wm.windows:
            for a in w.screen.areas:
                a.tag_redraw()
        return {"FINISHED"}


class KINEMA_OT_add_shot_at_playhead(KinemaOperator):
    """プレイヘッド位置に新規 Shot を追加する。

    既定の長さは 50 フレーム。トラックは Shot Track が無ければ作る。
    """
    bl_idname = "kinema.add_shot_at_playhead"
    bl_label = "Add Shot at Playhead"
    bl_description = "現在フレームから新規 Shot を追加（50 フレーム分）"

    duration: IntProperty(default=50, min=1)

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        track = _ensure_default_track(st)

        # アクティブ Instance のカメラを採用（無ければ scene.camera）
        cam = None
        if 0 <= st.active_instance_index < len(st.instances):
            cam = refs.safe_object(st.instances[st.active_instance_index].camera_ref)
        if cam is None:
            cam = scene.camera

        clip = st.shot_clips.add()
        clip.uid = uuid.uuid4().hex
        clip.name = f"Shot_{len(st.shot_clips):03d}"
        clip.track_uid = track.uid
        clip.frame_start = scene.frame_current
        clip.frame_end = scene.frame_current + self.duration
        if cam is not None:
            clip.camera = cam

        st.active_clip_uid = clip.uid
        self.report({"INFO"}, f"Added: {clip.name} ({clip.frame_start}-{clip.frame_end})")
        return {"FINISHED"}


class KINEMA_OT_delete_active_shot(KinemaOperator):
    """active_clip_uid の Shot を削除する。"""
    bl_idname = "kinema.delete_active_shot"
    bl_label = "Delete Active Shot"
    bl_description = "現在選択中の Shot を削除"

    def run(self, context):
        st = context.scene.kinema
        if not st.active_clip_uid:
            return {"CANCELLED"}
        for i, clip in enumerate(st.shot_clips):
            if clip.uid == st.active_clip_uid:
                st.shot_clips.remove(i)
                st.active_clip_uid = ""
                return {"FINISHED"}
        return {"CANCELLED"}


class KINEMA_OT_clear_shots(KinemaOperator):
    """全 Shot を削除（テスト/リセット用）。"""
    bl_idname = "kinema.clear_shots"
    bl_label = "Clear All Shots"
    bl_description = "全ての Shot を削除"

    def run(self, context):
        st = context.scene.kinema
        st.shot_clips.clear()
        st.active_clip_uid = ""
        return {"FINISHED"}
