"""kinema.ops — Operators 一括 register。"""

from __future__ import annotations

import bpy

from . import (
    _base,
    preset_ops,
    instance_ops,
    workspace_ops,
    handler_ops,
    source_ops,
    diagnostics_ops,
    keyframe_ops,
    clipboard_ops,
    io_ops,
    cineflow_import,
    bake_ops,
    render_ops,
    repair_ops,
    shot_ops,
)


_CLASSES = (
    source_ops.KINEMA_OT_init_preset_root,
    source_ops.KINEMA_OT_quick_start,
    source_ops.KINEMA_OT_capture_view_as_preset,
    source_ops.KINEMA_OT_add_selected_cameras_as_presets,
    preset_ops.KINEMA_OT_scan_presets,
    preset_ops.KINEMA_OT_toggle_preset_group_collapse,
    preset_ops.KINEMA_OT_load_preset,
    # Duplicate Instance Operator は廃止 (beta2.8)。
    # 複数欲しい場合は Preset を複数回 Load する運用に変更。
    # Preset 側に事前設定 (KinemaCameraPreset) が持てるようになったため。
    instance_ops.KINEMA_OT_detach_follow,
    instance_ops.KINEMA_OT_unload_instance,
    instance_ops.KINEMA_OT_preview_instance,
    instance_ops.KINEMA_OT_set_follow_angle,
    instance_ops.KINEMA_OT_apply_lens,
    instance_ops.KINEMA_OT_move_instance,
    instance_ops.KINEMA_OT_refresh_instances,
    workspace_ops.KINEMA_OT_create_workspace,
    workspace_ops.KINEMA_OT_remove_workspace,
    handler_ops.KINEMA_OT_disable_cineflow_and_enable_handlers,
    handler_ops.KINEMA_OT_toggle_handlers,
    diagnostics_ops.KINEMA_OT_run_diagnostics,
    keyframe_ops.KINEMA_OT_keyframe_all,
    keyframe_ops.KINEMA_OT_clear_unchanged_keys,
    keyframe_ops.KINEMA_OT_rebuild_keying_set,
    keyframe_ops.KINEMA_OT_toggle_auto_keyframe,
    clipboard_ops.KINEMA_OT_copy_settings,
    clipboard_ops.KINEMA_OT_paste_settings,
    io_ops.KINEMA_OT_export_json,
    io_ops.KINEMA_OT_import_json,
    cineflow_import.KINEMA_OT_import_from_cineflow,
    bake_ops.KINEMA_OT_bake_animation,
    render_ops.KINEMA_OT_render,
    render_ops.KINEMA_OT_render_selected_instances,
    render_ops.KINEMA_OT_render_active_instance,
    render_ops.KINEMA_OT_cancel_render_queue,
    repair_ops.KINEMA_OT_repair_scene,
    # Shot Ops（Phase 2 で旧 cut_ops を吸収済み）
    shot_ops.KINEMA_OT_migrate_to_shots,
    shot_ops.KINEMA_OT_sync_shots_from_markers,
    shot_ops.KINEMA_OT_add_shot,
    shot_ops.KINEMA_OT_remove_shot,
    shot_ops.KINEMA_OT_move_shot,
    shot_ops.KINEMA_OT_rename_shot,
    shot_ops.KINEMA_OT_jump_to_shot,
    shot_ops.KINEMA_OT_shot_cast_toggle,
    shot_ops.KINEMA_OT_diagnose_shots,
)


def register() -> None:
    """各 Operator を登録。1 件失敗しても残りは登録継続 + Console にエラーログ。

    旧 class が registry に残っていて register が衝突するケースは pre-unregister
    で対処する。
    """
    for cls in _CLASSES:
        try:
            # 旧バージョンの class が残っている場合は pre-unregister して衝突回避
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
            bpy.utils.register_class(cls)
        except Exception as exc:
            print(f"[kinema:ops] register_class FAILED for {cls.__name__}: {exc}")


def unregister() -> None:
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
