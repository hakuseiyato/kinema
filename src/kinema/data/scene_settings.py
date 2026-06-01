"""KinemaSceneSettings — Scene にぶら下がる最上位 PropertyGroup。

Shot Timeline 関連の集合 (tracks / shot_clips / timeline_view) は撤回した。
代わりに Blender 標準 Timeline / VSE / Marker を運用で使う。
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    IntProperty,
    StringProperty,
)

from ..config import constants as C
from . import preset_item, instance_item, cut_item, shot_item


def _select_only_object(context, obj):
    """指定オブジェクトのみを Outliner / Viewport で選択し active にする。

    既存選択は全解除する（kinema 行クリック = カメラを 1 つ選択する直感）。
    """
    if obj is None:
        return
    try:
        for o in context.view_layer.objects:
            try:
                if o.select_get():
                    o.select_set(False)
            except Exception:
                pass
        obj.select_set(True)
        context.view_layer.objects.active = obj
    except Exception:
        pass


def _on_active_instance_changed(self, context):
    """Active Instance 切替時の連動:
      1) "Kinema Camera" Keying Set があれば最新 Active で Rebuild
      2) 該当 Instance のカメラを Outliner / Viewport で選択 + active に
    """
    # 1) Keying Set 自動 Rebuild
    try:
        from ..ops.keyframe_ops import KEYING_SET_LABEL  # noqa: PLC0415
        scene = context.scene
        ks = scene.keying_sets.get(KEYING_SET_LABEL)
        if ks is not None:
            bpy.ops.kinema.rebuild_keying_set("INVOKE_DEFAULT")
    except Exception:
        pass

    # 2) Outliner 連動 + Auto Preview
    try:
        idx = self.active_instance_index
        if 0 <= idx < len(self.instances):
            cam = self.instances[idx].camera_ref
            _select_only_object(context, cam)
            # Auto Preview: 該当カメラを scene.camera に設定（OFF にしてもらえれば抑止可能）
            if getattr(self, "auto_preview_on_select", True):
                try:
                    if cam is not None and cam.type == "CAMERA":
                        context.scene.camera = cam
                except Exception:
                    pass
    except Exception:
        pass


def _on_active_shot_changed(self, context):
    """Active Shot 切替時:
      1. Shot.frame_start に jump
      2. 紐付け Instance のカメラを scene.camera に切替
      3. active_instance_index も連動
    Shot Manager パネルで Shot 行クリックするだけで該当 frame + カメラに飛ぶ運用。
    """
    try:
        idx = self.active_shot_index
        if not (0 <= idx < len(self.shots)):
            return
        shot = self.shots[idx]
        scene = context.scene
        # フレーム jump
        try:
            from ..ops.shot_ops import _resolve_shot_frame_range, _sorted_markers  # noqa: PLC0415
            sorted_ms = _sorted_markers(scene)
            fs, _fe = _resolve_shot_frame_range(scene, shot, sorted_ms)
            scene.frame_current = int(fs)
        except Exception:
            pass
        # カメラ切替
        if not getattr(self, "auto_preview_on_select", True):
            return
        if not shot.instance_name:
            return
        inst = next((i for i in self.instances if i.name == shot.instance_name), None)
        if inst is None:
            return
        from ..utils import refs as _refs  # noqa: PLC0415
        cam = _refs.safe_object(inst.camera_ref)
        if cam is None or cam.type != "CAMERA":
            return
        try:
            scene.camera = cam
            _select_only_object(context, cam)
            try:
                self.active_instance_index = list(self.instances).index(inst)
            except ValueError:
                pass
        except Exception:
            pass
    except Exception:
        pass


def _on_active_cut_changed(self, context):
    """Phase 2 で deprecated。cuts[] は auto-migrate で shots[] に統合されたので
    このコールバックは実質呼ばれない（cuts[] が空のため）。互換のため stub を残す。"""
    pass


def _trigger_camera_visibility_update(scene):
    """auto_hide_unused_cameras 変更 / shots[] 編集時に呼ぶ。"""
    try:
        from ..runtime import camera_visibility  # noqa: PLC0415
        camera_visibility.apply_camera_visibility(scene)
    except Exception as exc:
        print(f"[kinema] camera visibility update failed: {exc}")


def _on_active_preset_changed(self, context):
    """Active Preset 切替時、該当 Camera オブジェクトを Outliner で選択 + active に。

    `auto_preview_on_select` が True なら `scene.camera` も切替えてカメラビュー
    でフォーカスする（Instance 側と同じ挙動）。
    `scene.camera` 切替後に dispatcher を呼んで Preset の事前設定をライブ
    プレビュー適用する（`_apply_preview_preset` がトリガされる）。
    """
    try:
        idx = self.active_preset_index
        if 0 <= idx < len(self.presets):
            item = self.presets[idx]
            if item.is_header:
                return
            cam = bpy.data.objects.get(item.name)
            if cam is not None and cam.type == "CAMERA":
                _select_only_object(context, cam)
                if getattr(self, "auto_preview_on_select", True):
                    try:
                        context.scene.camera = cam
                    except Exception:
                        pass
                    # Preset 設定をライブプレビュー適用
                    try:
                        from ..runtime import instance_dispatcher  # noqa: PLC0415
                        instance_dispatcher.dispatch(context.scene, force=True)
                    except Exception:
                        pass
    except Exception:
        pass


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

    # --- Preset 一覧（scan_presets の結果キャッシュ）---
    presets: CollectionProperty(type=preset_item.KinemaPresetItem)
    active_preset_index: IntProperty(
        name="Active Preset",
        default=0,
        update=_on_active_preset_changed,
    )

    # --- Instance 一覧 ---
    instances: CollectionProperty(type=instance_item.KinemaInstanceItem)
    active_instance_index: IntProperty(
        name="Active Instance",
        default=0,
        update=_on_active_instance_changed,
    )

    # --- Cut 一覧（旧 schema、Phase 2 で削除予定）---
    cuts: CollectionProperty(type=cut_item.KinemaCut)
    active_cut_index: IntProperty(
        name="Active Cut",
        default=0,
        update=_on_active_cut_changed,
    )

    # --- Shot 一覧（統合 schema, Phase 2 で canonical 化）---
    # Timeline Marker × カメラ × 出演 Cast を統合管理する新エンティティ
    shots: CollectionProperty(type=shot_item.KinemaShot)
    active_shot_index: IntProperty(
        name="Active Shot",
        default=0,
        update=_on_active_shot_changed,
    )

    # Phase B: 使用してないカメラの自動非表示
    auto_hide_unused_cameras: BoolProperty(
        name="Auto-hide Unused Cameras",
        description=(
            "shots[] で参照されていないカメラを hide_viewport=True にする。"
            "ON にすると Timeline で使ってないカメラがビューポートから消える"
        ),
        default=False,
        update=lambda self, ctx: _trigger_camera_visibility_update(ctx.scene),
    )

    # データフォーマットバージョン
    # 1 = 旧 (cuts[] と yato_vis.cast_markers が canonical)
    # 2 = 新 (shots[] が canonical、cuts[] / cast_markers は Phase 2 で削除)
    data_format_version: IntProperty(
        name="Data Format Version",
        description="kinema scene データのスキーマ世代",
        default=1,
    )

    # --- 動作 ---
    auto_preview_on_select: BoolProperty(
        name="Auto Preview on Select",
        description="Cameras タブで Instance / Preset を選択するだけで scene.camera を切り替える",
        default=True,
    )

    # --- パネル折り畳み状態 ---
    preset_config_collapsed: BoolProperty(
        name="Preset Config Collapsed",
        description="Preset Config セクションを折り畳む",
        default=False,
    )
    active_instance_collapsed: BoolProperty(
        name="Active Instance Collapsed",
        description="Active Instance セクションを折り畳む",
        default=False,
    )
    render_output_collapsed: BoolProperty(
        name="Render Output Collapsed",
        description="Render の出力設定セクションを折り畳む",
        default=True,
    )
    cuts_collapsed: BoolProperty(
        name="Cuts Collapsed",
        description="Cuts セクションを折り畳む",
        default=False,
    )

    # --- Render dispatch（単一ボタン + トグルで何を出力するか決める）---
    render_source: bpy.props.EnumProperty(
        name="Render Source",
        description="Render ボタンが対象にする source",
        items=(
            ("CUTS", "Cuts", "Cut を対象にする"),
            ("INSTANCES", "Instances", "Instance を対象にする"),
        ),
        default="CUTS",
    )
    render_mode: bpy.props.EnumProperty(
        name="Render Mode",
        description="Render ボタンが対象を絞る粒度",
        items=(
            ("ACTIVE", "Active", "選択中の 1 個だけ"),
            ("ENABLED", "Enabled", "enabled=ON のものすべて"),
        ),
        default="ACTIVE",
    )
