from dataclasses import asdict
import pytest
from app.content import load_content
from app.engine import State, apply, InvalidAction
from app.repository import Repository
from app.ui import render

def test_epilogue_choices_preserve_progress(tmp_path):
    c=load_content()
    s=State(started=True,screen='scene',scene='dry_seed_store',flags={'new_seeds_collected':True,'new_store_checked':True})
    apply(s,'event:store_new_seeds',c)
    assert s.screen=='garden_bloom'
    for screen in ('garden_bloom','garden_fruit','garden_valley'):
        apply(s,'ui:'+screen,c)
        card=render(s,c)
        assert card.asset=='epilogue.'+screen
        assert len(card.caption)<=1024
    buttons=[b.text for row in card.keyboard.inline_keyboard for b in row]
    assert buttons==['Закончить игру','Побродить по миру']
    flags=dict(s.flags);items=dict(s.item_locations);turns=s.turns
    apply(s,'ui:garden_goodbye',c)
    assert s.screen=='garden_goodbye'
    repo=Repository(tmp_path/'epilogue.sqlite3');repo.save(1,s)
    assert asdict(repo.get(1))==asdict(s)
    apply(s,'ui:scene',c)
    assert s.scene=='dry_seed_store' and s.flags==flags
    assert s.turns==turns and s.item_locations==items
    apply(s,'ui:menu',c)
    assert any(b.callback_data.endswith(':ui:garden_bloom') for row in render(s,c).keyboard.inline_keyboard for b in row)
    apply(s,'ui:garden_bloom',c)
    assert s.screen=='garden_bloom'

@pytest.mark.parametrize('screen',['garden_bloom','garden_fruit','garden_valley','garden_goodbye'])
def test_epilogue_requires_completed_garden(screen):
    c=load_content();s=State(started=True,screen='scene')
    with pytest.raises(InvalidAction):apply(s,'ui:'+screen,c)
