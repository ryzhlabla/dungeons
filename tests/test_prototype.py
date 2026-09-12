import asyncio
from dataclasses import asdict
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, timezone

from app.content import load_content
from app.engine import State, InvalidAction, apply
from app.repository import Repository
from app.ui import render
from app.media import Media
from app.bot import create_dispatcher


@pytest.fixture
def content():
    return load_content()


def test_full_flow_and_drop(content):
    s = State()
    for action in ["new", "move:enter_house", "take_lamp", "ui:inventory", "ui:item", "lamp_on",
                   "drop_lamp", "take_lamp", "move:exit_house", "move:follow_stream"]:
        apply(s, action, content)
    assert s.scene == "stream"
    assert s.item_locations["lamp"] == "inventory"
    assert s.item_states["lamp"]["power"] is True
    assert set(s.visited) == {"road_end", "inside_house", "stream"}
    assert s.turns == 7
    apply(s, "ui:inventory", content)
    assert s.turns == 7


def test_duplicate_and_remote_actions_rejected(content):
    s = apply(State(), "new", content)
    with pytest.raises(InvalidAction):
        apply(s, "take_lamp", content)
    apply(s, "move:enter_house", content)
    apply(s, "take_lamp", content)
    with pytest.raises(InvalidAction):
        apply(s, "take_lamp", content)
    with pytest.raises(InvalidAction):
        apply(s, "move:follow_stream", content)
    with pytest.raises(InvalidAction):
        apply(s, "reset", content)


def test_persistence_and_user_isolation(tmp_path, content):
    path = tmp_path / "save.sqlite3"
    repo = Repository(path)
    s = apply(State(), "new", content)
    apply(s, "move:enter_house", content)
    apply(s, "take_lamp", content)
    repo.save(1, s)
    assert asdict(Repository(path).get(1)) == asdict(s)
    assert repo.get(2).started is False


def test_all_reachable_buttons_render_and_execute(content):
    # Explore the original six-scene episode; new rooms have dedicated route tests.
    queue = [State()]
    seen = set()
    screens = set()
    while queue:
        s = queue.pop()
        key = (s.started, s.scene, s.screen, s.item_locations["lamp"],
               s.item_states["lamp"]["power"], s.hint_level, s.item_locations["keys"], tuple(sorted(s.flags.items())))
        if key in seen:
            continue
        seen.add(key)
        screens.add(s.screen)
        card = render(s, content)
        assert len(card.caption) <= 1024
        assert card.asset in content["media"]
        for row in card.keyboard.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= 64
                import copy
                target = copy.deepcopy(s)
                apply(target, button.callback_data.split(":", 2)[2], content)
                if button.callback_data.split(":", 2)[2] != "move:enter_debris":
                    queue.append(target)
    assert {"scene", "start", "help", "inventory", "item", "hint", "menu",
            "confirm", "progress", "journal", "inspect", "keys"} <= screens


def test_media_replacement_invalidates_cache(tmp_path):
    image = tmp_path / "scene.jpg"
    image.write_bytes(b"first image")
    media = Media({"media": {"scene": str(image)}})
    key, _ = media.resolve("scene")
    media.cache[key] = "telegram-file"
    assert media.resolve("scene")[1] == "telegram-file"
    image.write_bytes(b"other image")
    next_key, upload = media.resolve("scene")
    assert next_key != key
    assert upload.path == image


def test_telegram_dispatch_and_stale_buttons(tmp_path, content):
    async def run():
        repo = Repository(tmp_path / "bot.sqlite3")
        bot = Bot("123456:LOCAL_TEST_TOKEN")
        chat = Chat(id=42, type="private")
        user = User(id=42, is_bot=False, first_name="Tester")
        card_message = Message(message_id=100, date=datetime.now(timezone.utc), chat=chat,
                               photo=[PhotoSize(file_id="photo", file_unique_id="p", width=100, height=100)])
        bot.send_photo = AsyncMock(return_value=card_message)
        bot.edit_message_media = AsyncMock(return_value=card_message)
        bot.session.make_request = AsyncMock(return_value=True)
        bot.send_message = AsyncMock()
        dp = create_dispatcher(content, repo, Media(content))
        start = Message(message_id=1, date=datetime.now(timezone.utc), chat=chat, from_user=user,
                        text="/start", entities=[{"type": "bot_command", "offset": 0, "length": 6}])
        await dp.feed_update(bot, Update(update_id=1, message=start))
        async def click(action, revision=None):
            s = repo.get(42)
            q = CallbackQuery(id=str(s.turns) + action, from_user=user, chat_instance="test",
                              message=card_message, data=f"g:{revision or s.revision}:{action}")
            await dp.feed_update(bot, Update(update_id=2, callback_query=q))
        await click("new")
        await click("move:enter_house")
        old_revision = repo.get(42).revision
        await click("take_lamp")
        saved = asdict(repo.get(42))
        await click("take_lamp", old_revision)
        assert asdict(repo.get(42)) == saved
        assert repo.get(42).item_locations["lamp"] == "inventory"
        assert bot.send_photo.await_count == 1
        assert bot.session.make_request.await_count == 5  # Four callback acknowledgments and /start cleanup.
        bot.edit_message_media.side_effect = TelegramBadRequest(
            method=None, message="Bad Request: message to edit not found")
        await click("ui:inventory")
        assert bot.send_photo.await_count == 2
        await bot.session.close()
    asyncio.run(run())
