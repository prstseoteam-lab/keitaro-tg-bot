import logging
import random
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8721694709:AAFV48QMKlq0No2a6xz10fcSyUawHRjwg-I'
CHANNEL_ID = '-1003713449715'  # ЗАМЕНИ НА СВОЙ ЮЗЕРНЕЙМ КАНАЛА
BRAND_NAME = 'CoinFlow'
SUPPORTS = ["Rachel", "Alex", "Jordan", "Sarah", "Mike", "Linda", "Kevin", "Emma", "Justin", "Chloe"]

# Инициализация бота и хранилища состояний
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
logging.basicConfig(level=logging.INFO)

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('users.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, support_name TEXT, tp_nick TEXT, wallet TEXT, status TEXT)''')
conn.commit()

# --- СОСТОЯНИЯ (FSM) ---
class ReportState(StatesGroup):
    waiting_for_nick = State()
    waiting_for_photo = State()
    waiting_for_wallet = State()

# --- КЛАВИАТУРЫ ---
def get_start_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🌊 Join Channel", url=f"https://t.me/{CHANNEL_ID[1:]}"),
        InlineKeyboardButton("✅ I HAVE JOINED", callback_data="check_sub")
    )
    return kb

# --- ХЕНДЛЕРЫ ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer(
        f"🌊 **Welcome to the {BRAND_NAME} Reward Program!**\n\n"
        f"To participate in our **$50 USDT Weekly Giveaway**, you must be a member of our community.",
        reply_markup=get_start_kb(),
        parse_mode="Markdown"
    )

@dp.callback_query_handler(text="check_sub")
async def check_sub(call: types.CallbackQuery):
    status = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=call.from_user.id)
    if status.status != 'left':
        # Выдаем уникальное имя саппорта
        agent = random.choice(SUPPORTS)
        cursor.execute("INSERT OR REPLACE INTO users (user_id, support_name, status) VALUES (?, ?, ?)", 
                       (call.from_user.id, agent, 'started'))
        conn.commit()

        text = (
            f"✅ **Verification successful!**\n\n"
            f"**YOUR MISSION:**\n"
            f"1️⃣ Search Google for: `{BRAND_NAME} Trustpilot`\n"
            f"2️⃣ Write a 5-star review (min. 40 words).\n"
            f"3️⃣ **CRITICAL:** You must mention our agent **{agent}** in your review!\n\n"
            f"Example: _'Thanks to {agent} for the amazing service, CoinFlow is the best!'_\n\n"
            f"⏳ You have 60 minutes. Click below to submit proof 👇"
        )
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("📤 SUBMIT PROOF", callback_data="start_report"))
        await call.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await call.answer("❌ Please join the channel first!", show_alert=True)

@dp.callback_query_handler(text="start_report")
async def start_report(call: types.CallbackQuery):
    await ReportState.waiting_for_nick.set()
    await call.message.answer("📝 Enter your **Trustpilot Username**:")

@dp.message_handler(state=ReportState.waiting_for_nick)
async def process_nick(message: types.Message, state: FSMContext):
    await state.update_data(nick=message.text)
    await ReportState.next()
    await message.answer("📸 Now upload a **Screenshot** of your review (from 'My Reviews' section):")

@dp.message_handler(content_types=['photo'], state=ReportState.waiting_for_photo)
async def process_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await ReportState.next()
    await message.answer("💰 Enter your **USDT (TRC20)** or **LTC** wallet address for rewards:")

@dp.message_handler(state=ReportState.waiting_for_wallet)
async def process_wallet(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    
    # Сохраняем в БД
    cursor.execute("UPDATE users SET tp_nick = ?, wallet = ?, status = ? WHERE user_id = ?",
                   (user_data['nick'], message.text, 'pending', message.from_user.id))
    conn.commit()

    await state.finish()
    await message.answer(
        "🎯 **SUCCESS!**\n\n"
        "Your report has been sent to our system.\n"
        "🛡 **Status:** Pending Review (24-48h).\n\n"
        "Stay in our channel to see the winner announcement this Sunday! 🌊",
        parse_mode="Markdown"
    )

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
