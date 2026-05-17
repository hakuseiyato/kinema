"""kinema.ui.timeline — 独自タイムライン UI（Image Editor 流用）。"""

from __future__ import annotations

import bpy

from . import host_resolver, drawer, header_append, modal_ops


def register() -> None:
    modal_ops.register()
    header_append.register()
    drawer.register()


def unregister() -> None:
    drawer.unregister()
    header_append.unregister()
    modal_ops.unregister()
