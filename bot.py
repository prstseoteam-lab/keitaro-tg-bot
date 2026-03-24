import os, subprocess, sys

# Блок авто-установки библиотек для Bothost
def install_deps():
    for package in ['gspread', 'oauth2client', 'requests']:
        try:
            __import__(package)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

install_deps()

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
ETHERSCAN_KEY = 'UZEUWY6ATS69HY1Q6YYAD5B6ENIJ1IQQ2Q'

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

def find_matches(eur_amount, network, tx_id):
    try:
        sheet = get_sheet()
        grid = sheet.spreadsheet.fetch_sheet_metadata({'includeGridData': True})
        sheet_data = grid['sheets'][0]['data'][0]['rowData']
        all_values = sheet.get_all_values()
        pp_names = all_values[1] # 2-я строка
        
        matches_found = []
        today = datetime.now().strftime("%d.%m.%Y %H:%M")

        # Проходим по каждому столбцу (по каждой ПП отдельно)
        for col_idx in range(1, len(pp_names)):
            unpaid_cells = []
            
            # Собираем все НЕ зеленые ячейки в этом столбце
            for row_idx, row_data in enumerate(sheet_data[2:], start=):
                cells = row_data.get('values', [])
                if col_idx >= len(cells): continue
                
                cell = cells[col_idx]
                bg = cell.get('effectiveFormat', {}).get('backgroundColor', {})
                # Проверка на зеленый (если не зеленый)
                is_green = bg.get('red', 0) < 0.8 and bg.get('green', 0) > 0.8 and bg.get('blue', 0) < 0.8
                
                if not is_green:
                    val_text = cell.get('formattedValue', '')
                    if val_text:
                        try:
                            num = float(val_text.replace(',', '.').replace(' ', '').replace('\xa0', ''))
                            unpaid_cells.append({'row': row_idx, 'val': num, 'month': all_values[row_idx-1][0]})
                        except: continue

            # 1. Проверка одиночных выплат
            for item in unpaid_cells:
                if abs(item['val'] - eur_amount) / item['val'] < 0.04:
                    addr = gspread.utils.rowcol_to_a1(item['row'], col_idx + 1)
                    sheet.update_notes({addr: f"✅ Транза {network}: {eur_amount}€\nДата: {today}"})
                    matches_found.append(f"🎯 {pp_names[col_idx]} ({item['month']}) — {item['val']}€")

            # 2. Проверка суммы ДВУХ месяцев (комбо)
            for i in range(len(unpaid_cells)):
                for j in range(i + 1, len(unpaid_cells)):
                    combo_sum = unpaid_cells[i]['val'] + unpaid_cells[j]['val']
                    if abs(combo_sum - eur_amount) / combo_sum < 0.04:
                        for k in [i, j]:
                            addr = gspread.utils.rowcol_to_a1(unpaid_cells[k]['row'], col_idx + 1)
                            sheet.update_notes({addr: f"🔗 Комбо-транза {network}: {eur_amount}€\nЧасть суммы: {unpaid_cells[k]['val']}€"})
                        matches_found.append(f"👯 {pp_names[col_idx]} (КОМБО: {unpaid_cells[i]['month']} + {unpaid_cells[j]['month']})")

        return matches_found
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        return []

async def get_rates():
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=EURUSDT").json()
        u_to_e = 1 / float(r['price'])
        b = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCEUR").json()
        return {'USDT': u_to_e, 'BTC': float(b['price'])}
    except: return {'USDT': 0.92, 'BTC': 63000}

async def process_income(network, amount, sender, tx_id):
    if tx_id in seen_txs: return
    if not seen_txs: # При запуске просто запоминаем старые
        seen_txs.add(tx_id)
        return

    rates = await get_rates()
    eur_sum = amount * (rates['BTC'] if 'BTC' in network else rates['USDT'])
    matches = find_matches(round(eur_sum, 2), network, tx_id)
    
    match_text = "✅ **Совпадения:**\n" + "\n".join(matches) if matches else "❓ Совпадений не найдено."
    msg = (f"📥 **ПРИХОД {network}**\n💰 `{amount}` (~`{round(eur_sum, 2)}€`)\n👤 От: `{sender}`\n\n{match_text}")
    
    requests.post(f"https://api.telegram.org/bot{API_TOKEN}/sendMessage", data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'})
    seen_txs.add(tx_id)

# --- СКАНЕРЫ ---
async def check_trc20():
    addr = WALLETS['TRC20']
    try:
        res = requests.get(f"https://api.trongrid.io/v1/accounts/{addr}/transactions/trc20").json()
        for tx in res.get('data', []):
            if tx['to'] == addr: await process_income('USDT (TRC20)', int(tx['value'])/1_000_000, tx['from'], tx['transaction_id'])
    except: pass

async def check_erc20():
    addr = WALLETS['ERC20']
    try:
        res = requests.get(f"https://api.etherscan.io/api?module=account&action=tokentx&address={addr}&sort=desc&apikey={ETHERSCAN_KEY}").json()
        if res.get('status') == '1':
            for tx in res['result']:
                if tx['to'].lower() == addr.lower(): await process_income('USDT (ERC20)', int(tx['value'])/(10**int(tx['tokenDecimal'])), tx['from'], tx['hash'])
    except: pass

async def check_btc():
    addr = WALLETS['BTC']
    try:
        res = requests.get(f"https://blockchain.info/rawaddr/{addr}").json()
        for tx in res.get('txs', []):
            for out in tx.get('out', []):
                if out.get('addr') == addr: await process_income('BTC', out['value']/100_000_000, 'BTC_Net', tx['hash'])
    except: pass

async def main():
    print("🚀 Бот запущен!")
    while True:
        await check_trc20()
        await check_erc20()
        await check_btc()
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
