from dataclasses import asdict
import pytest
from app.content import load_content
from app.engine import State, apply, InvalidAction
from app.ui import render
from app.repository import Repository
from app.save_tools import rewind_star
from test_bird_episode import play

@pytest.fixture(scope='module')
def c():return load_content()

def start():
    return State(started=True,screen='scene',scene='sunny_terrace',
        flags={f:True for f in ('episode10_complete','episode11_complete','episode12_complete','episode13_complete','seedlings_verified','return_path_known','garden_spring_flowing','seed_sample_taken')},
        visited=['star_vault','jar_hall','seed_reserve','service_descent'])

BACK=('move:back_shelter','move:back_terrace','move:back_beds','move:back_descent','move:back_waymark','move:back_pass','move:back_marker','move:back_cedars','move:back_gate','move:back_house','move:back_wall','move:enter_descent','move:descend_storage','move:enter_reserve')
FORWARD=('move:back_hall','move:back_descent','move:back_wall','move:enter_watcher','move:enter_gate','move:enter_cedars','move:enter_marker','move:enter_pass','move:enter_waymark','move:descend_valley','move:enter_beds','move:enter_terrace','move:enter_shelter','move:enter_bed','move:enter_plot')

def test_full_sowing_and_return(c,tmp_path):
    s=start()
    play(s,c,'move:enter_shelter','move:enter_bed')
    with pytest.raises(InvalidAction):apply(s,'event:prepare_bed',c)
    play(s,c,'move:back_shelter','move:enter_work','ui:inspect')
    assert s.flags['garden_tools_taken']
    journal=list(s.journal);apply(s,'ui:inspect',c);assert s.journal==journal
    play(s,c,'ui:scene','move:back_shelter','move:enter_leaves','ui:inspect','ui:scene','move:back_shelter','move:enter_bed','event:prepare_bed')
    with pytest.raises(InvalidAction):apply(s,'event:prepare_bed',c)
    play(s,c,*BACK)
    assert s.scene=='seed_reserve'
    apply(s,'event:take_main_seeds',c)
    with pytest.raises(InvalidAction):apply(s,'event:take_main_seeds',c)
    apply(s,'ui:inventory',c)
    assert c['copy']['interface']['Семена_для_сада'] in render(s,c).caption
    play(s,c,'ui:scene',*FORWARD,'event:sow_seeds')
    assert not s.flags.get('episode14_complete')
    with pytest.raises(InvalidAction):apply(s,'event:water_seeds',c)
    with pytest.raises(InvalidAction):apply(s,'event:sow_seeds',c)
    apply(s,'ui:inventory',c)
    assert c['copy']['interface']['Семена_для_сада'] not in render(s,c).caption
    play(s,c,'ui:scene','move:back_basin','ui:inspect','ui:scene','move:enter_plot','event:water_seeds')
    assert s.flags['episode14_complete']
    with pytest.raises(InvalidAction):apply(s,'event:water_seeds',c)
    repo=Repository(tmp_path/'sowing.sqlite3');repo.save(1,s);assert asdict(repo.get(1))==asdict(s)
    rolled=rewind_star(asdict(s),c)
    for f in ('garden_tools_taken','watering_can_taken','leaf_mould_known','main_bed_ready','main_seed_portion_taken','main_seeds_sown','episode14_complete'):assert not rolled['flags'].get(f)

def test_gates(c):
    s=start();s.flags.pop('episode13_complete')
    with pytest.raises(InvalidAction):apply(s,'move:enter_shelter',c)
    s.scene='seed_reserve'
    with pytest.raises(InvalidAction):apply(s,'event:take_main_seeds',c)
    s.scene='sowing_plot'
    with pytest.raises(InvalidAction):apply(s,'event:sow_seeds',c)

@pytest.mark.parametrize('stage',range(4))
def test_cards(c,stage):
    s=start()
    s.flags.update(garden_tools_taken=stage>0,watering_can_taken=stage>0,leaf_mould_known=stage>0,main_bed_ready=stage>0,main_seed_portion_taken=stage>0,main_seeds_sown=stage>1,episode14_complete=stage>2)
    for sid,scene in c['scenes'].items():
        if scene['step']<69 and sid not in ('seed_reserve','sunny_terrace'):continue
        s.scene=sid
        for screen in ('scene','inspect','hint','inventory','progress'):
            s.screen=screen;card=render(s,c)
            assert len(card.caption)<=1024
            assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
