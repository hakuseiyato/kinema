"""キーフレーム関連 Operator。

設計方針:
  - Blender 標準の `keyframe_insert` を素直にラップして「一括キー」を提供
  - Blender 標準の Auto Keyframe（赤丸、`scene.tool_settings.use_keyframe_insert_auto`）
    を流用。kinema 側は Instance プロパティの update callback でフックして自動キー
  - kinema 専用 Keying Set "Kinema Camera" を Active Instance ベースで自動生成し、
    Blender 標準の I キーや Auto Keyframe と統合
"""

from __future__ import annotations

import bpy

from ..utils import refs
from ._base import KinemaOperator


KEYING_SET_IDNAME = "kinema_camera"
KEYING_SET_LABEL = "Kinema Camera"


# 一括キー対象パスのテーブル
# (target_kind, attr_or_path, optional_array_index)
# target_kind:
#   "cam_obj"  : Camera オブジェクト
#   "cam_data" : Camera Data
#   "dof"      : Camera Data.dof
#   "instance" : Instance Item (collection で indexed)
_CAMERA_OBJ_PATHS = (
    ("location", -1),
    ("rotation_euler", -1),
)
_CAMERA_DATA_PATHS = (
    ("lens", -1),
    ("shift_x", -1),
    ("shift_y", -1),
)
_DOF_PATHS = (
    ("use_dof", -1),
    ("focus_distance", -1),
    ("aperture_fstop", -1),
    ("aperture_blades", -1),
    ("aperture_rotation", -1),
    ("aperture_ratio", -1),
)
_INSTANCE_PATHS = (
    "lens_mm",
    "follow_distance",
    "follow_rot_x",
    "follow_rot_y",
    "follow_rot_z",
    "follow_height",
    "follow_side",
    "follow_damping",
    "lookat_damping",
    "noise_strength_pos",
    "noise_strength_rot",
    "noise_frequency",
    "noise_seed",
)


def _key_paths_on(obj, paths, frame: int) -> int:
    """obj に対して指定パスを keyframe_insert する。成功したパス数を返す。"""
    count = 0
    if obj is None:
        return 0
    for path, index in paths:
        try:
            if index >= 0:
                obj.keyframe_insert(data_path=path, index=index, frame=frame)
            else:
                obj.keyframe_insert(data_path=path, frame=frame)
            count += 1
        except Exception:
            pass
    return count


def _key_instance_props(scene, inst_index: int, frame: int) -> int:
    """Scene に対して `kinema.instances[i].xxx` のパスでキーを打つ。"""
    count = 0
    for prop in _INSTANCE_PATHS:
        path = f"kinema.instances[{inst_index}].{prop}"
        try:
            scene.keyframe_insert(data_path=path, frame=frame)
            count += 1
        except Exception:
            pass
    return count


def insert_keys_for_instance(scene, inst, inst_index: int, frame: int) -> int:
    """1 Instance に対して全項目を keyframe_insert する。"""
    total = 0
    cam = refs.safe_object(inst.camera_ref)
    if refs.is_camera_object(cam):
        total += _key_paths_on(cam, _CAMERA_OBJ_PATHS, frame)
        if cam.data is not None:
            total += _key_paths_on(cam.data, _CAMERA_DATA_PATHS, frame)
            if hasattr(cam.data, "dof") and cam.data.dof is not None:
                total += _key_paths_on(cam.data.dof, _DOF_PATHS, frame)
    total += _key_instance_props(scene, inst_index, frame)
    return total


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class KINEMA_OT_keyframe_all(KinemaOperator):
    """Active Instance の全項目を現フレームにキー打ち。"""
    bl_idname = "kinema.keyframe_all"
    bl_label = "Key All (current frame)"
    bl_description = (
        "選択中 Instance の Transform / Lens / Shift / DoF / Follow パラメータを"
        "現フレームに一括キーフレーム挿入"
    )

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        inst = st.instances[idx]
        count = insert_keys_for_instance(scene, inst, idx, scene.frame_current)
        self.report({"INFO"}, f"{count} keys inserted @ frame {scene.frame_current}")
        return {"FINISHED"}


class KINEMA_OT_rebuild_keying_set(KinemaOperator):
    """Active Instance を元に "Kinema Camera" Keying Set を再構築。

    Blender 標準の I キーや Auto Keyframe と統合する。Keying Set が選択されていると
    Auto Keyframe (赤丸) でその Keying Set の path のみが対象になる。
    """
    bl_idname = "kinema.rebuild_keying_set"
    bl_label = "Rebuild Keying Set"
    bl_description = "Active Instance を対象とした kinema 専用 Keying Set を再構築"

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            self.report({"WARNING"}, "Active Instance にカメラがありません")
            return {"CANCELLED"}

        # 既存の同名 KS があれば paths をクリアして再利用する
        # （Blender 5.x で scene.keying_sets.remove() が消えたため new + remove は不可）
        existing = scene.keying_sets.get(KEYING_SET_LABEL)
        if existing is not None:
            try:
                existing.paths.clear()
                ks = existing
            except Exception:
                ks = scene.keying_sets.new(idname=KEYING_SET_IDNAME, name=KEYING_SET_LABEL)
        else:
            ks = scene.keying_sets.new(idname=KEYING_SET_IDNAME, name=KEYING_SET_LABEL)
        try:
            ks.bl_description = "Auto-generated by kinema for the active Instance camera"
        except Exception:
            pass

        # Camera Object
        for path, _idx in _CAMERA_OBJ_PATHS:
            try:
                ks.paths.add(cam, path)
            except Exception:
                pass
        # Camera Data
        if cam.data is not None:
            for path, _idx in _CAMERA_DATA_PATHS:
                try:
                    ks.paths.add(cam.data, path)
                except Exception:
                    pass
            if hasattr(cam.data, "dof") and cam.data.dof is not None:
                for path, _idx in _DOF_PATHS:
                    try:
                        ks.paths.add(cam.data.dof, path)
                    except Exception:
                        pass
        # Instance プロパティ（target=scene, path に indexed access）
        for prop in _INSTANCE_PATHS:
            try:
                ks.paths.add(scene, f"kinema.instances[{idx}].{prop}")
            except Exception:
                pass

        # 自分を active にしておく
        scene.keying_sets.active = ks
        self.report(
            {"INFO"},
            f"Keying Set '{KEYING_SET_LABEL}' rebuilt ({len(ks.paths)} paths)",
        )
        return {"FINISHED"}


class KINEMA_OT_toggle_auto_keyframe(KinemaOperator):
    """Blender 標準の Auto Keyframe (赤丸) を kinema パネルからトグル。"""
    bl_idname = "kinema.toggle_auto_keyframe"
    bl_label = "Toggle Auto Keyframe"
    bl_description = "Blender 標準の Auto Keyframe (タイムラインの赤丸) を ON/OFF"

    def run(self, context):
        ts = context.scene.tool_settings
        ts.use_keyframe_insert_auto = not ts.use_keyframe_insert_auto
        state = "ON" if ts.use_keyframe_insert_auto else "OFF"
        self.report({"INFO"}, f"Auto Keyframe {state}")
        return {"FINISHED"}
