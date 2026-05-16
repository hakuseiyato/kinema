"""Instance UIList。"""

from __future__ import annotations

import bpy

from ..utils import refs


class KINEMA_UL_instances(bpy.types.UIList):
    """Instance 一覧 UIList。"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):  # noqa: ARG002
        cam = refs.safe_object(item.camera_ref)
        coll = refs.safe_collection(item.collection_ref)

        row = layout.row(align=True)
        row.prop(item, "enabled", text="", icon="HIDE_OFF" if item.enabled else "HIDE_ON", emboss=False)
        if coll is None and cam is None:
            row.label(text=f"{item.name} (Missing)", icon="ERROR")
            return

        label = coll.name if coll is not None else item.name
        row.label(text=label, icon="OUTLINER_COLLECTION")

        if cam is None:
            row.label(text="No camera", icon="ERROR")
        else:
            row.label(text=f"{cam.data.lens:.0f}mm" if cam.data else "")

        # ショートカット: Preview
        op = row.operator("kinema.preview_instance", text="", icon="RESTRICT_VIEW_OFF")
        op.index = index
        # ショートカット: Unload
        op = row.operator("kinema.unload_instance", text="", icon="X")
        op.index = index
