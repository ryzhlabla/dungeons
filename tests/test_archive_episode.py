import json
from dataclasses import asdict

import pytest

from app.content import load_content
from app.engine import State, apply, InvalidAction, scene_view, scene_actions
from app.repository import Repository
from app.ui import render
from test_bird_episode import play


NEW_SCENES = ('constellation_stairs', 'flooded_threshold', 'water_clock',
              'sluice_room', 'dry_channel', 'keepers_archive')


def expedition():
    content = load_content()
    state = State(started=True, screen='scene', scene='high_balcony',
                  visited=['high_balcony', 'star_vault', 'underground_lake'],
                  flags={'episode4_complete': True, 'episode5_complete': True})
    state.item_locations.update(lamp='inventory', silver='treasury')
    state.item_states['lamp']['power'] = True
    return state, content


def test_complete_archive_episode_shortcut_and_save(tmp_path):
    s, c = expedition()
    play(s, c, 'move:enter_constellation', 'move:descend_water', 'event:try_descent')
    assert s.scene == 'flooded_threshold' and not s.flags.get('water_diverted')
    with pytest.raises(InvalidAction):
        apply(s, 'move:enter_channel', c)
    play(s, c, 'move:enter_clock', 'ui:inspect')
    assert s.flags['water_signs_read']
    with pytest.raises(InvalidAction):
        apply(s, 'event:read_water_signs', c)
    play(s, c, 'ui:scene', 'move:back_threshold', 'move:enter_sluice')
    journal = list(s.journal)
    turns = s.turns
    play(s, c, 'event:keep_flow', 'event:keep_flow')
    assert s.journal == journal and s.turns == turns + 2
    play(s, c, 'event:divert_water', 'move:back_threshold')
    assert 'показались ступени' in scene_view(s, c)['text']
    play(s, c, 'move:enter_channel', 'move:enter_archive', 'event:read_archive')
    assert s.flags['episode6_complete']
    with pytest.raises(InvalidAction):
        apply(s, 'event:read_archive', c)
    play(s, c, 'event:open_lake_shortcut', 'move:enter_lake')
    assert s.scene == 'underground_lake'
    assert 'enter_archive' in {a['id'] for a in scene_actions(s, c)}
    repo = Repository(tmp_path / 'saves.sqlite3')
    repo.save(1, s)
    restored = repo.get(1)
    assert asdict(restored) == asdict(s)
    play(restored, c, 'move:enter_archive')
    assert restored.returning and 'изучена и записана' in scene_view(restored, c)['text']
    play(restored, c, 'ui:progress')
    assert c['copy']['interface']['Седьмая_цель'] in render(restored, c).caption
    assert restored.item_locations['silver'] == 'treasury'
    play(restored, c, 'ui:confirm', 'reset')
    assert not restored.flags


def test_map_gate_and_light_recovery():
    s, c = expedition()
    s.flags.pop('episode5_complete')
    with pytest.raises(InvalidAction):
        apply(s, 'move:enter_constellation', c)
    s.flags['episode5_complete'] = True
    s.item_states['lamp']['power'] = False
    apply(s, 'move:enter_constellation', c)
    assert s.scene == 'high_balcony'
    s.item_states['lamp']['power'] = True
    play(s, c, 'move:enter_constellation', 'move:descend_water', 'move:enter_sluice')
    play(s, c, 'ui:item', 'drop_lamp')
    s.item_states['lamp']['power'] = False
    apply(s, 'event:divert_water', c)
    assert not s.flags.get('water_diverted')
    assert s.notice == c['scenes']['sluice_room']['messages']['dark']
    play(s, c, 'move:back_threshold', 'move:back_stairs', 'move:back_balcony',
         'move:enter_constellation', 'move:descend_water', 'move:enter_sluice', 'take_lamp')
    assert s.item_locations['lamp'] == 'inventory'
    play(s, c, 'ui:item', 'lamp_on', 'ui:scene', 'event:divert_water')
    # Reading the clue is optional, a correct independent solution works too.
    assert s.flags['water_diverted'] and not s.flags.get('water_signs_read')


def test_06_save_additive_upgrade(tmp_path):
    s, c = expedition()
    old = asdict(s)
    old['content_version'] = '0.6.0'
    old['flags']['striker_taken'] = True
    old['turns'] = 123
    repo = Repository(tmp_path / 'old.sqlite3')
    with repo.connect() as db:
        db.execute('INSERT INTO saves VALUES (?,?)', (1, json.dumps(old)))
    restored = repo.get(1)
    assert restored.content_version == '0.11.0'
    assert restored.flags == old['flags'] and restored.turns == 123
    assert restored.item_locations == old['item_locations']
    apply(restored, 'move:enter_constellation', c)
    assert restored.scene == 'constellation_stairs'


@pytest.mark.parametrize('sid', NEW_SCENES)
@pytest.mark.parametrize('lit', [False, True])
@pytest.mark.parametrize('done', [False, True])
def test_all_cards_and_returns(sid, lit, done):
    s, c = expedition()
    s.scene = sid
    s.returning = True
    s.flags.update({f: done for f in ('water_signs_read', 'water_diverted', 'archive_shortcut', 'episode6_complete')})
    s.item_states['lamp']['power'] = lit
    for screen in ('scene', 'inspect', 'hint', 'progress', 'inventory'):
        s.screen = screen
        card = render(s, c)
        assert len(card.caption) <= 1024
        if not lit:
            assert card.asset == 'scene.darkness'
        assert all(len(button.callback_data.encode()) <= 64
                   for row in card.keyboard.inline_keyboard for button in row)


def test_archive_shortcut_can_open_before_reading():
    s, c = expedition()
    s.scene = 'keepers_archive'
    apply(s, 'event:open_lake_shortcut', c)
    assert 'ждёт изучения' in scene_view(s, c)['text']
    apply(s, 'event:read_archive', c)
    assert 'изучена и записана' in scene_view(s, c)['text']
