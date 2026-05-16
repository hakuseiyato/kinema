"""AddonPreferences。

userprefs 永続：
  - keymap backup の JSON 文字列（beta3 で keymap_stack を実装する際に使用）
  - Pose タブの step enum（alpha2 で配線）
  - cineflow 共存時の自動有効化フラグ
"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty


_STEP_TRANSLATE_ITEMS = (
    ("FINE", "Fine (0.01 m)", "細かいステップ"),
    ("NORMAL", "Normal (0.1 m)", "標準ステップ"),
    ("COARSE", "Coarse (1.0 m)", "粗いステップ"),
)

_STEP_ROTATE_ITEMS = (
    ("FINE", "Fine (1°)", "細かいステップ"),
    ("NORMAL", "Normal (5°)", "標準ステップ"),
    ("COARSE", "Coarse (15°)", "粗いステップ"),
)

STEP_TRANSLATE_MAP = {"FINE": 0.01, "NORMAL": 0.1, "COARSE": 1.0}
STEP_ROTATE_MAP = {"FINE": 1.0, "NORMAL": 5.0, "COARSE": 15.0}


class KinemaPreferences(bpy.types.AddonPreferences):
    # Extensions 形式では bl_idname は __package__ (= "bl_ext.user_default.kinema") か
    # legacy "kinema" のどちらか。__package__ を使うと両対応できる。
    bl_idname = __package__

    keymap_backup_json: StringProperty(
        name="Keymap Backup (JSON)",
        description="kinema が一時無効化した keymap entry の id とその元状態",
        default="",
    )

    step_translate: EnumProperty(
        name="Translate Step",
        items=_STEP_TRANSLATE_ITEMS,
        default="NORMAL",
    )

    step_rotate: EnumProperty(
        name="Rotate Step",
        items=_STEP_ROTATE_ITEMS,
        default="NORMAL",
    )

    auto_enable_handler_after_cineflow_disable: BoolProperty(
        name="Auto-enable handlers after cineflow disable",
        description="cineflow が disabled に変わったら自動で kinema handler を有効化",
        default=True,
    )

    def draw(self, context):  # type: ignore[override]
        layout = self.layout

        col = layout.column(align=True)
        col.label(text="Pose タブの操作ステップ")
        col.prop(self, "step_translate")
        col.prop(self, "step_rotate")

        layout.separator()
        layout.prop(self, "auto_enable_handler_after_cineflow_disable")

        layout.separator()
        box = layout.box()
        box.label(text="Diagnostics", icon="TOOL_SETTINGS")
        box.label(text=f"keymap_backup_json: {len(self.keymap_backup_json)} chars")
