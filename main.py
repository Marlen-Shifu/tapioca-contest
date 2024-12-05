import logging
from logging.handlers import RotatingFileHandler
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import sqlite3
import os

import config

# Configure logging
LOG_FILE = "log.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Logs to console
        RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)  # Rotating log file
    ]
)
logger = logging.getLogger(__name__)

# Bot token
API_TOKEN = config.TOKEN
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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

# FSM States for Receipt Submission
class ReceiptForm(StatesGroup):
    waiting_for_name = State()
    waiting_for_contact = State()
    waiting_for_city = State()
    waiting_for_photo = State()

# Helper function to create Cancel Button
def get_cancel_button():
    """Generate a cancel button."""
    buttons = InlineKeyboardBuilder()
    buttons.add(InlineKeyboardButton(text="Cancel", callback_data="cancel"))
    return buttons

# /start Command Handler
@dp.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    """Start the bot interaction and ask for the user's name."""
    logger.info(f"User {message.from_user.id} ({message.from_user.username}) started interaction.")
    await message.answer(
        "Добро пожаловать в бот Розыгрыша от Tapioca! 🎉\n"
        "Для участия в розыгрыше заполните следующие данные.\n"
        "Как Вас зовут?",
        reply_markup=get_cancel_button().as_markup()
    )
    await state.set_state(ReceiptForm.waiting_for_name)

# Name Input Handler
@dp.message(ReceiptForm.waiting_for_name)
async def handle_name_input(message: types.Message, state: FSMContext):
    """Handle the user's name input."""
    logger.info(f"User {message.from_user.id} provided name: {message.text.strip()}")
    await state.update_data(name=message.text.strip())
    await message.answer(
        "Приятно познакомиться! Отправьте пожалуйста Ваш номер телефона для связи.",
        reply_markup=get_cancel_button().as_markup()
    )
    await state.set_state(ReceiptForm.waiting_for_contact)

# Contact Input Handler
@dp.message(ReceiptForm.waiting_for_contact)
async def handle_contact_input(message: types.Message, state: FSMContext):
    """Handle the user's contact input."""
    logger.info(f"User {message.from_user.id} provided contact: {message.text.strip()}")
    await state.update_data(contact=message.text.strip())
    await message.answer(
        "Из какого города? 🏙",
        reply_markup=get_cancel_button().as_markup()
    )
    await state.set_state(ReceiptForm.waiting_for_city)

# City Input Handler
@dp.message(ReceiptForm.waiting_for_city)
async def handle_city_input(message: types.Message, state: FSMContext):
    """Handle the user's city input."""
    logger.info(f"User {message.from_user.id} provided city: {message.text.strip()}")
    await state.update_data(city=message.text.strip())
    await message.answer(
        "Спасибо! Пожалуйста отправьте фото чека. 📸",
        reply_markup=get_cancel_button().as_markup()
    )
    await state.set_state(ReceiptForm.waiting_for_photo)

# Photo Input Handler
@dp.message(ReceiptForm.waiting_for_photo, F.photo)
async def handle_photo_input(message: types.Message, state: FSMContext):
    """Handle the user's photo input."""
    photo_id = message.photo[-1].file_id
    user_data = await state.get_data()
    logger.info(f"User {message.from_user.id} uploaded photo with ID: {photo_id}")

    # Save to database
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO receipts (user_id, user_name, name, contact, city, photo_id)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            message.from_user.id,
            message.from_user.username or "No Username",
            user_data['name'],
            user_data['contact'],
            user_data['city'],
            photo_id
        ))
        receipt_id = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Receipt saved with ID: {receipt_id} for user {message.from_user.id}")

        # Confirmation message
        await message.answer(
            f"Спасибо за оставленную заявку! Вы стали участником розыгрыша от Tapioca. 🎉\n"
            f"Ваш номер заявки: {receipt_id}\n"
            "Хотите оставить еще одну заявку? Нажмите /start."
        )
    except Exception as e:
        logger.error(f"Error saving receipt for user {message.from_user.id}: {e}")
        await message.answer("Произошла ошибка при сохранении заявки. Попробуйте еще раз.")

    await state.clear()

# Cancel Handler
@dp.callback_query(lambda query: query.data == "cancel")
async def handle_cancel(callback_query: types.CallbackQuery, state: FSMContext):
    """Handle user cancellation."""
    logger.info(f"User {callback_query.from_user.id} canceled the submission process.")
    await state.clear()
    await callback_query.message.answer(
        "Заявка отклонена. Вы можете начать заново нажав /start.",
        reply_markup=None
    )
    await callback_query.answer()

# Main Function
async def main():
    """Run the bot."""
    init_db()
    logger.info("Bot started.")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
