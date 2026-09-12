from dataclasses import dataclass, field
from uuid import uuid4


class InvalidAction(ValueError):
    pass


@dataclass
class State:
    content_version: str = "0.11.0"
    started: bool = False
    scene: str = "road_end"
    screen: str = "start"
    turns: int = 0
    item_locations: dict = field(default_factory=lambda: {"lamp": "inside_house", "keys": "inside_house", "cage": "debris_grotto", "bird": "bird_grotto", "silver": "silver_grotto"})
    item_states: dict = field(default_factory=lambda: {"lamp": {"power": False}})
    visited: list = field(default_factory=list)
    returning: bool = False
    journal: list = field(default_factory=list)
    hint_level: int = 0
    revision: str = field(default_factory=lambda: uuid4().hex[:12])
    message_id: int | None = None
    notice: str = ""
    flags: dict = field(default_factory=dict)


def record(state, text):
    state.journal = (state.journal + [text])[-20:]



def condition(state, spec):
    if not spec:
        return True
    if "all" in spec:
        return all(condition(state, child) for child in spec["all"])
    if "not" in spec:
        return not condition(state, spec["not"])
    op = spec["op"]
    if op == "item_at":
        return state.item_locations.get(spec["item"]) == spec["location"]
    if op == "has_item":
        return state.item_locations.get(spec["item"]) == "inventory"
    if op == "flag_set":
        return bool(state.flags.get(spec["flag"]))
    if op == "flag_not_set":
        return not state.flags.get(spec["flag"], False)
    lamp_on = state.item_states["lamp"]["power"]
    location = state.item_locations["lamp"]
    if op == "light_or_known_path":
        return (lamp_on and location == "inventory") or spec["scene"] in state.visited
    if op == "carried_light":
        return lamp_on and location == "inventory"
    if op == "light_here":
        return lamp_on and location in ("inventory", state.scene)
    if op == "no_light_here":
        return not (lamp_on and location in ("inventory", state.scene))
    raise ValueError(f"Unknown condition: {op}")


def scene_actions(state, content):
    scene = scene_view(state, content)
    return [dict(a, label=scene["buttons"].get(a["id"], a["label"])) for a in scene["actions"]
            if condition(state, a.get("visible_if"))]


def scene_view(state, content):
    scene = dict(content["scenes"][state.scene])
    if state.returning and scene.get("return_media"):
        scene["media"] = scene["return_media"]
    for variant in scene.get("variants", []):
        if condition(state, variant["when"]):
            if variant.get("daylight"):
                scene["dark"] = False
            if variant.get("media"):
                scene["media"] = variant["media"]
            if state.returning and variant.get("return_media"):
                scene["media"] = variant["return_media"]
            for field in ("text", "inspect", "buttons", "hints"):
                if field + "_key" in variant:
                    scene[field] = scene[variant[field + "_key"]]
    return scene


def apply(state, action, content):
    """Mutate a loaded snapshot; repository commits only successful actions."""
    state.notice = ""
    if action == "ui:start":
        state.screen = "start"
    elif action == "ui:help":
        state.screen = "help"
    elif action == "new":
        if state.started:
            raise InvalidAction("Use confirmation")
        state.started = True
        state.scene = content["start_scene"]
        state.returning = False
        state.visited = [state.scene]
        state.screen = "scene"
        record(state, content["copy"]["events"]["Приключение_началось"])
    elif action == "reset":
        if state.screen != "confirm":
            raise InvalidAction("Confirmation required")
        old_message = state.message_id
        fresh = State(started=True, screen="scene", visited=[content["start_scene"]])
        state.__dict__.update(fresh.__dict__)
        state.message_id = old_message
        record(state, content["copy"]["events"]["Начато_новое_приключение"])
    elif not state.started:
        raise InvalidAction("Start the game first")
    elif action.startswith("ui:"):
        screen = action[3:]
        if screen not in {"scene", "inspect", "inventory", "item", "hint", "menu",
                          "journal", "progress", "confirm", "keys", "cage", "silver"}:
            raise InvalidAction("Unknown screen")
        if screen == "item" and state.item_locations["lamp"] != "inventory":
            raise InvalidAction("Item not carried")
        if screen == "keys" and state.item_locations["keys"] != "inventory":
            raise InvalidAction("Item not carried")
        if screen == "cage" and state.item_locations["cage"] != "inventory":
            raise InvalidAction("Item not carried")
        if screen == "silver" and state.item_locations["silver"] != "inventory":
            raise InvalidAction("Item not carried")
        state.screen = screen
        if screen == "inspect":
            discovery = content["scenes"][state.scene].get("inspect_discovery")
            if discovery and (not scene_view(state, content).get("dark") or condition(state, {"op": "light_here"})) and not state.flags.get(discovery["flag"]):
                state.flags[discovery["flag"]] = True
                record(state, content["scenes"][state.scene]["messages"][discovery["message"]])
        if screen == "hint":
            state.hint_level = 0
    elif action == "hint_more":
        if state.screen != "hint":
            raise InvalidAction("Wrong screen")
        state.hint_level = min(2, state.hint_level + 1)
    elif action.startswith(("move:", "event:")):
        if state.screen != "scene":
            raise InvalidAction("Wrong screen")
        choices = {a["id"]: a for a in scene_actions(state, content)}
        selected = choices.get(action.split(":", 1)[1])
        if not selected or action.split(":", 1)[0] != ("event" if selected.get("type") == "event" else "move"):
            raise InvalidAction("Action unavailable")
        state.turns += 1
        scene = content["scenes"][state.scene]
        if not condition(state, selected.get("requires")):
            state.notice = scene["messages"][selected["failure"]]
        elif selected.get("type") == "event":
            flag = selected["effects"].get("flag")
            if flag:
                state.flags[flag] = True
            state.item_locations.update(selected["effects"].get("item_locations", {}))
            state.notice = scene["messages"][selected["message"]]
            if selected["effects"]:
                record(state, state.notice)
        else:
            state.returning = selected["target"] in state.visited
            state.scene = selected["target"]
            if state.scene not in state.visited:
                state.visited.append(state.scene)
                record(state, content["copy"]["events"]["Открыто_место"] + content["scenes"][state.scene]["title"])
    elif action == "take_silver":
        if state.screen != "scene" or state.item_locations["silver"] != state.scene:
            raise InvalidAction("Item unavailable")
        if scene_view(state, content).get("dark") and not condition(state, {"op": "light_here"}):
            raise InvalidAction("Light required")
        state.item_locations["silver"] = "inventory"
        state.turns += 1
        first = not state.flags.get("silver_found")
        state.flags["silver_found"] = True
        state.notice = content["copy"]["silver"]["found_notice" if first else "take_notice"]
        if first:
            record(state, content["copy"]["silver"]["found_journal"])
    elif action == "drop_silver":
        if state.screen != "silver" or state.item_locations["silver"] != "inventory":
            raise InvalidAction("Item not carried")
        state.item_locations["silver"] = state.scene
        state.screen = "scene"
        state.turns += 1
        state.notice = content["copy"]["silver"]["drop_notice"]
    elif action == "take_cage":
        if state.screen != "scene" or state.item_locations["cage"] != state.scene:
            raise InvalidAction("Item unavailable")
        state.item_locations["cage"] = "inventory"
        state.turns += 1
        state.notice = content["copy"]["cage"]["take_notice"]
        record(state, content["copy"]["cage"]["take_journal"])
    elif action == "drop_cage":
        if state.screen != "cage" or state.item_locations["cage"] != "inventory":
            raise InvalidAction("Item unavailable")
        state.item_locations["cage"] = state.scene
        state.screen = "scene"
        state.turns += 1
        state.notice = content["copy"]["cage"]["drop_notice"]
    elif action == "take_keys":
        if state.screen != "scene" or state.item_locations["keys"] != state.scene:
            raise InvalidAction("Item unavailable")
        state.item_locations["keys"] = "inventory"
        state.turns += 1
        state.notice = content["copy"]["keys"]["take_notice"]
        record(state, content["copy"]["keys"]["take_journal"])
    elif action == "drop_keys":
        if state.screen != "keys" or state.item_locations["keys"] != "inventory":
            raise InvalidAction("Item unavailable")
        state.item_locations["keys"] = state.scene
        state.screen = "scene"
        state.turns += 1
        state.notice = content["copy"]["keys"]["drop_notice"]
    elif action == "take_lamp":
        if state.screen != "scene" or state.item_locations["lamp"] != state.scene:
            raise InvalidAction("Item unavailable")
        state.item_locations["lamp"] = "inventory"
        state.turns += 1
        state.notice = content["copy"]["events"]["Вы_бережно_убираете_старую_лампу_в_рюкзак"]
        record(state, content["copy"]["events"]["Подобрана_старая_лампа"])
    elif action in {"lamp_on", "lamp_off", "drop_lamp"}:
        if state.screen != "item" or state.item_locations["lamp"] != "inventory":
            raise InvalidAction("Item unavailable")
        if action == "drop_lamp":
            state.item_locations["lamp"] = state.scene
            state.screen = "scene"
            state.notice = content["copy"]["events"]["Вы_оставляете_лампу_здесь_Её_можно_подобрать"]
        else:
            power = action == "lamp_on"
            if state.item_states["lamp"]["power"] == power:
                raise InvalidAction("Already done")
            state.item_states["lamp"]["power"] = power
            state.notice = content["copy"]["events"]["Лампа_мягко_освещает_всё_вокруг"] if power else content["copy"]["events"]["Вы_гасите_лампу"]
        state.turns += 1
    else:
        raise InvalidAction("Unknown action")
    state.revision = uuid4().hex[:12]
    return state
