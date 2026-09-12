import asyncio
import logging
import os
from collections import defaultdict
from uuid import uuid4

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter, TelegramUnauthorizedError
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from dotenv import load_dotenv

from .content import ROOT, load_content
from .engine import InvalidAction, apply
from .media import Media
from .repository import Repository
from .ui import render
from .text_reload import TextContentSource, env_flag
from .catalog import write_catalog

log = logging.getLogger("dungeon")


def create_dispatcher(content, repository, media, content_source=None):
    dp = Dispatcher()
    locks = defaultdict(asyncio.Lock)
    source = content_source or TextContentSource(content)

    async def show(bot, chat_id, user_id, state, snapshot, force_new=False):
        card = render(state, snapshot)
        key, photo = media.resolve(card.asset)
        if state.message_id and not force_new:
            try:
                result = await bot.edit_message_media(
                    chat_id=chat_id, message_id=state.message_id,
                    media=InputMediaPhoto(media=photo, caption=card.caption, parse_mode="HTML"),
                    reply_markup=card.keyboard)
                if isinstance(result, Message):
                    media.remember(key, result)
                return
            except TelegramBadRequest as exc:
                reason = exc.message.lower()
                if "message is not modified" in reason:
                    return
                if "message to edit not found" not in reason and "message can't be edited" not in reason:
                    raise
        result = await bot.send_photo(chat_id=chat_id, photo=photo, caption=card.caption,
                                      parse_mode="HTML", reply_markup=card.keyboard)
        state.message_id = result.message_id
        repository.save(user_id, state)
        media.remember(key, result)

    async def safely_show(bot, chat_id, user_id, state, snapshot, force_new=False):
        try:
            await show(bot, chat_id, user_id, state, snapshot, force_new=force_new)
            return True
        except (TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter, OSError) as exc:
            # Do not include HTTP URLs or tokens in logs.
            log.warning("render_failed user_id=%s error_type=%s", user_id, type(exc).__name__)
            try:
                await bot.send_message(chat_id, "Прогресс сохранён, но карточку не удалось обновить. Отправьте /start, чтобы восстановить её.")
            except (TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter):
                log.warning("recovery_message_failed user_id=%s", user_id)
            return False

    async def clean_start_message(bot, chat_id, message_id, old_card=False):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramAPIError as exc:
            log.info("start_cleanup_failed error_type=%s", type(exc).__name__)
            if old_card:
                try:
                    await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
                except TelegramAPIError:
                    # Revision and message-id checks also reject stale buttons.
                    pass

    @dp.message(CommandStart())
    async def start(message: Message, bot: Bot):
        if message.chat.type != "private" or not message.from_user:
            await message.answer("Откройте личный чат с ботом и отправьте /start.")
            return
        user_id = message.from_user.id
        async with locks[user_id]:
            snapshot = source.get()
            state = repository.get(user_id)
            old_message_id = state.message_id
            state.screen, state.notice = "start", ""
            state.revision = uuid4().hex[:12]
            repository.save(user_id, state)
            sent = await safely_show(bot, message.chat.id, user_id, state, snapshot, force_new=True)
            if sent:
                # Remove the previous UI only after the replacement is sent and saved.
                if old_message_id and old_message_id != state.message_id:
                    await clean_start_message(bot, message.chat.id, old_message_id, old_card=True)
                await clean_start_message(bot, message.chat.id, message.message_id)

    @dp.message(Command("refresh"))
    async def refresh(message: Message, bot: Bot):
        if message.chat.type != "private" or not message.from_user:
            return
        user_id = message.from_user.id
        async with locks[user_id]:
            snapshot = source.get()
            state = repository.get(user_id)
            state.notice = ""
            state.revision = uuid4().hex[:12]
            repository.save(user_id, state)
            await safely_show(bot, message.chat.id, user_id, state, snapshot)

    @dp.callback_query(F.data.startswith("g:"))
    async def click(query: CallbackQuery, bot: Bot):
        if not isinstance(query.message, Message) or query.message.chat.type != "private":
            await query.answer("Откройте личный чат с ботом.", show_alert=True)
            return
        user_id = query.from_user.id
        # Acknowledge before disk or media work.
        try:
            await query.answer()
        except TelegramBadRequest:
            return
        async with locks[user_id]:
            snapshot = source.get()
            state = repository.get(user_id)
            parts = (query.data or "").split(":", 2)
            if len(parts) != 3 or parts[1] != state.revision or query.message.message_id != state.message_id:
                # Old or repeated buttons never mutate progress. Restore current UI.
                await safely_show(bot, query.message.chat.id, user_id, state, snapshot)
                return
            try:
                apply(state, parts[2], snapshot)
            except InvalidAction:
                return
            repository.save(user_id, state)
            log.info("action user_id=%s scene_id=%s action_id=%s turn=%s",
                     user_id, state.scene, parts[2], state.turns)
            await safely_show(bot, query.message.chat.id, user_id, state, snapshot)

    @dp.message()
    async def other(message: Message):
        await message.answer("Для игры используйте кнопки. Отправьте /start, чтобы открыть приключение.")

    return dp


async def main():
    load_dotenv(ROOT / ".env")
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "replace_me":
        raise SystemExit("Укажите BOT_TOKEN в файле dungeon/.env. Инструкция — в README.md.")
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # HTTP client logs must never expose bot-token URLs, even in debug mode.
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    content = load_content()
    source = TextContentSource(content, enabled=env_flag(os.getenv("DEV_TEXT_RELOAD", "false")), on_reload=write_catalog)
    repository = Repository(ROOT / "data/prototype.sqlite3")
    bot = Bot(token=token)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        log.info("Бот запущен. Откройте личный чат и отправьте /start. Остановка: Ctrl+C.")
        await create_dispatcher(content, repository, Media(content), source).start_polling(bot, handle_as_tasks=True)
    except TelegramUnauthorizedError:
        raise SystemExit("Telegram отклонил BOT_TOKEN. Проверьте его в .env.") from None
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
