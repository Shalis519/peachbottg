import os
import asyncio
import threading
import signal
from flask import Flask
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Импортируем бота после настройки
from bot import dp, bot  # замените на ваши импорты

# Флаг для отслеживания состояния бота
bot_started = False
bot_thread = None

async def start_bot():
    """Запуск бота"""
    try:
        logger.info("Запуск бота...")
        # Удаляем вебхук перед поллингом
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

def run_bot():
    """Запуск бота в отдельном потоке с собственным event loop"""
    global bot_started
    try:
        # Создаем новый event loop для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Запускаем бота
        loop.run_until_complete(start_bot())
        bot_started = True
    except Exception as e:
        logger.error(f"Ошибка в потоке бота: {e}")
        bot_started = False

@app.before_request
def before_request():
    """Запуск бота при первом запросе, если он еще не запущен"""
    global bot_thread, bot_started
    
    if not bot_started:
        if bot_thread is None or not bot_thread.is_alive():
            logger.info("Запуск бота в отдельном потоке...")
            bot_thread = threading.Thread(target=run_bot, daemon=True)
            bot_thread.start()
            logger.info("Бот запущен в фоновом потоке")

@app.route('/')
def home():
    return "Bot is running!", 200

@app.route('/health')
def health():
    return {"status": "ok", "bot_started": bot_started}, 200

# Для Render - проверка здоровья
@app.route('/healthz')
def healthz():
    return "OK", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
