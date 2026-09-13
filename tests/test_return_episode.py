from copy import deepcopy
from dataclasses import asdict
import json
import pytest
from app.content import load_content
from app.engine import State, apply, InvalidAction
from app.repository import Repository
from app.save_tools import rewind_star
from app.ui import render
from test_bird_episode import play

SCENES=('watcher_house','garden_wicket','cedar_path','boundary_stone','dry_pass','forest_waymark')
TO_MARKER=('move:enter_gate','move:enter_cedars','move:enter_marker','ui:inspect','ui:scene','move:enter_pass','move:enter_waymark')
TO_HOUSE=('move:back_pass','move:back_marker','move:back_cedars','move:back_gate','move:back_house')
TO_BED=('move:back_wall','move:enter_descent','move:descend_storage','move:enter_reserve','move:enter_light')
FROM_BED=('move:back_reserve','move:back_hall','move:back_descent','move:back_wall','move:enter_watcher')

@pytest.fixture(scope='module')
def content():return load_content()

def expedition():
    return State(started=True,screen='scene',scene='light_chamber',
        visited=['star_vault','wall_path','service_descent','jar_hall','seed_reserve','light_chamber'],
        flags={'episode10_complete':True,'episode11_complete':True,'seed_sample_taken':True})

def test_sprouts_before_route_and_save(content,tmp_path):
    c=content;s=expedition()
    apply(s,'ui:inspect',c)
    assert not s.flags.get('seedlings_verified')
    assert render(s,c).asset=='scene.light_chamber'
    play(s,c,'ui:scene',*FROM_BED)
    with pytest.raises(InvalidAction):apply(s,'event:tend_seedbed',c)
    play(s,c,'ui:inspect','ui:scene')
    with pytest.raises(InvalidAction):apply(s,'move:enter_gate',c)
    assert not any(b.callback_data=='move:enter_gate' for row in render(s,c).keyboard.inline_keyboard for b in row)
    turns=s.turns;items=dict(s.item_locations)
    apply(s,'event:tend_seedbed',c)
    assert s.turns==turns+1 and s.item_locations==items
    assert s.flags['seedlings_ready'] and not s.flags.get('seedlings_verified')
    assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['watcher_house']['messages']['days_passed']
    with pytest.raises(InvalidAction):apply(s,'move:enter_gate',c)
    assert not any(b.callback_data=='move:enter_gate' for row in render(s,c).keyboard.inline_keyboard for b in row)
    with pytest.raises(InvalidAction):apply(s,'event:tend_seedbed',c)
    play(s,c,*TO_BED,'ui:inspect')
    assert s.flags['seedlings_verified']
    assert render(s,c).asset=='scene.light_chamber.sprouts'
    journal=list(s.journal)
    apply(s,'ui:inspect',c)
    assert s.journal==journal
    play(s,c,'ui:scene',*FROM_BED,*TO_MARKER,'ui:inspect')
    assert s.flags['episode12_complete']
    journal=list(s.journal)
    apply(s,'ui:inspect',c)
    assert s.journal==journal
    repo=Repository(tmp_path/'return.sqlite3');repo.save(1,s);s=repo.get(1)
    assert s.flags['episode12_complete'] and s.flags['seedlings_verified']
    apply(s,'ui:progress',c)
    assert c['copy']['interface']['Двенадцатая_цель_выполнена'] in render(s,c).caption
    rolled=rewind_star(asdict(s),c)
    assert not set(SCENES).intersection(rolled['visited'])
    assert not any(rolled['flags'].get(f) for f in ('watcher_notes_read','seedlings_ready','seedlings_verified','return_path_known','episode12_complete'))

def test_entry_and_wait_require_sowing(content):
    s=expedition();s.scene='wall_path';s.flags.pop('episode11_complete')
    with pytest.raises(InvalidAction):apply(s,'move:enter_watcher',content)
    s.scene='watcher_house';s.flags['watcher_notes_read']=True
    with pytest.raises(InvalidAction):apply(s,'event:tend_seedbed',content)
    s.scene='boundary_stone'
    with pytest.raises(InvalidAction):apply(s,'move:enter_pass',content)

def test_0120_migration(content,tmp_path):
    s=expedition();old=asdict(s);old['content_version']='0.12.0'
    repo=Repository(tmp_path/'old.sqlite3')
    with repo.connect() as db:db.execute('INSERT INTO saves VALUES (?,?)',(1,json.dumps(old)))
    loaded=repo.get(1)
    assert loaded.content_version=='0.13.0'
    comparison=asdict(loaded);comparison['content_version']='0.12.0'
    assert comparison==old

def test_inspect_requirement_validation_and_light(content):
    bad=deepcopy(content['_manifest'])
    bad['scenes']['light_chamber']['inspect_discovery']['requires']={'op':'unknown'}
    with pytest.raises(ValueError,match='Unknown condition'):load_content(bad)
    c=deepcopy(content)
    c['scenes']['seed_records']['inspect_discovery']['requires']={'op':'flag_set','flag':'seedlings_ready'}
    s=expedition();s.scene='seed_records';s.item_locations['lamp']='inventory'
    s.item_states['lamp']['power']=True
    apply(s,'ui:inspect',c)
    assert not s.flags.get('seed_instructions_read')
    s.flags['seedlings_ready']=True;s.item_states['lamp']['power']=False
    apply(s,'ui:inspect',c)
    assert not s.flags.get('seed_instructions_read')
    s.item_states['lamp']['power']=True
    apply(s,'ui:inspect',c)
    assert s.flags['seed_instructions_read']

@pytest.mark.parametrize('sid',SCENES+('light_chamber',))
@pytest.mark.parametrize('stage',[0,1,2])
def test_daylight_state_cards(content,sid,stage):
    s=expedition();s.scene=sid;s.returning=True
    s.flags.update(watcher_notes_read=stage>0,seedlings_ready=stage>0,seedlings_verified=stage>0,return_path_known=stage>0,episode12_complete=stage>1)
    for screen in ('scene','inspect','hint','progress','inventory'):
        s.screen=screen;card=render(s,content)
        assert card.asset!='scene.darkness'
        assert len(card.caption)<=1024
        assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
        if sid=='light_chamber':
            assert card.asset==('scene.light_chamber.sprouts' if stage else 'scene.light_chamber')
