import json
from dataclasses import asdict
import pytest
from app.content import load_content
from app.engine import State, apply, scene_view, scene_actions, InvalidAction
from app.repository import Repository
from app.save_tools import rewind_star
from app.ui import render
from test_bird_episode import play

SCENES=('root_path','stone_tree','dew_alcove','mirror_ledge','hidden_garden','first_shoot')

def expedition():
 c=load_content()
 s=State(started=True,scene='underground_lake',screen='scene',
         visited=['star_vault','underground_lake'],flags={'episode6_complete':True,'episode5_complete':True,'episode4_complete':True})
 s.item_locations.update(lamp='inventory',silver='treasury')
 s.item_states['lamp']['power']=True
 return s,c

def test_full_garden_route_save_and_return(tmp_path):
 s,c=expedition()
 play(s,c,'move:enter_roots','move:enter_tree','event:try_leaf')
 assert not s.flags.get('garden_gate_open')
 with pytest.raises(InvalidAction): apply(s,'move:enter_garden',c)
 play(s,c,'move:enter_dew','ui:inspect')
 assert s.flags['root_signs_read']
 journal=list(s.journal);turns=s.turns
 apply(s,'ui:inspect',c)
 assert s.journal==journal and s.turns==turns
 play(s,c,'ui:scene','move:back_tree','move:enter_mirror')
 journal=list(s.journal);turns=s.turns
 play(s,c,'event:aim_crown','event:aim_crown')
 assert s.journal==journal and s.turns==turns+2
 assert render(s,c).caption.split('\n\n',1)[1]==c['scenes']['mirror_ledge']['messages']['wrong']
 play(s,c,'event:aim_roots','move:back_tree')
 assert scene_view(s,c)['media']=='scene.stone_tree.lit'
 assert not s.flags.get('garden_gate_open')
 play(s,c,'event:press_leaf')
 assert scene_view(s,c)['media']=='scene.stone_tree.open'
 play(s,c,'move:enter_garden','move:enter_pavilion','ui:inspect')
 assert s.flags['episode7_complete']
 assert render(s,c).caption.count(c['scenes']['first_shoot']['messages']['discovery'])==1
 journal=list(s.journal)
 apply(s,'ui:inspect',c)
 assert s.journal==journal
 repo=Repository(tmp_path/'save.sqlite3');repo.save(1,s);s=repo.get(1)
 assert s.flags['episode7_complete']
 play(s,c,'ui:scene','move:back_garden','move:back_tree')
 assert s.returning and scene_view(s,c)['media']=='scene.stone_tree.open'
 assert 'press_leaf' not in {a['id'] for a in scene_actions(s,c)}
 assert s.item_locations['silver']=='treasury'
 r=rewind_star(asdict(s),c)
 assert not any(r['flags'].get(f) for f in ('root_signs_read','root_beam','garden_gate_open','episode7_complete'))
 assert not set(r['visited']).intersection(SCENES)
 play(s,c,'ui:confirm','reset')
 assert not s.flags

def test_gate_darkness_and_lamp_recovery():
 s,c=expedition();s.flags.pop('episode6_complete')
 with pytest.raises(InvalidAction):apply(s,'move:enter_roots',c)
 s.flags['episode6_complete']=True
 s.item_states['lamp']['power']=False
 apply(s,'move:enter_roots',c);assert s.scene=='underground_lake'
 s.item_states['lamp']['power']=True
 play(s,c,'move:enter_roots','move:enter_tree','move:enter_mirror','ui:item','drop_lamp')
 s.item_states['lamp']['power']=False
 apply(s,'event:aim_roots',c);assert not s.flags.get('root_beam')
 play(s,c,'move:back_tree','move:back_roots','move:back_lake','move:enter_roots','move:enter_tree','move:enter_mirror','take_lamp')
 play(s,c,'ui:item','lamp_on','ui:scene','event:aim_roots')
 assert s.flags['root_beam'] and not s.flags.get('root_signs_read')

@pytest.mark.parametrize('sid',SCENES)
@pytest.mark.parametrize('lit',[True,False])
@pytest.mark.parametrize('stage',[0,1,2])
def test_cards_states_and_returns(sid,lit,stage):
 s,c=expedition();s.scene=sid;s.returning=True
 s.flags.update(root_beam=stage>0,garden_gate_open=stage>1,episode7_complete=stage>1)
 s.item_states['lamp']['power']=lit
 for screen in ('scene','inspect','hint','inventory','progress'):
  s.screen=screen;card=render(s,c)
  assert len(card.caption)<=1024
  if not lit:assert card.asset=='scene.darkness'
  assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)

def test_old_save_upgrade_and_dark_inspection(tmp_path):
 s,c=expedition();old=asdict(s);old['content_version']='0.7.0'
 repo=Repository(tmp_path/'save.sqlite3')
 with repo.connect() as db:db.execute('INSERT INTO saves VALUES(?,?)',(1,json.dumps(old)))
 restored=repo.get(1)
 assert restored.content_version=='0.10.0' and restored.flags==s.flags
 assert restored.item_locations==s.item_locations
 for sid,f in [('dew_alcove','root_signs_read'),('first_shoot','episode7_complete')]:
  restored.scene=sid;restored.item_states['lamp']['power']=False
  apply(restored,'ui:inspect',c)
  assert not restored.flags.get(f)
