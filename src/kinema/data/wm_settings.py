"""WindowManager.kinema_clipboard — Active Instance の設定をコピペするための
session-only クリップボード。

各カテゴリごとに JSON 文字列でスロットを持つ。`all` だけ別スロットにして
「カテゴリ別ペースト」と「一括ペースト」を独立に扱えるようにする。
PointerProperty は対象 ID の名前を保存し、ペースト時に `bpy.data` から解決する。

WindowManager は session-only（.blend を跨いで保持される）なので、Blender
を閉じない限り別 .blend でもペースト可能。
"""

from __future__ import annotations

import bpy
from bpy.props import StringProperty


class KinemaClipboard(bpy.types.PropertyGroup):
    pose_json: StringProperty(name="Lens/Shift", default="")
    dof_json: StringProperty(name="DoF", default="")
    follow_json: StringProperty(name="Follow", default="")
    lookat_json: StringProperty(name="LookAt", default="")
    noise_json: StringProperty(name="Noise", default="")
    all_json: StringProperty(name="All", default="")

    # Diagnostics の出力（最新 Run の結果。\n 区切り）
    diag_log: StringProperty(name="Diagnostics Log", default="")


def register() -> None:
    bpy.utils.register_class(KinemaClipboard)
    bpy.types.WindowManager.kinema_clipboard = bpy.props.PointerProperty(
        type=KinemaClipboard,
    )


def unregister() -> None:
    try:
        del bpy.types.WindowManager.kinema_clipboard
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(KinemaClipboard)
    except Exception:
        pass
