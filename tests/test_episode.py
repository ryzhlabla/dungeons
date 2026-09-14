import json
from dataclasses import asdict

import pytest

from app.content import load_content
from app.engine import State, InvalidAction, apply, scene_view
from app.repository import Repository
from app.ui import render


def play(s, content, *actions):
    for action in actions:
        apply(s, action, content)
    return s


def prepared():
    c = load_content()
    s = play(State(), c, "new", "move:enter_house", "take_lamp", "take_keys",
             "move:exit_house", "move:follow_stream", "move:follow_rocks")
    return s, c


def test_locked_grate_and_first_complete_episode():
    c = load_content()
    s = play(State(), c, "new", "move:follow_stream", "move:follow_rocks")
    play(s, c, "event:open_grate")
    assert s.scene == "grate"
    assert not s.flags.get("grate_open")
    assert s.notice == c["scenes"]["grate"]["messages"]["locked"]
    with pytest.raises(InvalidAction):
        apply(s, "move:enter_cave", c)
    play(s, c, "move:back_stream", "move:return_road", "move:enter_house",
         "take_keys", "take_lamp", "move:exit_house", "move:follow_stream",
         "move:follow_rocks", "event:open_grate")
    assert s.flags["grate_open"]
    assert scene_view(s,c)["media"] == "scene.grate.open"
    turns=s.turns
    with pytest.raises(InvalidAction):
        apply(s, "event:open_grate", c)
    assert s.turns == turns
    play(s,c,"move:enter_cave","move:enter_hall")
    assert s.scene == "cave_entrance"  # Lamp is still off.
    play(s,c,"ui:inventory","ui:item","lamp_on","ui:scene","move:enter_hall","event:read_marks")
    assert s.scene == "first_hall"
    assert s.flags["chapter_complete"]
    count=len(s.journal)
    with pytest.raises(InvalidAction):
        apply(s,"event:read_marks",c)
    assert len(s.journal)==count
    play(s,c,"move:back_entrance","move:climb_out")
    assert s.scene=="grate"


def test_darkness_dropped_lamp_and_recovery():
    s,c=prepared()
    play(s,c,"event:open_grate","move:enter_cave","ui:inventory","ui:item","lamp_on",
         "drop_lamp","move:enter_hall")
    assert s.scene=="cave_entrance"  # Light must be carried through the passage.
    play(s,c,"take_lamp","move:enter_hall","ui:inventory","ui:item","lamp_off","ui:scene")
    assert scene_view(s,c)["media"]=="scene.first_hall.dark"
    assert scene_view(s,c)["text"]==c["scenes"]["first_hall"]["text_dark"]
    play(s,c,"event:read_marks")
    assert not s.flags.get("chapter_complete")
    play(s,c,"ui:inventory","ui:item","lamp_on","drop_lamp")
    assert scene_view(s,c)["media"]=="scene.first_hall"  # Lit lamp on floor still lights room.
    play(s,c,"event:read_marks")
    assert s.flags["chapter_complete"]
    play(s,c,"move:back_entrance","move:enter_hall")
    assert s.scene=="first_hall"  # A known route remains accessible to recover the lamp.
    play(s,c,"take_lamp","ui:inventory","ui:item","lamp_off","drop_lamp",
         "move:back_entrance","move:enter_hall","take_lamp")
    assert s.item_locations["lamp"]=="inventory"
    assert scene_view(s,c)["media"]=="scene.first_hall.dark"


def test_keys_can_be_left_recovered_and_are_not_consumed():
    s,c=prepared()
    play(s,c,"ui:inventory","ui:keys","drop_keys","event:open_grate")
    assert not s.flags.get("grate_open")
    play(s,c,"take_keys","event:open_grate")
    assert s.flags["grate_open"]
    assert s.item_locations["keys"]=="inventory"


def test_old_save_migrates_without_reset(tmp_path):
    repo=Repository(tmp_path/"saves.sqlite3")
    old=asdict(State(started=True,scene="stream",turns=17,visited=["road_end","inside_house","stream"]))
    old["content_version"]="0.1.0"
    old["item_locations"]={"lamp":"inventory"}
    old["item_states"]["lamp"]["power"]=True
    old.pop("flags")
    with repo.connect() as db:
        db.execute("INSERT INTO saves VALUES (?, ?)",(42,json.dumps(old)))
    loaded=repo.get(42)
    assert loaded.content_version=="0.13.0"
    assert loaded.scene=="stream" and loaded.turns==17
    assert loaded.item_locations=={"lamp":"inventory","keys":"inside_house","cage":"debris_grotto","bird":"bird_grotto","silver":"silver_grotto"}
    assert loaded.item_states["lamp"]["power"]
    assert loaded.flags=={}
    repo.save(42,loaded)
    assert asdict(repo.get(42))==asdict(loaded)


def test_numbered_text_and_variant_images_are_linked():
    c=load_content()
    assert sorted(s["step"] for s in c["scenes"].values())==list(range(1,75))
    s,c=prepared()
    play(s,c,"event:open_grate")
    assert render(s,c).asset=="scene.grate.open"
    play(s,c,"ui:confirm","reset")
    assert not s.flags and s.scene=="road_end"
    assert s.item_locations["keys"]=="inside_house"
