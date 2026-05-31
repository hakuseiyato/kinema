"""Blender app handler の登録/解除を一括管理する。

handler 重複防止のため、register 時に **同関数名のものを先に remove してから append**
する。開発中の Reload Scripts で二重登録される事故を防ぐ。

cineflow 共存時は frame_change handler を登録せず待機する（プラン v7「handler 登録分岐」）。
"""

from __future__ import annotations

import bpy
from bpy.app.handlers import persistent

from . import instance_dispatcher


# ---------------------------------------------------------------------------
# Handler bodies
# ---------------------------------------------------------------------------

@persistent
def kinema_frame_change_post(scene, depsgraph):  # noqa: ARG001
    """フレーム切替後の Follow/LookAt 適用。

    重要: `frame_change_pre` ではなく **post** を使う。pre は anim eval より
    前なので kinema の書込が直後の anim eval（keyframe 復元）で上書きされる。
    特に再生中は depsgraph_update_post が burst 抑制で skip され、結果として
    keyframe 値だけが render される＝「Key 入りカメラで follow が効かない」
    バグになる。post は anim eval 完了後に走るので kinema の書込が勝つ。

    再生時の取りこぼし防止のため force=True。
    """
    instance_dispatcher.dispatch(scene, force=True)


# depsgraph_update_post でも常に dispatch する。
# 再生中 / 停止中の区別はせず、compute_dt のハイブリッド実装が:
#   - フレームが進んだら: フレーム dt → damping
#   - 同フレーム内なら:   実時間 dt → damping（ふんわり追従）
#   - 長期放置後の最初:    dt=0 → スナップ
# を判定するので、handler 側で再生状態を見て分岐する必要は無い。
@persistent
def kinema_depsgraph_update_post(scene, depsgraph):  # noqa: ARG001
    if instance_dispatcher._in_dispatch:
        return
    # render 中は frame_change_post だけで十分。depsgraph は mesh deform /
    # material eval 等で連発するので、render 中は全 skip して overhead 削減。
    if instance_dispatcher.is_rendering():
        return
    instance_dispatcher.dispatch(scene)


@persistent
def kinema_render_init(*args):  # noqa: ARG001
    """レンダージョブ開始時（animation render なら 1 回だけ）。

    dispatcher を render モードに切替え、depsgraph_update_post の dispatch
    を skip + _apply_preview_preset を skip して per-frame overhead を削減。

    シグネチャ防御: Blender バージョンによって `(scene)` または
    `(scene, depsgraph)` で呼ばれるので `*args` で受ける（引数不一致での
    クラッシュ防止）。
    """
    try:
        instance_dispatcher.set_rendering(True)
    except Exception as exc:
        print(f"[kinema] render_init error: {exc}")


@persistent
def kinema_render_complete(*args):  # noqa: ARG001
    """レンダージョブ完了時。render モード解除。"""
    try:
        instance_dispatcher.set_rendering(False)
    except Exception as exc:
        print(f"[kinema] render_complete error: {exc}")


@persistent
def kinema_render_cancel_clear(*args):  # noqa: ARG001
    """Esc 等でキャンセルされた場合も render モードを解除する。

    関数名が render_ops 側の _on_render_cancel と被らないように _clear を付与。
    """
    try:
        instance_dispatcher.set_rendering(False)
    except Exception as exc:
        print(f"[kinema] render_cancel error: {exc}")


def _auto_migrate_cuts_to_shots(scene) -> None:
    """`data_format_version < 2` かつ旧 cuts[] が存在すれば、shots[] へ自動 migrate。

    Phase 2 で導入: .blend 読込時に旧データを検出 → ワンクリック不要で透過 migrate。
    migrate 完了後、旧 cuts[] はクリアする（ユーザー希望「移行後すぐ消す」）。
    既存設定（カメラ / Cast / frame / notes 等）は shots[] へ完全コピーされる。
    """
    st = getattr(scene, "kinema", None)
    if st is None:
        return
    dfv = getattr(st, "data_format_version", 1)
    has_legacy = hasattr(st, "cuts") and len(st.cuts) > 0
    if dfv >= 2 and not has_legacy:
        return
    # 既に shots[] があれば skip（手動 migrate 済み）
    if dfv >= 2 and len(st.shots) > 0:
        return
    try:
        # 旧 cuts[] / yato_vis.cast_markers → shots[] へ
        from ..ops.shot_ops import _sorted_markers, _find_instance_name_by_camera, _find_instance_by_name
        from ..utils import visibility_kit_bridge as _vkb

        # 既存 shots は一旦クリア（auto-migrate は決定的に動く）
        st.shots.clear()

        # 旧 cuts を marker_name / name でインデックス
        cut_by_marker = {}
        cut_by_name = {}
        if has_legacy:
            for c in st.cuts:
                try:
                    if c.marker_name:
                        cut_by_marker[c.marker_name] = c
                    if c.name:
                        cut_by_name.setdefault(c.name, c)
                except Exception:
                    continue

        # yato_vis groups の cast を marker → group リストに索引
        cast_by_marker: dict = {}
        if _vkb.is_available(scene):
            for g in _vkb.list_groups(scene):
                try:
                    gname = g.name
                except Exception:
                    continue
                solo = _vkb.resolve_solo_target(g) or ""
                try:
                    for cm in g.cast_markers:
                        cast_by_marker.setdefault(cm.marker_name, []).append(
                            {"group_name": gname, "solo_target_name": solo}
                        )
                except Exception:
                    continue

        sorted_ms = _sorted_markers(scene)
        seen_markers = set()
        added = 0
        for m in sorted_ms:
            seen_markers.add(m.name)
            shot = st.shots.add()
            shot.marker_name = m.name
            cut = cut_by_marker.get(m.name) or cut_by_name.get(m.name)
            if cut is not None:
                shot.name = cut.name or m.name
                shot.instance_name = getattr(cut, "instance_name", "") or ""
                shot.enabled = bool(getattr(cut, "enabled", True))
                shot.frame_override = bool(getattr(cut, "frame_override", False))
                shot.frame_start_override = int(getattr(cut, "frame_start_override", 1))
                shot.frame_end_override = int(getattr(cut, "frame_end_override", 250))
                shot.notes = getattr(cut, "notes", "") or ""
            else:
                shot.name = m.name
            # Instance 未解決ならカメラ → 同名でフォールバック
            if not shot.instance_name:
                try:
                    cam_obj = getattr(m, "camera", None)
                except Exception:
                    cam_obj = None
                resolved = ""
                if cam_obj is not None:
                    resolved = _find_instance_name_by_camera(st, cam_obj)
                if not resolved:
                    resolved = _find_instance_by_name(st, m.name)
                if resolved:
                    shot.instance_name = resolved
            # Cast 移行
            for entry in cast_by_marker.get(m.name, []):
                ce = shot.cast.add()
                ce.group_name = entry["group_name"]
                ce.enabled = True
                ce.solo_target_name = entry["solo_target_name"]
            shot.orphan = False
            added += 1

        # Marker が消えた orphan cuts も保持
        if has_legacy:
            for c in st.cuts:
                try:
                    mn = c.marker_name or c.name
                    if mn in seen_markers:
                        continue
                except Exception:
                    continue
                shot = st.shots.add()
                shot.name = c.name or "(orphan)"
                shot.marker_name = c.marker_name
                shot.instance_name = getattr(c, "instance_name", "") or ""
                shot.enabled = bool(getattr(c, "enabled", True))
                shot.frame_override = bool(getattr(c, "frame_override", False))
                shot.frame_start_override = int(getattr(c, "frame_start_override", 1))
                shot.frame_end_override = int(getattr(c, "frame_end_override", 250))
                shot.notes = getattr(c, "notes", "") or ""
                shot.orphan = True
                added += 1

        # 旧 cuts[] を削除（ユーザー希望「移行後すぐ消す」）
        if has_legacy:
            st.cuts.clear()
            st.active_cut_index = 0

        # version 昇格
        try:
            st.data_format_version = 2
        except Exception:
            pass

        n_cast = sum(len(s.cast) for s in st.shots)
        print(
            f"[kinema] auto-migrated scene '{scene.name}': "
            f"{added} shots, {n_cast} cast entries"
        )
    except Exception as exc:
        print(f"[kinema] auto-migrate failed for '{scene.name}': {exc}")


@persistent
def kinema_load_post(_dummy):
    """`.blend` 読込時のセッション状態リセット + 健全性チェック + 自動 migrate。

    - dispatcher キャッシュをクリア
    - **旧 cuts[] / cast_markers → shots[] へ自動 migrate**（Phase 2 で追加）
    - 各 Scene の active_instance_index / active_preset_index を範囲内に補正
    - 参照切れ Instance（collection_ref と camera_ref がどちらも切れた）件数を
      System Console に warning ログ（破壊はしない）
    """
    instance_dispatcher.reset_state()
    try:
        from ..utils import refs  # noqa: PLC0415
        for scene in bpy.data.scenes:
            st = getattr(scene, "kinema", None)
            if st is None:
                continue
            # 自動 migrate（旧 cuts[] → shots[]）
            _auto_migrate_cuts_to_shots(scene)
            # index 範囲補正
            max_inst = max(0, len(st.instances) - 1)
            if st.active_instance_index > max_inst:
                st.active_instance_index = max_inst
            max_preset = max(0, len(st.presets) - 1)
            if st.active_preset_index > max_preset:
                st.active_preset_index = max_preset
            max_shot = max(0, len(st.shots) - 1)
            if st.active_shot_index > max_shot:
                st.active_shot_index = max_shot
            # 参照切れカウント（破壊しない、ログのみ）
            broken = sum(
                1 for inst in st.instances
                if refs.safe_collection(inst.collection_ref) is None
                and refs.safe_object(inst.camera_ref) is None
            )
            if broken:
                print(
                    f"[kinema] load_post: Scene '{scene.name}' に参照切れ "
                    f"Instance が {broken} 件あります。"
                    f"Properties > Scene > Kinema > Refresh Instances を実行してください"
                )
    except Exception as exc:
        print(f"[kinema] load_post 健全性チェック失敗: {exc}")


# (window_manager.kinema は session-only なので load_post で host pointer 等を
#  リセットする予定だが、v2.0 beta1 で WindowManager.kinema を導入するまでは
#  最小限のキャッシュリセットだけで足りる)


# ---------------------------------------------------------------------------
# Registration with duplicate-guard
# ---------------------------------------------------------------------------

_HOOKS = (
    ("frame_change_post", kinema_frame_change_post),
    ("depsgraph_update_post", kinema_depsgraph_update_post),
    ("load_post", kinema_load_post),
    ("render_init", kinema_render_init),
    ("render_complete", kinema_render_complete),
    ("render_cancel", kinema_render_cancel_clear),
)


# レガシー名残のフックを掃除する（旧 frame_change_pre 版がぶら下がってると
# kinema_frame_change_pre が二重稼働して anim eval 上書き問題が再発する）。
_LEGACY_HOOKS = (
    ("frame_change_pre", "kinema_frame_change_pre"),
)


def _remove_legacy_hooks() -> None:
    for hook_name, fn_name in _LEGACY_HOOKS:
        hook = getattr(bpy.app.handlers, hook_name, None)
        if hook is None:
            continue
        for existing in list(hook):
            if getattr(existing, "__name__", "") == fn_name:
                try:
                    hook.remove(existing)
                except Exception:
                    pass


def _is_cineflow_enabled() -> bool:
    """cineflow アドオンが有効かどうか。"""
    addons = bpy.context.preferences.addons
    return ("cineflow" in addons.keys()) or ("bl_ext.user_default.cineflow" in addons.keys())


def _remove_if_present(hook_list, fn) -> None:
    """同関数 / 同名関数を全削除する（重複登録対策）。"""
    target_name = getattr(fn, "__name__", "")
    for existing in list(hook_list):
        if existing is fn:
            try:
                hook_list.remove(existing)
            except Exception:
                pass
            continue
        if target_name and getattr(existing, "__name__", "") == target_name:
            try:
                hook_list.remove(existing)
            except Exception:
                pass


def register_all() -> bool:
    """handler を登録する。cineflow が enabled なら登録 skip。

    戻り値: 実際に登録したら True、skip したら False。
    """
    _remove_legacy_hooks()
    if _is_cineflow_enabled():
        # cineflow と同時稼働すると scene.camera を奪い合うので待機
        unregister_all()
        return False
    for name, fn in _HOOKS:
        hook = getattr(bpy.app.handlers, name)
        _remove_if_present(hook, fn)
        hook.append(fn)
    return True


def unregister_all() -> None:
    _remove_legacy_hooks()
    for name, fn in _HOOKS:
        hook = getattr(bpy.app.handlers, name)
        _remove_if_present(hook, fn)
