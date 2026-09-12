import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import Chat, Message, Update, User

from app.bot import create_dispatcher
from app.content import load_content
from app.engine import State
from app.media import Media
from app.repository import Repository


@pytest.mark.parametrize('failure', [None, 'delete', 'send'])
def test_start_moves_card_preserves_game_and_handles_failures(tmp_path, failure):
    async def run():
        content = load_content()
        repo = Repository(tmp_path / 'save.sqlite3')
        state = State(started=True, scene='inside_house', screen='scene', turns=99,
                      message_id=10, returning=True, flags={'episode4_complete': True},
                      visited=['road_end', 'inside_house'])
        state.item_locations['silver'] = 'treasury'
        repo.save(42, state)
        bot = Bot('123456:LOCAL_TEST_TOKEN')
        bot.session.make_request = AsyncMock(return_value=True)
        chat = Chat(id=42, type='private')
        user = User(id=42, is_bot=False, first_name='Test')
        calls = []
        async def send(**kwargs):
            calls.append('send')
            if failure == 'send':
                raise TelegramNetworkError(method=None, message='Offline')
            return Message(message_id=20 + calls.count('send'), date=datetime.now(timezone.utc), chat=chat)
        async def delete(**kwargs):
            calls.append(('delete', kwargs['message_id']))
            assert repo.get(42).message_id != 10
            if failure == 'delete':
                raise TelegramBadRequest(method=None, message="message can't be deleted")
            return True
        bot.send_photo = AsyncMock(side_effect=send)
        bot.delete_message = AsyncMock(side_effect=delete)
        bot.edit_message_media = AsyncMock()
        bot.edit_message_reply_markup = AsyncMock()
        bot.send_message = AsyncMock()
        dp = create_dispatcher(content, repo, Media(content))
        try:
            for number in (1, 2):
                command = Message(message_id=number, date=datetime.now(timezone.utc), chat=chat,
                                  from_user=user, text='/start',
                                  entities=[{'type': 'bot_command', 'offset': 0, 'length': 6}])
                await dp.feed_update(bot, Update(update_id=number, message=command))
                saved = repo.get(42)
                for key, value in asdict(state).items():
                    if key not in {'message_id', 'revision', 'screen', 'notice'}:
                        assert getattr(saved, key) == value
                assert saved.screen == 'start'
            assert bot.send_photo.await_count == 2
            bot.edit_message_media.assert_not_awaited()
            if failure == 'send':
                assert repo.get(42).message_id == 10
                bot.delete_message.assert_not_awaited()
            else:
                assert repo.get(42).message_id == 22
                assert calls == ['send', ('delete', 10), ('delete', 1), 'send', ('delete', 21), ('delete', 2)]
                assert bot.edit_message_reply_markup.await_count == (2 if failure == 'delete' else 0)
        finally:
            await bot.session.close()
    asyncio.run(run())
