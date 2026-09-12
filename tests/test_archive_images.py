import pytest
from app.content import load_content
from app.engine import State, scene_view


@pytest.mark.parametrize('sid,flag,asset', [
    ('flooded_threshold','water_diverted','scene.flooded_threshold.dry'),
    ('sluice_room','water_diverted','scene.sluice_room.diverted'),
    ('keepers_archive','archive_shortcut','scene.keepers_archive.open'),
])
def test_state_images_and_darkness(sid, flag, asset):
    c=load_content()
    s=State(scene=sid,returning=True)
    s.item_locations['lamp']='inventory'
    s.item_states['lamp']['power']=True
    assert scene_view(s,c)['media']==c['scenes'][sid]['media']
    s.flags[flag]=True
    assert scene_view(s,c)['media']==asset
    s.flags['episode6_complete']=True
    assert scene_view(s,c)['media']==asset
    s.item_states['lamp']['power']=False
    assert scene_view(s,c)['media']=='scene.darkness'
