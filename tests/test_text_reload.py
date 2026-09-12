import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import Chat, Message, PhotoSize, Update, User

from app.bot import create_dispatcher
from app.catalog import build_catalog, write_catalog
from app.content import load_content
from app.engine import State
from app.media import Media
from app.repository import Repository
from app.text_reload import TextContentSource, env_flag


@pytest.fixture
def editable(tmp_path):
    initial = load_content()
    for path, value in initial["_text_sources"].items():
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return initial, tmp_path


def edit(root, relative, key, value):
    target = root / relative
    data = json.loads(target.read_text(encoding="utf-8"))
    data[key] = value
    target.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


SCENE = "texts/scenes/007_Грот_обломков.json"


def test_dev_reload_updates_return_variant_buttons_and_map(editable):
    initial, root = editable
    output = root / "map.md"
    source = TextContentSource(initial, enabled=True, root=root,
                               on_reload=lambda data: write_catalog(data, output))
    source.get()
    edit(root, SCENE, "text_released", "В соседнем гроте теперь совершенно тихо.")
    edit(root, SCENE, "buttons_quiet", {"enter_bird_grotto": "Пройти в тихий грот"})
    current = source.get()
    assert current is not initial
    assert current["scenes"]["debris_grotto"]["text_released"] == "В соседнем гроте теперь совершенно тихо."
    assert "Пройти в тихий грот" in output.read_text(encoding="utf-8")
    assert "В соседнем гроте теперь совершенно тихо." in output.read_text(encoding="utf-8")
    assert initial["scenes"]["debris_grotto"]["text_released"] != current["scenes"]["debris_grotto"]["text_released"]
    assert source.get() is current  # Unchanged files reuse validated snapshot.


def test_production_does_not_read_or_reload_text_files(editable):
    initial, root = editable
    source = TextContentSource(initial, enabled=False, root=root / "does-not-exist",
                               on_reload=lambda _: pytest.fail("Map must not be regenerated"))
    assert source.get() is initial
    edit(root, SCENE, "text", "Правка для разработки")
    assert source.get() is initial


def test_invalid_json_missing_file_and_repair_keep_last_valid_snapshot(editable):
    initial, root = editable
    source = TextContentSource(initial, enabled=True, root=root)
    current = source.get()
    target = root / SCENE
    valid = target.read_bytes()
    target.write_text('{"text":', encoding="utf-8")
    assert source.get() is current
    assert source.last_error
    target.unlink()
    assert source.get() is current
    target.write_bytes(valid)
    edit(root, SCENE, "text", "Исправленный текст.")
    assert source.get()["scenes"]["debris_grotto"]["text"] == "Исправленный текст."
    assert source.last_error is None


def test_invalid_schema_or_placeholders_rejected(editable):
    initial, root = editable
    source = TextContentSource(initial, enabled=True, root=root)
    current = source.get()
    edit(root, SCENE, "buttons", [])
    assert source.get() is current
    target = root / SCENE
    target.write_text(json.dumps(initial["_text_sources"][SCENE], ensure_ascii=False), encoding="utf-8")
    edit(root, SCENE, "hints", ["A", "B", "{missing_location}"])
    assert source.get() is current


def test_catalog_contains_every_editable_string_and_return_conditions(editable):
    initial, _ = editable
    catalog = build_catalog(initial)
    def values(node):
        if isinstance(node, dict):
            for child in node.values():
                yield from values(child)
        elif isinstance(node, list):
            for child in node:
                yield from values(child)
        elif isinstance(node, str):
            yield node
    for source in initial["_text_sources"].values():
        for value in values(source):
            assert value.replace("|", "&#124;").replace("\n", "<br>") in catalog
    assert "007.04" in catalog
    assert "Применяется и при возвращении" in catalog
    assert "text_released" in catalog and "buttons_quiet" in catalog


def test_refresh_and_callback_use_new_text_without_gameplay_turn(editable):
    async def run():
        initial, root = editable
        repo = Repository(root / "save.sqlite3")
        state = State(started=True, scene="debris_grotto", screen="scene",
                      turns=25, message_id=100, flags={"snake_gone": True})
        state.item_locations.update(lamp="inventory", bird="gone", cage="inventory")
        state.item_states["lamp"]["power"] = True
        repo.save(42, state)
        source = TextContentSource(initial, enabled=True, root=root)
        bot = Bot("123456:LOCAL_TEST_TOKEN")
        chat = Chat(id=42, type="private")
        user = User(id=42, is_bot=False, first_name="Tester")
        response = Message(message_id=100, date=datetime.now(timezone.utc), chat=chat,
                           photo=[PhotoSize(file_id="photo", file_unique_id="p", width=100, height=100)])
        bot.edit_message_media = AsyncMock(return_value=response)
        bot.send_photo = AsyncMock(return_value=response)
        bot.session.make_request = AsyncMock(return_value=True)
        dp = create_dispatcher(initial, repo, Media(initial), source)
        edit(root, SCENE, "text_released", "Обновлённое описание возвращения.")
        message = Message(message_id=2, date=datetime.now(timezone.utc), chat=chat, from_user=user,
                          text="/refresh", entities=[{"type": "bot_command", "offset": 0, "length": 8}])
        await dp.feed_update(bot, Update(update_id=1, message=message))
        assert "Обновлённое описание возвращения." in bot.edit_message_media.call_args.kwargs["media"].caption
        after = repo.get(42)
        assert after.turns == state.turns and after.scene == state.scene
        assert after.item_locations == state.item_locations and after.flags == state.flags
        from aiogram.types import CallbackQuery
        edit(root, SCENE, "inspect_released", "Обновлённый осмотр.")
        query = CallbackQuery(id="inspect", from_user=user, chat_instance="test", message=response,
                              data=f"g:{after.revision}:ui:inspect")
        await dp.feed_update(bot, Update(update_id=2, callback_query=query))
        assert "Обновлённый осмотр." in bot.edit_message_media.call_args.kwargs["media"].caption
        assert repo.get(42).turns == state.turns
        await bot.session.close()
    asyncio.run(run())


@pytest.mark.parametrize("value, expected", [("true", True), ("false", False), ("", False), ("1", True)])
def test_development_flag(value, expected):
    assert env_flag(value) is expected

