import pytest

from app.content import load_content
from app.engine import State, apply, scene_view
from app.repository import Repository


def test_return_image_only_after_reentry_and_survives_save(tmp_path):
    content = load_content()
    content['scenes']['road_end']['return_media'] = 'scene.stream'
    state = State()
    apply(state, 'new', content)
    assert scene_view(state, content)['media'] == 'scene.road_end'
    apply(state, 'move:enter_house', content)
    assert not state.returning
    apply(state, 'move:exit_house', content)
    assert state.returning
    assert scene_view(state, content)['media'] == 'scene.stream'
    apply(state, 'ui:inspect', content)
    repository = Repository(tmp_path / 'saves.sqlite3')
    repository.save(1, state)
    restored = repository.get(1)
    assert scene_view(restored, content)['media'] == 'scene.stream'
    apply(restored, 'ui:confirm', content)
    apply(restored, 'reset', content)
    assert not restored.returning
    assert scene_view(restored, content)['media'] == 'scene.road_end'


def test_state_return_override_fallback_and_darkness():
    content = load_content()
    state = State(started=True, scene='debris_grotto', returning=True)
    state.item_locations.update(lamp='inventory', bird='gone', cage='inventory')
    state.item_states['lamp']['power'] = True
    variant = next(v for v in content['scenes']['debris_grotto']['variants'] if v['id'] == '007.04')
    assert scene_view(state, content)['media'] == 'scene.debris_grotto.empty'
    variant['media'] = 'scene.king_hall.open'
    assert scene_view(state, content)['media'] == 'scene.king_hall.open'
    variant['return_media'] = 'scene.bird_grotto.empty'
    assert scene_view(state, content)['media'] == 'scene.bird_grotto.empty'
    state.returning = False
    assert scene_view(state, content)['media'] == 'scene.king_hall.open'
    state.returning = True
    state.item_states['lamp']['power'] = False
    assert scene_view(state, content)['media'] == 'scene.darkness'


@pytest.mark.parametrize('variant', [False, True])
def test_unknown_return_image_rejected(variant):
    initial = load_content()
    manifest = initial['_manifest']
    scene = manifest['scenes']['debris_grotto']
    target = scene['variants'][0] if variant else scene
    target['return_media'] = 'missing-image'
    with pytest.raises(ValueError, match='return_media|return media'):
        load_content(manifest, initial['_text_sources'])
