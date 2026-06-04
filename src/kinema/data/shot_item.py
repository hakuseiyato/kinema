"""KinemaShot — kinema と yato_visibility_kit の共通 Shot 概念。

設計（Phase 1）:
  - Timeline Camera Marker 1 つ = Shot 1 つ
  - 1 つの Shot に「カメラ (Instance)」と「出演メンバ (Cast)」をまとめて保持
  - 既存の `kinema.cuts[]` と `yato_vis.groups[].cast_markers` を統合する
  - Phase 1 では旧データは触らず、Migrate で shots[] を populate する

データ構造:
  Scene.kinema.shots[] (KinemaShot)
    ├ name                       : 表示名
    ├ marker_name                : Timeline Marker との紐付け ID
    ├ instance_name              : Camera (kinema.instances[].name)
    ├ frame_override / 範囲       : 自動 (Marker 由来) か手動
    ├ enabled                    : Render 対象に含むか
    ├ notes                      : 自由メモ
    ├ orphan                     : Marker が消えた状態
    └ cast: [ KinemaShotCastEntry ]
         ├ group_name            : yato_vis.groups[].name 参照
         ├ enabled               : 出演する/しない
         └ solo_target_name      : Solo モード時のターゲット名（""=Solo OFF）

更新時の伝播（Phase 2 で実装予定）:
  cast.enabled / solo_target_name の変更 → visibility_kit に bake を依頼
  shot.instance_name 変更 → kinema 側で render target 更新
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    StringProperty,
)


def _on_cast_entry_changed(self, context):
    """cast entry の enabled / solo_target_name 変更で visibility_kit に bake 依頼。

    **clean_rebuild を使う**: 通常 bake は marker frame でしか key を消さず
    prev_hidden 最適化で key を間引くため、過去キーが支配して toggle の差分が
    反映されない。clean_rebuild は対象 group の visibility fcurve を全消去して
    全 marker に明示 key を打ち直すので、差分が確実に反映される。

    対象は **自分の group のみ**: cast に未登録の他 group は事前に Rebuild All
    Visibility Keys ボタンで初期化してから、以降は per-group の clean rebuild
    だけで差分が維持される。
    """
    try:
        from ..utils import visibility_kit_bridge as _vkb  # noqa: PLC0415
        scene = getattr(context, "scene", None)
        if scene is None:
            return
        _vkb.request_clean_rebuild_for_group(scene, self.group_name)
        _vkb.force_viewport_refresh(scene)
    except Exception as exc:
        print(f"[kinema:shot] cast entry update bake failed: {exc}")


class KinemaShotCastEntry(bpy.types.PropertyGroup):
    """Shot に出演する Group エントリ。yato_vis.groups[].name を参照する。"""

    group_name: StringProperty(
        name="Group",
        description="yato_vis.groups[].name を指す参照名",
        default="",
    )
    enabled: BoolProperty(
        name="On Stage",
        description="この Shot に出演するか（OFF = 非表示）",
        default=True,
        update=_on_cast_entry_changed,
    )
    solo_target_name: StringProperty(
        name="Solo Target",
        description=(
            "Solo モード時に表示する Object 名。空文字なら Solo OFF（Group 全員可視）"
        ),
        default="",
        update=_on_cast_entry_changed,
    )


class KinemaShot(bpy.types.PropertyGroup):
    """1 Shot = 1 Camera Marker セグメント。"""

    # --- 識別 ---
    name: StringProperty(
        name="Name",
        description="Shot 表示名。Rename Shot Operator で Marker / Instance / Cast 参照を連動",
        default="Shot",
    )
    marker_name: StringProperty(
        name="Marker Name",
        description="対応する Timeline Marker 名（rename 耐性の追跡 ID）",
        default="",
    )

    # --- カメラ紐付け ---
    instance_name: StringProperty(
        name="Instance",
        description="この Shot で使う kinema.instances[].name",
        default="",
    )

    # --- 出演メンバ ---
    cast: CollectionProperty(type=KinemaShotCastEntry)

    # --- 制御 ---
    enabled: BoolProperty(
        name="Enabled",
        description="Render Shots で対象にするか",
        default=True,
    )

    # --- フレーム範囲 ---
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

    # --- メモ ---
    notes: StringProperty(
        name="Notes",
        description="Shot 個別のメモ",
        default="",
    )

    # --- Sync 状態 ---
    orphan: BoolProperty(
        name="Orphan",
        description="対応 Marker が見つからない状態（Sync で検出、削除はユーザー判断）",
        default=False,
    )
