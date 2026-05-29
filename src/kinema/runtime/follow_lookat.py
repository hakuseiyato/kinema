"""Follow / LookAt の更新ロジック。

旧 cineflow `runtime.py:_update_follow / _update_lookat` を移植 + 拡張。
設計ポイント:
  - Follow は **球面座標 (yaw / pitch / distance)** で target の周りに配置
    - yaw=0 が target.matrix_world の +Y（正面）、180 で背後（旧 TPS 動作）
    - pitch で見下ろし / 見上げ
  - LookAt は中継 Empty (LookatProxy) を介してラグ追従
  - Damping は fps 非依存 `alpha = 1 - exp(-dt/tau)`（damping.py に分離）
"""

from __future__ import annotations

import math

import bpy
from mathutils import Euler, Vector

from ..config import constants as C
from ..utils import refs
from . import damping as damping_mod


# ---------------------------------------------------------------------------
# Damping math は damping.py に切り出してテスト容易にした。
# 後方互換のため、本モジュールからも同じシンボルを再エクスポートする。
# ---------------------------------------------------------------------------

reset_frame_cache = damping_mod.reset_frame_cache
damping_alpha = damping_mod.damping_alpha


def compute_dt(scene) -> float:
    """Scene から fps/frame を取り出して damping.compute_dt を呼ぶ。"""
    return damping_mod.compute_dt(
        scene.name,
        scene.frame_current,
        float(scene.render.fps),
        float(scene.render.fps_base),
    )


# ---------------------------------------------------------------------------
# Follow
# ---------------------------------------------------------------------------

def update_follow(cam_obj, params, dt: float, target_override=None) -> None:
    """カメラを follow_target の周りに **Euler XYZ 軸回転** で配置する。

    params に以下の属性を要求:
      follow_target, follow_distance, follow_rot_x, follow_rot_y, follow_rot_z,
      follow_height, follow_side, follow_damping

    target_override: Collection モード等で解決済みの target を渡す。
      None なら params.follow_target を refs.safe_object で解決して使う。

    軸回転 (target ローカル空間):
      - rot_x: X 軸回り（上下角）。正値=見下ろし、負値=見上げ
      - rot_y: Y 軸回り（カメラのロール、位置には影響しない）
      - rot_z: Z 軸回り（水平回り）。0=正面 (+Y), 90=右 (+X), 180=背後 (-Y), -90=左 (-X)
    """
    if target_override is not None:
        target = target_override
    else:
        target = refs.safe_object(getattr(params, "follow_target", None))
    if target is None or cam_obj is None:
        return

    dist = float(params.follow_distance)
    rot_x_rad = math.radians(float(getattr(params, "follow_rot_x", 0.0)))
    rot_z_rad = math.radians(float(getattr(params, "follow_rot_z", 0.0)))
    height = float(params.follow_height)
    side = float(params.follow_side)

    # Euler XYZ 回転で初期方向 (0, 1, 0) を回転 → カメラ位置の方向ベクトル
    # Y 軸回転は (0, 1, 0) を変えないので、ここでは X と Z だけ使う。
    # Y は roll として後段で扱う（instance_dispatcher._apply_roll）。
    rot_mat = Euler((rot_x_rad, 0.0, rot_z_rad), "XYZ").to_matrix()
    dir_local = rot_mat @ Vector((0.0, 1.0, 0.0))

    # target の rotation 部分でワールド空間に変換
    rot_3x3 = target.matrix_world.to_3x3()
    dir_world = rot_3x3 @ dir_local

    # 接線右方向（カメラ視線と直交、ワールド上向きと外積）
    world_up = Vector((0.0, 0.0, 1.0))
    if abs(dir_world.dot(world_up)) > 0.999:
        tangent_right = (rot_3x3 @ Vector((1.0, 0.0, 0.0))).normalized()
    else:
        tangent_right = dir_world.cross(world_up).normalized()

    ideal = (
        target.matrix_world.translation
        + dir_world * dist
        + world_up * height
        + tangent_right * side
    )

    # use_damping=False のときは damping を 0 とみなしてスナップ
    if getattr(params, "use_damping", True):
        damping_val = float(params.follow_damping)
    else:
        damping_val = 0.0
    alpha = damping_alpha(damping_val, dt)
    if alpha >= 0.999:
        cam_obj.location = ideal
    else:
        cam_obj.location = Vector(cam_obj.location).lerp(ideal, alpha)


# ---------------------------------------------------------------------------
# LookAt
# ---------------------------------------------------------------------------

def _ensure_lookat_proxy(cam_obj, target) -> bpy.types.Object:
    """LookAt 用の中継 Empty を取得 or 作成。

    Proxy は target 位置を damping で滑らかに追跡する。カメラの回転は自前
    計算でこの Proxy を見るようにする（Track To 制約は使わない → Roll 自由）。
    """
    proxy_name = cam_obj.name + C.KN_LOOKAT_PROXY_SUFFIX
    proxy = bpy.data.objects.get(proxy_name)
    if proxy is None:
        proxy = bpy.data.objects.new(proxy_name, None)
        proxy.empty_display_type = "PLAIN_AXES"
        proxy.empty_display_size = 0.2
        for coll in cam_obj.users_collection:
            coll.objects.link(proxy)
            break
        else:
            bpy.context.scene.collection.objects.link(proxy)
        proxy.location = target.matrix_world.translation
    return proxy


def _remove_track_to_constraints(cam_obj) -> None:
    """カメラから kinema 由来の Track To 制約を撤去する。

    旧 cineflow / 旧 kinema 実装は Track To 制約を使っていたが、Y 軸 Roll が
    効かないため自前 LookAt に切替えた。既存 .blend で残っている Track To が
    あれば取り除く（target が KnLookatProxy のものだけを安全に削除）。
    """
    if cam_obj is None:
        return
    for con in list(cam_obj.constraints):
        if con.type != "TRACK_TO":
            continue
        tgt = getattr(con, "target", None)
        if tgt is not None and tgt.name.endswith(C.KN_LOOKAT_PROXY_SUFFIX):
            try:
                cam_obj.constraints.remove(con)
            except Exception:
                pass


def update_lookat(cam_obj, params, dt: float) -> None:
    """LookAt Proxy を `params.lookat_target` にラグ追従させる（後方互換用）。"""
    target = refs.safe_object(getattr(params, "lookat_target", None))
    if target is None:
        return
    update_lookat_with_target(cam_obj, target, params.lookat_damping, dt)


def update_lookat_with_target(
    cam_obj, target, damping: float, dt: float, roll_deg: float = 0.0,
) -> None:
    """target を明示指定して LookAt 追従させる（Roll 対応版）。

    Proxy の位置を damping で smoothing → カメラを Proxy に向ける自前計算。
    Track To 制約を使わないので、`roll_deg` を local Z 軸（カメラ視線軸）
    回転として確実に適用できる。
    """
    if target is None or cam_obj is None:
        return

    proxy = _ensure_lookat_proxy(cam_obj, target)
    # 旧 Track To 制約があれば撤去（自前 LookAt と衝突するため）
    _remove_track_to_constraints(cam_obj)

    # Proxy 位置を damping で smoothing
    alpha = damping_alpha(damping, dt)
    target_pos = target.matrix_world.translation
    if alpha >= 0.999:
        proxy.location = target_pos
    else:
        proxy.location = Vector(proxy.location).lerp(target_pos, alpha)

    # 自前 LookAt: cam の rotation を Proxy 方向に向ける
    direction = proxy.matrix_world.translation - cam_obj.matrix_world.translation
    if direction.length < 1e-6:
        return  # 同一位置 → 回転を変えない

    # -Z を direction、+Y を world up に向けるクォータニオン
    try:
        quat = direction.to_track_quat("-Z", "Y")
        euler = quat.to_euler("XYZ")
        # Roll: カメラの local Z 軸（視線軸）まわりの回転
        if abs(roll_deg) > 0.001:
            euler.rotate_axis("Z", math.radians(roll_deg))
        cam_obj.rotation_euler = euler
    except Exception:
        pass


def cleanup_lookat_proxy(cam_obj) -> None:
    """LookAt Proxy を削除（lookat_target=None / unload 時）。"""
    if cam_obj is None:
        return
    proxy_name = cam_obj.name + C.KN_LOOKAT_PROXY_SUFFIX
    proxy = bpy.data.objects.get(proxy_name)
    if proxy is None:
        return
    # 念のため Track To 制約も撤去
    _remove_track_to_constraints(cam_obj)
    for coll in list(proxy.users_collection):
        coll.objects.unlink(proxy)
    if proxy.users == 0:
        bpy.data.objects.remove(proxy, do_unlink=True)
