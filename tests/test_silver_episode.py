import json
from dataclasses import asdict
import pytest
from app.content import load_content
from app.engine import State, apply, InvalidAction, scene_view
from app.repository import Repository
from app.ui import render
from test_water_episode import reach_gallery
from test_bird_episode import play


def reach_silver():
    s,c=reach_gallery()
    play(s,c,'move:enter_echo','event:study_ledge','move:back_gallery','move:follow_ledge','event:study_lake','move:enter_calcite','move:enter_silver')
    return s,c


def test_treasure_full_route_store_and_revisit(tmp_path):
    s,c=reach_silver()
    play(s,c,'take_silver')
    assert s.flags['silver_found'] and s.item_locations['silver']=='inventory'
    assert scene_view(s,c)['media']=='scene.silver_grotto.empty'
    with pytest.raises(InvalidAction): apply(s,'take_silver',c)
    play(s,c,'ui:inventory')
    assert c['copy']['silver']['title'] in render(s,c).caption
    play(s,c,'ui:silver','drop_silver')
    assert scene_view(s,c)['media']=='scene.silver_grotto'
    play(s,c,'take_silver')
    assert s.journal.count(c['copy']['silver']['found_journal'])==1
    play(s,c,'move:back_calcite','move:back_lake','move:back_gallery','move:back_king','move:back_bird','move:back_debris','move:back_first_hall','move:back_entrance','move:climb_out','move:back_stream','move:return_road','move:enter_house')
    play(s,c,'ui:silver','drop_silver')
    assert not s.flags.get('episode4_complete')
    play(s,c,'take_silver','event:store_silver')
    assert s.item_locations['silver']=='treasury' and s.flags['episode4_complete']
    assert len(render(s,c).caption)<=1024
    for action in ('event:store_silver','take_silver','ui:silver'):
        with pytest.raises(InvalidAction): apply(s,action,c)
    repo=Repository(tmp_path/'save.sqlite3'); repo.save(1,s); s=repo.get(1)
    play(s,c,'move:exit_house','move:enter_house','ui:inspect')
    assert 'на хранении' in render(s,c).caption
    play(s,c,'ui:progress')
    assert 'Доставлено в дом: 1 / 1' in render(s,c).caption
    play(s,c,'ui:hint')
    assert 'Четвёртый эпизод завершён' in render(s,c).caption
    play(s,c,'ui:confirm','reset')
    assert s.item_locations['silver']=='silver_grotto' and not s.flags


def test_drop_darkness_recovery_and_hint():
    s,c=reach_silver()
    play(s,c,'ui:item','lamp_off','ui:scene')
    with pytest.raises(InvalidAction): apply(s,'take_silver',c)
    assert all(b.callback_data.split(':',2)[2]!='take_silver' for row in render(s,c).keyboard.inline_keyboard for b in row)
    play(s,c,'ui:item','lamp_on','ui:scene','take_silver','move:back_calcite','ui:silver','drop_silver','move:back_lake','ui:hint')
    assert 'Кальцитовый проход' in render(s,c).caption
    play(s,c,'ui:scene','move:enter_calcite','take_silver','move:enter_silver')
    assert 'плита пуста' in scene_view(s,c)['text']
    assert s.returning


def test_04_save_upgrade(tmp_path):
    repo=Repository(tmp_path/'save.sqlite3')
    old=asdict(State(started=True,scene='underground_lake',screen='scene',flags={'episode3_complete':True}))
    old['content_version']='0.4.0'; old['item_locations'].pop('silver')
    with repo.connect() as db: db.execute('INSERT INTO saves VALUES (?,?)',(1,json.dumps(old)))
    s=repo.get(1)
    assert s.content_version=='0.10.0' and s.item_locations['silver']=='silver_grotto'
    assert s.flags==old['flags'] and s.scene==old['scene']


@pytest.mark.parametrize('location',['silver_grotto','inventory','calcite_passage','treasury'])
@pytest.mark.parametrize('lit',[False,True])
def test_silver_state_screens(location,lit):
    c=load_content(); s=State(started=True,scene='silver_grotto',returning=True)
    s.item_locations.update(silver=location,lamp='inventory')
    s.item_states['lamp']['power']=lit
    s.flags.update(silver_found=location!='silver_grotto',episode4_complete=location=='treasury')
    for screen in ('scene','inspect','inventory','hint','progress','silver'):
        s.screen=screen; card=render(s,c)
        assert len(card.caption)<=1024
        assert card.asset==('scene.darkness' if not lit else ('scene.silver_grotto' if location=='silver_grotto' else 'scene.silver_grotto.empty'))
