import asyncio
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- НАСТРОЙКИ ---
API_TOKEN = '8694184437:AAHwO0RTBnTotmsAFWkCbpB2LyboUY7bcgY'
CHAT_ID = '-5051888275' 
SPREADSHEET_ID = '1BjUwJrAtoAKbQKdZL80KsLnT4FGxn9HBSC4JXuEXcIY' 
CREDS_FILE = 'creds.json' 

WALLETS = {
    'TRC20': 'THuKC89JjXG9Wf5VfUfvPzSYU2i8XzzKfb',
    'ERC20': '0xc4a4E461Cb792Bd96b4D12e1c648427462FC7bAa',
    'BTC': 'bc1q86f03w674rqh7srvv5wak2446ce4dsm7s0a6ze'
}

seen_txs = set()

def get_sheet():
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1

def find_and_comment(eur_amount, network, tx_id):
    try:
        sheet = get_sheet()
        all_data = sheet.get_all_values()
        if len(all_data) < 2: return []
        
        pp_names = all_data[1] # 2-я строка с названиями ПП
        matches = []
        today = datetime.now().strftime("%d.%m.%Y %H:%M")

        for row_idx, row in enumerate(all_data[2:], start=3):
            month_name = row[0] if row else "???"
            for col_idx, value in enumerate(row):
                if not value or col_idx == 0: continue
                try:
                    val = float(value.replace(',', '.').replace(' ', ''))
                    # Если разница меньше 3%
                    if abs(val - eur_amount) / val < 0.03:
                        cell_address = gspread.utils.rowcol_to_a1(row_idx, col_idx + 1)
                        note_text = f"✅ Транза {network}: {eur_amount}€\nДата: {today}\nTX: {tx_id[:10]}..."
                        sheet.update_notes({cell_address: note_text})
                        matches.append(f"{pp_names[col_idx]} ({month_name}) — {val}€")
                except: continue
        return matches
    except Exception as e:
        print(f"Ошибка таблицы: {e}")
        return []

async def get_rates():
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=EURUSDT").json()
        u_to_e = 1 / float(r['price'])
        b = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCEUR").json()
        return {'USDT': u_to_e, 'BTC': float(b['price'])}
    except: return {'USDT': 0.93, 'BTC': 60000}

async def process_income(network, amount, sender, tx_id):
    if tx_id in seen_txs: return
    rates = await get_rates()
    eur_sum = amount * (rates['BTC'] if 'BTC' in network else rates['USDT'])
    matches = find_and_comment(round(eur_sum, 2), network, tx_id)
    
    match_text = "✅ **Нашел совпадения и оставил заметки в таблице:**\n" + "\n".join(matches) if matches else "❓ Совпадений по сумме не найдено."
    msg = (f"💳 **НОВЫЙ ПРИХОД!**\nСеть: `{network}`\nСумма: `{amount}` (~`{round(eur_sum, 2)}€`)\nОт: `{sender}`\n\n{match_text}")
    requests.post(f"https://api.telegram.org/bot{API_TOKEN}/sendMessage", data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'})
    seen_txs.add(tx_id)

async def check_trc20():
    addr = WALLETS['TRC20']
    url = f"https://api.trongrid.io/v1/accounts/{addr}/transactions/trc20"
    try:
        res = requests.get(url).json()
        for tx in res.get('data', []):
            if tx['to'] == addr and tx['transaction_id'] not in seen_txs:
                amount = int(tx['value']) / 1_000_000
                await process_income('USDT (TRC20)', amount, tx['from'], tx['transaction_id'])
    except: pass

async def main():
    print("Бот запущен...")
    while True:
        await check_trc20()
        # Позже добавим BTC и ERC20 аналогично
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
