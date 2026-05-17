"""Blender app handler の登録/解除を一括管理する。

handler 重複防止のため、register 時に **同関数名のものを先に remove してから append**
する。開発中の Reload Scripts で二重登録される事故を防ぐ。

cineflow 共存時は frame_change handler を登録せず待機する（プラン v7「handler 登録分岐」）。
"""

from __future__ import annotations

import bpy
from bpy.app.handlers import persistent

from . import shot_dispatcher


# ---------------------------------------------------------------------------
# Handler bodies
# ---------------------------------------------------------------------------

@persistent
def kinema_frame_change_pre(scene, depsgraph):  # noqa: ARG001
    shot_dispatcher.dispatch(scene)


# depsgraph_update_post でも dispatch する。
# これにより Follow Target / LookAt Target が動いたとき（オブジェクト操作・
# Outliner ドラッグ・他アドオンによる移動など）、再生していなくてもカメラが
# 追従するようになる。dispatch 内の `_in_dispatch` ガードで再帰を防ぐ。
@persistent
def kinema_depsgraph_update_post(scene, depsgraph):  # noqa: ARG001
    # 再帰防止：dispatch 自身が cam.location を書き換えると再度 depsgraph が
    # 更新されるが、_in_dispatch ガードがそれを抑止する。
    if shot_dispatcher._in_dispatch:
        return
    shot_dispatcher.dispatch(scene)


@persistent
def kinema_load_post(_dummy):
    """`.blend` 読込時のセッション状態リセット。"""
    shot_dispatcher.reset_state()


# (window_manager.kinema は session-only なので load_post で host pointer 等を
#  リセットする予定だが、v2.0 beta1 で WindowManager.kinema を導入するまでは
#  最小限のキャッシュリセットだけで足りる)


# ---------------------------------------------------------------------------
# Registration with duplicate-guard
# ---------------------------------------------------------------------------

_HOOKS = (
    ("frame_change_pre", kinema_frame_change_pre),
    ("depsgraph_update_post", kinema_depsgraph_update_post),
    ("load_post", kinema_load_post),
)


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
    for name, fn in _HOOKS:
        hook = getattr(bpy.app.handlers, name)
        _remove_if_present(hook, fn)
