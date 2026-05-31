"""kinema.ui — Panel / UIList の登録。"""

from __future__ import annotations

import bpy

from . import main_panel, presets_view, instances_view, shot_manager_panel


_CLASSES = (
    presets_view.KINEMA_UL_presets,
    instances_view.KINEMA_UL_instances,
    shot_manager_panel.KINEMA_UL_shots,
    main_panel.KINEMA_PT_main,
    shot_manager_panel.KINEMA_PT_shot_manager,
)


def register() -> None:
    """Panel / UIList を登録。失敗時は Console にエラーログを出し、残りは継続登録。"""
    for cls in _CLASSES:
        try:
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
            bpy.utils.register_class(cls)
        except Exception as exc:
            print(f"[kinema:ui] register_class FAILED for {cls.__name__}: {exc}")


def unregister() -> None:
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
