import os
import time
import threading
import requests
import telebot
from telebot import types
from flask import Flask

# --- 1. ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bybit Bot Active 24/7"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. НАСТРОЙКИ ---
TELEGRAM_TOKEN = "8924895868:AAG5w69mIJrImVHp3a-YA-HzU-JyxieT0Wk"
CHAT_ID = "7960144135"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "NEARUSDT", "LINKUSDT", "DOTUSDT"
]

is_running = True
mode = "futures"
strategy = "rsi"
last_signals = {}

def send_telegram(text):
    try:
        bot.send_message(CHAT_ID, text, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка Telegram: {e}", flush=True)

# --- 3. ПОЛУЧЕНИЕ СВЕЧЕЙ ---
def get_klines_data(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=100"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return [float(item[4]) for item in data]
    except Exception as e:
        print(f"Ошибка получения свечей {symbol}: {e}", flush=True)
    return []

# --- 4. ИНДИКАТОРЫ ---
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i-1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(prices) - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_ema(prices, period):
    if len(prices) < period:
        return prices[-1] if prices else 0
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price * k) + (ema * (1 - k))
    return round(ema, 4)

# --- 5. ИНЛАЙН-МЕНЮ И ОБРАБОТКА ---
def get_main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    s1 = "✅ " if strategy == "smart_trend" else ""
    s2 = "✅ " if strategy == "rsi" else ""
    s3 = "✅ " if strategy == "ema_cross" else ""
    
    btn1 = types.InlineKeyboardButton(f"{s1}🎯 Умный Трендовый Снайпер (EMA200)", callback_data="strat_smart_trend")
    btn2 = types.InlineKeyboardButton(f"{s2}🔥 Экстремальный RSI", callback_data="strat_rsi")
    btn3 = types.InlineKeyboardButton(f"{s3}📈 Пересечение EMA (9/21)", callback_data="strat_ema_cross")
    
    mode_label = "🟢 Рынок: SPOT (нажми для FUTURES)" if mode == "spot" else "🔴 Рынок: FUTURES (нажми для SPOT)"
    btn_mode = types.InlineKeyboardButton(mode_label, callback_data="toggle_mode")
    
    pause_label = "▶️️ Возобновить работу" if not is_running else "⏸️ Поставить на паузу"
    btn_pause = types.InlineKeyboardButton(pause_label, callback_data="toggle_pause")
    
    btn_status = types.InlineKeyboardButton("ℹ️ Проверить статус", callback_data="check_status")

    markup.add(btn1, btn2, btn3, btn_mode, btn_pause, btn_status)
    return markup

@bot.message_handler(commands=['start', 'menu'])
def start_cmd(message):
    bot.send_message(
        message.chat.id, 
        f"🤖 <b>Панель управления AI Signals</b>\n\nТекущий рынок: <b>{mode.upper()}</b>\nАктивная стратегия: <b>{strategy.upper()}</b>", 
        parse_mode="HTML", 
        reply_markup=get_main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    global is_running, mode, strategy
    
    if call.data.startswith("strat_"):
        strategy = call.data.replace("strat_", "")
        bot.answer_callback_query(call.id, f"Стратегия изменена на {strategy.upper()}")
    elif call.data == "toggle_mode":
        mode = "spot" if mode == "futures" else "futures"
        bot.answer_callback_query(call.id, f"Режим изменен на {mode.upper()}")
    elif call.data == "toggle_pause":
        is_running = not is_running
        st = "запущен 🟢" if is_running else "на паузе ⏸"
        bot.answer_callback_query(call.id, f"Бот {st}")
    elif call.data == "check_status":
        st = "Активен 🟢" if is_running else "На паузе ⏸"
        bot.answer_callback_query(call.id, f"Статус: {st} | Режим: {mode.upper()}")

    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🤖 <b>Панель управления AI Signals</b>\n\nТекущий рынок: <b>{mode.upper()}</b>\nАктивная стратегия: <b>{strategy.upper()}</b>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    except Exception:
        pass

# --- 6. МОНИТОРИНГ РЫНКА ---
def analyze_market():
    global is_running, mode, strategy, last_signals
    
    while True:
        if is_running:
            for symbol in SYMBOLS:
                close_prices = get_klines_data(symbol)
                if not close_prices:
                    continue
                    
                current_price = close_prices[-1]
                rsi_val = calculate_rsi(close_prices)
                ema_9 = calculate_ema(close_prices, 9)
                ema_21 = calculate_ema(close_prices, 21)
                ema_200 = calculate_ema(close_prices, 200)
                
                signal_type = None
                
                if strategy == "rsi":
                    if rsi_val <= 45:
                        signal_type = "BUY 🟢 (Перепроданность RSI)"
                    elif rsi_val >= 55:
                        signal_type = "SELL 🔴 (Перекупленность RSI)"
                elif strategy == "ema_cross":
                    if ema_9 > ema_21 and close_prices[-2] <= calculate_ema(close_prices[:-1], 21):
                        signal_type = "BUY 🟢 (Пересечение EMA Вверх)"
                    elif ema_9 < ema_21 and close_prices[-2] >= calculate_ema(close_prices[:-1], 21):
                        signal_type = "SELL 🔴 (Пересечение EMA Вниз)"
                elif strategy == "smart_trend":
                    if current_price > ema_200 and rsi_val < 50:
                        signal_type = "BUY 🟢 (Трендовый откат EMA200)"
                    elif current_price < ema_200 and rsi_val > 50:
                        signal_type = "SELL 🔴 (Трендовый откат EMA200)"

                last_time = last_signals.get(f"{symbol}_{strategy}", 0)
                if signal_type and (time.time() - last_time > 300):
                    msg = (
                        f"🚀 <b>СИГНАЛ: {symbol}</b>\n"
                        f"<b>Тип:</b> {signal_type}\n"
                        f"<b>Рынок:</b> {mode.upper()}\n"
                        f"<b>Цена:</b> {current_price}\n"
                        f"<b>RSI:</b> {rsi_val}"
                    )
                    send_telegram(msg)
                    last_signals[f"{symbol}_{strategy}"] = time.time()
                
                time.sleep(0.5)
        time.sleep(10)

def start_telebot():
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Ошибка Telebot: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=analyze_market, daemon=True).start()
    
    send_telegram("🤖 Бот успешно запущен и ведет анализ рынка!")
    
    start_telebot()
