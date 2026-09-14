from dataclasses import asdict
import pytest
from app.content import load_content
from app.engine import State, apply, InvalidAction
from app.ui import render
from app.repository import Repository
from app.save_tools import rewind_star
from test_bird_episode import play

@pytest.fixture(scope='module')
def content(): return load_content()

def start():
    return State(started=True,screen='scene',scene='forest_waymark',
                 flags={'episode12_complete':True},visited=['star_vault','forest_waymark'])

@pytest.mark.parametrize('soil_first',[False,True])
def test_garden_route(content,tmp_path,soil_first):
    s=start(); c=content
    play(s,c,'move:descend_valley','move:enter_beds','move:enter_terrace','ui:inspect')
    assert not s.flags.get('episode13_complete')
    play(s,c,'ui:scene','move:back_beds')
    if soil_first:
        play(s,c,'move:enter_soil','ui:inspect','ui:scene','move:back_beds')
    play(s,c,'move:enter_spring')
    with pytest.raises(InvalidAction): apply(s,'event:clear_outlet',c)
    play(s,c,'move:enter_channel','ui:inspect')
    assert not s.flags.get('garden_water_checked')
    play(s,c,'ui:scene','move:back_spring','ui:inspect','ui:scene','event:clear_outlet')
    assert s.flags['garden_spring_flowing']
    with pytest.raises(InvalidAction): apply(s,'event:clear_outlet',c)
    play(s,c,'move:enter_channel','ui:inspect')
    assert s.flags['garden_water_checked']
    play(s,c,'ui:scene','move:enter_terrace','ui:inspect')
    assert bool(s.flags.get('episode13_complete')) == soil_first
    if not soil_first:
        play(s,c,'ui:scene','move:back_beds','move:enter_soil','ui:inspect','ui:scene','move:back_beds','move:enter_terrace','ui:inspect')
    assert s.flags['episode13_complete']
    journal=list(s.journal); apply(s,'ui:inspect',c); assert journal==s.journal
    repo=Repository(tmp_path/'garden.sqlite3'); repo.save(1,s)
    assert asdict(repo.get(1))==asdict(s)
    apply(s,'ui:progress',c)
    assert c['copy']['interface']['Четырнадцатая_цель'] in render(s,c).caption
    rolled=rewind_star(asdict(s),c)
    assert not any(rolled['flags'].get(f) for f in ('garden_soil_checked','garden_water_checked','garden_spring_flowing','spring_blockage_seen','episode13_complete'))
    play(s,c,'ui:scene','move:back_beds','move:back_descent','move:back_waymark')
    assert s.scene=='forest_waymark'

def test_entry_requires_waymark(content):
    s=start();s.flags.clear()
    with pytest.raises(InvalidAction):apply(s,'move:descend_valley',content)

def test_terrace_guidance_tracks_remaining_check(content):
    s=start();s.scene='sunny_terrace'
    s.flags.update(garden_soil_checked=True,garden_spring_flowing=True)
    apply(s,'ui:inspect',content)
    caption=render(s,content).caption
    assert 'Почва у орешника проверена' in caption
    assert 'перейдите в каменный водовод' in caption
    assert not s.flags.get('episode13_complete')
    play(s,content,'ui:scene','move:back_channel','ui:inspect','ui:scene','move:enter_terrace','ui:inspect')
    assert s.flags['episode13_complete']
    assert 'садовый навес' in render(s,content).caption
    assert 'ещё не проверена' not in render(s,content).caption

@pytest.mark.parametrize('stage',[False,True])
def test_cards(content,stage):
    s=start()
    for f in ('garden_soil_checked','garden_water_checked','garden_spring_flowing','spring_blockage_seen','episode13_complete'):s.flags[f]=stage
    for sid,scene in content['scenes'].items():
        if scene['step']<63:continue
        s.scene=sid
        for screen in ('scene','inspect','hint','progress'):
            s.screen=screen;card=render(s,content)
            assert len(card.caption)<=1024
            assert card.asset!='scene.darkness'
            assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
