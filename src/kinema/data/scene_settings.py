"""KinemaSceneSettings — Scene にぶら下がる最上位 PropertyGroup。"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    StringProperty,
)

from ..config import constants as C
from . import preset_item, instance_item, shot, track, timeline_view


class KinemaSceneSettings(bpy.types.PropertyGroup):
    # --- Source roots ---
    preset_root_name: StringProperty(
        name="Preset Root",
        description="プリセットを格納したコレクション名。Scene のルート直下に置く",
        default=C.DEFAULT_PRESET_ROOT,
    )
    instances_root_name: StringProperty(
        name="Instances Root",
        description="ロードしたカメラを格納するコレクション名",
        default=C.DEFAULT_INSTANCES_ROOT,
    )

    # --- Filters (将来用、alpha1 では UI 未配線) ---
    tag_filter: StringProperty(
        name="Tag Filter",
        description="カンマ区切りで AND マッチ（例: Cinematic, Hero）",
        default="",
    )

    # --- Preset 一覧（scan_presets の結果キャッシュ）---
    presets: CollectionProperty(type=preset_item.KinemaPresetItem)
    active_preset_index: IntProperty(name="Active Preset", default=0)

    # --- Instance 一覧 ---
    instances: CollectionProperty(type=instance_item.KinemaInstanceItem)
    active_instance_index: IntProperty(name="Active Instance", default=0)

    # --- Timeline data ---
    tracks: CollectionProperty(type=track.KinemaTrack)
    shot_clips: CollectionProperty(type=shot.KinemaShotClip)
    active_clip_uid: StringProperty(name="Active Clip UID", default="")
    timeline_view: bpy.props.PointerProperty(type=timeline_view.KinemaTimelineView)

    # --- 動作 ---
    auto_preview_on_select: BoolProperty(
        name="Auto Preview on Select",
        description="Cameras タブで Instance を選択するだけで scene.camera を切り替える",
        default=True,
    )
