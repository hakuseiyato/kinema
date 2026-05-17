"""kinema.data — PropertyGroup 定義群。

責務別にファイルを分割し、本モジュールでまとめて register/unregister する。
"""

from __future__ import annotations

import bpy

from . import preset_item, instance_item, shot, track, timeline_view, scene_settings, wm_settings


_CLASSES = (
    # 子要素は親より先に register する必要がある
    preset_item.KinemaPresetItem,
    instance_item.KinemaInstanceItem,
    shot.KinemaShotClip,
    track.KinemaTrack,
    timeline_view.KinemaTimelineView,
    scene_settings.KinemaSceneSettings,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kinema = bpy.props.PointerProperty(type=scene_settings.KinemaSceneSettings)
    wm_settings.register()


def unregister() -> None:
    wm_settings.unregister()
    try:
        del bpy.types.Scene.kinema
    except Exception:
        pass
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
