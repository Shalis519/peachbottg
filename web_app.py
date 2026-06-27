import os
import sys
import asyncio
import threading
from flask import Flask

# Добавляем папку bot в путь
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'bot'))

from bot import bot, dp, main

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running!", 200

def run_bot():
    """Запускает бота с правильной обработкой сигналов."""
    # Создаём новый цикл событий для этого потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Отключаем обработку сигналов (они не нужны в фоновом потоке)
    try:
        loop.run_until_complete(main())
    except Exception as e:
        print(f"Ошибка в боте: {e}")
    finally:
        loop.close()

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке с правильной настройкой
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask в главном потоке
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
