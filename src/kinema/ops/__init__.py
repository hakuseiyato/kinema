"""kinema.ops — Operators 一括 register。"""

from __future__ import annotations

import bpy

from . import _base, preset_ops, instance_ops, workspace_ops, handler_ops, source_ops, diagnostics_ops


_CLASSES = (
    source_ops.KINEMA_OT_init_preset_root,
    source_ops.KINEMA_OT_quick_start,
    source_ops.KINEMA_OT_capture_view_as_preset,
    source_ops.KINEMA_OT_add_selected_cameras_as_presets,
    preset_ops.KINEMA_OT_scan_presets,
    preset_ops.KINEMA_OT_toggle_preset_group_collapse,
    preset_ops.KINEMA_OT_load_preset,
    instance_ops.KINEMA_OT_unload_instance,
    instance_ops.KINEMA_OT_preview_instance,
    instance_ops.KINEMA_OT_apply_lens,
    instance_ops.KINEMA_OT_refresh_instances,
    workspace_ops.KINEMA_OT_create_workspace,
    workspace_ops.KINEMA_OT_remove_workspace,
    handler_ops.KINEMA_OT_disable_cineflow_and_enable_handlers,
    handler_ops.KINEMA_OT_toggle_handlers,
    diagnostics_ops.KINEMA_OT_run_diagnostics,
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
