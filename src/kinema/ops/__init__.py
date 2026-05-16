"""kinema.ops — Operators 一括 register。"""

from __future__ import annotations

import bpy

from . import _base, preset_ops, instance_ops, workspace_ops, handler_ops


_CLASSES = (
    preset_ops.KINEMA_OT_scan_presets,
    preset_ops.KINEMA_OT_load_preset,
    instance_ops.KINEMA_OT_unload_instance,
    instance_ops.KINEMA_OT_preview_instance,
    instance_ops.KINEMA_OT_apply_lens,
    instance_ops.KINEMA_OT_refresh_instances,
    workspace_ops.KINEMA_OT_create_workspace,
    workspace_ops.KINEMA_OT_remove_workspace,
    handler_ops.KINEMA_OT_disable_cineflow_and_enable_handlers,
    handler_ops.KINEMA_OT_toggle_handlers,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
