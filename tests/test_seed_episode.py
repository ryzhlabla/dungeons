from dataclasses import asdict
import json
import pytest
from app.content import load_content
from app.engine import State, apply, InvalidAction
from app.repository import Repository
from app.save_tools import rewind_star
from app.ui import render
from test_bird_episode import play

SCENES=('wall_path','service_descent','jar_hall','seed_records','seed_reserve','light_chamber')

@pytest.fixture(scope='module')
def content():return load_content()

def expedition():
    s=State(started=True,screen='scene',scene='seed_court',
            visited=['star_vault','twin_towers','seed_court'],flags={'episode9_complete':True})
    s.item_locations['lamp']='inventory'
    return s

def test_full_seed_route_and_consumption(content,tmp_path):
    c=content;s=expedition()
    play(s,c,'move:back_towers')
    with pytest.raises(InvalidAction):apply(s,'move:enter_wall_path',c)
    play(s,c,'move:enter_court','ui:inspect','ui:scene','move:back_towers',
         'move:enter_wall_path','move:enter_descent','move:descend_storage')
    assert s.scene=='service_descent'
    play(s,c,'ui:item','lamp_on','ui:scene','move:descend_storage','move:enter_reserve')
    with pytest.raises(InvalidAction):apply(s,'event:take_sample',c)
    journal=list(s.journal);turns=s.turns
    apply(s,'event:open_large',c)
    assert s.journal==journal and s.turns==turns+1
    assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['seed_reserve']['messages']['sealed']
    play(s,c,'move:back_hall','move:enter_records','ui:inspect')
    assert s.flags['seed_instructions_read']
    journal=list(s.journal);turns=s.turns
    apply(s,'ui:inspect',c)
    assert s.journal==journal and s.turns==turns
    play(s,c,'ui:scene','move:back_hall','move:enter_reserve','ui:item','lamp_off','drop_lamp','event:take_sample')
    assert s.flags['seed_sample_taken']
    assert render(s,c).asset=='scene.seed_reserve'
    apply(s,'ui:inventory',c)
    label=c['copy']['interface']['Пробная_порция_семян']
    assert render(s,c).caption.count(label)==1
    repo=Repository(tmp_path/'seed.sqlite3');repo.save(1,s);s=repo.get(1)
    assert s.flags['seed_sample_taken'] and not s.flags.get('episode11_complete')
    play(s,c,'ui:scene','move:enter_light','event:sow_sample')
    assert s.flags['episode11_complete']
    assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['light_chamber']['messages']['sown']
    with pytest.raises(InvalidAction):apply(s,'event:sow_sample',c)
    apply(s,'ui:inventory',c)
    assert label not in render(s,c).caption
    repo.save(1,s);s=repo.get(1)
    assert s.flags['episode11_complete']
    play(s,c,'ui:scene','move:back_reserve')
    with pytest.raises(InvalidAction):apply(s,'event:take_sample',c)
    play(s,c,'take_lamp','move:back_hall')
    assert render(s,c).asset=='scene.darkness'
    play(s,c,'move:back_descent','move:back_wall','move:back_towers')
    assert render(s,c).asset!='scene.darkness'
    rolled=rewind_star(asdict(s),c)
    assert not set(SCENES).intersection(rolled['visited'])
    assert not any(rolled['flags'].get(f) for f in ('seed_instructions_read','seed_sample_taken','episode11_complete'))
    apply(s,'ui:progress',c)
    assert c['copy']['interface']['Одиннадцатая_цель_выполнена'] in render(s,c).caption
    play(s,c,'ui:confirm','reset','ui:inventory')
    assert not s.flags and label not in render(s,c).caption

def test_dark_inspection_and_lamp_recovery(content):
    s=expedition();s.scene='seed_records';s.visited.extend(SCENES)
    play(s,content,'ui:item','drop_lamp','ui:inspect')
    assert not s.flags.get('seed_instructions_read')
    play(s,content,'ui:scene','move:back_hall','move:back_descent','move:descend_storage','move:enter_records','take_lamp','ui:item','lamp_on','ui:inspect')
    assert s.flags['seed_instructions_read']

def test_no_sowing_without_sample(content):
    s=expedition();s.scene='light_chamber'
    with pytest.raises(InvalidAction):apply(s,'event:sow_sample',content)
    assert not s.flags.get('episode11_complete')

def test_0110_save_upgrade(content,tmp_path):
    s=expedition();s.flags['episode10_complete']=True
    old=asdict(s);old['content_version']='0.11.0'
    repo=Repository(tmp_path/'old.sqlite3')
    with repo.connect() as db:db.execute('INSERT INTO saves VALUES (?,?)',(1,json.dumps(old)))
    loaded=repo.get(1)
    assert loaded.content_version=='0.12.0'
    comparison=asdict(loaded);comparison['content_version']='0.11.0'
    assert comparison==old
    apply(loaded,'ui:progress',content)
    assert content['copy']['interface']['Одиннадцатая_цель'] in render(loaded,content).caption

@pytest.mark.parametrize('sid',SCENES)
@pytest.mark.parametrize('lit',[False,True])
@pytest.mark.parametrize('complete',[False,True])
def test_cards_light_and_return(content,sid,lit,complete):
    s=expedition();s.scene=sid;s.returning=True
    s.item_states['lamp']['power']=lit
    s.flags.update(episode10_complete=True,seed_instructions_read=complete,seed_sample_taken=complete,episode11_complete=complete)
    for screen in ('scene','inspect','hint','inventory','progress'):
        s.screen=screen;card=render(s,content)
        assert len(card.caption)<=1024
        assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
        assert (card.asset=='scene.darkness')==(not lit and sid in ('jar_hall','seed_records'))
