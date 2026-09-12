import json
from dataclasses import asdict
import pytest
from app.content import load_content
from app.engine import State, apply, InvalidAction, scene_view
from app.repository import Repository
from app.ui import render
from test_bird_episode import play


def expedition():
    c=load_content()
    s=State(started=True,scene='calcite_passage',screen='scene',visited=['calcite_passage'],
            flags={'episode4_complete':True,'silver_found':True})
    s.item_locations.update(lamp='inventory',silver='treasury')
    s.item_states['lamp']['power']=True
    apply(s,'move:enter_wind',c)
    return s,c


def test_full_episode_wrong_answer_gate_shortcut_and_return(tmp_path):
    s,c=expedition()
    with pytest.raises(InvalidAction): apply(s,'move:climb_shortcut',c)
    play(s,c,'move:enter_bells','move:enter_gate','event:open_gate')
    assert not s.flags.get('resonance_gate_open')
    with pytest.raises(InvalidAction): apply(s,'move:enter_balcony',c)
    play(s,c,'move:back_bells','move:back_wind','move:enter_signs','event:read_signs')
    assert s.flags['bell_signs_read']
    play(s,c,'move:back_wind','move:enter_bells')
    play(s,c,'event:take_striker')
    journal=list(s.journal); turns=s.turns
    play(s,c,'event:ring_wrong','event:ring_wrong')
    assert s.journal==journal and s.turns==turns+2
    assert not s.flags.get('bell_lock_released')
    play(s,c,'event:ring_correct','move:enter_gate')
    assert 'запор уже отпущен' in scene_view(s,c)['text']
    assert scene_view(s,c)['media']=='scene.resonance_gate'
    play(s,c,'event:open_gate')
    assert scene_view(s,c)['media']=='scene.resonance_gate.open'
    with pytest.raises(InvalidAction): apply(s,'event:open_gate',c)
    play(s,c,'move:enter_balcony','event:trace_stairs','move:enter_stars','ui:inspect','ui:scene')
    assert s.flags['episode5_complete']
    with pytest.raises(InvalidAction): apply(s,'event:study_stars',c)
    repo=Repository(tmp_path/'saves.sqlite3');repo.save(1,s);s=repo.get(1)
    play(s,c,'move:back_balcony','move:descend_shortcut','move:climb_shortcut','move:back_gate')
    assert s.returning and scene_view(s,c)['media']=='scene.resonance_gate.open'
    play(s,c,'move:back_bells')
    with pytest.raises(InvalidAction): apply(s,'event:ring_wrong',c)
    assert s.item_locations['silver']=='treasury'
    play(s,c,'ui:progress'); assert 'Пятый эпизод завершён' in render(s,c).caption
    play(s,c,'ui:confirm','reset'); assert not s.flags


def test_entry_gate_and_dark_recovery():
    s,c=expedition()
    s.scene='calcite_passage';s.flags.pop('episode4_complete')
    with pytest.raises(InvalidAction):apply(s,'move:enter_wind',c)
    s.flags['episode4_complete']=True
    play(s,c,'move:enter_wind','ui:item','lamp_off','ui:scene','move:enter_bells')
    assert s.scene=='wind_gallery'
    play(s,c,'ui:item','lamp_on','ui:scene','move:enter_bells','event:take_striker','ui:item','lamp_off','ui:scene','event:ring_correct')
    assert not s.flags.get('bell_lock_released')
    play(s,c,'ui:item','lamp_on','ui:scene','event:ring_correct','move:enter_gate','event:open_gate','move:enter_balcony','event:trace_stairs','ui:item','drop_lamp','move:descend_shortcut','move:climb_shortcut','take_lamp')
    assert s.scene=='high_balcony' and s.item_locations['lamp']=='inventory'


def test_previous_save_keeps_treasure_and_unlocks_new_route(tmp_path):
    s,c=expedition();s.scene='calcite_passage'
    data=asdict(s);data['content_version']='0.5.0'
    repo=Repository(tmp_path/'save.sqlite3')
    with repo.connect() as db:db.execute('INSERT INTO saves VALUES (?,?)',(1,json.dumps(data)))
    restored=repo.get(1)
    assert restored.content_version=='0.10.0' and restored.flags==s.flags
    apply(restored,'move:enter_wind',c)
    assert restored.scene=='wind_gallery' and restored.item_locations['silver']=='treasury'


@pytest.mark.parametrize('sid',['wind_gallery','signs_alcove','stone_bells','resonance_gate','high_balcony','star_vault'])
@pytest.mark.parametrize('done',[False,True])
@pytest.mark.parametrize('lit',[False,True])
def test_every_new_state_and_return_card(sid,done,lit):
    s,c=expedition();s.scene=sid;s.returning=True
    s.flags.update({f:done for f in ['bell_signs_read','bell_lock_released','resonance_gate_open','wind_shortcut','episode5_complete']})
    s.item_states['lamp']['power']=lit
    for screen in ('scene','inspect','hint','progress','inventory'):
        s.screen=screen;card=render(s,c)
        assert len(card.caption)<=1024
        if not lit:assert card.asset=='scene.darkness'
        assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
