"""ロード済みカメラインスタンス（Preset から複製されたもの）。"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


def _is_camera_poll(self, obj):
    return obj is None or obj.type == "CAMERA"


def _is_object_poll(self, obj):
    return True


def _find_owner_scene(inst):
    """この Instance Item を所有する Scene を bpy.data.scenes から逆引き。

    `context.scene` をそのまま信用すると、複数 Scene 構成で別 Scene の
    Instance を編集中に「常に context.scene （= 最初のシーン）」を対象にして
    しまうため、必ず所有 scene を特定して使う。
    """
    import bpy
    for scene in bpy.data.scenes:
        st = getattr(scene, "kinema", None)
        if st is None:
            continue
        for it in st.instances:
            if it.as_pointer() == inst.as_pointer():
                return scene
    return None


# Instance.name の update callback で再帰防止のためのフラグ。
# PropertyGroup 自体に属性を後付けできないので、モジュール内 set で管理。
_renaming_in_progress: set = set()


def _on_name_changed(self, context):
    """Instance.name 変更時、対応する Collection と Camera も同名にリネーム。

    Blender が衝突回避で `.001` を付けた場合は、その結果を inst.name に
    書き戻して整合させる。再帰防止は `_renaming_in_progress` で管理。
    """
    uid = id(self)
    if uid in _renaming_in_progress:
        return
    _renaming_in_progress.add(uid)
    try:
        new_name = self.name
        if not new_name:
            return
        # Collection をリネーム
        coll = self.collection_ref
        if coll is not None and coll.name != new_name:
            try:
                coll.name = new_name
                if coll.name != new_name:
                    # Blender が衝突回避で別名にしたら inst.name もそれに合わせる
                    self.name = coll.name
                    return
            except Exception:
                pass
        # Camera オブジェクトも同名にリネーム（衝突時は黙って許容）
        cam = self.camera_ref
        if cam is not None and cam.name != new_name:
            try:
                cam.name = new_name
            except Exception:
                pass
    finally:
        _renaming_in_progress.discard(uid)


def _apply_now(self, context):
    """Instance プロパティが変わった時に即座に Follow/LookAt/Noise を 1 ステップ適用。

    再生していない状態でもユーザーがスライダーを動かしたら追従が見えるようにする。
    Blender 標準の Auto Keyframe (赤丸) が ON のときは、変更されたプロパティに
    対しても keyframe_insert を呼んで標準動作に合わせる。

    所有 Scene を確実に特定するため bpy.data.scenes を逆引きする。
    """
    try:
        # 所有 scene を逆引き（context.scene と一致しない場合への対策）
        scene = _find_owner_scene(self)
        if scene is None:
            return

        from ..runtime import instance_dispatcher
        # 再帰防止：dispatch 中の自己呼び出しを抑止
        if instance_dispatcher._in_dispatch:
            return
        instance_dispatcher.dispatch(scene)

        # Lock 中は Auto Keyframe 対象外
        if getattr(self, "locked", False):
            return

        # Auto Keyframe 連携: 標準赤丸 ON なら変更プロパティを scene 経由でキー
        ts = scene.tool_settings
        if not ts.use_keyframe_insert_auto:
            return
        st = scene.kinema
        try:
            idx = list(st.instances).index(self)
        except ValueError:
            return
        # 全 Instance プロパティを 1 度ずつキーする（個別パスを特定するより安全）
        from ..ops.keyframe_ops import _key_instance_props  # noqa: PLC0415
        _key_instance_props(scene, idx, scene.frame_current)
    except Exception:
        # update callback は何があっても UI を壊さない
        pass


class KinemaInstanceItem(bpy.types.PropertyGroup):
    """1 つのロード済みプリセット = 1 行。"""

    # --- 識別 ---
    name: StringProperty(
        name="Name",
        description=(
            "Instance 名。UIList でダブルクリックすると編集可能。"
            "編集時は対応する Collection と Camera も同名にリネームされる"
        ),
        default="",
        update=_on_name_changed,
    )
    source_preset: StringProperty(name="Source Preset", default="")
    collection_ref: PointerProperty(name="Collection", type=bpy.types.Collection)
    camera_ref: PointerProperty(
        name="Camera",
        type=bpy.types.Object,
        poll=_is_camera_poll,
    )

    # --- ON/OFF / Solo / Lock ---
    enabled: BoolProperty(
        name="Enabled",
        description="ランタイム（Follow/LookAt/Noise）を適用するか。"
                    "OFF = Mute（dispatcher が skip）",
        default=True,
        update=_apply_now,
    )
    solo: BoolProperty(
        name="Solo",
        description="ON にした Instance だけを dispatcher が評価する。"
                    "複数 Instance を solo にすればその全てが評価対象",
        default=False,
        update=_apply_now,
    )
    locked: BoolProperty(
        name="Locked",
        description="編集ロック。UI で Follow/LookAt/Noise スライダーを"
                    "灰色表示し、Key All / Auto Keyframe からも除外",
        default=False,
    )

    # --- Lens ---
    lens_mm: FloatProperty(
        name="Lens (mm)",
        description="焦点距離。Pose タブから上書きできる",
        default=50.0,
        min=1.0,
        max=5000.0,
    )

    # --- Follow ---
    follow_target: PointerProperty(
        name="Follow Target", type=bpy.types.Object, poll=_is_object_poll,
        update=_apply_now,
    )
    follow_target_use_collection: BoolProperty(
        name="Use Collection",
        description="Follow Target を Collection で指定。"
                    "毎フレーム collection 内の hide_viewport==False の最初の "
                    "オブジェクトを動的に解決して target にする（Solo モード連動）",
        default=False,
        update=_apply_now,
    )
    follow_target_collection: PointerProperty(
        name="Follow Target Collection", type=bpy.types.Collection,
        update=_apply_now,
    )
    follow_distance: FloatProperty(
        name="Distance", description="target からの半径距離",
        default=5.0, min=0.0, update=_apply_now,
    )
    # Euler XYZ 軸回転で target 周りに自由配置
    follow_rot_x: FloatProperty(
        name="X 軸回転 (上下)",
        description=(
            "target を中心とした X 軸回り（上下角）。"
            "0=水平, 正値=見下ろし（上から）, 負値=見上げ（下から）"
        ),
        default=0.0, min=-89.0, max=89.0,
        update=_apply_now,
    )
    follow_rot_y: FloatProperty(
        name="Y 軸回転 (ロール)",
        description=(
            "カメラのロール（傾き）。"
            "target との位置関係には影響せず、画面の傾きだけ変える"
        ),
        default=0.0, min=-180.0, max=180.0,
        update=_apply_now,
    )
    follow_rot_z: FloatProperty(
        name="Z 軸回転 (水平回り)",
        description=(
            "target を中心とした Z 軸回り（水平角）。"
            "0=正面, 90=右, 180=背後, -90=左"
        ),
        default=0.0, min=-360.0, max=360.0,
        update=_apply_now,
    )
    follow_height: FloatProperty(
        name="Height", description="ワールド Z 軸方向の追加オフセット",
        default=0.0, update=_apply_now,
    )
    follow_side: FloatProperty(
        name="Side Offset", description="ビュー横方向の追加オフセット",
        default=0.0, update=_apply_now,
    )
    follow_damping: FloatProperty(name="Follow Damping", default=0.3, min=0.0, max=1.0, update=_apply_now)
    follow_auto_lookat: BoolProperty(
        name="Auto Look at Follow Target",
        description=(
            "LookAt Target が未指定の場合、Follow Target を自動的に注視する。"
            "「変な方向を見る」事故を防ぐ"
        ),
        default=True,
        update=_apply_now,
    )

    # --- LookAt ---
    lookat_target: PointerProperty(
        name="LookAt Target", type=bpy.types.Object, poll=_is_object_poll,
        update=_apply_now,
    )
    lookat_target_use_collection: BoolProperty(
        name="Use Collection",
        description="LookAt Target を Collection で指定。"
                    "毎フレーム collection 内の hide_viewport==False の最初の "
                    "オブジェクトを動的に解決して target にする",
        default=False,
        update=_apply_now,
    )
    lookat_target_collection: PointerProperty(
        name="LookAt Target Collection", type=bpy.types.Collection,
        update=_apply_now,
    )
    lookat_damping: FloatProperty(name="LookAt Damping", default=0.3, min=0.0, max=1.0, update=_apply_now)

    # --- DoF Focus (Camera Data.dof.focus_object の Collection モード拡張) ---
    dof_focus_use_collection: BoolProperty(
        name="DoF Focus Use Collection",
        description="被写界深度の焦点オブジェクトを Collection で指定。"
                    "毎フレーム collection 内の hide_viewport==False の最初の "
                    "オブジェクトを cam.data.dof.focus_object に書き戻す",
        default=False,
        update=_apply_now,
    )
    dof_focus_collection: PointerProperty(
        name="DoF Focus Collection", type=bpy.types.Collection,
        update=_apply_now,
    )

    # --- Noise ---
    noise_enabled: BoolProperty(name="Noise", default=False, update=_apply_now)
    noise_strength_pos: FloatProperty(name="Noise Pos", default=0.05, min=0.0, update=_apply_now)
    noise_strength_rot: FloatProperty(
        name="Noise Rot (deg)", default=0.5, min=0.0,
        description="ローテーション側のノイズ振幅（度）",
        update=_apply_now,
    )
    noise_frequency: FloatProperty(name="Noise Freq", default=0.5, min=0.0, update=_apply_now)
    noise_seed: IntProperty(name="Noise Seed", default=0, min=0, update=_apply_now)
