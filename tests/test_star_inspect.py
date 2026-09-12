import pytest
from app.content import load_content
from app.engine import State, apply, scene_actions, InvalidAction


def test_star_inspect_and_independent_stairs():
    c=load_content()
    s=State(started=True,scene='star_vault',screen='scene',visited=['star_vault','high_balcony','wind_gallery'])
    s.item_locations['lamp']='inventory'
    apply(s,'ui:inspect',c)
    assert not s.flags.get('episode5_complete')
    s.item_states['lamp']['power']=True
    apply(s,'ui:inspect',c)
    assert s.flags['episode5_complete']
    journal=list(s.journal);turns=s.turns
    apply(s,'ui:inspect',c)
    assert s.journal==journal and s.turns==turns
    assert 'study_stars' not in {a['id'] for a in scene_actions(s,c)}
    apply(s,'ui:scene',c)
    apply(s,'move:back_balcony',c)
    ids={a['id'] for a in scene_actions(s,c)}
    assert 'trace_stairs' in ids and 'enter_constellation' in ids
    assert 'descend_shortcut' not in ids
    with pytest.raises(InvalidAction): apply(s,'move:descend_shortcut',c)
    apply(s,'event:trace_stairs',c)
    ids={a['id'] for a in scene_actions(s,c)}
    assert 'descend_shortcut' in ids and 'trace_stairs' not in ids
    apply(s,'move:descend_shortcut',c)
    assert s.scene=='wind_gallery'
