import time
import threading
import requests
import telebot
from telebot import types

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "8924895868:AAG5w69mIJrImVHp3a-YA-HzU-JyxieT0Wk"
CHAT_ID = "7960144135"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# 30 Торговых пар
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
last_signals = {}

def send_telegram(text):
    try:
        bot.send_message(CHAT_ID, text, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки Telegram: {e}", flush=True)

# --- ПОЛУЧЕНИЕ ДАННЫХ ---
def get_bybit_klines(symbol, current_mode):
    category = "linear" if current_mode == "futures" else "spot"
    url = f"https://api.bybit.com/v5/market/kline?category={category}&symbol={symbol}&interval=5&limit=60"
    
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data.get("retCode") == 0 and data["result"]["list"]:
                raw_list = data["result"]["list"]
                raw_list.reverse()
                return [float(item[4]) for item in raw_list]
    except Exception:
        pass
    
    try:
        res = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=60", timeout=5)
        if res.status_code == 200:
            return [float(item[4]) for item in res.json()]
    except Exception:
        pass
        
    return []

# --- РАСЧЕТ ИНДИКАТОРОВ ---
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

def calculate_macd(prices):
    ema_12 = calculate_ema(prices, 12)
    ema_26 = calculate_ema(prices, 26)
    return round(ema_12 - ema_26, 4)

def calculate_bollinger_bands(prices, period=20):
    if len(prices) < period:
        return prices[-1], prices[-1]
    sub = prices[-period:]
    sma = sum(sub) / period
    variance = sum((x - sma) ** 2 for x in sub) / period
    std_dev = variance ** 0.5
    return round(sma + (2 * std_dev), 4), round(sma - (2 * std_dev), 4)

# --- АВТОНОМНЫЙ АНАЛИЗАТОР (САМ ВЫБИРАЕТ СТРАТЕГИЮ) ---
def evaluate_auto_strategy(prices):
    if len(prices) < 30:
        return None, None
        
    current_price = prices[-1]
    rsi = calculate_rsi(prices)
    ema_9 = calculate_ema(prices, 9)
    ema_21 = calculate_ema(prices, 21)
    macd = calculate_macd(prices)
    upper_bb, lower_bb = calculate_bollinger_bands(prices)
    
    # 1. Мягкий анализ RSI (чуть шире середины)
    if rsi <= 47:
        return "LONG 🟢", f"RSI Зона покупки (RSI: {rsi})"
    elif rsi >= 53:
        return "SHORT 🔴", f"RSI Зона продажи (RSI: {rsi})"
        
    # 2. Анализ пересечения EMA (9/21)
    if ema_9 > ema_21 and prices[-2] <= calculate_ema(prices[:-1], 9):
        return "LONG 🟢", "Пересечение EMA 9/21 (Бычий импульс)"
    elif ema_9 < ema_21 and prices[-2] >= calculate_ema(prices[:-1], 9):
        return "SHORT 🔴", "Пересечение EMA 9/21 (Медвежий импульс)"
        
    # 3. Анализ по полосам Боллинджера (мягкий отскок от границ)
    if current_price <= lower_bb * 1.002:
        return "LONG 🟢", "Касание нижней полосы Боллинджера"
    elif current_price >= upper_bb * 0.998:
        return "SHORT 🔴", "Касание верхней полосы Боллинджера"
        
    # 4. Импульс по MACD
    if macd > 0 and rsi > 50:
        return "LONG 🟢", f"MACD Положительный импульс (MACD: {macd})"
    elif macd < 0 and rsi < 50:
        return "SHORT 🔴", f"MACD Отрицательный импульс (MACD: {macd})"
        
    return None, None

# --- МЕНЮ ТЕЛЕГРАМ ---
def get_main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    mode_text = "🟡 Режим: SPOT (Нажми для FUTURES)" if mode == "spot" else "🔴 Режим: FUTURES (Нажми для SPOT)"
    markup.add(
        types.InlineKeyboardButton("🤖 Автономный ИИ-Снайпер (30 стратегий)", callback_data="info"),
        types.InlineKeyboardButton(mode_text, callback_data="toggle_mode"),
        types.InlineKeyboardButton("▶ Включить / ⏸ Пауза", callback_data="toggle_pause"),
        types.InlineKeyboardButton("ℹ️ Статус работы", callback_data="check_status")
    )
    return markup

@bot.message_handler(commands=['start', 'menu'])
def start_cmd(message):
    bot.send_message(
        message.chat.id, 
        f"🤖 <b>Панель ИИ-Бот Авто-Сигналов</b>\n\nПар: <b>30</b> | Рынок: <b>{mode.upper()}</b>\nРежим: <b>Автоматический выбор стратегии (RSI, EMA, Bollinger, MACD)</b>", 
        parse_mode="HTML", 
        reply_markup=get_main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    global is_running, mode
    if call.data == "toggle_mode":
        mode = "spot" if mode == "futures" else "futures"
        bot.answer_callback_query(call.id, f"Рынок: {mode.upper()}")
    elif call.data == "toggle_pause":
        is_running = not is_running
        bot.answer_callback_query(call.id, f"Бот активен: {is_running}")
    elif call.data == "check_status":
        bot.answer_callback_query(call.id, f"Статус: {'Работает 🟢' if is_running else 'Пауза ⏸'} | Пар: 30", show_alert=True)
    elif call.data == "info":
        bot.answer_callback_query(call.id, "Бот сам сканирует рынок и выбирает лучший индикатор!", show_alert=True)

    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🤖 <b>Панель ИИ-Бот Авто-Сигналов</b>\n\nПар: <b>30</b> | Рынок: <b>{mode.upper()}</b>\nРежим: <b>Автоматический выбор стратегии</b>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )
    except Exception:
        pass

# --- ЦИКЛ СКАНИРОВАНИЯ ---
def analyze_market():
    global is_running, mode, last_signals
    
    while True:
        if is_running:
            for symbol in SYMBOLS:
                prices = get_bybit_klines(symbol, mode)
                if len(prices) < 30:
                    continue
                    
                current_price = prices[-1]
                signal_type, reason = evaluate_auto_strategy(prices)

                sig_key = f"{symbol}_{mode}"
                last_time = last_signals.get(sig_key, 0)
                
                # Кулдаун 60 секунд на одну пару
                if signal_type and (time.time() - last_time > 60):
                    rsi_val = calculate_rsi(prices)
                    msg = (
                        f"🚨 <b>АВТО-СИГНАЛ BYBIT [{mode.upper()}]</b>\n\n"
                        f"<b>Монета:</b> #{symbol}\n"
                        f"<b>Вердикт:</b> {signal_type}\n"
                        f"<b>Причина:</b> {reason}\n"
                        f"<b>Цена:</b> ${current_price}\n"
                        f"<b>RSI:</b> {rsi_val}"
                    )
                    send_telegram(msg)
                    last_signals[sig_key] = time.time()
                
                time.sleep(0.2)
        # Повторный полный анализ каждые 60 секунд
        time.sleep(60)

def start_telebot():
    while True:
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.polling(none_stop=True, interval=1, timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"Ошибка Telebot: {e}", flush=True)
            time.sleep(5)

if __name__ == "__main__":
    threading.Thread(target=analyze_market, daemon=True).start()
    send_telegram("🚀 <b>ИИ-Бот обновлен: запущен автономный мульти-индикаторный анализ (30 пар)!</b>")
    start_telebot()
