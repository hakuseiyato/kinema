"""タイムライン描画（gpu + blf）。

ホスト Video Sequencer (VSE) の WINDOW Region に POST_PIXEL レイヤで描画:
  1. 背景（暗色、VSE 標準ストリップを上書き）
  2. フレームグリッド + 秒目盛り
  3. トラック行
  4. Shot ストリップ
  5. プレイヘッド（縦線）

座標系（Region ピクセル空間）:
  - 左マージン: トラック名表示用に 80px
  - 上マージン: ツールバー想定で 30px
  - 下マージン: TC（タイムコード）表示用に 24px
  - 残りがタイムライン本体
"""

from __future__ import annotations

from typing import Optional

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader

from . import host_resolver


# 描画ハンドル
_draw_handle = None

# レイアウト定数
LEFT_MARGIN = 80
TOP_MARGIN = 30
BOTTOM_MARGIN = 24
TRACK_HEIGHT = 32
FONT_ID = 0


def _frame_to_x(frame: int, scroll_frame: int, pixels_per_frame: float) -> float:
    return LEFT_MARGIN + (frame - scroll_frame) * pixels_per_frame


def _draw_rect(x, y, w, h, color):
    """塗り潰し矩形。"""
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    verts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    indices = [(0, 1, 2), (0, 2, 3)]
    batch = batch_for_shader(shader, "TRIS", {"pos": verts}, indices=indices)
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _draw_line(x1, y1, x2, y2, color):
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(shader, "LINES", {"pos": [(x1, y1), (x2, y2)]})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _draw_text(x, y, text, size=12, color=(1.0, 1.0, 1.0, 1.0)):
    blf.position(FONT_ID, x, y, 0)
    blf.size(FONT_ID, size)
    blf.color(FONT_ID, *color)
    blf.draw(FONT_ID, text)


def _draw_background(region):
    """ホスト Region 全面を kinema の背景色で塗る。"""
    _draw_rect(0, 0, region.width, region.height, (0.13, 0.13, 0.15, 1.0))


def _draw_grid(region, scroll_frame, ppf, fps):
    """フレーム/秒グリッドを描く。"""
    height = region.height
    width = region.width
    body_top = height - TOP_MARGIN
    body_bottom = BOTTOM_MARGIN
    # 見える範囲のフレーム
    leftmost_frame = scroll_frame
    rightmost_frame = scroll_frame + int((width - LEFT_MARGIN) / max(ppf, 0.01)) + 1

    # フレーム単位の細グリッド
    frame_step = max(1, int(round(1.0 / max(ppf, 0.01))) // 5 * 5 or 1)
    # ppf が大きい時は 1 frame ごと、小さい時は数 frame ごと
    if ppf >= 8:
        frame_step = 1
    elif ppf >= 4:
        frame_step = 2
    elif ppf >= 2:
        frame_step = 5
    elif ppf >= 1:
        frame_step = 10
    else:
        frame_step = max(10, int(1.0 / ppf) * 5)

    line_color = (0.20, 0.20, 0.22, 1.0)
    sec_color = (0.30, 0.30, 0.34, 1.0)
    label_color = (0.7, 0.7, 0.75, 1.0)

    for f in range(leftmost_frame, rightmost_frame + 1, frame_step):
        x = _frame_to_x(f, scroll_frame, ppf)
        if x < LEFT_MARGIN:
            continue
        is_second_tick = (fps > 0) and (f % int(fps) == 0)
        _draw_line(x, body_bottom, x, body_top, sec_color if is_second_tick else line_color)
        if is_second_tick:
            _draw_text(x + 2, BOTTOM_MARGIN - 14, str(f), size=10, color=label_color)


def _draw_tracks(region, tracks):
    """トラック行（左マージンにラベル、右側に背景帯）を描く。"""
    width = region.width
    height = region.height
    body_top = height - TOP_MARGIN
    body_bottom = BOTTOM_MARGIN

    track_total = max(len(tracks), 1)
    label_color = (0.85, 0.85, 0.85, 1.0)

    for i, track in enumerate(tracks):
        y_top = body_top - i * TRACK_HEIGHT
        y_bot = y_top - TRACK_HEIGHT
        if y_bot < body_bottom:
            break
        # 行背景（縞模様）
        bg = (0.16, 0.16, 0.18, 1.0) if i % 2 == 0 else (0.18, 0.18, 0.20, 1.0)
        _draw_rect(LEFT_MARGIN, y_bot, width - LEFT_MARGIN, TRACK_HEIGHT, bg)
        # トラック名
        _draw_text(8, y_bot + (TRACK_HEIGHT - 12) // 2, track.name or f"Track {i+1}",
                   size=11, color=label_color)


def _draw_shots(region, scene, scroll_frame, ppf):
    """Shot ストリップを描く。"""
    height = region.height
    body_top = height - TOP_MARGIN

    st = getattr(scene, "kinema", None)
    if st is None:
        return

    # track_uid -> order を引くマップ
    track_order: dict[str, int] = {}
    tracks = list(st.tracks)
    for i, t in enumerate(tracks):
        track_order[t.uid] = i

    for clip in st.shot_clips:
        i = track_order.get(clip.track_uid, 0)
        y_top = body_top - i * TRACK_HEIGHT
        y_bot = y_top - TRACK_HEIGHT + 2  # 上下 1px ずつ余白
        x1 = _frame_to_x(clip.frame_start, scroll_frame, ppf)
        x2 = _frame_to_x(clip.frame_end, scroll_frame, ppf)
        if x2 < LEFT_MARGIN:
            continue
        x1 = max(x1, LEFT_MARGIN)
        w = max(2.0, x2 - x1)
        h = TRACK_HEIGHT - 4
        body = (clip.color[0], clip.color[1], clip.color[2], 0.85)
        # ストリップ本体
        _draw_rect(x1, y_bot + 2, w, h, body)
        # 名前
        _draw_text(x1 + 4, y_bot + 2 + (h - 12) // 2, clip.name or "Shot",
                   size=11, color=(0.05, 0.05, 0.05, 1.0))


def _draw_playhead(region, scene, scroll_frame, ppf):
    height = region.height
    body_top = height - TOP_MARGIN
    body_bottom = BOTTOM_MARGIN
    x = _frame_to_x(scene.frame_current, scroll_frame, ppf)
    if x < LEFT_MARGIN:
        return
    _draw_line(x, body_bottom, x, body_top, (1.0, 0.4, 0.4, 1.0))
    _draw_text(x + 3, body_top - 14, str(scene.frame_current),
               size=11, color=(1.0, 0.5, 0.5, 1.0))


def _draw_callback():
    """draw_handler が呼ぶエントリポイント。"""
    try:
        context = bpy.context
        area = context.area
        if area is None or area.type != host_resolver.HOST_AREA_TYPE:
            return
        if not host_resolver.is_host_area(area, context.window):
            return
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region is None:
            return

        scene = context.scene
        st = scene.kinema
        view = st.timeline_view
        ppf = view.pixels_per_frame
        scroll_frame = view.scroll_frame
        fps = float(scene.render.fps) / max(1.0, float(scene.render.fps_base))

        _draw_background(region)
        _draw_grid(region, scroll_frame, ppf, fps)
        _draw_tracks(region, list(st.tracks))
        _draw_shots(region, scene, scroll_frame, ppf)
        _draw_playhead(region, scene, scroll_frame, ppf)
    except Exception as exc:  # noqa: BLE001
        # draw コールバックで例外を出すと Blender が連発で出るので潰す
        print(f"[kinema:drawer] {exc}")


def register() -> None:
    global _draw_handle
    if _draw_handle is None:
        _draw_handle = bpy.types.SpaceSequenceEditor.draw_handler_add(
            _draw_callback, (), "WINDOW", "POST_PIXEL",
        )


def unregister() -> None:
    global _draw_handle
    if _draw_handle is not None:
        try:
            bpy.types.SpaceSequenceEditor.draw_handler_remove(_draw_handle, "WINDOW")
        except Exception:
            pass
        _draw_handle = None
