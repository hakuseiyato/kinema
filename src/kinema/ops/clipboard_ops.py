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
from ._base import KinemaOperator


CATEGORY_ITEMS = (
    ("all", "All", "全カテゴリ一括"),
    ("pose", "Lens/Shift", "Lens (mm) + Shift X/Y"),
    ("dof", "DoF", "被写界深度一式"),
    ("follow", "Follow", "追従パラメータ一式"),
    ("lookat", "LookAt", "LookAt パラメータ"),
    ("noise", "Noise", "Noise パラメータ"),
)

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


def _copy_fields(fields, targets) -> dict:
    out: dict = {}
    for kind, attr in fields:
        target = targets.get(kind)
        if target is None:
            continue
        try:
            val = getattr(target, attr, None)
            # FloatVector のような RNA 配列を JSON 化
            if hasattr(val, "__iter__") and not isinstance(val, str):
                val = list(val)
            out[f"{kind}.{attr}"] = val
        except Exception:
            pass
    return out


def _paste_fields(fields, targets, data: dict) -> int:
    count = 0
    for kind, attr in fields:
        target = targets.get(kind)
        if target is None:
            continue
        key = f"{kind}.{attr}"
        if key not in data:
            continue
        val = data[key]
        try:
            setattr(target, attr, val)
            count += 1
        except Exception:
            pass
    return count


def _copy_object_ref(ref_def, targets) -> dict:
    kind, attr = ref_def
    target = targets.get(kind)
    if target is None:
        return {}
    try:
        obj = getattr(target, attr, None)
        name = obj.name if obj is not None else ""
    except Exception:
        return {}
    return {f"{kind}.{attr}__name": name}


def _paste_object_ref(ref_def, targets, data: dict) -> int:
    kind, attr = ref_def
    target = targets.get(kind)
    if target is None:
        return 0
    key = f"{kind}.{attr}__name"
    if key not in data:
        return 0
    name = data[key]
    obj = bpy.data.objects.get(name) if name else None
    try:
        setattr(target, attr, obj)
        return 1
    except Exception:
        return 0


def _serialize_category(category: str, inst, cam) -> dict:
    targets = _get_targets(inst, cam)
    out: dict = {}
    if category in ("all", "pose"):
        out.update(_copy_fields(_POSE_FIELDS, targets))
    if category in ("all", "dof"):
        out.update(_copy_fields(_DOF_FIELDS, targets))
        out.update(_copy_object_ref(_DOF_OBJECT_REF, targets))
    if category in ("all", "follow"):
        out.update(_copy_fields(_FOLLOW_FIELDS, targets))
        out.update(_copy_object_ref(_FOLLOW_OBJECT_REF, targets))
    if category in ("all", "lookat"):
        out.update(_copy_fields(_LOOKAT_FIELDS, targets))
        out.update(_copy_object_ref(_LOOKAT_OBJECT_REF, targets))
    if category in ("all", "noise"):
        out.update(_copy_fields(_NOISE_FIELDS, targets))
    return out


def _apply_category(category: str, data: dict, inst, cam) -> int:
    targets = _get_targets(inst, cam)
    count = 0
    if category in ("all", "pose"):
        count += _paste_fields(_POSE_FIELDS, targets, data)
    if category in ("all", "dof"):
        count += _paste_fields(_DOF_FIELDS, targets, data)
        count += _paste_object_ref(_DOF_OBJECT_REF, targets, data)
    if category in ("all", "follow"):
        count += _paste_fields(_FOLLOW_FIELDS, targets, data)
        count += _paste_object_ref(_FOLLOW_OBJECT_REF, targets, data)
    if category in ("all", "lookat"):
        count += _paste_fields(_LOOKAT_FIELDS, targets, data)
        count += _paste_object_ref(_LOOKAT_OBJECT_REF, targets, data)
    if category in ("all", "noise"):
        count += _paste_fields(_NOISE_FIELDS, targets, data)
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


class KINEMA_OT_paste_settings(KinemaOperator):
    """クリップボードに保存された設定を Active Instance に適用。"""
    bl_idname = "kinema.paste_settings"
    bl_label = "Paste Settings"
    bl_description = "クリップボードの設定を Active Instance に適用"

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

        count = _apply_category(self.category, data, inst, cam)
        self.report(
            {"INFO"},
            f"Pasted [{self.category}] into '{inst.name}' ({count} fields)",
        )
        return {"FINISHED"}
