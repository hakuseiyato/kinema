"""kinema — Blender 5.x カメラ + マルチトラックタイムラインアドオン。

主担当: Yato
プラン v7: C:\\Users\\brain\\.claude\\plans\\blender-cineflow-...-foamy-bengio.md
リポ:    C:\\Work\\Yato\\Claude\\kinema\\ (GitHub: hakuseiyato/kinema)

alpha1 のスコープ:
  - Properties > Scene > Kinema パネル (Cameras タブ)
  - Preset スキャン / Load / Instance 一覧
  - Follow / LookAt / Noise の cineflow からの移植
  - cineflow との衝突回避（同時稼働時は handler 待機）
  - 専用 Workspace "Kinema" の append/remove
  - dev_install.ps1 (Junction)
"""

bl_info = {
    "name": "Kinema",
    "author": "Yato",
    "version": (2, 0, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Scene > Kinema",
    "description": "Camera workflow + multi-track shot timeline (cineflow successor)",
    "category": "Camera",
}

# bpy が利用できない環境（pytest など）でもパッケージを import 可能にする。
# サブモジュールの読込は register() 内で遅延する。
try:
    import bpy  # noqa: F401
    _HAS_BPY = True
except ImportError:
    _HAS_BPY = False


# ---------------------------------------------------------------------------
# 遅延セットアップ（WindowManager / keyconfigs が完成してから呼ぶ）
# ---------------------------------------------------------------------------

def _deferred_setup():
    """register 直後では WindowManager 等が未完成のため、timer で 1 tick 遅らせる。"""
    try:
        from .runtime import handlers  # noqa: PLC0415
        registered = handlers.register_all()
        if not registered:
            print("[kinema] cineflow が enabled のため frame_change handler 登録を待機しました")
    except Exception as exc:
        print(f"[kinema] deferred setup failed: {exc}")
    return None  # timer を再実行しない


_REGISTERED = False


def register():
    global _REGISTERED
    if not _HAS_BPY:
        return
    import bpy
    from . import preferences, data, ops, ui  # noqa: PLC0415
    if _REGISTERED:
        # 多重 register 防止（Reload Scripts で Disable→Enable を踏み外した場合）
        try:
            unregister()
        except Exception:
            pass
    bpy.utils.register_class(preferences.KinemaPreferences)
    data.register()
    ops.register()
    ui.register()
    bpy.app.timers.register(_deferred_setup, first_interval=0.1)
    _REGISTERED = True


def unregister():
    global _REGISTERED
    if not _HAS_BPY:
        return
    import bpy
    from . import preferences, data, ops, ui  # noqa: PLC0415
    from .runtime import handlers  # noqa: PLC0415
    try:
        handlers.unregister_all()
    except Exception:
        pass
    try:
        ui.unregister()
    except Exception:
        pass
    try:
        ops.unregister()
    except Exception:
        pass
    try:
        data.unregister()
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(preferences.KinemaPreferences)
    except Exception:
        pass
    _REGISTERED = False
