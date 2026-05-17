"""プリセット一覧の 1 行。スキャン結果のキャッシュビュー。"""

from __future__ import annotations

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty


class KinemaPresetItem(bpy.types.PropertyGroup):
    """Preset Root をスキャンした結果の 1 件、または UI 用のグループヘッダ。

    `is_header=True` のものはクリック不可の見出し行として扱う。
    ヘッダ行は `header_collapsed` を持ち、True の時はそのグループの子を
    UIList の draw_filter が非表示にする。
    """

    # 共通
    name: StringProperty(name="Name", default="")
    is_header: BoolProperty(name="Is Group Header", default=False)
    header_collapsed: BoolProperty(name="Header Collapsed", default=False)
    child_count: IntProperty(name="Child Count", default=0)
    group: StringProperty(name="Group", default="")
    short_name: StringProperty(name="Short Name", default="")
    display_name: StringProperty(name="Display Name", default="")

    # 代表カメラ
    camera_name: StringProperty(name="Camera Name", default="")

    # メタ（カスタムプロパティから読んだもの）
    tags: StringProperty(name="Tags", default="")
    has_anim: BoolProperty(name="Has Animation", default=False)
    default_lens: FloatProperty(name="Default Lens (mm)", default=0.0)
    preview_end: IntProperty(name="Preview End Frame", default=0)
    follow_target: StringProperty(name="Follow Target", default="")
    lookat_target: StringProperty(name="LookAt Target", default="")
