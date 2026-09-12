import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEMS = {"lamp", "keys", "cage", "bird", "silver"}


def validate_condition(spec, scenes):
    if spec is None:
        return
    if not isinstance(spec, dict) or not spec:
        raise ValueError(f"Invalid condition: {spec}")
    if "all" in spec:
        if not isinstance(spec["all"], list) or not spec["all"]:
            raise ValueError("all must contain conditions")
        for child in spec["all"]:
            validate_condition(child, scenes)
        return
    if "not" in spec:
        validate_condition(spec["not"], scenes)
        return
    op = spec.get("op")
    if op not in {"has_item", "item_at", "flag_set", "flag_not_set", "carried_light",
                  "light_here", "no_light_here", "light_or_known_path"}:
        raise ValueError(f"Unknown condition: {op}")
    if op in {"has_item", "item_at"} and spec.get("item") not in ITEMS:
        raise ValueError("Unknown item in condition")
    if op == "item_at" and spec.get("location") not in set(scenes) | {"inventory", "cage", "gone", "treasury"}:
        raise ValueError("Unknown item location")
    if op == "light_or_known_path" and spec.get("scene") not in scenes:
        raise ValueError("Unknown scene in condition")
    if op in {"flag_set", "flag_not_set"} and not isinstance(spec.get("flag"), str):
        raise ValueError("Missing flag in condition")


def read_text_file(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT / "texts"):
        raise ValueError(f"Invalid text path: {relative}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read text file {relative}: {exc}") from exc


def load_content(manifest=None, text_sources=None):
    if manifest is None:
        manifest = json.loads((ROOT / "games/colossal_cave/game.json").read_text(encoding="utf-8-sig"))
    data = deepcopy(manifest)
    paths = set(data["copy_files"].values()) | {s["text_file"] for s in data["scenes"].values()}
    sources = {path: read_text_file(path) for path in paths} if text_sources is None else deepcopy(text_sources)
    data["_manifest"] = deepcopy(manifest)
    data["_text_sources"] = sources
    data["copy"] = {name: sources[path] for name, path in data["copy_files"].items()}
    scenes = data["scenes"]
    if data["start_scene"] not in scenes:
        raise ValueError("Unknown start scene")
    steps = set()
    for scene_id, scene in scenes.items():
        step = scene["step"]
        if not isinstance(step, int) or step < 1 or step in steps:
            raise ValueError(f"Invalid or duplicate step: {step}")
        steps.add(step)
        copy = sources[scene["text_file"]]
        scene["buttons"] = copy["buttons"]
        for field in ("title", "text", "inspect"):
            if not isinstance(copy.get(field), str) or not copy[field].strip():
                raise ValueError(f"Missing {field} in {scene['text_file']}")
            scene[field] = copy[field]
        for field in ("messages", "hints", "text_open", "inspect_open", "text_dark", "inspect_dark", "text_empty", "inspect_empty"):
            if field in copy:
                scene[field] = copy[field]
        for variant in scene.get("variants", []):
            if "daylight" in variant and not isinstance(variant["daylight"], bool):
                raise ValueError(f"Invalid daylight variant: {scene_id}")
            validate_condition(variant["when"], scenes)
            for field in ("media", "return_media"):
                if variant.get(field) is not None and variant[field] not in data["media"]:
                    raise ValueError(f"Invalid variant {field}: {scene_id}")
            for field in ("text", "inspect", "buttons", "hints"):
                key = variant.get(field + "_key")
                if key is None:
                    continue
                value = copy.get(key)
                if field == "hints":
                    if not isinstance(value, list) or len(value) != 3 or any(not isinstance(v, str) or not v.strip() for v in value):
                        raise ValueError(f"Invalid variant hints: {scene_id}/{key}")
                    scene[key] = value
                elif field == "buttons":
                    ids = {a["id"] for a in scene["actions"]}
                    if not isinstance(value, dict) or any(k not in ids or not isinstance(v, str) or not v.strip() for k, v in value.items()):
                        raise ValueError(f"Invalid variant buttons: {scene_id}/{key}")
                    scene[key] = dict(copy["buttons"], **value)
                else:
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(f"Invalid variant text: {scene_id}/{key}")
                    scene[key] = value
        if scene["media"] not in data["media"]:
            raise ValueError(f"Unknown media: {scene_id}")
        if scene.get("return_media") is not None and scene["return_media"] not in data["media"]:
            raise ValueError(f"Unknown return media: {scene_id}")
        text_stem = Path(scene["text_file"]).stem
        image_stem = Path(data["media"][scene["media"]]).stem
        if text_stem != image_stem or not text_stem.startswith(f"{step:03d}_"):
            raise ValueError(f"Scene text/image numbering mismatch: {scene_id}")
        seen = set()
        discovery = scene.get("inspect_discovery")
        if discovery is not None and (not isinstance(discovery, dict)
                or not isinstance(discovery.get("flag"), str) or not discovery["flag"]
                or discovery.get("message") not in scene.get("messages", {})):
            raise ValueError(f"Invalid inspect discovery: {scene_id}")
        for action in scene["actions"]:
            if action["id"] in seen or (action.get("type") != "event" and action.get("target") not in scenes):
                raise ValueError(f"Invalid action: {scene_id}/{action['id']}")
            for spec in (action.get("requires"), action.get("visible_if")):
                validate_condition(spec, scenes)
            if action.get("requires") and action.get("failure") not in scene.get("messages", {}):
                raise ValueError(f"Missing failure text: {scene_id}")
            if action.get("type") == "event":
                effects = action.get("effects")
                if not isinstance(effects, dict) or set(effects) - {"flag", "item_locations"} or action.get("message") not in scene.get("messages", {}):
                    raise ValueError(f"Invalid event: {scene_id}")
                if "flag" in effects and (not isinstance(effects["flag"], str) or not effects["flag"]):
                    raise ValueError(f"Invalid event flag: {scene_id}")
            for item, location in action.get("effects", {}).get("item_locations", {}).items():
                if item not in ITEMS or location not in set(scenes) | {"inventory", "cage", "gone", "treasury"}:
                    raise ValueError(f"Invalid item effect: {scene_id}/{item}")
            seen.add(action["id"])
            label = copy["buttons"].get(action["id"])
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"Missing button label: {scene_id}/{action['id']}")
            action["label"] = label
    for asset, relative in data["media"].items():
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT / "media") or not path.is_file():
            raise ValueError(f"Missing or invalid image: {asset} -> {relative}")
    return data
