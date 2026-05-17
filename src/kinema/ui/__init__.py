"""kinema.ui — Panel / UIList の登録。"""

from __future__ import annotations

import bpy

from . import main_panel, presets_view, instances_view, timeline


_CLASSES = (
    presets_view.KINEMA_UL_presets,
    instances_view.KINEMA_UL_instances,
    main_panel.KINEMA_PT_main,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    timeline.register()


def unregister() -> None:
    timeline.unregister()
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
