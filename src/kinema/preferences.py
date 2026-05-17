"""AddonPreferences。

beta 段階では設定項目を持たない。将来 Pose タブやキーマップ stack 等で
必要になったら拡張する想定。
"""

from __future__ import annotations

import bpy


class KinemaPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, context):  # type: ignore[override]
        layout = self.layout
        box = layout.box()
        box.label(text="Kinema", icon="CAMERA_DATA")
        box.label(text="設定は Properties > Scene > Kinema パネルから")
        box.label(
            text="cineflow が enabled な場合は警告が出るので無効化してください",
            icon="INFO",
        )
