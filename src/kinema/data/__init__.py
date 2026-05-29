"""kinema.data — PropertyGroup 定義群。

責務別にファイルを分割し、本モジュールでまとめて register/unregister する。

beta1 で実装した独自タイムライン UI と Shot/Track/TimelineView/WMSettings 系
PropertyGroup は撤回した（Yato さん要望：Blender 標準タイムラインを使う運用に戻す）。
"""

from __future__ import annotations

import bpy

from . import preset_item, instance_item, scene_settings, wm_settings, camera_preset, cut_item


_CLASSES = (
    # 子要素は親より先に register する必要がある
    preset_item.KinemaPresetItem,
    instance_item.KinemaInstanceItem,
    camera_preset.KinemaCameraPreset,
    cut_item.KinemaCut,
    scene_settings.KinemaSceneSettings,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kinema = bpy.props.PointerProperty(type=scene_settings.KinemaSceneSettings)
    bpy.types.Camera.kinema_preset = bpy.props.PointerProperty(
        type=camera_preset.KinemaCameraPreset,
    )
    wm_settings.register()


def unregister() -> None:
    wm_settings.unregister()
    try:
        del bpy.types.Camera.kinema_preset
    except Exception:
        pass
    try:
        del bpy.types.Scene.kinema
    except Exception:
        pass
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
