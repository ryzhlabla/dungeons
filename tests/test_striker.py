import pytest
from app.engine import apply, InvalidAction, scene_view
from app.repository import Repository
from app.ui import render
from test_wind_episode import expedition


def test_striker_required_persists_and_changes_picture(tmp_path):
    s, c = expedition()
    apply(s, 'move:enter_bells', c)
    apply(s, 'event:try_bells', c)
    assert s.notice == 'Колокола слишком тяжелые и висят слишком высоко. Нужно найти что-то, чем можно ударить по ним'
    with pytest.raises(InvalidAction):
        apply(s, 'event:ring_correct', c)
    s.item_states['lamp']['power'] = False
    apply(s, 'event:take_striker', c)
    assert not s.flags.get('striker_taken')
    s.item_states['lamp']['power'] = True
    apply(s, 'event:take_striker', c)
    assert scene_view(s, c)['media'] == 'scene.stone_bells.empty'
    with pytest.raises(InvalidAction):
        apply(s, 'event:take_striker', c)
    repo = Repository(tmp_path / 'save.sqlite3')
    repo.save(1, s)
    s = repo.get(1)
    apply(s, 'ui:inventory', c)
    assert 'Ударник' in render(s, c).caption
    apply(s, 'ui:scene', c)
    apply(s, 'event:ring_correct', c)
    assert s.flags['bell_lock_released']
    assert scene_view(s, c)['media'] == 'scene.stone_bells.empty'
