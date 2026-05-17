"""Damping math のみを集めた純粋モジュール（bpy 非依存）。

FPS 非依存の lerp 係数計算と、frame_change / depsgraph_update / update callback
の **どこから呼ばれても適切な dt を返す** ハイブリッド compute_dt を提供する。

仕様:
  - フレームが進んだ場合（再生中の自然な進行）: フレーム差 / fps を dt とする
  - フレームジャンプ（|Δf|>2）の場合: dt=0 → スナップ
  - フレームが変わっていない場合（停止中の Outliner 操作や Modal）:
      - 前回呼び出しから経過した実時間（time.monotonic）を dt とする
      - 経過が極短（< 1ms）の場合: 0 を返してスナップ抑止
      - 経過が長い（> 1.0s）の場合: dt=0 → スナップ（長期停止後の最初の更新）

これにより:
  - 再生中の自然な追従: フレーム dt で damping
  - 再生中にターゲットを掴んで動かした: 短時間連続で呼ばれるので実時間 dt で damping
  - 停止中にターゲットを動かした: 実時間 dt で damping（ふんわり追従）
  - 長時間放置後の操作: dt=0 でスナップ（瞬間ジャンプ）
"""

from __future__ import annotations

import math
import time

# scene.name -> 最後に処理したフレーム
_last_frame_seen: dict[str, int] = {}
# scene.name -> 最後に compute_dt を呼んだ実時間 (monotonic)
_last_time_seen: dict[str, float] = {}


def compute_dt(scene_name: str, frame_current: int, fps: float, fps_base: float = 1.0) -> float:
    """Damping 計算用の dt（秒）を返す。

    再生中はフレーム差分、停止中は実時間経過を使う。Damping 計算の dt は
    「**滑らかに追従させたい時に > 0**」「**瞬間スナップさせたい時に 0**」を返す:

      - フレームジャンプ |Δf|>2 → 0（スクラブで瞬間移動）
      - 通常のフレーム進行 → フレーム dt > 0（damping）
      - 同フレーム内の連続呼び出し → 経過実時間 > 0（damping）
      - 長期放置後の最初の更新 → 0（瞬間スナップで最新位置に）

    バースト抑制は呼び出し側（shot_dispatcher.dispatch）の責務にする。
    本関数は「dt の意味」だけ責任を持つ。
    """
    effective_fps = max(1.0, fps / max(1.0, fps_base))
    now = time.monotonic()

    # 初回呼び出し判定（リセット後 / .blend 読込直後）
    is_first_call = scene_name not in _last_frame_seen
    prev_frame = _last_frame_seen.get(scene_name, frame_current)
    prev_time = _last_time_seen.get(scene_name, now)
    _last_frame_seen[scene_name] = frame_current
    _last_time_seen[scene_name] = now

    if is_first_call:
        # セッション最初はスナップ（現位置を起点に）
        return 0.0

    delta_f = frame_current - prev_frame

    # フレームジャンプ: スナップ
    if abs(delta_f) > 2:
        return 0.0

    # フレームが進んだ: フレーム dt
    if delta_f != 0:
        return abs(delta_f) / effective_fps

    # 同一フレーム内: 実時間 dt
    elapsed = now - prev_time
    if elapsed > 1.0:
        # 長時間放置後の最初の更新 → スナップ
        return 0.0
    # 連続バーストでも 0 にしない（呼び出し側でバースト抑制する）。
    # 0 を返すと damping_alpha が 1.0 (スナップ) になり、ふんわり追従が崩れる。
    return max(elapsed, 1e-4)


def reset_frame_cache() -> None:
    """`.blend` 読み込み時に呼ぶ。"""
    _last_frame_seen.clear()
    _last_time_seen.clear()


def damping_alpha(damping: float, dt: float) -> float:
    """damping (0..1) と dt から、その 1 ステップで適用すべき lerp 係数を返す。

    damping=0 → 即時 (alpha=1)、damping=1 → 動かない (alpha=0)。
    `alpha = 1 - exp(-dt/tau)`、tau = damping * 0.5（0..0.5 秒の時定数）。
    """
    if dt <= 0.0:
        return 1.0  # スナップ
    if damping <= 0.001:
        return 1.0
    if damping >= 0.999:
        return 0.0
    tau = damping * 0.5
    return 1.0 - math.exp(-dt / tau)
