"""旧 cineflow Instance → kinema Instance への変換 Operator。

cineflow が enabled 状態で実行することを想定。読み込んだ後、cineflow を
無効化してから kinema handler を有効化する運用。

PropertyGroup の対応:
  cineflow.instance.camera_ref         → kinema.instance.camera_ref
  cineflow.instance.collection_ref     → kinema.instance.collection_ref
  cineflow.instance.instance_name      → kinema.instance.name
  cineflow.instance.camera_name        → (camera_ref が None なら逆引き)
  cineflow.instance.enabled            → kinema.instance.enabled
  cineflow.instance.follow_target      → kinema.instance.follow_target
  cineflow.instance.lookat_target      → kinema.instance.lookat_target
  cineflow.instance.follow_distance    → kinema.instance.follow_distance
  cineflow.instance.follow_height      → kinema.instance.follow_height
  cineflow.instance.follow_side        → kinema.instance.follow_side
  cineflow.instance.follow_damping     → kinema.instance.follow_damping
  cineflow.instance.lookat_damping     → kinema.instance.lookat_damping
  cineflow.instance.noise_enabled      → kinema.instance.noise_enabled
  cineflow.instance.noise_strength_pos → kinema.instance.noise_strength_pos
  cineflow.instance.noise_strength_rot → kinema.instance.noise_strength_rot
  cineflow.instance.noise_frequency    → kinema.instance.noise_frequency
  cineflow.instance.noise_seed         → kinema.instance.noise_seed

Follow の球面座標 (rot_x, rot_z) は cineflow には対応する概念が無いので 0,0
で初期化（cineflow の挙動は yaw=180 後方追従固定だったため、必要なら手動で
rot_z=180 に切替）。
"""

from __future__ import annotations

import bpy

from ._base import KinemaOperator


_FIELDS_SCALAR = (
    "enabled",
    "follow_distance",
    "follow_height",
    "follow_side",
    "follow_damping",
    "lookat_damping",
    "noise_enabled",
    "noise_strength_pos",
    "noise_strength_rot",
    "noise_frequency",
    "noise_seed",
)
_FIELDS_POINTER = (
    "collection_ref",
    "camera_ref",
    "follow_target",
    "lookat_target",
)


class KINEMA_OT_import_from_cineflow(KinemaOperator):
    """現シーンの cineflow Instance を kinema Instance に変換。"""
    bl_idname = "kinema.import_from_cineflow"
    bl_label = "Import from cineflow"
    bl_description = (
        "現シーンの cineflow Instance を kinema Instance に変換する。"
        "cineflow が enabled な状態で実行してください"
    )

    def run(self, context):
        scene = context.scene
        cf = getattr(scene, "cineflow_settings", None)
        if cf is None:
            self.report(
                {"ERROR"},
                "scene.cineflow_settings が見つかりません。"
                "cineflow が有効化されているか確認してください",
            )
            return {"CANCELLED"}

        st = scene.kinema
        imported = 0
        warnings: list[str] = []

        for src in cf.instances:
            new_inst = st.instances.add()

            # Name
            try:
                name = getattr(src, "instance_name", "") or ""
            except Exception:
                name = ""
            new_inst.name = name or f"Imported_{imported + 1}"
            new_inst.source_preset = name

            # PointerProperty
            for f in _FIELDS_POINTER:
                try:
                    setattr(new_inst, f, getattr(src, f, None))
                except Exception:
                    pass

            # camera_name フォールバック
            if new_inst.camera_ref is None:
                cam_name = getattr(src, "camera_name", "") or ""
                if cam_name:
                    new_inst.camera_ref = bpy.data.objects.get(cam_name)

            # スカラー
            for f in _FIELDS_SCALAR:
                if not hasattr(src, f):
                    continue
                try:
                    setattr(new_inst, f, getattr(src, f))
                except Exception:
                    pass

            # 球面座標は cineflow に無いのでデフォルト維持
            # (旧 cineflow は yaw=180 後方追従だったが、新 kinema のデフォルト
            #  正面 (rot_z=0) に揃える。必要なら手動で 180 に変更してもらう)

            # lens_mm: カメラ data から取得
            cam = new_inst.camera_ref
            if cam is not None and cam.data is not None:
                try:
                    new_inst.lens_mm = float(cam.data.lens)
                except Exception:
                    pass

            imported += 1

        if imported == 0:
            warnings.append("cineflow Instance が 0 件でした")
        self.report(
            {"INFO"},
            f"Imported {imported} instances from cineflow. "
            + (" ".join(warnings) if warnings else "")
            + " (cineflow を無効化 → kinema handler 有効化を推奨)",
        )
        return {"FINISHED"}
