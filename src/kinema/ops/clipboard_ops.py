"""Active Instance の設定をカテゴリ別 / 一括でコピペする Operator 群。

カテゴリ:
  - pose   : Lens (mm) / Shift X / Y
  - dof    : Depth of Field 一式
  - follow : Follow 系（target / distance / rot_x/y/z / height / side / damping
             / auto_lookat）
  - lookat : LookAt 系（target / damping）
  - noise  : Noise 系
  - all    : 上記すべて

PointerProperty (Object) は名前を保存・復元する形（PointerProperty 自体は
セッション間で安定しないため）。
"""

from __future__ import annotations

import json

import bpy
from bpy.props import EnumProperty

from ..utils import refs
from ..utils import clipboard as cb
from ._base import KinemaOperator


CATEGORY_ITEMS = (
    ("all", "All", "全カテゴリ一括"),
    ("pose", "Lens/Shift", "Lens (mm) + Shift X/Y"),
    ("dof", "DoF", "被写界深度一式"),
    ("follow", "Follow", "追従パラメータ一式"),
    ("lookat", "LookAt", "LookAt パラメータ"),
    ("noise", "Noise", "Noise パラメータ"),
)


def _selected_instance_indices(scene) -> list[int]:
    """Outliner / Viewport で選択中のカメラに紐づく Instance の index リスト。"""
    selected_cams = {
        obj for obj in bpy.context.selected_objects if obj.type == "CAMERA"
    }
    if not selected_cams:
        return []
    st = scene.kinema
    out = []
    for i, inst in enumerate(st.instances):
        if inst.camera_ref in selected_cams:
            out.append(i)
    return out

# 各カテゴリのフィールド定義
# (target_kind, attr_name) target_kind: "inst" | "cam_data" | "dof"
_POSE_FIELDS = (
    ("inst", "lens_mm"),
    ("cam_data", "shift_x"),
    ("cam_data", "shift_y"),
)

_DOF_FIELDS = (
    ("dof", "use_dof"),
    ("dof", "focus_distance"),
    ("dof", "aperture_fstop"),
    ("dof", "aperture_blades"),
    ("dof", "aperture_rotation"),
    ("dof", "aperture_ratio"),
)
_DOF_OBJECT_REF = ("dof", "focus_object")  # PointerProperty 別扱い

_FOLLOW_FIELDS = (
    ("inst", "follow_distance"),
    ("inst", "follow_rot_x"),
    ("inst", "follow_rot_y"),
    ("inst", "follow_rot_z"),
    ("inst", "follow_height"),
    ("inst", "follow_side"),
    ("inst", "follow_damping"),
    ("inst", "follow_auto_lookat"),
    ("inst", "use_damping"),
)
_FOLLOW_OBJECT_REF = ("inst", "follow_target")

_LOOKAT_FIELDS = (
    ("inst", "lookat_damping"),
)
_LOOKAT_OBJECT_REF = ("inst", "lookat_target")

_NOISE_FIELDS = (
    ("inst", "noise_enabled"),
    ("inst", "noise_strength_pos"),
    ("inst", "noise_strength_rot"),
    ("inst", "noise_frequency"),
    ("inst", "noise_seed"),
)


def _get_targets(inst, cam):
    """カテゴリで使う target オブジェクトをまとめる。"""
    cam_data = cam.data if cam is not None else None
    dof = cam_data.dof if cam_data is not None and hasattr(cam_data, "dof") else None
    return {"inst": inst, "cam_data": cam_data, "dof": dof}


def _resolve_obj(name: str):
    """名前から bpy.data.objects を解決。空名は None。"""
    return bpy.data.objects.get(name) if name else None


def _serialize_category(category: str, inst, cam) -> dict:
    targets = _get_targets(inst, cam)
    out: dict = {}
    if category in ("all", "pose"):
        out.update(cb.copy_fields(_POSE_FIELDS, targets))
    if category in ("all", "dof"):
        out.update(cb.copy_fields(_DOF_FIELDS, targets))
        out.update(cb.copy_object_ref(_DOF_OBJECT_REF, targets))
    if category in ("all", "follow"):
        out.update(cb.copy_fields(_FOLLOW_FIELDS, targets))
        out.update(cb.copy_object_ref(_FOLLOW_OBJECT_REF, targets))
    if category in ("all", "lookat"):
        out.update(cb.copy_fields(_LOOKAT_FIELDS, targets))
        out.update(cb.copy_object_ref(_LOOKAT_OBJECT_REF, targets))
    if category in ("all", "noise"):
        out.update(cb.copy_fields(_NOISE_FIELDS, targets))
    return out


def _apply_category(category: str, data: dict, inst, cam) -> int:
    targets = _get_targets(inst, cam)
    count = 0
    if category in ("all", "pose"):
        count += cb.paste_fields(_POSE_FIELDS, targets, data)
    if category in ("all", "dof"):
        count += cb.paste_fields(_DOF_FIELDS, targets, data)
        count += cb.paste_object_ref(_DOF_OBJECT_REF, targets, data, _resolve_obj)
    if category in ("all", "follow"):
        count += cb.paste_fields(_FOLLOW_FIELDS, targets, data)
        count += cb.paste_object_ref(_FOLLOW_OBJECT_REF, targets, data, _resolve_obj)
    if category in ("all", "lookat"):
        count += cb.paste_fields(_LOOKAT_FIELDS, targets, data)
        count += cb.paste_object_ref(_LOOKAT_OBJECT_REF, targets, data, _resolve_obj)
    if category in ("all", "noise"):
        count += cb.paste_fields(_NOISE_FIELDS, targets, data)
    return count


def _slot_attr(category: str) -> str:
    return {
        "all": "all_json",
        "pose": "pose_json",
        "dof": "dof_json",
        "follow": "follow_json",
        "lookat": "lookat_json",
        "noise": "noise_json",
    }[category]


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class KINEMA_OT_copy_settings(KinemaOperator):
    """Active Instance の指定カテゴリの設定をクリップボードに保存。"""
    bl_idname = "kinema.copy_settings"
    bl_label = "Copy Settings"
    bl_description = "Active Instance の設定をカテゴリ別 / 一括でコピー"

    category: EnumProperty(items=CATEGORY_ITEMS, default="all")

    def run(self, context):
        scene = context.scene
        st = scene.kinema
        idx = st.active_instance_index
        if idx < 0 or idx >= len(st.instances):
            self.report({"WARNING"}, "Instance が選択されていません")
            return {"CANCELLED"}
        inst = st.instances[idx]
        cam = refs.safe_object(inst.camera_ref)

        data = _serialize_category(self.category, inst, cam)
        clipboard = context.window_manager.kinema_clipboard
        slot = _slot_attr(self.category)
        try:
            setattr(clipboard, slot, json.dumps(data, ensure_ascii=False))
        except Exception as exc:
            self.report({"ERROR"}, f"クリップボード保存失敗: {exc}")
            return {"CANCELLED"}
        self.report(
            {"INFO"},
            f"Copied [{self.category}] from '{inst.name}' ({len(data)} fields)",
        )
        return {"FINISHED"}


_TARGET_ITEMS = (
    ("ACTIVE", "Active only", "Active Instance のみ"),
    ("SELECTED", "Selected", "Outliner / Viewport で選択中のカメラに紐づく全 Instance"),
)


class KINEMA_OT_paste_settings(KinemaOperator):
    """クリップボードに保存された設定を Active Instance に適用。"""
    bl_idname = "kinema.paste_settings"
    bl_label = "Paste Settings"
    bl_description = "クリップボードの設定を Active / Selected Instance に適用"

    category: EnumProperty(items=CATEGORY_ITEMS, default="all")
    target: EnumProperty(items=_TARGET_ITEMS, default="ACTIVE")

    def run(self, context):
        scene = context.scene
        st = scene.kinema

        # ターゲット index 群を決定
        if self.target == "SELECTED":
            indices = _selected_instance_indices(scene)
            if not indices:
                # 選択無しなら Active にフォールバック
                indices = [st.active_instance_index] if (
                    0 <= st.active_instance_index < len(st.instances)
                ) else []
        else:
            indices = [st.active_instance_index] if (
                0 <= st.active_instance_index < len(st.instances)
            ) else []

        if not indices:
            self.report({"WARNING"}, "対象 Instance がありません")
            return {"CANCELLED"}

        clipboard = context.window_manager.kinema_clipboard
        slot = _slot_attr(self.category)
        raw = getattr(clipboard, slot, "")
        if not raw:
            self.report({"WARNING"}, f"クリップボード [{self.category}] が空です")
            return {"CANCELLED"}
        try:
            data = json.loads(raw)
        except Exception as exc:
            self.report({"ERROR"}, f"クリップボード読込失敗: {exc}")
            return {"CANCELLED"}
        if not isinstance(data, dict) or not data:
            self.report({"WARNING"}, "クリップボードが空です")
            return {"CANCELLED"}

        total_count = 0
        for idx in indices:
            inst = st.instances[idx]
            if getattr(inst, "locked", False):
                continue  # Lock 中は skip
            cam = refs.safe_object(inst.camera_ref)
            total_count += _apply_category(self.category, data, inst, cam)

        self.report(
            {"INFO"},
            f"Pasted [{self.category}] into {len(indices)} instance(s) "
            f"({total_count} fields)",
        )
        return {"FINISHED"}
