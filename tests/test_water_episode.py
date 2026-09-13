import json
from dataclasses import asdict
import pytest

from app.content import load_content
from app.engine import State, apply, InvalidAction, scene_view
from app.repository import Repository
from app.ui import render
from test_bird_episode import reach_debris, play


def reach_gallery():
    state, content = reach_debris()
    play(state, content, 'take_cage', 'move:enter_bird_grotto', 'event:catch_bird',
         'move:enter_king_hall', 'event:release_bird', 'event:cross_hall', 'move:enter_gallery')
    return state, content


def test_complete_water_episode_and_return(tmp_path):
    s, c = reach_gallery()
    play(s, c, 'move:follow_ledge')
    assert s.scene == 'water_gallery' and not s.flags.get('water_path_known')
    play(s, c, 'move:enter_echo', 'event:study_ledge')
    assert s.flags['water_path_known']
    with pytest.raises(InvalidAction):
        apply(s, 'event:study_ledge', c)
    play(s, c, 'move:back_gallery', 'ui:hint')
    assert 'Обход найден' in render(s, c).caption
    play(s, c, 'ui:scene', 'move:follow_ledge', 'event:study_lake')
    assert s.flags['episode3_complete']
    assert len(render(s, c).caption) <= 1024
    with pytest.raises(InvalidAction):
        apply(s, 'event:study_lake', c)
    repository = Repository(tmp_path / 'save.sqlite3')
    repository.save(1, s)
    s = repository.get(1)
    play(s, c, 'move:back_gallery')
    assert s.returning and 'Теперь вы знаете' in scene_view(s, c)['text']
    play(s, c, 'move:back_king', 'move:enter_gallery', 'move:follow_ledge')
    assert 'Ближний берег изучен' in scene_view(s, c)['text']
    assert s.item_locations['bird'] == 'gone'
    play(s, c, 'ui:progress')
    assert c['copy']['interface']['Четвёртая_цель'] in render(s, c).caption


def test_light_and_recovery_on_known_path():
    s, c = reach_gallery()
    play(s, c, 'move:enter_echo', 'ui:item', 'lamp_off', 'ui:scene', 'event:study_ledge')
    assert not s.flags.get('water_path_known')
    assert scene_view(s, c)['media'] == 'scene.darkness'
    play(s, c, 'ui:item', 'lamp_on', 'ui:scene', 'event:study_ledge', 'ui:item', 'drop_lamp', 'move:back_gallery', 'move:follow_ledge')
    assert s.scene == 'water_gallery'  # Unknown lake cannot be entered without lamp.
    play(s, c, 'move:enter_echo', 'take_lamp', 'move:back_gallery', 'move:follow_ledge')
    assert s.scene == 'underground_lake'
    play(s, c, 'ui:item', 'lamp_off', 'ui:scene', 'event:study_lake')
    assert not s.flags.get('episode3_complete')
    play(s, c, 'ui:item', 'drop_lamp', 'move:back_gallery', 'move:follow_ledge', 'take_lamp', 'ui:item', 'lamp_on', 'ui:scene', 'event:study_lake')
    assert s.flags['episode3_complete']


def test_old_finished_save_can_continue(tmp_path):
    repository = Repository(tmp_path / 'save.sqlite3')
    old = State(started=True, scene='king_hall', screen='scene', visited=['king_hall'], flags={'snake_gone': True, 'episode2_complete': True})
    old.item_locations.update(lamp='inventory', bird='gone')
    old.item_states['lamp']['power'] = True
    data = asdict(old)
    data['content_version'] = '0.3.0'
    data.pop('returning')
    with repository.connect() as db:
        db.execute('INSERT INTO saves VALUES (?, ?)', (1, json.dumps(data)))
    restored = repository.get(1)
    assert restored.content_version == '0.13.0'
    apply(restored, 'move:enter_gallery', load_content())
    assert restored.scene == 'water_gallery' and restored.item_locations['bird'] == 'gone'


@pytest.mark.parametrize('sid', ['water_gallery', 'echo_hall', 'underground_lake'])
@pytest.mark.parametrize('known', [False, True])
@pytest.mark.parametrize('lit', [False, True])
def test_new_scene_state_cards(sid, known, lit):
    c = load_content()
    s = State(started=True, scene=sid, returning=True, flags={'water_path_known': known, 'episode3_complete': known})
    s.item_locations['lamp'] = 'inventory'
    s.item_states['lamp']['power'] = lit
    for screen in ('scene', 'inspect', 'hint', 'progress'):
        s.screen = screen
        card = render(s, c)
        assert len(card.caption) <= 1024
        assert card.asset == ('scene.' + sid if lit else 'scene.darkness')
        assert all(len(b.callback_data.encode()) <= 64 for row in card.keyboard.inline_keyboard for b in row)
