"""WindowManager.kinema — session-only な kinema 状態。

ホスト Area の識別子（`Window.as_pointer()` 等）や Modal の dry-run バッファ等、
`.blend` を跨いで持ち越したくないデータをここに置く。Scene Settings (永続)
とは別管理。
"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty


class KinemaWMSettings(bpy.types.PropertyGroup):
    # --- Timeline ホスト識別 ---
    host_window_pointer: StringProperty(
        name="Host Window Pointer",
        description="session 中だけ有効な Window.as_pointer() の文字列化",
        default="",
    )
    host_area_pointer: StringProperty(
        name="Host Area Pointer",
        description="session 中だけ有効な Area.as_pointer() の文字列化",
        default="",
    )
    # 二次キー（pointer が無効化された時のフォールバック）
    host_screen_name: StringProperty(name="Host Screen Name", default="")
    host_area_index: IntProperty(name="Host Area Index", default=-1)

    # kinema timeline モードの ON/OFF
    timeline_mode_on: BoolProperty(
        name="Timeline Mode",
        description="Image Editor を kinema タイムラインビューに切り替える",
        default=False,
    )

    # Modal dry-run 中のバッファ（JSON 文字列）
    modal_dryrun_state: StringProperty(
        name="Modal Dry-run State",
        description="Modal Operator の確定前一時バッファ（JSON）",
        default="",
    )


def register() -> None:
    bpy.utils.register_class(KinemaWMSettings)
    bpy.types.WindowManager.kinema = bpy.props.PointerProperty(type=KinemaWMSettings)


def unregister() -> None:
    try:
        del bpy.types.WindowManager.kinema
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(KinemaWMSettings)
    except Exception:
        pass
