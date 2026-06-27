import os
import sys
import asyncio
from flask import Flask

# Добавляем папку bot в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

# Импортируем бота
from bot import bot, dp, main

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

# Запускаем бота при старте приложения
@app.before_first_request
def start_bot():
    """Запускает бота в отдельном потоке с правильным циклом."""
    import threading
    def run_bot():
        # Создаём новый цикл событий для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Запускаем бота
        loop.run_until_complete(main())
    
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
