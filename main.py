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

# 30 Торговых пар (Spot и Futures)
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "NEARUSDT", "LINKUSDT", "DOTUSDT",
    "SUIUSDT", "PEPEUSDT", "RENDERUSDT", "APTUSDT", "MATICUSDT",
    "ARBUSDT", "OPUSDT", "TIAUSDT", "INJUSDT", "FETUSDT",
    "ATOMUSDT", "LTCUSDT", "BCHUSDT", "ETCUSDT", "UNIUSDT",
    "ICPUSDT", "FILUSDT", "STXUSDT", "IMXUSDT", "KASUSDT"
]

is_running = True
mode = "futures"  # spot или futures
strategy = "rsi"  # rsi, ema_cross, smart_trend
last_signals = {}

def send_telegram(text):
    try:
        bot.send_message(CHAT_ID, text, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки Telegram: {e}", flush=True)

# --- 3. ПОЛУЧЕНИЕ ДАННЫХ BYBIT (СПОТ И ФЬЮЧЕРСЫ) ---
def get_bybit_klines(symbol, current_mode):
    category = "linear" if current_mode == "futures" else "spot"
    url = f"https://api.bybit.com/v5/market/kline?category={category}&symbol={symbol}&interval=5&limit=50"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("retCode") == 0 and data["result"]["list"]:
                raw_list = data["result"]["list"]
                raw_list.reverse()
                return [float(item[4]) for item in raw_list]
    except Exception as e:
        print(f"Ошибка Bybit API ({symbol}): {e}", flush=True)
    
    # Резервный источник (Binance)
    try:
        res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=50", timeout=5)
        if res.status_code == 200:
            return [float(item[4]) for item in res.json()]
    except Exception:
        pass
        
    return []

# --- 4. РАСЧЕТ ИНДИКАТОРОВ ---
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

# --- 5. МЕНЮ И КНОПКИ ---
def get_main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    s1 = "✅ " if strategy == "smart_trend" else ""
    s2 = "✅ " if strategy == "rsi" else ""
    s3 = "✅ " if strategy == "ema_cross" else ""
    
    btn1 = types.InlineKeyboardButton(f"{s1}🎯 Умный Трендовый Снайпер", callback_data="strat_smart_trend")
    btn2 = types.InlineKeyboardButton(f"{s2}🔥 Сигналы по RSI (Чувствительные)", callback_data="strat_rsi")
    btn3 = types.InlineKeyboardButton(f"{s3}📈 Пересечение EMA (9/21)", callback_data="strat_ema_cross")
    
    mode_text = "🟡 Режим: SPOT (Нажми для FUTURES)" if mode == "spot" else "🔴 Режим: FUTURES (Нажми для SPOT)"
    btn_mode = types.InlineKeyboardButton(mode_text, callback_data="toggle_mode")
    
    pause_text = "▶ Возобновить сканирование" if not is_running else "⏸ Поставить на паузу"
    btn_pause = types.InlineKeyboardButton(pause_text, callback_data="toggle_pause")
    
    btn_status = types.InlineKeyboardButton("ℹ️ Статус работы", callback_data="check_status")

    markup.add(btn1, btn2, btn3, btn_mode, btn_pause, btn_status)
    return markup

@bot.message_handler(commands=['start', 'menu'])
def start_cmd(message):
    bot.send_message(
        message.chat.id, 
        f"🤖 <b>Панель управления Bybit AI Signals</b>\n\nМониторинг пар: <b>30 штук</b>\nРынок: <b>{mode.upper()}</b>\nСтратегия: <b>{strategy.upper()}</b>", 
        parse_mode="HTML", 
        reply_markup=get_main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    global is_running, mode, strategy
    
    if call.data.startswith("strat_"):
        strategy = call.data.replace("strat_", "")
        bot.answer_callback_query(call.id, f"Стратегия: {strategy.upper()}")
    elif call.data == "toggle_mode":
        mode = "spot" if mode == "futures" else "futures"
        bot.answer_callback_query(call.id, f"Рынок изменен на {mode.upper()}")
    elif call.data == "toggle_pause":
        is_running = not is_running
        st = "запущен 🟢" if is_running else "на паузе ⏸"
        bot.answer_callback_query(call.id, f"Бот {st}")
    elif call.data == "check_status":
        st = "Активен 🟢" if is_running else "На паузе ⏸"
        bot.answer_callback_query(call.id, f"Статус: {st} | Пар: 30 | Рынок: {mode.upper()}", show_alert=True)

    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🤖 <b>Панель управления Bybit AI Signals</b>\n\nМониторинг пар: <b>30 штук</b>\nРынок: <b>{mode.upper()}</b>\nСтратегия: <b>{strategy.upper()}</b>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    except Exception:
        pass

# --- 6. МОНИТОРИНГ И АНАЛИЗ РЫНКА ---
def analyze_market():
    global is_running, mode, strategy, last_signals
    
    while True:
        if is_running:
            for symbol in SYMBOLS:
                prices = get_bybit_klines(symbol, mode)
                if len(prices) < 25:
                    continue
                    
                current_price = prices[-1]
                rsi_val = calculate_rsi(prices)
                ema_9 = calculate_ema(prices, 9)
                ema_21 = calculate_ema(prices, 21)
                
                signal_type = None
                
                if strategy == "rsi":
                    # Смягченные пороги для частых сигналов
                    if rsi_val <= 48:
                        signal_type = "LONG 🟢 (RSI Зона покупки)"
                    elif rsi_val >= 52:
                        signal_type = "SHORT 🔴 (RSI Зона продажи)"
                        
                elif strategy == "ema_cross":
                    if ema_9 > ema_21:
                        signal_type = "LONG 🟢 (EMA 9 выше EMA 21)"
                    elif ema_9 < ema_21:
                        signal_type = "SHORT 🔴 (EMA 9 ниже EMA 21)"
                        
                elif strategy == "smart_trend":
                    ema_50 = calculate_ema(prices, 50)
                    if current_price > ema_50 and rsi_val > 48:
                        signal_type = "LONG 🟢 (Бычий тренд выше EMA50)"
                    elif current_price < ema_50 and rsi_val < 52:
                        signal_type = "SHORT 🔴 (Медвежий тренд ниже EMA50)"

                sig_key = f"{symbol}_{mode}_{strategy}"
                last_time = last_signals.get(sig_key, 0)
                
                # Уменьшили кулдаун до 60 секунд
                if signal_type and (time.time() - last_time > 60):
                    msg = (
                        f"🚨 <b>СИГНАЛ BYBIT [{mode.upper()}]</b>\n\n"
                        f"<b>Монета:</b> #{symbol}\n"
                        f"<b>Направление:</b> {signal_type}\n"
                        f"<b>Цена:</b> ${current_price}\n"
                        f"<b>RSI:</b> {rsi_val}\n"
                        f"<b>Стратегия:</b> {strategy.upper()}"
                    )
                    send_telegram(msg)
                    last_signals[sig_key] = time.time()
                
                time.sleep(0.2)
        time.sleep(5)

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
    
    send_telegram("🚀 <b>Бот обновлен: повышенная чувствительность сигналов включена!</b>")
    start_telebot()
