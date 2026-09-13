from dataclasses import asdict
import json
import pytest
from app.content import load_content
from app.engine import State, apply, scene_actions, InvalidAction
from app.repository import Repository
from app.save_tools import rewind_star
from app.ui import render
from test_bird_episode import play

SCENES=('outer_stairs','pine_fork','trail_shelter','white_hollow','old_road','road_house')

@pytest.fixture(scope='module')
def content():
    return load_content()

def expedition():
    return State(started=True,screen='scene',scene='valley_terrace',
                 visited=['star_vault','eye_gallery','eye_ring','valley_terrace'],
                 flags={'episode7_complete':True,'tower_eye_open':True})

def test_full_daylight_route_and_return(content,tmp_path):
    c=content;s=expedition()
    play(s,c,'move:back_ring')
    with pytest.raises(InvalidAction):apply(s,'move:descend_outer',c)
    play(s,c,'move:climb_terrace','ui:inspect','ui:scene','move:back_ring','move:descend_outer','move:descend_fork')
    with pytest.raises(InvalidAction):apply(s,'move:descend_stones',c)
    turns=s.turns;journal=list(s.journal)
    apply(s,'event:scout_pine',c)
    assert s.scene=='pine_fork' and s.turns==turns+1 and s.journal==journal
    assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['pine_fork']['messages']['wrong']
    play(s,c,'move:enter_shelter','ui:inspect')
    assert s.flags['valley_signs_read']
    journal=list(s.journal);turns=s.turns
    apply(s,'ui:inspect',c)
    assert s.journal==journal and s.turns==turns
    assert render(s,c).caption.count(c['scenes']['trail_shelter']['messages']['discovery'])==1
    play(s,c,'ui:scene','move:back_fork','event:scout_stones')
    assert s.scene=='pine_fork' and s.flags['valley_path_found']
    assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['pine_fork']['messages']['found']
    with pytest.raises(InvalidAction):apply(s,'event:scout_stones',c)
    play(s,c,'move:descend_stones','move:descend_road','move:enter_wayhouse','ui:inspect')
    assert s.flags['episode9_complete']
    journal=list(s.journal)
    apply(s,'ui:inspect',c)
    assert s.journal==journal
    apply(s,'ui:progress',c)
    assert c['copy']['interface']['Десятая_цель'] in render(s,c).caption
    repo=Repository(tmp_path/'road.sqlite3');repo.save(1,s);s=repo.get(1)
    assert s.flags['episode9_complete']
    play(s,c,'ui:scene','move:back_road','move:back_hollow','move:back_fork','move:back_stairs','move:back_ring','move:back_gallery')
    assert s.scene=='eye_gallery' and s.returning
    assert render(s,c).asset=='scene.eye_gallery.open'
    rolled=rewind_star(asdict(s),c)
    assert not set(SCENES).intersection(rolled['visited'])
    assert not any(rolled['flags'].get(f) for f in ('valley_signs_read','valley_path_found','episode9_complete'))

def test_path_can_be_found_without_reading_clue(content):
    s=expedition();s.scene='pine_fork'
    play(s,content,'event:scout_stones','move:descend_stones')
    assert s.scene=='white_hollow' and not s.flags.get('valley_signs_read')

def test_090_save_upgrade_preserves_state(content,tmp_path):
    s=expedition();s.flags['episode8_complete']=True
    old=asdict(s);old['content_version']='0.9.0'
    repo=Repository(tmp_path/'old.sqlite3')
    with repo.connect() as db:db.execute('INSERT INTO saves VALUES (?,?)',(1,json.dumps(old)))
    restored=repo.get(1)
    assert restored.content_version=='0.12.0'
    comparison=asdict(restored);comparison['content_version']='0.9.0'
    assert comparison==old

@pytest.mark.parametrize('sid',SCENES)
@pytest.mark.parametrize('complete',[False,True])
def test_daylight_cards_and_returns(content,sid,complete):
    s=expedition();s.scene=sid;s.returning=True
    s.flags.update(episode8_complete=True,valley_path_found=complete,valley_signs_read=complete,episode9_complete=complete)
    for screen in ('scene','inspect','hint','progress','inventory'):
        s.screen=screen;card=render(s,content)
        assert card.asset!='scene.darkness'
        assert len(card.caption)<=1024
        assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
    s.screen='hint'
    assert 'ламп' not in render(s,content).caption.lower()

def test_ring_entry_and_progress_after_terrace(content):
    s=expedition();s.scene='eye_ring'
    assert 'descend_outer' not in {a['id'] for a in scene_actions(s,content)}
    s.flags['episode8_complete']=True
    assert 'descend_outer' in {a['id'] for a in scene_actions(s,content)}
    apply(s,'ui:progress',content)
    assert content['copy']['interface']['Девятая_цель'] in render(s,content).caption
