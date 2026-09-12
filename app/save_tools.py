"""Offline save maintenance. Stop the bot before applying changes."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from .content import ROOT, load_content


def rewind_star(snapshot, content, map_studied=False):
    result = deepcopy(snapshot)
    if 'star_vault' not in result.get('visited', []):
        raise ValueError('Звёздный свод ещё не посещён: эта команда только откатывает прогресс.')
    later = {sid for sid, scene in content['scenes'].items() if scene['step'] > 20}
    flags = result.setdefault('flags', {})
    for sid in later:
        discovery = content['scenes'][sid].get('inspect_discovery')
        if discovery:
            flags.pop(discovery['flag'], None)
        for action in content['scenes'][sid]['actions']:
            name = action.get('effects', {}).get('flag')
            if name:
                flags.pop(name, None)
    flags.pop('episode5_complete', None)
    marker = content['copy']['events']['Открыто_место'] + content['scenes']['star_vault']['title']
    journal = result.get('journal', [])
    if marker in journal:
        index = journal.index(marker)
        after = journal[index + 1:]
        # The balcony shortcut can be discovered either before or after visiting the vault.
        shortcut = content['scenes']['high_balcony']['messages']['shortcut']
        if shortcut in after:
            flags.pop('wind_shortcut', None)
        result['journal'] = journal[:index + 1]
    else:
        # Old journal entries are capped at 20, so don't invent a lost history.
        result['journal'] = [marker]
        flags.pop('wind_shortcut', None)
    if map_studied:
        flags['episode5_complete'] = True
        result['journal'].append(content['scenes']['star_vault']['messages']['complete'])
    result['visited'] = [sid for sid in result['visited'] if sid not in later]
    for item, location in result.get('item_locations', {}).items():
        if location in later:
            result['item_locations'][item] = 'inventory'
    result.update(scene='star_vault', screen='scene', started=True, returning=False,
                  notice='', hint_level=0, revision=uuid4().hex[:12])
    return result


def choose_save(db, user_id=None):
    rows = db.execute('SELECT user_id,snapshot FROM saves' +
                      (' WHERE user_id=?' if user_id is not None else ''),
                      (user_id,) if user_id is not None else ()).fetchall()
    if len(rows) != 1:
        raise ValueError('Нужно ровно одно сохранение. При нескольких игроках укажите --user-id.')
    return rows[0]


def commit_change(db, user_id, original, replacement, backup_dir):
    db.execute('BEGIN IMMEDIATE')
    try:
        current = choose_save(db, user_id)[1]
        if current != original:
            raise ValueError('Сохранение изменилось. Остановите бота и повторите команду.')
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        backup = backup_dir / f'save-{user_id}-{stamp}-{uuid4().hex[:8]}.json'
        with backup.open('x', encoding='utf-8') as file:
            json.dump({'user_id': user_id, 'snapshot': json.loads(original)}, file, ensure_ascii=False, indent=2)
        db.execute('UPDATE saves SET snapshot=? WHERE user_id=?',
                   (json.dumps(replacement, ensure_ascii=False), user_id))
        db.commit()
        return backup
    except Exception:
        db.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['rewind-star', 'restore'])
    parser.add_argument('--user-id', type=int)
    parser.add_argument('--map-studied', action='store_true')
    parser.add_argument('--file', type=Path, help='JSON backup for restore')
    parser.add_argument('--apply', action='store_true', help='Write changes; stop bot first. Default: preview.')
    args = parser.parse_args()
    target = (ROOT / 'data/prototype.sqlite3').resolve()
    mode = 'rw' if args.apply else 'ro'
    with sqlite3.connect(target.as_uri() + '?mode=' + mode, uri=True) as db:
        restore = None
        if args.action == 'restore':
            if args.file is None:
                parser.error('Для restore нужен --file с резервной копией.')
            restore = json.loads(args.file.read_text(encoding='utf-8'))
            if args.user_id is not None and args.user_id != restore['user_id']:
                parser.error('Резервная копия принадлежит другому игроку.')
            args.user_id = restore['user_id']
        uid, raw = choose_save(db, args.user_id)
        before = json.loads(raw)
        after = deepcopy(restore['snapshot']) if restore else rewind_star(before, load_content(), args.map_studied)
        after['revision'] = uuid4().hex[:12]
        # Keep the current Telegram card reference rather than a stale backup reference.
        after['message_id'] = before.get('message_id')
        print(f"Игрок: {uid}. Место: {before['scene']} -> {after['scene']}.")
        print('Карта изучена:', bool(after.get('flags', {}).get('episode5_complete')))
        print('Ходы:', after['turns'])
        if args.apply:
            backup = commit_change(db, uid, raw, after, ROOT / 'data/backups')
            print('Сохранение обновлено. Резервная копия:', backup)
        else:
            print('Это предварительный просмотр. Для записи остановите бота и добавьте --apply.')


if __name__ == '__main__':
    main()
