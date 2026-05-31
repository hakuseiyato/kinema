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


_CUT_FIELDS = (
    "name", "marker_name", "instance_name", "enabled",
    "frame_override", "frame_start_override", "frame_end_override",
    "notes", "orphan",
)


def serialize_cut(cut) -> dict:
    """旧 cuts[] のシリアライズ。Phase 2 以降は shots[] を使うが、
    旧 JSON との互換のため関数自体は残す。"""
    out: dict[str, Any] = {}
    for f in _CUT_FIELDS:
        try:
            out[f] = getattr(cut, f)
        except Exception:
            pass
    return out


def deserialize_cut(cut, data: dict) -> int:
    """旧 cuts[] のデシリアライズ（互換のため残置）。"""
    count = 0
    for f in _CUT_FIELDS:
        if f not in data:
            continue
        try:
            setattr(cut, f, data[f])
            count += 1
        except Exception:
            pass
    return count


# --- Shot serialize（Phase 2 の canonical 形式）---

_SHOT_SCALAR_FIELDS = (
    "name", "marker_name", "instance_name", "enabled",
    "frame_override", "frame_start_override", "frame_end_override",
    "notes", "orphan",
)
_CAST_FIELDS = ("group_name", "enabled", "solo_target_name")


def serialize_shot(shot) -> dict:
    """1 Shot を辞書化。cast[] も含む。"""
    out: dict[str, Any] = {}
    for f in _SHOT_SCALAR_FIELDS:
        try:
            out[f] = getattr(shot, f)
        except Exception:
            pass
    cast_list: list[dict] = []
    try:
        for ce in shot.cast:
            entry: dict[str, Any] = {}
            for cf in _CAST_FIELDS:
                try:
                    entry[cf] = getattr(ce, cf)
                except Exception:
                    pass
            cast_list.append(entry)
    except Exception:
        pass
    out["cast"] = cast_list
    return out


def deserialize_shot(shot, data: dict) -> int:
    count = 0
    for f in _SHOT_SCALAR_FIELDS:
        if f not in data:
            continue
        try:
            setattr(shot, f, data[f])
            count += 1
        except Exception:
            pass
    cast_data = data.get("cast") or []
    try:
        shot.cast.clear()
        for entry_data in cast_data:
            ce = shot.cast.add()
            for cf in _CAST_FIELDS:
                if cf in entry_data:
                    try:
                        setattr(ce, cf, entry_data[cf])
                    except Exception:
                        pass
            count += 1
    except Exception:
        pass
    return count


def serialize_scene(scene_settings, kinema_version: str = "2.0.0") -> dict:
    """Scene 全体（Instance / Shot / Preset Root / Instances Root 設定）を辞書化。

    Phase 2: shots[] が canonical。旧 cuts[] は空のはずだが互換のため空配列でも出す。
    """
    import datetime as _dt
    return {
        "kinema_schema": SCHEMA_VERSION,
        "kinema_version": kinema_version,
        "exported_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "preset_root_name": getattr(scene_settings, "preset_root_name", ""),
        "instances_root_name": getattr(scene_settings, "instances_root_name", ""),
        "data_format_version": int(getattr(scene_settings, "data_format_version", 2)),
        "instances": [serialize_instance(i) for i in scene_settings.instances],
        "shots": [serialize_shot(s) for s in getattr(scene_settings, "shots", [])],
        # 旧 cuts[] は Phase 2 で deprecated。空でも互換のため出力
        "cuts": [serialize_cut(c) for c in getattr(scene_settings, "cuts", [])],
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
    # Shots（Phase 2 で canonical 化）
    shots_added = 0
    shots_data = data.get("shots")
    if shots_data and hasattr(scene_settings, "shots"):
        for shot_data in shots_data:
            new_shot = scene_settings.shots.add()
            deserialize_shot(new_shot, shot_data)
            shots_added += 1

    # Cuts（旧スキーマ互換 - import 後、load_post の自動 migrate で shots[] に
    # 移行される。手動互換のため一応 cuts[] にも入れる）
    cuts_added = 0
    cuts_data = data.get("cuts")
    if cuts_data and hasattr(scene_settings, "cuts"):
        for cut_data in cuts_data:
            new_cut = scene_settings.cuts.add()
            deserialize_cut(new_cut, cut_data)
            cuts_added += 1

    # data_format_version 設定
    dfv = data.get("data_format_version")
    if dfv is not None and hasattr(scene_settings, "data_format_version"):
        try:
            scene_settings.data_format_version = int(dfv)
        except Exception:
            pass

    return {
        "ok": True, "added": added, "cuts_added": cuts_added,
        "shots_added": shots_added, "schema": schema,
    }
