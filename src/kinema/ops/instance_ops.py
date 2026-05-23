"""Instance 系 Operator。"""

from __future__ import annotations

import bpy
from bpy.props import IntProperty, FloatProperty  # noqa: F401

from ..utils import collections as kn_collections
from ..utils import refs
from ..runtime import follow_lookat
from ._base import KinemaOperator


class KINEMA_OT_duplicate_instance(KinemaOperator):
    """選択中の Instance を複製する。

    新ルール:
      - 名前: ベース名 + _NNN の連番採番 (`next_serial_from`)
        Hero → Hero_001、Hero_001 → Hero_002（suffix 増殖しない）
      - 名前同期: Collection / Camera も新名前にリネーム
      - Lock / Solo: 複製先は両方 False にリセット（即編集可能）
      - source_preset: `copy of <元 Instance 名>` で複製元を明示
      - dispatcher は複製中 suspend し、終了後に 1 度だけ呼ぶ
        （中間状態で Follow 計算が走って変な位置に飛ぶのを防止）
    """
    bl_idname = "kinema.duplicate_instance"
    bl_label = "Duplicate Instance"
    bl_description = "選択中の Instance を関連オブジェクトごと複製 (連番採番)"

    index: IntProperty(default=-1)

    def run(self, context):
        from ..runtime import instance_dispatcher  # noqa: PLC0415
        from ..utils import naming  # noqa: PLC0415

        scene = context.scene
        st = scene.kinema
        idx = self.index if self.index >= 0 else st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}

        src = st.instances[idx]
        src_cam = refs.safe_object(src.camera_ref)
        if not refs.is_camera_object(src_cam):
            self.report({"ERROR"}, "複製元 Camera が見つかりません")
            return {"CANCELLED"}

        src_coll = refs.safe_collection(src.collection_ref)
        instances_root = kn_collections.get_or_create_instances_root(
            scene, st.instances_root_name,
        )

        # 連番採番: 既存名から base + _NNN の次の番号を計算
        src_name = src.name or (src_coll.name if src_coll else src_cam.name)
        all_names = (
            set(bpy.data.collections.keys())
            | set(bpy.data.objects.keys())
            | {i.name for i in st.instances}
        )
        new_name = naming.next_serial_from(src_name, all_names)

        # dispatcher を suspend してバッチ書込
        instance_dispatcher.suspend_dispatch()
        try:
            # Camera + 関連オブジェクトを複製
            try:
                new_coll, new_cam = kn_collections.duplicate_camera_as_instance(
                    src_cam, instances_root,
                    root_scope=src_coll,
                    base_name=new_name,
                )
            except Exception as exc:
                self.report({"ERROR"}, f"複製失敗: {exc}")
                return {"CANCELLED"}

            # 新規 collection / camera が衝突回避された場合は new_name を実名に
            actual_name = new_coll.name

            inst = st.instances.add()
            # name を最後に設定（他フィールド設定中に _on_name_changed で
            # 副作用が出るのを避ける）
            inst.collection_ref = new_coll
            inst.camera_ref = new_cam

            # Lock / Solo は新ルールでリセット
            inst.enabled = src.enabled
            inst.solo = False
            inst.locked = False

            inst.lens_mm = src.lens_mm

            # Follow / LookAt / Noise パラメータをコピー
            inst.follow_target = src.follow_target
            inst.follow_distance = src.follow_distance
            inst.follow_rot_x = src.follow_rot_x
            inst.follow_rot_y = src.follow_rot_y
            inst.follow_rot_z = src.follow_rot_z
            inst.follow_height = src.follow_height
            inst.follow_side = src.follow_side
            inst.follow_damping = src.follow_damping
            inst.follow_auto_lookat = src.follow_auto_lookat
            inst.lookat_target = src.lookat_target
            inst.lookat_damping = src.lookat_damping
            inst.noise_enabled = src.noise_enabled
            inst.noise_strength_pos = src.noise_strength_pos
            inst.noise_strength_rot = src.noise_strength_rot
            inst.noise_frequency = src.noise_frequency
            inst.noise_seed = src.noise_seed

            # 実カメラの lens も同期（data は data.copy() で独立済）
            if new_cam.data is not None and src_cam.data is not None:
                new_cam.data.lens = src_cam.data.lens

            # source_preset: 複製元 Instance 名を表示
            inst.source_preset = f"copy of {src.name}"

            # 名前は最後（update callback で coll/cam を再リネーム）
            inst.name = actual_name

            st.active_instance_index = len(st.instances) - 1
        finally:
            instance_dispatcher.resume_dispatch()

        # 終了後に 1 度だけ dispatch を呼んで正しい状態に
        try:
            instance_dispatcher.dispatch(scene, force=True)
        except Exception:
            pass

        self.report({"INFO"}, f"Duplicated: {new_name}")
        return {"FINISHED"}


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
