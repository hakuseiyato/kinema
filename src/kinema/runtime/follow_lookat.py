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
from mathutils import Vector

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

def update_follow(cam_obj, params, dt: float) -> None:
    """カメラを follow_target の周りに **Euler XYZ 軸回転** で配置する。

    params に以下の属性を要求:
      follow_target, follow_distance, follow_rot_x, follow_rot_y, follow_rot_z,
      follow_height, follow_side, follow_damping

    軸回転 (target ローカル空間):
      - rot_x: X 軸回り（上下角）。正値=見下ろし、負値=見上げ
      - rot_y: Y 軸回り（カメラのロール、位置には影響しない）
      - rot_z: Z 軸回り（水平回り）。0=正面 (+Y), 90=右 (+X), 180=背後 (-Y), -90=左 (-X)

    初期方向は target の +Y。これを XYZ 軸回転で動かしたベクトルが
    カメラの相対方向ベクトルになる（Y 軸回転は (0,1,0) を回しても変わらないので
    位置には影響しない＝ロール専用）。
    """
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
    # Y は roll として後段で扱う（drawer ではなく Track To の up_axis 等）が、
    # alpha 段階では未対応で OK（Y 軸スライダーは値を保持するだけ）。
    from mathutils import Euler  # noqa: PLC0415
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

    alpha = damping_alpha(params.follow_damping, dt)
    if alpha >= 0.999:
        cam_obj.location = ideal
    else:
        cam_obj.location = Vector(cam_obj.location).lerp(ideal, alpha)


# ---------------------------------------------------------------------------
# LookAt
# ---------------------------------------------------------------------------

def _ensure_lookat_proxy(cam_obj, target) -> bpy.types.Object:
    """LookAt 用の中継 Empty を取得 or 作成。"""
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


def _find_or_set_track_to(cam_obj, proxy) -> bpy.types.Constraint:
    """カメラの Track To 制約を取得 or 作成し、target を proxy にする。"""
    track_to = None
    for con in cam_obj.constraints:
        if con.type == "TRACK_TO":
            track_to = con
            break
    if track_to is None:
        track_to = cam_obj.constraints.new("TRACK_TO")
        track_to.track_axis = "TRACK_NEGATIVE_Z"
        track_to.up_axis = "UP_Y"
    track_to.target = proxy
    track_to.influence = 1.0
    return track_to


def update_lookat(cam_obj, params, dt: float) -> None:
    """LookAt Proxy を `params.lookat_target` にラグ追従させる（後方互換用）。"""
    target = refs.safe_object(getattr(params, "lookat_target", None))
    if target is None:
        return
    update_lookat_with_target(cam_obj, target, params.lookat_damping, dt)


def update_lookat_with_target(cam_obj, target, damping: float, dt: float) -> None:
    """target を明示指定して LookAt 追従させる。

    Follow Target を自動 LookAt する場合などで Instance Item のスキーマに
    縛られず使えるようにした版。
    """
    if target is None or cam_obj is None:
        return

    proxy = _ensure_lookat_proxy(cam_obj, target)
    _find_or_set_track_to(cam_obj, proxy)

    alpha = damping_alpha(damping, dt)
    target_pos = target.matrix_world.translation
    if alpha >= 0.999:
        proxy.location = target_pos
    else:
        proxy.location = Vector(proxy.location).lerp(target_pos, alpha)


def cleanup_lookat_proxy(cam_obj) -> None:
    """LookAt Proxy を削除（lookat_target=None / unload 時）。"""
    if cam_obj is None:
        return
    proxy_name = cam_obj.name + C.KN_LOOKAT_PROXY_SUFFIX
    proxy = bpy.data.objects.get(proxy_name)
    if proxy is None:
        return
    for con in list(cam_obj.constraints):
        if con.type == "TRACK_TO" and con.target == proxy:
            cam_obj.constraints.remove(con)
    for coll in list(proxy.users_collection):
        coll.objects.unlink(proxy)
    if proxy.users == 0:
        bpy.data.objects.remove(proxy, do_unlink=True)
