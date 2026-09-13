from dataclasses import asdict
import json
import pytest
from app.content import load_content
from app.engine import State, apply, scene_actions, InvalidAction
from app.repository import Repository
from app.save_tools import rewind_star
from app.ui import render
from test_bird_episode import play

SCENES=('reed_path','near_landing','ferry_house','far_landing','twin_towers','seed_court')

@pytest.fixture(scope='module')
def content():
    return load_content()

def expedition():
    return State(started=True,screen='scene',scene='road_house',
                 visited=['star_vault','old_road','road_house'],
                 flags={'episode8_complete':True})

def test_full_ferry_route_save_return_and_rewind(content,tmp_path):
    c=content;s=expedition()
    play(s,c,'move:back_road')
    with pytest.raises(InvalidAction):apply(s,'move:enter_reeds',c)
    play(s,c,'move:enter_wayhouse','ui:inspect','ui:scene','move:back_road',
         'move:enter_reeds','move:enter_landing')
    with pytest.raises(InvalidAction):apply(s,'move:cross_river',c)
    turns=s.turns;journal=list(s.journal);items=dict(s.item_locations)
    apply(s,'event:try_cross',c)
    assert s.scene=='near_landing' and s.turns==turns+1
    assert s.journal==journal and s.item_locations==items
    assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['near_landing']['messages']['blocked']
    apply(s,'move:enter_house',c)
    assert not {'lift_stop','press_stop'}.intersection(a['id'] for a in scene_actions(s,c))
    with pytest.raises(InvalidAction):apply(s,'event:lift_stop',c)
    apply(s,'ui:inspect',c)
    assert s.flags['ferry_brake_seen']
    turns=s.turns;journal=list(s.journal)
    apply(s,'ui:inspect',c)
    assert s.turns==turns and s.journal==journal
    play(s,c,'ui:scene','event:press_stop')
    assert s.turns==turns+1 and s.journal==journal
    assert not s.flags.get('ferry_released')
    assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['ferry_house']['messages']['wrong']
    apply(s,'event:lift_stop',c)
    assert s.flags['ferry_released']
    assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['ferry_house']['messages']['released']
    with pytest.raises(InvalidAction):apply(s,'event:lift_stop',c)
    play(s,c,'move:back_landing','move:cross_river','move:enter_towers','move:enter_court','ui:inspect')
    assert s.flags['episode10_complete']
    journal=list(s.journal)
    apply(s,'ui:inspect',c)
    assert s.journal==journal
    apply(s,'ui:progress',c)
    assert c['copy']['interface']['Одиннадцатая_цель'] in render(s,c).caption
    repo=Repository(tmp_path/'ferry.sqlite3');repo.save(1,s);s=repo.get(1)
    assert s.flags['episode10_complete'] and s.flags['ferry_released']
    play(s,c,'ui:scene','move:back_towers','move:back_landing','move:cross_back')
    assert s.scene=='near_landing' and s.returning
    assert 'try_cross' not in {a['id'] for a in scene_actions(s,c)}
    assert s.item_locations==items
    play(s,c,'move:cross_river','move:cross_back','move:back_reeds','move:back_road')
    rolled=rewind_star(asdict(s),c)
    assert not set(SCENES).intersection(rolled['visited'])
    assert not any(rolled['flags'].get(f) for f in ('ferry_brake_seen','ferry_released','episode10_complete'))
    play(s,c,'ui:confirm','reset')
    assert not s.flags

def test_dropped_lamp_recoverable_across_river(content):
    s=expedition();s.scene='near_landing';s.flags['ferry_released']=True
    s.item_locations['lamp']='inventory'
    play(s,content,'move:cross_river','ui:item','drop_lamp','move:cross_back')
    assert s.item_locations['lamp']=='far_landing'
    play(s,content,'move:cross_river','take_lamp')
    assert s.item_locations['lamp']=='inventory'

def test_0100_save_upgrade_preserves_state(content,tmp_path):
    s=expedition();s.flags['episode9_complete']=True
    old=asdict(s);old['content_version']='0.10.0'
    repo=Repository(tmp_path/'old.sqlite3')
    with repo.connect() as db:db.execute('INSERT INTO saves VALUES (?,?)',(1,json.dumps(old)))
    restored=repo.get(1)
    assert restored.content_version=='0.12.0'
    comparison=asdict(restored);comparison['content_version']='0.10.0'
    assert comparison==old
    apply(restored,'ui:progress',content)
    assert content['copy']['interface']['Десятая_цель'] in render(restored,content).caption

@pytest.mark.parametrize('sid',SCENES)
@pytest.mark.parametrize('stage',[0,1,2])
def test_daylight_cards_and_returns(content,sid,stage):
    s=expedition();s.scene=sid;s.returning=True
    s.flags.update(episode9_complete=True,ferry_brake_seen=stage>0,ferry_released=stage>1,episode10_complete=stage>1)
    for screen in ('scene','inspect','hint','progress','inventory'):
        s.screen=screen;card=render(s,content)
        assert card.asset!='scene.darkness'
        assert len(card.caption)<=1024
        assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
    s.screen='hint'
    assert 'ламп' not in render(s,content).caption.lower()

def test_banks_have_no_alternative_crossing(content):
    # Ferry follows the player: no path can leave it on the other bank.
    far_side={sid for sid,scene in content['scenes'].items() if scene['step']>=48}
    crossings=[]
    for sid,scene in content['scenes'].items():
        for action in scene['actions']:
            target=action.get('target')
            if target and ((sid in far_side)!=(target in far_side)):
                crossings.append((sid,target,action['id']))
    assert sorted(crossings)==[('far_landing','near_landing','cross_back'),('near_landing','far_landing','cross_river')]
