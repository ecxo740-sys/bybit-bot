import os
import time
import threading
import requests
import telebot
from telebot import types
from flask import Flask

# --- 1. ВЕБ-СЕРВЕР ---
app = Flask('')

@app.route('/')
def home():
    return "Bybit Bot Active 24/7"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. НАСТРОЙКИ ---
TELEGRAM_TOKEN = "8924895868:AAG5w69mIJr"
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

# --- 3. ПОЛУЧЕНИЕ СВЕЧЕЙ (Используем API Binance как альтернативный источник котировок, если Bybit банит IP) ---
def get_klines_data(symbol):
    # Запрос к публичному API Binance (не банит Render и совпадает по ценам на 99.9%)
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=15m&limit=100"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            # Формат свечи Binance: [time, open, high, low, close, ...]
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

# --- 5. TELEGRAM МЕНЮ ---
def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("🎯 Умный Трендовый Снайпер (EMA200)")
    btn2 = types.KeyboardButton("🔥 Экстремальный RSI")
    btn3 = types.KeyboardButton("📈 Пересечение EMA")
    
    pause_txt = "▶️️ Возобновить" if not is_running else "⏸ Приостановить"
    btn4 = types.KeyboardButton(pause_txt)
    
    mode_txt = "🟢 Переключить на Spot" if mode == "futures" else "🔴 Переключить на Futures"
    btn5 = types.KeyboardButton(mode_txt)
    btn6 = types.KeyboardButton("ℹ️ Текущий статус")
    
    markup.row(btn1)
    markup.row(btn2, btn3)
    markup.row(btn4, btn5)
    markup.row(btn6)
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(message.chat.id, "🤖 Бот подключен и готовит аналитику!", reply_markup=get_main_keyboard())

@bot.message_handler(func=lambda m: True)
def handle_menu(message):
    global is_running, mode, strategy
    txt = message.text

    if "Снайпер" in txt:
        strategy = "smart_trend"
        bot.send_message(message.chat.id, "🎯 Стратегия: Умный Трендовый Снайпер", reply_markup=get_main_keyboard())
    elif "Экстремальный RSI" in txt:
        strategy = "rsi"
        bot.send_message(message.chat.id, "🔥 Стратегия: Экстремальный RSI", reply_markup=get_main_keyboard())
    elif "Пересечение EMA" in txt:
        strategy = "ema_cross"
        bot.send_message(message.chat.id, "📈 Стратегия: Пересечение EMA 9/21", reply_markup=get_main_keyboard())
    elif "Приостановить" in txt or "Возобновить" in txt:
        is_running = not is_running
        status = "активен 🟢" if is_running else "на паузе ⏸"
        bot.send_message(message.chat.id, f"Состояние: {status}", reply_markup=get_main_keyboard())
    elif "Переключить на" in txt:
        mode = "spot" if mode == "futures" else "futures"
        bot.send_message(message.chat.id, f"Режим: {mode.upper()}", reply_markup=get_main_keyboard())
    elif "Текущий статус" in txt:
        st = "Активен 🟢" if is_running else "На паузе ⏸"
        msg = f"<b>Статус:</b> {st}\n<b>Рынок:</b> {mode.upper()}\n<b>Стратегия:</b> {strategy.upper()}"
        bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=get_main_keyboard())

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
    # Запуск фоновых потоков
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=analyze_market, daemon=True).start()
    
    # Отправка стартового сообщения
    send_telegram("🤖 Бот успешно запущен и ведет анализ рынка!")
    
    # Запуск Telegram бота в основном потоке
    start_telebot()
