import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from zubepredict_core.shared.config import get_settings

settings = get_settings()
dispatcher = Dispatcher()


@dispatcher.message(Command("start"))
async def start(message: Message) -> None:
    await message.answer(
        "Welcome to ZubePredict AI. I can help turn a dataset into a verified "
        "machine-learning experiment. The starter bot is connected; staged dataset "
        "upload arrives in Stage 7."
    )


@dispatcher.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "/start — introduction\n"
        "/help — available commands\n"
        "Later stages add /new_project, /upload, /status, /results and /cancel."
    )


@dispatcher.message(F.document)
async def document_placeholder(message: Message) -> None:
    await message.answer(
        "I received your document. Dataset processing is deliberately disabled in the "
        "starter bot until secure storage and job ownership are added in Stage 7."
    )


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("Add TELEGRAM_BOT_TOKEN to .env before starting the bot.")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(settings.telegram_bot_token)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
