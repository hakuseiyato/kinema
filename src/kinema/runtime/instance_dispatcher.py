"""Instance dispatcher — frame_change / depsgraph_update_post から呼ばれ、
Instance に設定された Follow / LookAt / Noise を毎フレーム適用する。

旧 `shot_dispatcher` から Shot Clip 関連を取り除き、Instance ベースの追従だけに
責務を絞ったもの。Blender 標準の Timeline / VSE / Marker と組み合わせて運用する。
"""

from __future__ import annotations

import math
import time

from ..utils import refs
from . import follow_lookat, noise as noise_mod
from . import target_resolve


# 再帰防止フラグ
_in_dispatch = False

# Duplicate Operator など、複数プロパティを連続書込中に dispatch を全停止する
# ための明示フラグ。書込終了後 1 度だけ dispatch するパターンで使う。
_dispatch_suspended = False

# レンダー中フラグ（render_pre/post handler で切替）。
# True の間は:
#   - depsgraph_update_post 経由の dispatch を全 skip（frame_change_post で十分）
#   - _apply_preview_preset を skip（render 中はエディタプレビュー不要）
# これで render 中の per-frame overhead をほぼ半減させる。
_is_rendering = False


def set_rendering(active: bool) -> None:
    """render_pre / render_post から呼ぶ。"""
    global _is_rendering
    _is_rendering = active


def is_rendering() -> bool:
    return _is_rendering


# バースト抑制用: 直近の dispatch 時刻
_last_dispatch_time: dict[str, float] = {}

# ターゲット変更時の snap フラグ（次回 dispatch で damping を一度だけ無視）。
# Instance Item / Camera Preset の follow_target / lookat_target 系プロパティ
# 変更時に True にセットされる。dispatch 完了後にクリア。
_force_snap_once: bool = False


def request_snap_once() -> None:
    """次回 dispatch で damping を一度だけ無視して即時追従させる。

    Follow / LookAt ターゲット変更直後に呼ぶ。これがないと damping が大きい
    ときに「ほとんど動かない」状態に見えることがある。
    """
    global _force_snap_once
    _force_snap_once = True


def suspend_dispatch():
    """`with` ブロック相当: dispatch を抑止する（バッチ書込開始時に呼ぶ）。"""
    global _dispatch_suspended
    _dispatch_suspended = True


def resume_dispatch():
    """dispatch 抑止を解除する。"""
    global _dispatch_suspended
    _dispatch_suspended = False

# バースト抑制閾値（秒）。240Hz 上限。
_BURST_MIN_INTERVAL = 1.0 / 240.0


def reset_state() -> None:
    """`.blend` 読込時に呼ぶ。"""
    global _in_dispatch
    _in_dispatch = False
    _last_dispatch_time.clear()
    follow_lookat.reset_frame_cache()


def _resolve_follow_target(params):
    """Follow Target を解決。use_collection モード時は collection 内の
    hide_viewport==False の最初のオブジェクトを返す。解決失敗なら Object 直指定。
    """
    return target_resolve.resolve_target(params, "follow_target")


def _resolve_lookat_target(inst):
    """LookAt Target を決定。

    優先順位:
      1. lookat_target_use_collection ON → collection で解決
      2. lookat_target (Object 直指定)
      3. follow_auto_lookat が True なら Follow Target を採用（collection 経由も含む）
    "変な方向を見る" 事故防止のため、3 は最終フォールバック。
    """
    if getattr(inst, "lookat_target_use_collection", False):
        coll = getattr(inst, "lookat_target_collection", None)
        resolved = target_resolve.resolve_visible_in_collection(coll)
        if resolved is not None:
            return resolved
    explicit = refs.safe_object(inst.lookat_target)
    if explicit is not None:
        return explicit
    if getattr(inst, "follow_auto_lookat", True):
        return _resolve_follow_target(inst)
    return None


def _apply_dof_focus(cam, params) -> None:
    """params.dof_focus_use_collection ON 時、cam.data.dof.focus_object に
    collection 解決結果を書き戻す。OFF 時は触らない（標準 UI 経由のユーザー指定を尊重）。
    """
    if not getattr(params, "dof_focus_use_collection", False):
        return
    if cam is None or cam.data is None or not hasattr(cam.data, "dof"):
        return
    coll = getattr(params, "dof_focus_collection", None)
    resolved = target_resolve.resolve_visible_in_collection(coll)
    try:
        if cam.data.dof.focus_object is not resolved:
            cam.data.dof.focus_object = resolved
    except Exception:
        pass


def _apply_preview_preset(scene) -> None:
    """Active Preset の Camera Data.kinema_preset をライブプレビュー適用する。

    判定:
      - scene.kinema.active_preset_index が有効な Preset 行を指す
      - その Camera オブジェクトが scene.camera と一致している
        (= ユーザーが Auto Preview でこの Preset を見ている状態)
      - その Camera が Instance としても Load 済みではない（Instance 側が優先）
    上記が満たされた場合のみ、`cam.data.kinema_preset` のパラメータで
    `update_follow / update_lookat / noise` を呼んで Camera を動かす。

    これにより Load する前段階でも Preset の事前設定が「実機で動く」のを
    確認できる。
    """
    import bpy  # noqa: PLC0415
    st = getattr(scene, "kinema", None)
    if st is None:
        return
    idx = st.active_preset_index
    if idx < 0 or idx >= len(st.presets):
        return
    item = st.presets[idx]
    if item.is_header:
        return
    cam = bpy.data.objects.get(item.name)
    if cam is None or cam.type != "CAMERA" or cam.data is None:
        return
    # scene.camera が preset cam でなければプレビュー対象外
    if scene.camera is not cam:
        return
    # 同じ Camera が Instance として Load 済みなら Instance 側が動かす
    for inst in st.instances:
        if refs.safe_object(inst.camera_ref) is cam:
            return
    cp = getattr(cam.data, "kinema_preset", None)
    if cp is None:
        return

    dt = follow_lookat.compute_dt(scene)

    # Follow （Collection モード対応）
    follow_obj = _resolve_follow_target(cp)
    if follow_obj is not None:
        follow_lookat.update_follow(cam, cp, dt, target_override=follow_obj)

    # LookAt （Collection / 明示指定 / Follow Target 自動採用）
    if getattr(cp, "lookat_target_use_collection", False):
        resolved = target_resolve.resolve_visible_in_collection(
            getattr(cp, "lookat_target_collection", None)
        )
    else:
        resolved = None
    if resolved is not None:
        effective_lookat = resolved
    else:
        explicit = refs.safe_object(cp.lookat_target)
        if explicit is not None:
            effective_lookat = explicit
        elif getattr(cp, "follow_auto_lookat", True):
            effective_lookat = _resolve_follow_target(cp)
        else:
            effective_lookat = None

    # DoF Focus Collection モード
    _apply_dof_focus(cam, cp)

    roll_deg = float(getattr(cp, "follow_rot_y", 0.0))
    if effective_lookat is not None:
        lookat_damp = cp.lookat_damping if getattr(cp, "use_damping", True) else 0.0
        follow_lookat.update_lookat_with_target(
            cam, effective_lookat, lookat_damp, dt, roll_deg=roll_deg,
        )
    else:
        follow_lookat.cleanup_lookat_proxy(cam)
        if abs(roll_deg) > 0.001:
            try:
                cam.rotation_euler[2] = math.radians(roll_deg)
            except Exception:
                pass

    if cp.noise_enabled:
        noise_mod.apply_noise_frame(cam, cp, scene.frame_current)


def _apply_instances(scene) -> None:
    """Instance に対して Follow/LookAt/Noise を 1 ステップ適用。

    Roll (follow_rot_y) は:
      - LookAt が active → update_lookat_with_target に roll を渡して
        rotation 計算の最終段で local Z 軸回転として加える
      - LookAt が無い → cam.rotation_euler[2] に直接書込
    """
    st = getattr(scene, "kinema", None)
    if st is None:
        return
    dt = follow_lookat.compute_dt(scene)
    frame = scene.frame_current

    # Solo: solo フラグの立った Instance があればそれだけ評価
    solo_set = [i for i in st.instances if getattr(i, "solo", False)]
    pool = solo_set if solo_set else list(st.instances)

    for inst in pool:
        if not inst.enabled:
            continue
        cam = refs.safe_object(inst.camera_ref)
        if not refs.is_camera_object(cam):
            continue
        # Follow （Collection モード対応）
        follow_obj = _resolve_follow_target(inst)
        if follow_obj is not None:
            follow_lookat.update_follow(cam, inst, dt, target_override=follow_obj)
        # LookAt は Collection モード / 明示指定 / Follow Target 自動採用 の順
        effective_lookat = _resolve_lookat_target(inst)
        # DoF Focus Collection モード
        _apply_dof_focus(cam, inst)
        roll_deg = float(getattr(inst, "follow_rot_y", 0.0))
        if effective_lookat is not None:
            lookat_damp = inst.lookat_damping if getattr(inst, "use_damping", True) else 0.0
            follow_lookat.update_lookat_with_target(
                cam, effective_lookat, lookat_damp, dt, roll_deg=roll_deg,
            )
        else:
            # 何も注視するものがない → 既存の Proxy を掃除
            follow_lookat.cleanup_lookat_proxy(cam)
            # LookAt 無し時の Roll: rotation_euler に直接書く
            if abs(roll_deg) > 0.001:
                try:
                    cam.rotation_euler[2] = math.radians(roll_deg)
                except Exception:
                    pass
        if inst.noise_enabled:
            noise_mod.apply_noise_frame(cam, inst, frame)


def dispatch(scene, force: bool = False) -> None:
    """frame_change_pre / depsgraph_update_post / update callback のエントリ。

    force=False 時はバースト抑制（240Hz 上限）を効かせる。
    `request_snap_once()` 直後の呼び出しは burst を無視して必ず処理し、
    damping cache をリセットしてから 1 回だけスナップ追従させる。
    """
    global _in_dispatch, _force_snap_once
    if _in_dispatch:
        return
    if _dispatch_suspended:
        return  # Duplicate などのバッチ書込中
    if not hasattr(scene, "kinema"):
        return

    # render 中の snap は damped follow の連続性を壊すので無視する。
    # snap 要求自体はクリアして、render 後の操作に影響しないようにする。
    snap_now = _force_snap_once and not _is_rendering
    if _force_snap_once and _is_rendering:
        _force_snap_once = False
    if snap_now:
        # ターゲット変更直後の追従漏れ防止: damping を 1 回だけ無視させる。
        # damping.compute_dt() は cache 不在 = 初回呼出として 0 を返すため、
        # damping_alpha(_, 0) → 1.0 (スナップ) になる。
        follow_lookat.reset_frame_cache()
        _last_dispatch_time[scene.name] = time.monotonic()
    elif not force:
        now = time.monotonic()
        last = _last_dispatch_time.get(scene.name, 0.0)
        if now - last < _BURST_MIN_INTERVAL:
            return
        _last_dispatch_time[scene.name] = now
    else:
        _last_dispatch_time[scene.name] = time.monotonic()

    _in_dispatch = True
    try:
        _apply_instances(scene)
        # Active Preset の Camera が scene.camera のとき、Preset 設定で
        # ライブプレビュー適用（Load 前のテスト用）。render 中はスキップ。
        if not _is_rendering:
            _apply_preview_preset(scene)
    finally:
        _in_dispatch = False
        if snap_now:
            _force_snap_once = False
