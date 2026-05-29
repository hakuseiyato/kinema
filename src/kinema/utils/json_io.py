"""Scene の kinema 設定を JSON でエクスポート / インポートする純粋ロジック。

PointerProperty は名前文字列で保存し、ロード時に bpy 経由で解決する想定。
schema_version でフォーマット世代を管理し、将来の互換性に備える。
"""

from __future__ import annotations

from typing import Any, Iterable

SCHEMA_VERSION = 1

# Instance Item に永続化する全フィールド（PointerProperty は別扱い）
_INSTANCE_SCALAR_FIELDS = (
    "name", "source_preset",
    "enabled", "solo", "locked",
    "lens_mm",
    "follow_distance",
    "follow_rot_x", "follow_rot_y", "follow_rot_z",
    "follow_height", "follow_side", "follow_damping",
    "follow_auto_lookat",
    "lookat_damping",
    "use_damping",
    "noise_enabled", "noise_strength_pos", "noise_strength_rot",
    "noise_frequency", "noise_seed",
)

# PointerProperty (名前で保存)
_INSTANCE_POINTERS = (
    ("collection_ref", "collection"),  # (attr, kind) kind: "collection" | "object"
    ("camera_ref", "object"),
    ("follow_target", "object"),
    ("lookat_target", "object"),
)


def serialize_instance(inst) -> dict:
    """1 Instance を辞書化する。"""
    out: dict[str, Any] = {}
    for f in _INSTANCE_SCALAR_FIELDS:
        try:
            val = getattr(inst, f, None)
            if hasattr(val, "__iter__") and not isinstance(val, str):
                val = list(val)
            out[f] = val
        except Exception:
            pass
    for attr, _kind in _INSTANCE_POINTERS:
        try:
            obj = getattr(inst, attr, None)
            out[f"{attr}__name"] = obj.name if obj is not None else ""
        except Exception:
            out[f"{attr}__name"] = ""
    return out


def deserialize_instance(inst, data: dict, resolve_object, resolve_collection) -> int:
    """辞書から Instance に書き込む。resolve_* は名前 → ID 解決の lambda。

    戻り値: 適用フィールド数。
    """
    count = 0
    for f in _INSTANCE_SCALAR_FIELDS:
        if f not in data:
            continue
        try:
            setattr(inst, f, data[f])
            count += 1
        except Exception:
            pass
    for attr, kind in _INSTANCE_POINTERS:
        key = f"{attr}__name"
        if key not in data:
            continue
        name = data[key]
        try:
            if not name:
                setattr(inst, attr, None)
            elif kind == "object":
                setattr(inst, attr, resolve_object(name))
            elif kind == "collection":
                setattr(inst, attr, resolve_collection(name))
            count += 1
        except Exception:
            pass
    return count


def serialize_scene(scene_settings, kinema_version: str = "2.0.0") -> dict:
    """Scene 全体（Instance / Preset Root / Instances Root 設定）を辞書化。"""
    import datetime as _dt
    return {
        "kinema_schema": SCHEMA_VERSION,
        "kinema_version": kinema_version,
        "exported_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "preset_root_name": getattr(scene_settings, "preset_root_name", ""),
        "instances_root_name": getattr(scene_settings, "instances_root_name", ""),
        "instances": [serialize_instance(i) for i in scene_settings.instances],
    }


def deserialize_scene(
    scene_settings, data: dict, resolve_object, resolve_collection,
    add_instance,
) -> dict:
    """辞書から Scene 設定を適用する。

    add_instance は CollectionProperty に新規 Instance を追加して返す callable
    (`lambda: scene_settings.instances.add()` を期待)。

    既存 Instance はクリアせず追加する（破壊を避ける）。呼出側で clear を選択する。
    """
    schema = data.get("kinema_schema", 0)
    if schema != SCHEMA_VERSION:
        return {"ok": False, "reason": f"未対応の kinema_schema={schema}"}
    # ルート名
    if "preset_root_name" in data:
        try:
            scene_settings.preset_root_name = data["preset_root_name"]
        except Exception:
            pass
    if "instances_root_name" in data:
        try:
            scene_settings.instances_root_name = data["instances_root_name"]
        except Exception:
            pass
    # Instances
    added = 0
    for inst_data in data.get("instances", []):
        new_inst = add_instance()
        deserialize_instance(new_inst, inst_data, resolve_object, resolve_collection)
        added += 1
    return {"ok": True, "added": added, "schema": schema}
