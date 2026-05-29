"""KinemaCut — Timeline Marker と Instance を紐付けたカット情報。

設計のポイント:
  - Timeline Marker をマスター情報源として扱う（frame と camera は Marker から取得）
  - kinema 側は独自属性（enabled / instance_ref / notes / 出力 subpath 等）を保持
  - `marker_name` で Marker と紐付け、Marker rename / Cut rename どちらにも対応
  - `Sync from Markers` で Marker ⇔ Cut の整合を取り直す（自動 sync は重いので明示）

データの正:
  - frame_start / frame_end は Marker 群から計算した「現在の有効範囲」を都度反映
    （次の Marker の frame - 1、末尾は scene.frame_end）
  - frame_override=True のときだけ手動値 frame_start_override / frame_end_override を使う
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    IntProperty,
    StringProperty,
)


class KinemaCut(bpy.types.PropertyGroup):
    """1 カット = 1 Timeline Marker セグメント。"""

    # --- 識別 ---
    name: StringProperty(
        name="Name",
        description=(
            "カット名。Cut rename すると Marker / Instance / Collection / "
            "Camera を同名にカスケード rename する"
        ),
        default="Cut",
        # update は ops 側でカスケード rename を扱う（無限再帰を避けるため
        # update callback には載せない）
    )
    marker_name: StringProperty(
        name="Marker Name",
        description=(
            "対応する Timeline Marker 名。kinema は Cut.name と別にこの ID で "
            "Marker を追跡するので、ユーザーが Marker rename しても Cut の "
            "設定が失われない"
        ),
        default="",
    )

    # --- リンク先 Instance ---
    instance_name: StringProperty(
        name="Instance",
        description=(
            "このカットで使う Instance 名。空なら未紐付（Render Cuts では skip）"
        ),
        default="",
    )

    # --- 制御 ---
    enabled: BoolProperty(
        name="Enabled",
        description="Render Cuts で対象にするか",
        default=True,
    )

    # --- フレーム範囲 ---
    # 通常は Marker 群から自動計算するが、override=True で手動上書き可能
    frame_override: BoolProperty(
        name="Override Frame Range",
        description="ON のとき frame_start_override / frame_end_override を使う",
        default=False,
    )
    frame_start_override: IntProperty(
        name="Frame Start", default=1, min=0,
    )
    frame_end_override: IntProperty(
        name="Frame End", default=250, min=0,
    )

    # --- 自由メモ ---
    notes: StringProperty(
        name="Notes",
        description="カット個別のメモ（自由記述）",
        default="",
    )

    # --- Sync 時の状態フラグ（orphan = Marker が消えた Cut）---
    orphan: BoolProperty(
        name="Orphan",
        description="対応する Marker が見つからない状態。Sync で立てられ、"
                    "ユーザーが手動で削除 or 復旧するまで保持される",
        default=False,
    )
