import copy
import json
from dataclasses import asdict

import pytest

from app.content import load_content, validate_condition
from app.engine import State, apply, InvalidAction, scene_view
from app.repository import Repository
from app.ui import render


def play(state, content, *actions):
    for action in actions:
        apply(state, action, content)
    return state


def reach_debris():
    content = load_content()
    s = play(State(), content, "new", "move:enter_house", "take_lamp", "take_keys",
             "ui:inventory", "ui:item", "lamp_on", "ui:scene", "move:exit_house",
             "move:follow_stream", "move:follow_rocks", "event:open_grate",
             "move:enter_cave", "move:enter_hall", "event:read_marks", "move:enter_debris")
    return s, content


def test_complete_bird_puzzle_and_single_use():
    s, c = reach_debris()
    play(s, c, "take_cage", "move:enter_bird_grotto", "event:catch_bird")
    assert s.item_locations["bird"] == "cage"
    assert scene_view(s, c)["media"] == "scene.bird_grotto.empty"
    turns = s.turns
    with pytest.raises(InvalidAction):
        apply(s, "event:catch_bird", c)
    assert s.turns == turns
    play(s, c, "ui:inventory")
    assert c["copy"]["cage"]["title_full"] in render(s, c).caption
    play(s, c, "ui:scene", "move:enter_king_hall", "event:release_bird")
    assert s.flags["snake_gone"]
    assert s.item_locations["bird"] == "gone"
    assert s.item_locations["cage"] == "inventory"
    assert scene_view(s, c)["media"] == "scene.king_hall.open"
    with pytest.raises(InvalidAction):
        apply(s, "event:release_bird", c)
    play(s, c, "event:cross_hall")
    assert s.flags["episode2_complete"]
    with pytest.raises(InvalidAction):
        apply(s, "event:cross_hall", c)
    play(s, c, "move:back_bird", "move:back_debris", "move:back_first_hall")
    assert s.scene == "first_hall"


def test_failed_catch_and_snake_do_not_consume_bird():
    s, c = reach_debris()
    play(s, c, "move:enter_bird_grotto", "event:catch_bird")
    assert s.item_locations["bird"] == "bird_grotto"
    assert not s.flags.get("bird_caught")
    play(s, c, "move:enter_king_hall", "event:cross_hall")
    assert not s.flags.get("episode2_complete")
    assert not s.flags.get("snake_gone")
    with pytest.raises(InvalidAction):
        apply(s, "event:release_bird", c)
    play(s, c, "move:back_bird", "move:back_debris", "take_cage", "move:enter_bird_grotto",
         "ui:inventory", "ui:item", "lamp_off", "ui:scene", "event:catch_bird")
    assert s.item_locations["bird"] == "bird_grotto"
    assert scene_view(s, c)["media"] == "scene.darkness"
    play(s, c, "ui:inventory", "ui:item", "lamp_on", "ui:scene", "event:catch_bird",
         "move:enter_king_hall", "ui:inventory", "ui:item", "lamp_off", "ui:scene",
         "event:release_bird")
    assert s.item_locations["bird"] == "cage"
    assert not s.flags.get("snake_gone")
    play(s, c, "ui:inventory", "ui:item", "lamp_on", "ui:scene", "event:release_bird")
    assert s.flags["snake_gone"]


def test_cage_and_bird_survive_drop_and_restart(tmp_path):
    s, c = reach_debris()
    play(s, c, "take_cage", "move:enter_bird_grotto", "event:catch_bird",
         "ui:inventory", "ui:cage", "drop_cage", "move:enter_king_hall")
    repo = Repository(tmp_path / "state.sqlite3")
    repo.save(1, s)
    restored = Repository(repo.path).get(1)
    assert asdict(restored) == asdict(s)
    with pytest.raises(InvalidAction):
        apply(restored, "event:release_bird", c)
    play(restored, c, "move:back_bird", "take_cage", "move:enter_king_hall", "event:release_bird")
    assert restored.flags["snake_gone"]


def test_known_dark_path_recovers_items_in_new_rooms():
    s, c = reach_debris()
    play(s, c, "take_cage", "move:enter_bird_grotto", "ui:inventory", "ui:item",
         "lamp_off", "drop_lamp", "move:back_debris", "move:enter_bird_grotto", "take_lamp")
    assert s.scene == "bird_grotto"
    assert s.item_locations["lamp"] == "inventory"
    play(s, c, "move:enter_king_hall")
    assert s.scene == "bird_grotto"  # Unvisited room still needs light.
    play(s, c, "ui:inventory", "ui:item", "lamp_on", "ui:scene", "move:enter_king_hall")
    assert s.scene == "king_hall"


@pytest.mark.parametrize("version", ["0.1.0", "0.2.0"])
def test_existing_saves_add_cage_without_losing_progress(tmp_path, version):
    repo = Repository(tmp_path / "save.sqlite3")
    old = asdict(State(started=True, scene="first_hall", turns=42,
                       flags={"grate_open": True, "chapter_complete": True}))
    old["content_version"] = version
    old["item_locations"] = {"lamp": "inventory", "keys": "grate"}
    old["item_states"]["lamp"]["power"] = True
    with repo.connect() as db:
        db.execute("INSERT INTO saves VALUES (?, ?)", (1, json.dumps(old)))
    s = repo.get(1)
    assert s.content_version == "0.11.0"
    assert s.scene == "first_hall" and s.turns == 42
    assert s.flags == old["flags"]
    assert s.item_locations["keys"] == "grate"
    assert s.item_locations["cage"] == "debris_grotto"
    assert s.item_locations["bird"] == "bird_grotto"
    assert s.item_states["lamp"]["power"]
    play(s, load_content(), "ui:scene", "move:enter_debris")
    assert s.scene == "debris_grotto"


def test_new_screens_buttons_and_variants():
    s, c = reach_debris()
    path = ["take_cage", "move:enter_bird_grotto", "event:catch_bird",
            "ui:inventory", "ui:cage", "drop_cage", "take_cage", "ui:scene",
            "move:enter_king_hall", "event:release_bird", "event:cross_hall"]
    for action in path:
        apply(s, action, c)
        card = render(s, c)
        assert len(card.caption) <= 1024
        assert card.asset in c["media"]
        for row in card.keyboard.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= 64
                next_state = copy.deepcopy(s)
                apply(next_state, button.callback_data.split(":", 2)[2], c)
    play(s, c, "ui:confirm", "reset")
    assert s.item_locations["bird"] == "bird_grotto" and not s.flags


def test_nested_conditions_reject_bad_references():
    scenes = load_content()["scenes"]
    with pytest.raises(ValueError):
        validate_condition({"all": [{"op": "has_item", "item": "missing"}]}, scenes)
    with pytest.raises(ValueError):
        validate_condition({"not": {"op": "item_at", "item": "bird", "location": "missing"}}, scenes)
    with pytest.raises(ValueError):
        validate_condition({"op": "light_or_known_path", "scene": "missing"}, scenes)


@pytest.mark.parametrize("bird_location", ["bird_grotto", "cage", "gone"])
@pytest.mark.parametrize("cage_here", [False, True])
@pytest.mark.parametrize("lamp_on", [False, True])
def test_debris_description_follows_bird_without_overriding_cage_image(bird_location, cage_here, lamp_on):
    c = load_content()
    s = State(started=True, scene="debris_grotto", screen="scene")
    s.item_locations.update(lamp="inventory", bird=bird_location,
                            cage="debris_grotto" if cage_here else "inventory")
    s.item_states["lamp"]["power"] = lamp_on
    view = scene_view(s, c)
    expected = "scene.debris_grotto" if cage_here else "scene.debris_grotto.empty"
    assert view["media"] == (expected if lamp_on else "scene.darkness")
    card = render(s, c)
    labels = " ".join(b.text for row in card.keyboard.inline_keyboard for b in row)
    if bird_location != "bird_grotto" or not lamp_on:
        assert "свист" not in (view["text"] + view["inspect"] + labels).lower()
    else:
        assert "свист" in view["inspect"].lower()
        assert "Идти на свист" in labels


def test_return_to_debris_after_releasing_bird_is_quiet():
    s, c = reach_debris()
    play(s, c, "take_cage", "move:enter_bird_grotto", "event:catch_bird",
         "move:enter_king_hall", "event:release_bird", "event:cross_hall",
         "move:back_bird", "move:back_debris")
    for action in ("ui:scene", "ui:inspect", "ui:hint"):
        apply(s, action, c)
        card = render(s, c)
        assert "свист" not in card.caption.lower()
        assert all("свист" not in b.text.lower() for row in card.keyboard.inline_keyboard for b in row)
    assert s.item_locations["bird"] == "gone"
