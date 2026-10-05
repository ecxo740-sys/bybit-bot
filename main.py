import threading
import time
import requests
from pybit.unified_trading import HTTP

# --- НАСТРОЙКИ ---
TELEGRAM_TOKEN = "8924895868:AAG5w69mIJrImVHp3a-YA-HzU-JyxieT0Wk"
CHAT_ID = "7960144135"

# Инициализация API Bybit
session = HTTP(testnet=False)

# Глобальное состояние бота
is_running = True
last_update_id = 0
mode = "spot"  # "spot" или "futures"
strategy = "smart_trend"  # По умолчанию умная стратегия

# Словарь для отслеживания времени последнего сигнала (защита от спама)
# Формат: {"BTCUSDT": timestamp}
last_signals = {}
COOLDOWN_SECONDS = 7200  # 2 часа кулдаун на монету

# Список из 100 криптовалютных пар
BASE_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "DOGEUSDT",
    "DOTUSDT",
    "MATICUSDT",
    "LINKUSDT",
    "UNIUSDT",
    "ATOMUSDT",
    "LTCUSDT",
    "NEARUSDT",
    "APTUSDT",
    "OPUSDT",
    "ARBUSDT",
    "INJUSDT",
    "SUIUSDT",
    "RENDERUSDT",
    "FETUSDT",
    "TIAUSDT",
    "SEIUSDT",
    "PEPEUSDT",
    "SHIBUSDT",
    "ICPUSDT",
    "FILUSDT",
    "ETCUSDT",
    "BCHUSDT",
    "XLMUSDT",
    "HBARUSDT",
    "STXUSDT",
    "IMXUSDT",
    "GRTUSDT",
    "RNDRUSDT",
    "ALGOUSDT",
    "AAVEUSDT",
    "FTMUSDT",
    "SANDUSDT",
    "MANAUSDT",
    "AXSUSDT",
    "THETAUSDT",
    "EGLDUSDT",
    "EOSUSDT",
    "FLOWUSDT",
    "CHZUSDT",
    "CRVUSDT",
    "MKRUSDT",
    "SNXUSDT",
    "COMPUSDT",
    "ZILUSDT",
    "ENJUSDT",
    "BATUSDT",
    "KAVAUSDT",
    "LDOUSDT",
    "GMXUSDT",
    "DYDXUSDT",
    "GALAUSDT",
    "FLOKIUSDT",
    "BONKUSDT",
    "WIFUSDT",
    "BOMEUSDT",
    "ORDIUSDT",
    "SATSUSDT",
    "RATSUSDT",
    "JUPUSDT",
    "PYTHUSDT",
    "WUSDT",
    "TNSRUSDT",
    "ZETAUSDT",
    "OMUSDT",
    "POLUSDT",
    "ALTUSDT",
    "PORTALUSDT",
    "PIXELUSDT",
    "MANTAUSDT",
    "XAIUSDT",
    "NFPUSDT",
    "ACEUSDT",
    "MEMEUSDT",
    "BLURUSDT",
    "BIGTIMEUSDT",
    "FRIENDUSDT",
    "ZKUSDT",
    "IOUSDT",
    "ZROUSDT",
    "BLASTUSDT",
    "SAFEUSDT",
    "REIUSDT",
    "BBUSDT",
    "NOTUSDT",
    "DOGSUSDT",
    "CATIUSDT",
    "HMSTRUSDT",
    "EIGENUSDT",
    "NEIROUSDT",
    "TURBOUSDT",
    "1000PEPEUSDT",
]


def get_keyboard():
  """Интерактивное меню кнопок для Telegram"""
  mode_btn = (
      "🔴 Переключить на FUTURES"
      if mode == "spot"
      else "🟢 Переключить на SPOT"
  )
  status_btn = "⏸ Приостановить" if is_running else "▶️ Запустить"

  keyboard = {
      "inline_keyboard": [
          [
              {"text": status_btn, "callback_data": "toggle_run"},
              {"text": mode_btn, "callback_data": "toggle_mode"},
          ],
          [
              {
                  "text": "🎯 Умный Трендовый Снайпер (EMA200)",
                  "callback_data": "strat_smart",
              }
          ],
          [
              {
                  "text": "🔥 Экстремальный RSI (<30)",
                  "callback_data": "strat_rsi_ext",
              },
              {
                  "text": "📈 Пересечение EMA (9/21)",
                  "callback_data": "strat_ema_cross",
              },
          ],
          [{"text": "ℹ️ Текущий статус", "callback_data": "status"}],
      ]
  }
  return keyboard


def send_telegram_message(text, reply_markup=None):
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
  if reply_markup:
    payload["reply_markup"] = reply_markup
  try:
    requests.post(url, json=payload, timeout=5)
  except Exception as e:
    print(f"Ошибка отправки в Telegram: {e}")


def answer_callback(callback_query_id):
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
  try:
    requests.post(url, json={"callback_query_id": callback_query_id}, timeout=3)
  except Exception:
    pass


def get_klines(symbol, interval="15", limit=220):
  """Запрашиваем 220 свечей для корректного расчета EMA 200"""
  category = "spot" if mode == "spot" else "linear"
  try:
    response = session.get_kline(
        category=category, symbol=symbol, interval=interval, limit=limit
    )
    if response["retCode"] == 0:
      list_data = response["result"]["list"]
      list_data.reverse()
      closes = [float(candle[4]) for candle in list_data]
      volumes = [float(candle[5]) for candle in list_data]
      return closes, volumes
  except Exception:
    pass
  return None, None


def calculate_ema(data, period):
  if len(data) < period:
    return None
  multiplier = 2 / (period + 1)
  ema = sum(data[:period]) / period
  for price in data[period:]:
    ema = (price - ema) * multiplier + ema
  return ema


def calculate_rsi(data, period=14):
  if len(data) < period + 1:
    return None
  gains, losses = [], []
  for i in range(1, len(data)):
    change = data[i] - data[i - 1]
    gains.append(max(change, 0))
    losses.append(abs(min(change, 0)))

  avg_gain = sum(gains[:period]) / period
  avg_loss = sum(losses[:period]) / period
  if avg_loss == 0:
    return 100.0

  for i in range(period, len(gains)):
    avg_gain = (avg_gain * (period - 1) + gains[i]) / period
    avg_loss = (avg_loss * (period - 1) + losses[i]) / period

  if avg_loss == 0:
    return 100.0

  rs = avg_gain / avg_loss
  return 100 - (100 / (1 + rs))


def telegram_listener():
  """Фоновая обработка нажатий кнопок"""
  global is_running, mode, strategy, last_update_id

  while True:
    try:
      url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={last_update_id + 1}&timeout=5"
      response = requests.get(url, timeout=10).json()

      if response.get("ok"):
        for result in response.get("result", []):
          last_update_id = result["update_id"]

          if "callback_query" in result:
            cb = result["callback_query"]
            data = cb.get("data")
            answer_callback(cb.get("id"))

            if data == "toggle_run":
              is_running = not is_running
              msg = (
                  "🟢 **Бот запущен!**"
                  if is_running
                  else "🔴 **Бот поставлен на паузу.**"
              )
              send_telegram_message(msg, get_keyboard())

            elif data == "toggle_mode":
              mode = "futures" if mode == "spot" else "spot"
              send_telegram_message(
                  f"🔄 **Режим изменен на:** `{mode.upper()}`", get_keyboard()
              )

            elif data == "strat_smart":
              strategy = "smart_trend"
              send_telegram_message(
                  "🎯 Активирована: **Умный Трендовый Снайпер (EMA 200 + RSI +"
                  " Объем)**",
                  get_keyboard(),
              )

            elif data == "strat_rsi_ext":
              strategy = "rsi_extreme"
              send_telegram_message(
                  "✅ Стратегия изменена на: **Экстремальный RSI (<30 / >70)**",
                  get_keyboard(),
              )

            elif data == "strat_ema_cross":
              strategy = "ema_cross"
              send_telegram_message(
                  "✅ Стратегия изменена на: **Пересечение EMA (9 / 21)**",
                  get_keyboard(),
              )

            elif data == "status":
              strat_name = {
                  "smart_trend": "Умный Снайпер (EMA 200 + Vol)",
                  "rsi_extreme": "Экстремальный RSI",
                  "ema_cross": "Пересечение EMA (9/21)",
              }.get(strategy, strategy)

              info = (
                  f"⚙️ **Текущий статус:**\n"
                  f"• Состояние: {'🟢 Работает' if is_running else '🔴 На паузе'}\n"
                  f"• Режим торговли: `{mode.upper()}`\n"
                  f"• Стратегия: *{strat_name}*\n"
                  f"• Фильтр спама: `2 часа`\n"
                  f"• Активных пар: `{len(BASE_SYMBOLS)}`"
              )
              send_telegram_message(info, get_keyboard())

          elif "message" in result:
            text = result["message"].get("text", "").strip().lower()
            if text in ["/start", "/menu"]:
              send_telegram_message(
                  "🎛 **Панель управления ботом:**", get_keyboard()
              )
    except Exception:
      pass
    time.sleep(0.5)


def scan_market():
  """Анализ рынка с глубокой фильтрацией"""
  print(f"Сканирование [{mode.upper()}] | Стратегия: [{strategy}]...")

  for symbol in BASE_SYMBOLS:
    if not is_running:
      return

    # Проверка защиты от спама (Cooldown)
    now = time.time()
    if symbol in last_signals and (now - last_signals[symbol]) < COOLDOWN_SECONDS:
      continue

    closes, volumes = get_klines(symbol, interval="15", limit=220)
    if not closes or len(closes) < 205:
      continue

    current_price = closes[-1]
    current_volume = volumes[-1]
    avg_volume = sum(volumes[-11:-1]) / 10 if len(volumes) >= 11 else 0

    signal_type = None
    reason = ""

    # --- УМНАЯ СТРАТЕГИЯ С ФИЛЬТРАМИ (SMART TREND) ---
    if strategy == "smart_trend":
      ema_200 = calculate_ema(closes, 200)
      ema_20 = calculate_ema(closes, 20)
      rsi_14 = calculate_rsi(closes, 14)

      if ema_200 and ema_20 and rsi_14:
        # Условие BUY: Глобальный аптренд + Локальный откатный RSI + Повышенный объем
        if (
            current_price > ema_200
            and current_price <= ema_20 * 1.005
            and rsi_14 < 38
            and current_volume > avg_volume * 1.1
        ):
          signal_type = "BUY"
          reason = f"Глобальный бычий тренд (Выше EMA200), RSI={rsi_14:.1f}, Объем +10%"

        # Условие SELL (Только для Futures): Глобальный даунтренд + Всплеск RSI вверх
        elif (
            mode == "futures"
            and current_price < ema_200
            and current_price >= ema_20 * 0.995
            and rsi_14 > 62
            and current_volume > avg_volume * 1.1
        ):
          signal_type = "SELL"
          reason = f"Глобальный медвежий тренд (Ниже EMA200), RSI={rsi_14:.1f}, Объем +10%"

    elif strategy == "rsi_extreme":
      rsi_14 = calculate_rsi(closes, 14)
      if rsi_14:
        if rsi_14 < 28:
          signal_type = "BUY"
          reason = f"Сильная перепроданность (RSI={rsi_14:.1f})"
        elif rsi_14 > 72 and mode == "futures":
          signal_type = "SELL"
          reason = f"Сильная перекупленность (RSI={rsi_14:.1f})"

    elif strategy == "ema_cross":
      ema_fast = calculate_ema(closes, 9)
      ema_slow = calculate_ema(closes, 21)
      prev_fast = calculate_ema(closes[:-1], 9)
      prev_slow = calculate_ema(closes[:-1], 21)

      if ema_fast and ema_slow and prev_fast and prev_slow:
        if prev_fast <= prev_slow and ema_fast > ema_slow:
          signal_type = "BUY"
          reason = "Пересечение EMA 9/21 снизу вверх"
        elif (
            prev_fast >= prev_slow
            and ema_fast < ema_slow
            and mode == "futures"
        ):
          signal_type = "SELL"
          reason = "Пересечение EMA 9/21 сверху вниз"

    # --- ОТПРАВКА СИГНАЛА ---
    if signal_type:
      last_signals[symbol] = now  # Фиксируем время отправки
      formatted_pair = (
          symbol.replace("USDT", "/USDT") if mode == "spot" else symbol
      )
      tp = round(current_price * (1.02 if signal_type == "BUY" else 0.98), 4)

      if mode == "spot":
        msg = (
            f"🎯 **ТОЧНЫЙ СИГНАЛ (SPOT BUY)**!\n\n"
            f"📌 Пара: `{formatted_pair}`\n"
            f"💵 Текущая цена: `${current_price}`\n"
            f"📊 Анализ: _{reason}_\n\n"
            f"🎯 Take Profit (+2%): `${tp}`\n"
            f"💡 *Чистый спот без плеч!*"
        )
      else:
        sl = round(current_price * (0.99 if signal_type == "BUY" else 1.01), 4)
        msg = (
            f"⚡ **СИГНАЛ НА ФЬЮЧЕРСАХ ({signal_type})**!\n\n"
            f"📌 Пара: `{formatted_pair}`\n"
            f"💵 Текущая цена: `${current_price}`\n"
            f"📊 Анализ: _{reason}_\n\n"
            f"🎯 Take Profit: `${tp}`\n"
            f"🛑 Stop Loss: `${sl}`"
        )

      send_telegram_message(msg)
      time.sleep(1)

    time.sleep(0.05)


if __name__ == "__main__":
  # Фоновый поток для кнопок Telegram
  listener_thread = threading.Thread(target=telegram_listener, daemon=True)
  listener_thread.start()

  send_telegram_message(
      "🎯 **Бот-снайпер Bybit запущен!**\nАктивирована умная фильтрация по EMA"
      " 200 и объему.",
      get_keyboard(),
  )

  while True:
    try:
      if is_running:
        scan_market()
      else:
        time.sleep(2)
    except Exception as e:
      print(f"Ошибка главного цикла: {e}")
      time.sleep(3)
