import sqlite3
import requests
import os
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- НАСТРОЙКИ (ПОДСТАВЬ СВОИ) ---
API_TOKEN = 'ТВОЙ_ТОКЕН_ТГ'
KEITARO_API_KEY = 'ТВОЙ_КЛЮЧ_КЕЙТАРО'
KEITARO_URL = 'http://85.158.110.171/admin_api/v1'

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# База данных
def init_db():
    conn = sqlite3.connect('users.db')
    conn.execute('CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, sub_id TEXT)')
    conn.commit()
    conn.close()

# Клавиатура
def get_main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("Сегодня", callback_data="stats_today"),
        InlineKeyboardButton("Вчера", callback_data="stats_yesterday"),
        InlineKeyboardButton("Этот месяц", callback_data="stats_this_month")
    )
    return keyboard

@dp.message_handler(commands=['start'])
async def start(m: types.Message):
    await m.answer("Привет! Введи свой sub_id_4 (ник в трекере) для привязки.\nНапример: `lesha_media`")

@dp.message_handler(lambda m: not m.text.startswith('/'))
async def register(m: types.Message):
    sub = m.text.strip()
    conn = sqlite3.connect('users.db')
    conn.execute('INSERT OR REPLACE INTO users VALUES (?, ?)', (m.chat.id, sub))
    conn.commit()
    conn.close()
    await m.answer(f"✅ Привязано к нику: {sub}", reply_markup=get_main_menu())

# Логика статистики
@dp.callback_query_handler(lambda c: c.data.startswith('stats_'))
async def get_stats(callback: types.CallbackQuery):
    period = callback.data.split('_')[1]
    ranges = {"today": "today", "yesterday": "yesterday", "this": "this_month"}
    
    conn = sqlite3.connect('users.db')
    sub_id = conn.execute('SELECT sub_id FROM users WHERE chat_id = ?', (callback.from_user.id,)).fetchone()
    conn.close()

    if not sub_id:
        return await callback.answer("Сначала привяжи ID!")

    payload = {
        "range": ranges.get(period, "today"),
        "columns": ["clicks", "conversions", "revenue", "profit"],
        "filters": [{"name": "sub_id_4", "operator": "EQUALS", "expression": sub_id[0]}]
    }
    
    headers = {'Api-Key': KEITARO_API_KEY}
    r = requests.post(f"{KEITARO_URL}/report/build", json=payload, headers=headers)
    
    if r.status_code == 200:
        data = r.json()['rows'][0] if r.json()['rows'] else {"clicks":0, "conversions":0, "profit":0}
        text = (f"📊 Стата ({sub_id[0]}):\nКл: {data.get('clicks')} | Лидов: {data.get('conversions')}\n"
                f"Профит: ${data.get('profit')}")
        await bot.send_message(callback.from_user.id, text, reply_markup=get_main_menu())
    else:
        await bot.send_message(callback.from_user.id, "Ошибка Keitaro API")
    await callback.answer()

# Прием постбэков (По КД)
async def handle_postback(request):
    sub_id = request.query.get('sub4')
    payout = request.query.get('payout', '0')
    geo = request.query.get('geo', '??')

    conn = sqlite3.connect('users.db')
    user = conn.execute('SELECT chat_id FROM users WHERE sub_id = ?', (sub_id,)).fetchone()
    conn.close()

    if user:
        await bot.send_message(user[0], f"🔥 ЛИД! | ГЕО: {geo} | +${payout} | Баер: {sub_id}")
    return web.Response(text="OK")

async def on_startup(dp):
    app = web.Application()
    app.router.add_get('/postback', handle_postback)
    runner = web.AppRunner(app)
    await runner.setup()
    # Bothost прокидывает порт через переменную PORT
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()

if __name__ == '__main__':
    init_db()
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
