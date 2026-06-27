import os
import sys
import threading
import asyncio
from flask import Flask
import time

# Добавляем папку bot в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

# Импортируем бота
from bot import bot, dp, main

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_bot():
    """Запускает бота в фоновом потоке с правильным циклом."""
    try:
        # Создаём новый цикл событий для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Запускаем бота
        loop.run_until_complete(main())
    except Exception as e:
        print(f"Ошибка в боте: {e}")

# Запускаем бота в фоновом потоке ПРИ СТАРТЕ (без before_first_request)
def start_bot_in_background():
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
    print("Бот запущен в фоновом потоке")

# Вызываем функцию запуска сразу при старте приложения
start_bot_in_background()
