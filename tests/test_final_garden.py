from dataclasses import asdict
import pytest
from app.content import load_content
from app.engine import State, apply, InvalidAction
from app.repository import Repository
from app.save_tools import rewind_star
from app.ui import render
from test_bird_episode import play

@pytest.fixture(scope='module')
def c():return load_content()

def start():return State(started=True,screen='scene',scene='sowing_plot',flags={'episode14_complete':True},visited=['star_vault','sowing_plot'])

@pytest.mark.parametrize('reverse',[False,True])
def test_care_harvest_ending(c,tmp_path,reverse):
    s=start();play(s,c,'move:enter_lodging')
    with pytest.raises(InvalidAction):apply(s,'event:tend_new_garden',c)
    play(s,c,'move:enter_round')
    with pytest.raises(InvalidAction):apply(s,'move:enter_shoots',c)
    play(s,c,'move:back_lodging','move:enter_calendar','ui:inspect','ui:scene','move:back_lodging')
    tasks=[('move:enter_screens','event:set_shade'),('move:enter_drain','event:clear_rain')]
    if reverse:tasks.reverse()
    for enter,event in tasks:
        play(s,c,enter)
        with pytest.raises(InvalidAction):apply(s,event,c)
        play(s,c,'ui:inspect','ui:scene',event)
        with pytest.raises(InvalidAction):apply(s,event,c)
        play(s,c,'move:back_lodging')
    play(s,c,'event:tend_new_garden')
    with pytest.raises(InvalidAction):apply(s,'event:tend_new_garden',c)
    play(s,c,'move:enter_round','move:enter_shoots')
    with pytest.raises(InvalidAction):apply(s,'move:enter_lower',c)
    play(s,c,'ui:inspect','ui:scene','move:enter_lower','move:enter_seasons')
    assert s.flags['episode15_complete']
    with pytest.raises(InvalidAction):apply(s,'event:grow_season',c)
    with pytest.raises(InvalidAction):apply(s,'move:enter_living',c)
    play(s,c,'move:back_lower')
    entries=['move:enter_record','move:enter_store','move:enter_linen']
    if reverse:entries.reverse()
    for enter in entries:play(s,c,enter,'ui:inspect','ui:scene','move:back_lower')
    play(s,c,'move:enter_seasons','event:grow_season')
    with pytest.raises(InvalidAction):apply(s,'event:grow_season',c)
    play(s,c,'move:enter_living')
    with pytest.raises(InvalidAction):apply(s,'event:collect_new_seeds',c)
    play(s,c,'ui:inspect','ui:scene','event:collect_new_seeds')
    assert not s.flags.get('episode16_complete')
    apply(s,'ui:inventory',c);assert c['copy']['interface']['Новый_сбор'] in render(s,c).caption
    play(s,c,'ui:scene','move:back_seasons','move:back_lower','move:enter_store','event:store_new_seeds')
    assert s.flags['episode16_complete']
    with pytest.raises(InvalidAction):apply(s,'event:store_new_seeds',c)
    apply(s,'ui:inventory',c);assert c['copy']['interface']['Новый_сбор'] not in render(s,c).caption
    apply(s,'ui:progress',c);assert c['copy']['interface']['Шестнадцатая_цель_выполнена'] in render(s,c).caption
    repo=Repository(tmp_path/'final.sqlite3');repo.save(1,s);assert asdict(repo.get(1))==asdict(s)
    rolled=rewind_star(asdict(s),c)
    for f in ('new_garden_grown','episode15_complete','garden_season_passed','new_seeds_collected','episode16_complete'):assert not rolled['flags'].get(f)
    play(s,c,'ui:scene','move:back_lower','move:back_shoots','move:back_round','move:back_lodging','move:back_plot')
    assert s.scene=='sowing_plot'

def test_no_early_entry(c):
    s=start();s.flags.clear()
    with pytest.raises(InvalidAction):apply(s,'move:enter_lodging',c)

@pytest.mark.parametrize('stage',range(5))
def test_final_cards(c,stage):
    s=start()
    for f in ('garden_care_known','shade_slots_seen','rain_outlet_seen','garden_shade_ready','garden_drain_ready','new_garden_grown'):s.flags[f]=stage>0
    for f in ('episode15_complete','harvest_method_known','new_store_checked','linen_bags_taken'):s.flags[f]=stage>1
    for f in ('garden_season_passed','ripe_pods_seen','new_seeds_collected'):s.flags[f]=stage>2
    s.flags['episode16_complete']=stage>3
    for sid,scene in c['scenes'].items():
        if scene['step']<64:continue
        s.scene=sid
        for screen in ('scene','inspect','hint','inventory','progress'):
            s.screen=screen;card=render(s,c)
            assert len(card.caption)<=1024,(sid,screen,stage)
            assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
