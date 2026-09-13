from dataclasses import asdict
import json
import pytest
from app.content import load_content
from app.engine import State, apply, scene_view, scene_actions, InvalidAction
from app.repository import Repository
from app.save_tools import rewind_star
from app.ui import render
from test_bird_episode import play

SCENES = ('tower_stairs', 'eye_tower', 'counterweight', 'eye_gallery', 'eye_ring', 'valley_terrace')

def expedition():
    c = load_content()
    s = State(started=True, screen='scene', scene='first_shoot',
              visited=['star_vault', 'hidden_garden', 'first_shoot'],
              flags={'episode6_complete': True})
    s.item_locations['lamp'] = 'inventory'
    s.item_states['lamp']['power'] = True
    return s, c

def test_full_route_gates_daylight_save_rewind(tmp_path):
    s, c = expedition()
    play(s,c,'move:back_garden')
    with pytest.raises(InvalidAction): apply(s,'move:enter_tower_stairs',c)
    play(s,c,'move:enter_pavilion','ui:inspect','ui:scene','move:back_garden',
         'move:enter_tower_stairs','move:climb_tower','move:climb_gallery')
    with pytest.raises(InvalidAction): apply(s,'move:climb_eye',c)
    apply(s,'event:turn_winch',c)
    assert not s.flags.get('tower_eye_open')
    play(s,c,'move:back_tower','move:enter_weight','ui:inspect')
    assert s.flags['tower_signs_read']
    journal = list(s.journal)
    apply(s,'ui:inspect',c)
    assert s.journal == journal
    play(s,c,'ui:scene')
    turns = s.turns
    apply(s,'event:raise_weight',c)
    assert s.turns == turns+1 and s.journal == journal
    assert render(s,c).caption.split('\n\n',1)[1] == c['scenes']['counterweight']['messages']['wrong']
    play(s,c,'event:lower_weight')
    assert scene_view(s,c)['media'] == 'scene.counterweight.ready'
    play(s,c,'move:back_tower','move:climb_gallery','event:turn_winch')
    assert render(s,c).caption.split('\n\n',1)[1] == c['scenes']['eye_gallery']['messages']['opened']
    with pytest.raises(InvalidAction): apply(s,'event:turn_winch',c)
    play(s,c,'ui:item','lamp_off','drop_lamp','move:climb_eye','move:climb_terrace','ui:inspect')
    assert s.flags['episode8_complete']
    journal = list(s.journal)
    apply(s,'ui:inspect',c)
    assert s.journal == journal
    apply(s,'ui:hint',c)
    assert c['scenes']['valley_terrace']['hints_open'][0] in render(s,c).caption
    repo = Repository(tmp_path/'tower.sqlite3')
    repo.save(1,s)
    restored = repo.get(1)
    assert restored.flags == s.flags and restored.content_version == '0.13.0'
    play(s,c,'ui:scene','move:back_ring','move:back_gallery')
    assert s.returning and scene_view(s,c)['media'] == 'scene.eye_gallery.open'
    assert not scene_view(s,c)['dark']
    # Silver dropped in the sunlit gallery remains collectible without a lamp.
    s.item_locations['silver'] = s.scene
    apply(s,'take_silver',c)
    assert s.item_locations['silver'] == 'inventory'
    play(s,c,'take_lamp','move:back_tower','move:enter_weight')
    assert scene_view(s,c)['media'] == 'scene.darkness'
    play(s,c,'ui:item','lamp_on','ui:scene')
    assert scene_view(s,c)['media'] == 'scene.counterweight.ready'
    rolled = rewind_star(asdict(s), c)
    assert not set(SCENES).intersection(rolled['visited'])
    assert not any(rolled['flags'].get(f) for f in ('tower_signs_read','tower_weight_ready','tower_eye_open','episode8_complete'))

def test_darkness_prevents_mechanism_and_discovery():
    s,c = expedition();s.scene = 'counterweight'
    s.item_states['lamp']['power'] = False
    play(s,c,'ui:inspect','ui:scene','event:lower_weight')
    assert not s.flags.get('tower_signs_read') and not s.flags.get('tower_weight_ready')
    s.scene = 'eye_gallery';s.flags['tower_weight_ready'] = True
    apply(s,'event:turn_winch',c)
    assert not s.flags.get('tower_eye_open')
    assert scene_view(s,c)['media'] == 'scene.darkness'

def test_version_080_migration_preserves_progress(tmp_path):
    s,c = expedition();s.flags['episode7_complete'] = True
    old = asdict(s);old['content_version'] = '0.8.0'
    repo = Repository(tmp_path/'old.sqlite3')
    with repo.connect() as db:
        db.execute('INSERT INTO saves VALUES (?,?)',(1,json.dumps(old)))
    loaded = repo.get(1)
    result = asdict(loaded);result['content_version']='0.8.0'
    assert result == old

@pytest.mark.parametrize('sid', SCENES)
@pytest.mark.parametrize('lit', [False, True])
@pytest.mark.parametrize('opened', [False, True])
def test_cards_and_daylight(sid,lit,opened):
    s,c = expedition();s.scene = sid;s.returning = True
    s.flags.update(episode7_complete=True,tower_weight_ready=opened,tower_eye_open=opened,episode8_complete=opened)
    s.item_states['lamp']['power'] = lit
    for screen in ('scene','inspect','hint','inventory','progress'):
        s.screen = screen
        card = render(s,c)
        assert len(card.caption) <= 1024
        assert all(len(b.callback_data.encode())<=64 for row in card.keyboard.inline_keyboard for b in row)
        dark = not lit and sid not in ('eye_ring','valley_terrace') and not (sid=='eye_gallery' and opened)
        assert (card.asset == 'scene.darkness') == dark

def test_daylight_variant_validation():
    c=load_content();g=c['_manifest']
    g['scenes']['eye_gallery']['variants'][-1]['daylight']='yes'
    with pytest.raises(ValueError, match='daylight'):load_content(g)
