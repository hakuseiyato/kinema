"""Kinema spike0 — Blender 5.x API 検証用テストアドオン。

8 検証項目:
  (1) blender_manifest.toml がアドオンとして認識される
  (2) SpaceImageEditor.draw_handler_add (POST_PIXEL) で矩形が描ける
  (3) gpu.types.GPUShader.from_builtin("UNIFORM_COLOR") 系が動く
  (4) blf.draw() で font_id=0 (default font) でテキストが描ける
  (5) Modal Operator が Image Editor 上で起動・終了、bl_options の REGISTER/UNDO でアンドゥが効く
  (6) Modal の CANCELLED 終了時にアンドゥスタックに何も積まれない
  (7) IMAGE_HT_header.append で kinema コントロールが見え、unregister で remove できる
  (8) Window.as_pointer() / Area.as_pointer() の安定性確認（workspace 切替・area 移動）

実行方法:
  1. Image Editor を開く（Sidebar の "Kinema spike0" タブにテスト UI が出る）
  2. "Toggle Draw Handler" で (2)(3)(4) を検証
  3. "Run Modal (commit)" / "Run Modal (cancel)" で (5)(6) を検証
  4. "Snapshot Pointers" → Workspace 切替や Area 移動 → "Check Pointers" で (8) を検証
  5. アドオン無効化で (7) を検証（ヘッダから "K-spike0" 表示が消えること）
  6. 結果を Image Editor の Sidebar > Kinema spike0 > Results に表示
"""

bl_info = {
    "name": "Kinema spike0",
    "author": "Yato",
    "version": (0, 0, 1),
    "blender": (4, 2, 0),
    "location": "Image Editor > Sidebar > Kinema spike0",
    "description": "Blender 5.x API 検証用 spike",
    "category": "Development",
}

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader


# ---------------------------------------------------------------------------
# 状態保持（モジュールローカル）
# ---------------------------------------------------------------------------

_draw_handle = None
_results: dict[str, str] = {}
_pointer_snapshot: dict[str, str] = {}


def _set_result(key: str, msg: str) -> None:
    _results[key] = msg
    # サイドバー強制再描画
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()


# ---------------------------------------------------------------------------
# (2)(3)(4) draw_handler / gpu shader / blf
# ---------------------------------------------------------------------------

def _draw_callback():
    try:
        # (3) gpu 組み込みシェーダ
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        verts = [(20, 20), (220, 20), (220, 80), (20, 80)]
        indices = [(0, 1, 2), (0, 2, 3)]
        batch = batch_for_shader(shader, 'TRIS', {"pos": verts}, indices=indices)
        shader.bind()
        shader.uniform_float("color", (0.2, 0.6, 1.0, 0.6))
        batch.draw(shader)
        _set_result("3_gpu_shader", "OK: UNIFORM_COLOR でクワッド描画成功")
        _set_result("2_draw_handler", "OK: POST_PIXEL draw_handler 動作中")

        # (4) blf テキスト
        font_id = 0
        blf.size(font_id, 16)
        blf.position(font_id, 30, 45, 0)
        blf.draw(font_id, "Kinema spike0: gpu+blf OK")
        _set_result("4_blf", "OK: font_id=0 でテキスト描画成功")

    except Exception as exc:  # noqa: BLE001
        _set_result("2_draw_handler", f"NG: {exc}")
        _set_result("3_gpu_shader", f"NG: {exc}")
        _set_result("4_blf", f"NG: {exc}")


class KINEMASPIKE0_OT_toggle_draw(bpy.types.Operator):
    """draw_handler の ON/OFF を切り替える"""
    bl_idname = "kinema_spike0.toggle_draw"
    bl_label = "Toggle Draw Handler"

    def execute(self, context):
        global _draw_handle
        if _draw_handle is None:
            _draw_handle = bpy.types.SpaceImageEditor.draw_handler_add(
                _draw_callback, (), 'WINDOW', 'POST_PIXEL'
            )
            self.report({'INFO'}, "draw_handler 登録")
        else:
            bpy.types.SpaceImageEditor.draw_handler_remove(_draw_handle, 'WINDOW')
            _draw_handle = None
            _set_result("2_draw_handler", "(off)")
            _set_result("3_gpu_shader", "(off)")
            _set_result("4_blf", "(off)")
            self.report({'INFO'}, "draw_handler 解除")
        for area in context.window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# (5)(6) Modal Operator + UNDO 挙動
#   テスト用 Property: scene["kinema_spike0_value"] を Modal で動かす
# ---------------------------------------------------------------------------

class KINEMASPIKE0_OT_modal_commit(bpy.types.Operator):
    """Modal を起動し、確定で終了する。UNDO スタックに 1 ステップ積まれることを確認"""
    bl_idname = "kinema_spike0.modal_commit"
    bl_label = "Run Modal (commit)"
    bl_options = {'REGISTER', 'UNDO'}

    _initial: int = 0
    _x_start: int = 0

    def invoke(self, context, event):
        scene = context.scene
        self._initial = int(scene.get("kinema_spike0_value", 0))
        self._x_start = event.mouse_x
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Modal 開始（マウス左右で値が動く、左クリックで確定）")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            delta = event.mouse_x - self._x_start
            context.scene["kinema_spike0_value"] = self._initial + delta
            context.area.tag_redraw()
        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            _set_result(
                "5_modal_commit",
                f"OK: 確定終了。値={context.scene.get('kinema_spike0_value')}。"
                "Ctrl+Z で 1 回戻ることを目視確認"
            )
            return {'FINISHED'}
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            context.scene["kinema_spike0_value"] = self._initial
            _set_result("5_modal_commit", "（cancel で戻された）")
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


class KINEMASPIKE0_OT_modal_cancel(bpy.types.Operator):
    """Modal を起動し、必ず CANCELLED で終了する。UNDO に積まれないことを確認"""
    bl_idname = "kinema_spike0.modal_cancel"
    bl_label = "Run Modal (cancel only)"
    bl_options = {'REGISTER', 'UNDO'}

    _initial: int = 0
    _x_start: int = 0

    def invoke(self, context, event):
        scene = context.scene
        self._initial = int(scene.get("kinema_spike0_value", 0))
        self._x_start = event.mouse_x
        context.window_manager.modal_handler_add(self)
        self.report({'INFO'}, "Modal 開始（マウス左右で値が動く、必ず ESC でキャンセル）")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            delta = event.mouse_x - self._x_start
            context.scene["kinema_spike0_value"] = self._initial + delta
            context.area.tag_redraw()
        elif event.type in {'RIGHTMOUSE', 'ESC', 'LEFTMOUSE'}:
            context.scene["kinema_spike0_value"] = self._initial
            _set_result(
                "6_modal_cancel",
                "確認: Ctrl+Z で undo してもこの Modal の起動前後で何も変わらないこと"
            )
            return {'CANCELLED'}
        return {'RUNNING_MODAL'}


# ---------------------------------------------------------------------------
# (7) IMAGE_HT_header.append
# ---------------------------------------------------------------------------

def _header_draw(self, context):
    layout = self.layout
    layout.label(text="K-spike0", icon='CAMERA_DATA')


# ---------------------------------------------------------------------------
# (8) Window / Area の as_pointer() 安定性
# ---------------------------------------------------------------------------

class KINEMASPIKE0_OT_snapshot_pointers(bpy.types.Operator):
    """現在の context.window / context.area の pointer をスナップショット"""
    bl_idname = "kinema_spike0.snapshot_pointers"
    bl_label = "Snapshot Pointers"

    def execute(self, context):
        win = context.window
        area = context.area
        _pointer_snapshot.clear()
        _pointer_snapshot["window_pointer"] = str(win.as_pointer()) if win else ""
        _pointer_snapshot["area_pointer"] = str(area.as_pointer()) if area else ""
        _pointer_snapshot["screen_name"] = win.screen.name if win and win.screen else ""
        # area index within screen
        if win and win.screen and area:
            try:
                _pointer_snapshot["area_index"] = str(list(win.screen.areas).index(area))
            except ValueError:
                _pointer_snapshot["area_index"] = "-1"
        _set_result(
            "8_snapshot",
            f"スナップ: screen={_pointer_snapshot['screen_name']} "
            f"area_idx={_pointer_snapshot.get('area_index','?')}"
        )
        return {'FINISHED'}


class KINEMASPIKE0_OT_check_pointers(bpy.types.Operator):
    """スナップショットした pointer が現在も生きているか確認"""
    bl_idname = "kinema_spike0.check_pointers"
    bl_label = "Check Pointers"

    def execute(self, context):
        if not _pointer_snapshot:
            self.report({'WARNING'}, "先に Snapshot Pointers を実行してください")
            return {'CANCELLED'}

        target_win_ptr = _pointer_snapshot.get("window_pointer", "")
        target_area_ptr = _pointer_snapshot.get("area_pointer", "")
        target_screen = _pointer_snapshot.get("screen_name", "")
        target_idx_raw = _pointer_snapshot.get("area_index", "-1")
        try:
            target_idx = int(target_idx_raw)
        except ValueError:
            target_idx = -1

        # 一次キー: pointer
        primary_hit = None
        for window in bpy.context.window_manager.windows:
            if str(window.as_pointer()) == target_win_ptr:
                for area in window.screen.areas:
                    if str(area.as_pointer()) == target_area_ptr:
                        primary_hit = (window, area)
                        break
                if primary_hit:
                    break

        # 二次キー: screen 名 + area index
        secondary_hit = None
        for window in bpy.context.window_manager.windows:
            if window.screen and window.screen.name == target_screen:
                areas = list(window.screen.areas)
                if 0 <= target_idx < len(areas):
                    secondary_hit = (window, areas[target_idx])
                    break

        if primary_hit and secondary_hit:
            _set_result("8_check", "OK: 一次キー (pointer) も二次キー (screen+index) も成立")
        elif primary_hit:
            _set_result("8_check", "OK: pointer 一致（二次キー外れ）— pointer は安定")
        elif secondary_hit:
            _set_result(
                "8_check",
                "NG: pointer 不一致だが screen+index で復帰可 → "
                "host_resolver は二次キー fallback 必須"
            )
        else:
            _set_result("8_check", "NG: 両方とも見つからず — ホスト消失扱い")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

class KINEMASPIKE0_PT_panel(bpy.types.Panel):
    bl_label = "Kinema spike0"
    bl_idname = "KINEMASPIKE0_PT_panel"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Kinema spike0"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        col = layout.column(align=True)
        col.label(text="(2)(3)(4) Draw / GPU / BLF")
        col.operator("kinema_spike0.toggle_draw")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="(5)(6) Modal + Undo")
        col.label(text=f"value: {scene.get('kinema_spike0_value', 0)}")
        col.operator("kinema_spike0.modal_commit")
        col.operator("kinema_spike0.modal_cancel")

        layout.separator()
        col = layout.column(align=True)
        col.label(text="(8) Pointer Stability")
        col.operator("kinema_spike0.snapshot_pointers")
        col.operator("kinema_spike0.check_pointers")

        layout.separator()
        box = layout.box()
        box.label(text="Results")
        if not _results:
            box.label(text="（未実行）")
        else:
            for key in sorted(_results):
                box.label(text=f"{key}: {_results[key]}")


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

_CLASSES = (
    KINEMASPIKE0_OT_toggle_draw,
    KINEMASPIKE0_OT_modal_commit,
    KINEMASPIKE0_OT_modal_cancel,
    KINEMASPIKE0_OT_snapshot_pointers,
    KINEMASPIKE0_OT_check_pointers,
    KINEMASPIKE0_PT_panel,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.IMAGE_HT_header.append(_header_draw)
    _set_result("1_manifest", "OK: アドオンとして認識・register 成功")
    _set_result("7_header_append", "OK: IMAGE_HT_header に 'K-spike0' を append")


def unregister():
    global _draw_handle
    if _draw_handle is not None:
        try:
            bpy.types.SpaceImageEditor.draw_handler_remove(_draw_handle, 'WINDOW')
        except Exception:
            pass
        _draw_handle = None
    try:
        bpy.types.IMAGE_HT_header.remove(_header_draw)
    except Exception:
        pass
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _results.clear()
    _pointer_snapshot.clear()
