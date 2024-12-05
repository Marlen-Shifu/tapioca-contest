import asyncio
import logging
import os
import sys
import sqlite3
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import config

# Bot token can be obtained via https://t.me/BotFather
TOKEN = config.TOKEN

# Webserver settings
WEB_SERVER_HOST = "127.0.0.1"
WEB_SERVER_PORT = 8080
WEBHOOK_PATH = "/webhook"
WEBHOOK_SECRET = config.WEBHOOK_SECRET
BASE_WEBHOOK_URL = f"http://{config.SERVER_ADDRESS}:{WEB_SERVER_PORT}"

# Logging configuration
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# Database setup
DB_FILE = "receipts_contest.db"

def init_db():
    """Initialize the database if it does not exist."""
    if not os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                name TEXT,
                contact TEXT,
                city TEXT,
                photo_id TEXT
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Database initialized.")

# FSM States
class ReceiptForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_contact = State()
    waiting_for_city = State()
    waiting_for_photo = State()

# Router
router = Router()

# Helper function for cancel button
def get_cancel_button():
    buttons = InlineKeyboardBuilder()
    buttons.add(InlineKeyboardButton(text="Cancel", callback_data="cancel"))
    return buttons

# Handlers
@router.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} ({message.from_user.username}) started interaction.")
    await message.answer(
        "Добро пожаловать в бот Розыгрыша от Tapioca! 🎉\n"
        "Как Вас зовут?",
        reply_markup=get_cancel_button().as_markup()
    )
    await state.set_state(ReceiptForm.waiting_for_name)

@router.message(ReceiptForm.waiting_for_name)
async def handle_name_input(message: types.Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} provided name: {message.text.strip()}")
    await state.update_data(name=message.text.strip())
    await message.answer("Отправьте пожалуйста Ваш номер телефона.", reply_markup=get_cancel_button().as_markup())
    await state.set_state(ReceiptForm.waiting_for_contact)

@router.message(ReceiptForm.waiting_for_contact)
async def handle_contact_input(message: types.Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} provided contact: {message.text.strip()}")
    await state.update_data(contact=message.text.strip())
    await message.answer("Из какого города вы?", reply_markup=get_cancel_button().as_markup())
    await state.set_state(ReceiptForm.waiting_for_city)

@router.message(ReceiptForm.waiting_for_city)
async def handle_city_input(message: types.Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} provided city: {message.text.strip()}")
    await state.update_data(city=message.text.strip())
    await message.answer("Пожалуйста отправьте фото чека.", reply_markup=get_cancel_button().as_markup())
    await state.set_state(ReceiptForm.waiting_for_photo)

@router.message(ReceiptForm.waiting_for_photo, F.photo)
async def handle_photo_input(message: types.Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    user_data = await state.get_data()
    logger.info(f"User {message.from_user.id} uploaded photo with ID: {photo_id}")

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO receipts (user_id, user_name, name, contact, city, photo_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (message.from_user.id, message.from_user.username or "No Username", user_data['name'], user_data['contact'], user_data['city'], photo_id))
        receipt_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Receipt saved with ID: {receipt_id} for user {message.from_user.id}")
        await message.answer(f"Спасибо! Ваш номер заявки: {receipt_id}")
    except Exception as e:
        logger.error(f"Error saving receipt: {e}")
        await message.answer("Произошла ошибка. Попробуйте еще раз.")

    await state.clear()

# Webhook setup
async def on_startup(bot: Bot):
    await bot.set_webhook(f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}", secret_token=WEBHOOK_SECRET)
    logger.info("Webhook has been set.")

async def polling(dp, bot):
    await dp.start_polling(bot, skip_updates=False)


# Main function
def main():
    init_db()

    # Dispatcher
    dp = Dispatcher()
    dp.include_router(router)

    if config.PROD:
        dp.startup.register(on_startup)

    # Bot instance
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    if config.PROD:
        # Web application
        app = web.Application()
        webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=WEBHOOK_SECRET)
        webhook_requests_handler.register(app, path=WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        # Start web server
        web.run_app(app, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
    else:
        asyncio.run(polling(dp, bot))

if __name__ == "__main__":
    main()
