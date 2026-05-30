"""Instance 系 Operator。

注: `KINEMA_OT_duplicate_instance` は beta2.x で廃止された（複数欲しい場合は
Preset を複数回 Load する運用に変更）。Preset 側に事前設定 (KinemaCameraPreset)
が持てるようになったため。
"""

from __future__ import annotations

import bpy
from bpy.props import IntProperty, FloatProperty  # noqa: F401

from ..utils import refs
from ..runtime import follow_lookat
from ._base import KinemaOperator


class KINEMA_OT_detach_follow(KinemaOperator):
    """Active Instance の Follow Target を解除し、現在のカメラ位置を保持する。

    Follow が active な状態でユーザーが手でカメラを動かすと dispatcher が
    上書きしてしまう問題への対処。
    1. 現在のカメラ位置 / 回転を「最終 dispatch 結果」のまま記録
    2. follow_target を None に設定（dispatcher が follow 処理を skip）
    3. lookat_target も同時に解除するかは引数で選べる
    """
    bl_idname = "kinema.detach_follow"
    bl_label = "Detach Follow"
    bl_description = (
        "Active Instance の Follow Target を解除して、現在のカメラ位置を凍結する。"
        "Follow 計算による位置上書きが止まる"
    )

    also_lookat: bpy.props.BoolProperty(
        name="Also detach LookAt",
        description="LookAt Target も同時に解除する",
        default=True,
    )

    def invoke(self, context, event):  # noqa: ARG002
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Detach Follow", icon="UNLINKED")
        layout.separator()
        layout.label(text="Follow Target を解除し、")
        layout.label(text="現在のカメラ位置・回転を保持します。")
        layout.label(text="（dispatcher による上書きが止まる）")
        layout.prop(self, "also_lookat")

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        inst = st.instances[idx]
        # 現在のカメラ位置を維持するため、target を None にするだけで OK
        # (dispatcher は follow_target が None なら follow をスキップする)
        inst.follow_target = None
        if self.also_lookat:
            inst.lookat_target = None
            inst.follow_auto_lookat = False
        self.report(
            {"INFO"},
            f"Detached follow from '{inst.name}'"
            + (" (and lookat)" if self.also_lookat else ""),
        )
        return {"FINISHED"}


class KINEMA_OT_unload_instance(KinemaOperator):
    """選択中のインスタンスをアンロード（コレクション削除）する。"""
    bl_idname = "kinema.unload_instance"
    bl_label = "Unload Instance"
    bl_description = "選択中の Instance をシーンから削除"

    index: IntProperty(default=-1)  # 指定があればその index、無ければ active

    def run(self, context):
        st = context.scene.kinema
        idx = self.index if self.index >= 0 else st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        inst = st.instances[idx]
        coll = refs.safe_collection(inst.collection_ref)
        cam = refs.safe_object(inst.camera_ref)
        # LookAt Proxy を掃除
        if cam is not None:
            follow_lookat.cleanup_lookat_proxy(cam)
        if coll is not None:
            kn_collections.remove_collection_recursive(coll)
        st.instances.remove(idx)
        st.active_instance_index = max(0, min(idx, len(st.instances) - 1))
        return {"FINISHED"}


class KINEMA_OT_preview_instance(KinemaOperator):
    """選択中の Instance のカメラを scene.camera にする（カメラビューには切替えない）。"""
    bl_idname = "kinema.preview_instance"
    bl_label = "Preview Camera"
    bl_description = "選択中の Instance のカメラを scene.camera に設定"

    index: IntProperty(default=-1)

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = self.index if self.index >= 0 else st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            return {"CANCELLED"}
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            self.report({"WARNING"}, "カメラが見つかりません")
            return {"CANCELLED"}
        scene.camera = cam
        return {"FINISHED"}


class KINEMA_OT_set_follow_angle(KinemaOperator):
    """選択中 Instance の follow_rot_x / y / z をプリセット値に設定。"""
    bl_idname = "kinema.set_follow_angle"
    bl_label = "Set Follow Angle"
    bl_description = "X / Y / Z 軸回転をワンクリックでプリセット角度に設定"

    rot_x: FloatProperty(default=0.0)
    rot_y: FloatProperty(default=0.0)
    rot_z: FloatProperty(default=0.0)

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            return {"CANCELLED"}
        inst = st.instances[idx]
        inst.follow_rot_x = self.rot_x
        inst.follow_rot_y = self.rot_y
        inst.follow_rot_z = self.rot_z
        return {"FINISHED"}


class KINEMA_OT_apply_lens(KinemaOperator):
    """選択中の Instance に焦点距離を適用。"""
    bl_idname = "kinema.apply_lens"
    bl_label = "Apply Lens"
    bl_description = "選択中の Instance のカメラに lens_mm を即時反映"

    lens: FloatProperty(default=0.0, min=0.0)

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            return {"CANCELLED"}
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam) or cam.data is None:
            return {"CANCELLED"}
        lens = self.lens if self.lens > 0.001 else inst.lens_mm
        cam.data.lens = lens
        inst.lens_mm = lens
        return {"FINISHED"}


class KINEMA_OT_move_instance(KinemaOperator):
    """Instance リスト内で Active を 1 つ上 / 下に動かす。"""
    bl_idname = "kinema.move_instance"
    bl_label = "Move Instance"
    bl_description = "選択中の Instance をリスト上で並べ替える"

    direction: bpy.props.EnumProperty(
        items=(("UP", "Up", ""), ("DOWN", "Down", "")),
        default="UP",
    )

    def run(self, context):
        st = context.scene.kinema
        idx = st.active_instance_index
        n = len(st.instances)
        if idx < 0 or idx >= n:
            return {"CANCELLED"}
        new_idx = idx - 1 if self.direction == "UP" else idx + 1
        if new_idx < 0 or new_idx >= n:
            return {"CANCELLED"}
        st.instances.move(idx, new_idx)
        st.active_instance_index = new_idx
        return {"FINISHED"}


class KINEMA_OT_refresh_instances(KinemaOperator):
    """Outliner で削除/リネームされた Instance を整理する。"""
    bl_idname = "kinema.refresh_instances"
    bl_label = "Refresh Instances"
    bl_description = "削除済み参照のクリーンアップとリネーム同期"

    def run(self, context):
        st = context.scene.kinema
        removed = 0
        # 後ろから走査して安全に削除
        for i in range(len(st.instances) - 1, -1, -1):
            inst = st.instances[i]
            coll = refs.safe_collection(inst.collection_ref)
            cam = refs.safe_object(inst.camera_ref)
            if coll is None and cam is None:
                st.instances.remove(i)
                removed += 1
                continue
            # 名前を同期
            if coll is not None and inst.name != coll.name:
                inst.name = coll.name
        if removed:
            self.report({"INFO"}, f"Cleaned up {removed} stale instances")
        return {"FINISHED"}
