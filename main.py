import os
import sys
import time
import threading
import requests
from flask import Flask
from pybit.unified_trading import HTTP

# --- 1. ВЕБ-СЕРВЕР ДЛЯ RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bybit Bot is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# --- 2. НАСТРОЙКИ БОТА ---
TELEGRAM_TOKEN = "8924895868:AAG5w69mIJr"
CHAT_ID = "7960144135"

session = HTTP(testnet=False)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "AVAXUSDT", "NEARUSDT", "LINKUSDT", "DOTUSDT"
]

is_running = True
mode = "futures"  # "spot" или "futures"
strategy = "rsi"  # "smart_trend", "rsi", "ema_cross"
last_signals = {}  # Защита от дублирования сигналов

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки Telegram: {e}", flush=True)

# --- 3. ВЫЧИСЛЕНИЕ ИНДИКАТОРОВ ---
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

# --- 4. АНАЛИЗ РЫНКА ---
def analyze_market():
    global is_running, mode, strategy, last_signals
    print("--- [ПОИСК СИГНАЛОВ ЗАПУЩЕН] ---", flush=True)
    
    category = "linear" if mode == "futures" else "spot"
    
    for symbol in SYMBOLS:
        if not is_running:
            break
            
        try:
            # Получаем 100 свечей 15-минутного таймфрейма
            response = session.get_kline(
                category=category,
                symbol=symbol,
                interval="15",
                limit=100
            )
            klines = response.get("result", {}).get("list", [])
            if not klines:
                continue
                
            # Свечи от старых к новым
            klines.reverse()
            close_prices = [float(k[4]) for k in klines]
            current_price = close_prices[-1]
            
            rsi_val = calculate_rsi(close_prices)
            ema_9 = calculate_ema(close_prices, 9)
            ema_21 = calculate_ema(close_prices, 21)
            ema_200 = calculate_ema(close_prices, 200)
            
            print(f"[{symbol}] Цена: {current_price} | RSI: {rsi_val} | EMA9: {ema_9} | EMA21: {ema_21}", flush=True)
            
            signal_type = None
            
            # Логика стратегий (Мягкие пороги)
            if strategy == "rsi":
                if rsi_val <= 45:
                    signal_type = "BUY 🟢 (Перепроданность RSI)"
                elif rsi_val >= 55:
                    signal_type = "SELL 🔴 (Перекупленность RSI)"
                    
            elif strategy == "ema_cross":
                if ema_9 > ema_21 and close_prices[-2] <= calculate_ema(close_prices[:-1], 21):
                    signal_type = "BUY 🟢 (Пересечение EMA 9/21 Вверх)"
                elif ema_9 < ema_21 and close_prices[-2] >= calculate_ema(close_prices[:-1], 21):
                    signal_type = "SELL 🔴 (Пересечение EMA 9/21 Вниз)"
                    
            elif strategy == "smart_trend":
                if current_price > ema_200 and rsi_val < 50:
                    signal_type = "BUY 🟢 (Трендовый откат EMA200)"
                elif current_price < ema_200 and rsi_val > 50:
                    signal_type = "SELL 🔴 (Трендовый откат EMA200)"

            # Отправка сигнала
            last_time = last_signals.get(f"{symbol}_{strategy}", 0)
            if signal_type and (time.time() - last_time > 300):  # Задержка между одинаковыми сигналами 5 минут
                msg = (
                    f"🚀 <b>СИГНАЛ: {symbol}</b>\n"
                    f"<b>Тип:</b> {signal_type}\n"
                    f"<b>Рынок:</b> {mode.upper()}\n"
                    f"<b>Цена:</b> {current_price}\n"
                    f"<b>RSI:</b> {rsi_val}\n"
                    f"<b>Стратегия:</b> {strategy.upper()}"
                )
                send_telegram(msg)
                last_signals[f"{symbol}_{strategy}"] = time.time()
                print(f">>> ОТПРАВЛЕН СИГНАЛ В TELEGRAM ПО {symbol}!", flush=True)

        except Exception as e:
            print(f"Ошибка анализа {symbol}: {e}", flush=True)
            
        time.sleep(0.5)

# --- 5. ГЛАВНЫЙ ЦИКЛ ---
def main_loop():
    send_telegram("🤖 Бот успешно обновлен и начинает сканирование!")
    print("=== ОСНОВНОЙ ЦИКЛ ЗАПУЩЕН ===", flush=True)
    while True:
        if is_running:
            analyze_market()
        else:
            print("Бот на паузе...", flush=True)
        time.sleep(15)  # Проверка каждые 15 секунд

if __name__ == "__main__":
    main_loop()
