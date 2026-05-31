"""kinema.data — PropertyGroup 定義群。

責務別にファイルを分割し、本モジュールでまとめて register/unregister する。

beta1 で実装した独自タイムライン UI と Shot/Track/TimelineView/WMSettings 系
PropertyGroup は撤回した（Yato さん要望：Blender 標準タイムラインを使う運用に戻す）。
"""

from __future__ import annotations

import bpy

from . import (
    preset_item,
    instance_item,
    scene_settings,
    wm_settings,
    camera_preset,
    cut_item,
    shot_item,
)


_CLASSES = (
    # 子要素は親より先に register する必要がある
    preset_item.KinemaPresetItem,
    instance_item.KinemaInstanceItem,
    camera_preset.KinemaCameraPreset,
    cut_item.KinemaCut,
    shot_item.KinemaShotCastEntry,
    shot_item.KinemaShot,
    scene_settings.KinemaSceneSettings,
)


def register() -> None:
    """PropertyGroup を登録。失敗時は Console にログ。"""
    for cls in _CLASSES:
        try:
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
            bpy.utils.register_class(cls)
        except Exception as exc:
            print(f"[kinema:data] register_class FAILED for {cls.__name__}: {exc}")
    try:
        bpy.types.Scene.kinema = bpy.props.PointerProperty(type=scene_settings.KinemaSceneSettings)
    except Exception as exc:
        print(f"[kinema:data] Scene.kinema register FAILED: {exc}")
    try:
        bpy.types.Camera.kinema_preset = bpy.props.PointerProperty(
            type=camera_preset.KinemaCameraPreset,
        )
    except Exception as exc:
        print(f"[kinema:data] Camera.kinema_preset register FAILED: {exc}")
    try:
        wm_settings.register()
    except Exception as exc:
        print(f"[kinema:data] wm_settings register FAILED: {exc}")


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
