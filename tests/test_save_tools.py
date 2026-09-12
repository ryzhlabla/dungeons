import json
import sqlite3
from dataclasses import asdict

import pytest

from app.content import load_content
from app.engine import State
from app.save_tools import rewind_star, commit_change


def test_rewind_removes_later_progress_and_keeps_earlier_items():
    c = load_content()
    marker = c['copy']['events']['Открыто_место'] + c['scenes']['star_vault']['title']
    s = asdict(State(started=True, scene='dry_channel', turns=149,
                     visited=['high_balcony', 'star_vault', 'dry_channel'],
                     flags={'episode4_complete':True, 'episode5_complete':True,
                            'water_diverted':True, 'water_signs_read':True, 'wind_shortcut':True},
                     journal=['earlier', marker, c['scenes']['high_balcony']['messages']['shortcut']]))
    s['item_locations'].update(lamp='dry_channel', silver='treasury')
    r = rewind_star(s, c)
    assert r['scene'] == 'star_vault' and r['turns'] == 149
    assert r['flags'] == {'episode4_complete':True}
    assert r['visited'] == ['high_balcony','star_vault']
    assert r['journal'] == ['earlier',marker]
    assert r['item_locations']['lamp'] == 'inventory'
    assert r['item_locations']['silver'] == 'treasury'
    assert s['scene'] == 'dry_channel'
    assert rewind_star(s,c,True)['flags']['episode5_complete']


def test_backup_is_exact_and_concurrent_change_rejected(tmp_path):
    with sqlite3.connect(tmp_path/'s.sqlite3') as db:
        db.execute('CREATE TABLE saves(user_id INTEGER PRIMARY KEY,snapshot TEXT)')
        raw = json.dumps(asdict(State()))
        db.execute('INSERT INTO saves VALUES(1,?)',(raw,))
        db.commit()
        after = asdict(State(scene='star_vault'))
        backup = commit_change(db,1,raw,after,tmp_path/'backups')
        assert json.loads(backup.read_text(encoding='utf-8'))['snapshot'] == json.loads(raw)
        with pytest.raises(ValueError,match='изменилось'):
            commit_change(db,1,raw,after,tmp_path/'backups')
        assert len(list((tmp_path/'backups').glob('*.json'))) == 1
